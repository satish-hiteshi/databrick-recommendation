"""Postgres precompute access — the two endpoint_4_search ranking tables, loaded once into dicts at startup.

property_popularity + entity_centrality. Read-only, loaded into memory so per-query ranking never hits
Postgres (UC4 latency). This module is CODE-ONLY — it does NOT rebuild the tables.

POST composite-key migration — THE JOIN KEY IS NOW ``entity_id`` (collision-safe):
  The old tables were **PUBLIC-property_id-keyed** (class A); that id is GONE from the graph. They must be
  regenerated carrying the composite. This loader keys the PRIMARY dicts on **entity_id** — the stable,
  globally-unique identity — so the ~321 cross-vertical ``media_source_guid`` collisions (e.g. Game:119163
  vs Movie:119163, which share source_id 119163) get **DISTINCT rows** and cannot collapse. entity_id is
  derived per row from an ``entity_id`` column if present, else built from
  ``make_entity_id(vertical | profile_key→vertical, media_source_guid)``.

  A secondary **source_id VIEW** (``*_by_sid``, collision-LOSSY / last-write-wins) is kept ONLY for the
  engine's internal source_id heuristics (twin-demote / prefix-pool caps), which operate on the
  already-source_id-keyed name index. The UC4 **ranking** (ranking.py) and **dedup** (dedup.py) key on
  entity_id → collision-safe. The lookup methods accept EITHER an entity_id (str → primary) or a source_id
  (int → view).

  If a table carries NO composite column (only the dead PUBLIC ``property_id``), it can't be re-keyed here:
  rows fall back to the legacy int in the source_id view, ``*_key`` is flagged ``legacy_property_id``, and
  every engine lookup returns the NEUTRAL default (0.0 / None) until the table is regenerated. Ranking math
  is UNCHANGED — only the key changed.

⇒ REGENERATE ``property_popularity`` and ``entity_centrality`` with an ``entity_id`` column (or
  ``media_source_guid`` + ``profile_key``/``vertical``), sourced from the re-key CSV's
  ``property_id``↔``media_source_guid``↔``vertical`` columns + the re-keyed graph — NOT from Postgres.
"""

from __future__ import annotations

import logging
import sys
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import Dict, Optional, Union


from . import config

try:
    from shared import identity as _ident                # repo-root layout (local dev tree)
except ImportError:
    try:
        from . import _identity as _ident                # vendored copy (serving bundle)
    except ImportError:
        import _identity as _ident

_log = logging.getLogger("search_api.store")


@dataclass(slots=True)
class PopRow:
    name: Optional[str]
    vertical: Optional[str]
    popularity_pct: float
    recency_date: Optional[date]
    dedup_key: Optional[str]


@dataclass(slots=True)
class Store:
    # PRIMARY — keyed on entity_id (collision-safe: the ~321 cross-vertical guid twins get DISTINCT rows).
    popularity: Dict[str, PopRow] = field(default_factory=dict)
    centrality: Dict[str, float] = field(default_factory=dict)
    # source_id VIEW — keyed on the numeric source_id (collision-LOSSY, last-write-wins). ONLY for the engine's
    # internal source_id heuristics; NOT used by ranking.py/dedup.py (those key on entity_id).
    popularity_by_sid: Dict[int, PopRow] = field(default_factory=dict)
    centrality_by_sid: Dict[int, float] = field(default_factory=dict)
    popularity_key: str = "entity_id"     # per-table: "entity_id" (re-keyed) | "legacy_property_id" (stale → neutral)
    centrality_key: str = "entity_id"

    @property
    def key_kind(self) -> str:            # overall: entity_id iff BOTH tables carry the composite
        return "entity_id" if (self.popularity_key == "entity_id" and self.centrality_key == "entity_id") \
            else "legacy_property_id"

    # ── lookups: str key → entity_id (collision-safe) · int key → source_id view (collision-lossy) ──
    def _pop_row(self, key: Union[str, int, None]) -> Optional[PopRow]:
        if key is None:
            return None
        return self.popularity.get(key) if isinstance(key, str) else self.popularity_by_sid.get(key)

    def popularity_pct(self, key: Union[str, int, None]) -> float:
        r = self._pop_row(key)
        return r.popularity_pct if r else 0.0

    def centrality_pct(self, key: Union[str, int, None]) -> float:
        if key is None:
            return 0.0
        return self.centrality.get(key, 0.0) if isinstance(key, str) else self.centrality_by_sid.get(key, 0.0)

    def dedup_key(self, key: Union[str, int, None]) -> Optional[str]:
        r = self._pop_row(key)
        return r.dedup_key if r else None

    def recency_date(self, key: Union[str, int, None]) -> Optional[date]:
        r = self._pop_row(key)
        return r.recency_date if r else None


def _colnames(cur, table: str) -> set:
    cur.execute("SELECT column_name FROM information_schema.columns WHERE table_name = %s", (table,))
    return {r[0] for r in cur.fetchall()}


def _row_entity_id(d: dict) -> Optional[str]:
    """Derive the collision-safe entity_id from a row's composite columns: an ``entity_id`` column if present,
    else ``make_entity_id(vertical | profile_key→vertical, media_source_guid)``. None ⇒ no composite."""
    if d.get("entity_id"):
        try:
            return _ident.parse_entity_id(str(d["entity_id"])).entity_id
        except ValueError:
            pass
    guid = d.get("media_source_guid")
    if guid is None:
        return None
    vert = d.get("vertical") or (_ident.vertical_for_profile_key(d["profile_key"]) if d.get("profile_key") else None)
    if not vert:
        return None
    try:
        return _ident.make_entity_id(vert, guid)
    except ValueError:
        return None


def _row_source_id(d: dict) -> Optional[int]:
    """Numeric source_id (=media_source_guid) for the collision-lossy engine view. None if non-numeric/absent."""
    guid = d.get("media_source_guid")
    if guid is None and d.get("entity_id"):
        try:
            guid = _ident.parse_entity_id(str(d["entity_id"])).media_source_guid
        except ValueError:
            return None
    try:
        return int(str(guid).strip())
    except (TypeError, ValueError):
        return None


# ── Databricks live source (env-gated; INERT for local Postgres runs) ────────────────────────────
# SEARCH_DATA_SOURCE=live: load_store() reads the two Silver precompute tables via an injected query_fn
# (databricks-sql-connector in serving) instead of Postgres — filled into the SAME entity_id-keyed Store
# (post composite-key migration). property_id in these tables IS the media_source_guid, so entity_id is
# derived per row via make_entity_id(vertical, guid) — collision-safe, matching the local loader.
import os as _os
_LIVE = _os.getenv("SEARCH_DATA_SOURCE", "").lower() == "live"
_SILVER_CAT = _os.getenv("SEARCH_SILVER_CATALOG", "stg_feeds_silver")
_SILVER_SCHEMA = _os.getenv("SEARCH_SILVER_SCHEMA", "ml")
_POP_TABLE = _os.getenv("SEARCH_POP_TABLE", f"{_SILVER_CAT}.{_SILVER_SCHEMA}.search_property_popularity")
_CENT_TABLE = _os.getenv("SEARCH_CENT_TABLE", f"{_SILVER_CAT}.{_SILVER_SCHEMA}.search_entity_centrality")
_QUERY_FN = None


def set_query_fn(fn):
    """Inject the Silver query function (serving). MUST be called before load_store() when live."""
    global _QUERY_FN
    _QUERY_FN = fn


def _load_store_live() -> Store:
    """Serving: fill the entity_id-keyed Store from the Silver precompute tables (same row logic as the
    local loader — _row_entity_id/_row_source_id — so twins stay collision-safe)."""
    st = Store()
    pop_has_composite = False
    for r in _QUERY_FN(f"SELECT * FROM {_POP_TABLE}"):
        d = dict(r)
        d.setdefault("media_source_guid", d.get("property_id"))   # property_id IS the guid in these tables
        pr = PopRow(name=d.get("name"), vertical=d.get("vertical"),
                    popularity_pct=float(d["popularity_pct"]) if d.get("popularity_pct") is not None else 0.0,
                    recency_date=d.get("recency_date"), dedup_key=d.get("dedup_key"))
        eid = _row_entity_id(d)
        if eid is not None:
            st.popularity[eid] = pr
            pop_has_composite = True
        sid = _row_source_id(d)
        if sid is None and d.get("property_id") is not None:
            sid = int(d["property_id"])
        if sid is not None:
            st.popularity_by_sid[sid] = pr
    cen_has_composite = False
    try:
        for r in _QUERY_FN(f"SELECT * FROM {_CENT_TABLE}"):
            d = dict(r)
            d.setdefault("media_source_guid", d.get("property_id"))
            cp = float(d["centrality_pct"]) if d.get("centrality_pct") is not None else 0.0
            eid = _row_entity_id(d)
            if eid is not None:
                st.centrality[eid] = cp
                cen_has_composite = True
            sid = _row_source_id(d)
            if sid is None and d.get("property_id") is not None:
                sid = int(d["property_id"])
            if sid is not None:
                st.centrality_by_sid[sid] = cp
    except Exception as e:                       # table absent -> neutral centrality (ranking weight absorbs it)
        print(f"[store] centrality table {_CENT_TABLE} unavailable ({str(e)[:80]}); neutral centrality", flush=True)
    st.popularity_key = "entity_id" if pop_has_composite else "legacy_property_id"
    st.centrality_key = "entity_id" if cen_has_composite else "legacy_property_id"
    print(f"[store] LIVE Silver: popularity={len(st.popularity)} eid-rows / {len(st.popularity_by_sid)} sid-rows "
          f"(key={st.popularity_key}); centrality={len(st.centrality)} eid-rows (key={st.centrality_key})", flush=True)
    return st


def load_store() -> Store:
    if _LIVE and _QUERY_FN is not None:
        return _load_store_live()
    import psycopg2                      # lazy: local Postgres path only — never imported in serving
    con = psycopg2.connect(dbname=config.PG_DB, host=config.PG_HOST, port=config.PG_PORT,
                           user=config.PG_USER, password=config.PG_PASSWORD)
    st = Store()
    try:
        with con.cursor() as c:
            # ── property_popularity ──
            pop_cols = _colnames(c, "property_popularity")
            has_composite_pop = ("entity_id" in pop_cols) or ("media_source_guid" in pop_cols)
            sel = ["property_id", "name", "vertical", "popularity_pct", "recency_date", "dedup_key"]
            for extra in ("entity_id", "media_source_guid", "profile_key"):
                if extra in pop_cols and extra not in sel:
                    sel.append(extra)
            c.execute(f"SELECT {', '.join(sel)} FROM property_popularity")
            for row in c.fetchall():
                d = dict(zip(sel, row))
                pr = PopRow(
                    name=d.get("name"), vertical=d.get("vertical"),
                    popularity_pct=float(d["popularity_pct"]) if d["popularity_pct"] is not None else 0.0,
                    recency_date=d.get("recency_date"), dedup_key=d.get("dedup_key"))
                eid = _row_entity_id(d) if has_composite_pop else None
                if eid is not None:
                    st.popularity[eid] = pr                         # PRIMARY (collision-safe)
                sid = _row_source_id(d) if has_composite_pop else None
                if sid is None:                                     # no composite → legacy PUBLIC id (view only, neutral)
                    sid = int(d["property_id"])
                st.popularity_by_sid[sid] = pr                      # source_id VIEW (collision-lossy)

            # ── entity_centrality ──
            cen_cols = _colnames(c, "entity_centrality")
            has_composite_cen = ("entity_id" in cen_cols) or ("media_source_guid" in cen_cols)
            sel_c = ["property_id", "centrality_pct"]
            for extra in ("entity_id", "media_source_guid", "profile_key", "vertical"):
                if extra in cen_cols and extra not in sel_c:
                    sel_c.append(extra)
            c.execute(f"SELECT {', '.join(sel_c)} FROM entity_centrality")
            for row in c.fetchall():
                d = dict(zip(sel_c, row))
                val = float(d["centrality_pct"]) if d["centrality_pct"] is not None else 0.0
                eid = _row_entity_id(d) if has_composite_cen else None
                if eid is not None:
                    st.centrality[eid] = val                        # PRIMARY (collision-safe)
                sid = _row_source_id(d) if has_composite_cen else None
                if sid is None:
                    sid = int(d["property_id"])
                st.centrality_by_sid[sid] = val                     # source_id VIEW (collision-lossy)

        # a table is entity_id-keyed (collision-safe, joins to the engine) iff it carries the composite; else it
        # is still keyed on the dead PUBLIC property_id → its signal is neutral until regenerated.
        st.popularity_key = "entity_id" if has_composite_pop else "legacy_property_id"
        st.centrality_key = "entity_id" if has_composite_cen else "legacy_property_id"
        for tbl, kk in (("property_popularity", st.popularity_key), ("entity_centrality", st.centrality_key)):
            if kk == "legacy_property_id":
                _log.warning("%s is still PUBLIC-property_id-keyed (no entity_id/media_source_guid column) — its "
                             "signal will be NEUTRAL (0.0) until regenerated with entity_id / "
                             "(profile_key, media_source_guid).", tbl)
    finally:
        con.close()
    return st
