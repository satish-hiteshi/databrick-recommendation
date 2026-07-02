"""Postgres precompute access — the two endpoint_4_search tables, loaded once into dicts at startup.

property_popularity (53,614 rows) and entity_centrality (44,052 rows), both keyed by property_id.
Read-only. We load into memory so per-query ranking never hits Postgres (UC4 latency).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Optional

import os

try:
    import psycopg2
except Exception:          # not needed on the live (Silver) serving path
    psycopg2 = None

from . import config

# ── Databricks live source (env-gated; INERT for local Postgres runs) ────────────────────────────
# When SEARCH_DATA_SOURCE=live, load_store() reads the two precompute tables from Silver via an injected
# query_fn (databricks-sql-connector in serving) instead of Postgres — SAME columns/shape. Those Silver
# tables are built by databricks_deploy/precompute_search_tables.py (part of this E4 bundle).
_LIVE = os.getenv("SEARCH_DATA_SOURCE", "").lower() == "live"
_SILVER_CAT = os.getenv("SEARCH_SILVER_CATALOG", "stg_feeds_silver")
_SILVER_SCHEMA = os.getenv("SEARCH_SILVER_SCHEMA", "ml")
_POP_TABLE = os.getenv("SEARCH_POP_TABLE", f"{_SILVER_CAT}.{_SILVER_SCHEMA}.search_property_popularity")
_CENT_TABLE = os.getenv("SEARCH_CENT_TABLE", f"{_SILVER_CAT}.{_SILVER_SCHEMA}.search_entity_centrality")
_QUERY_FN = None


def set_query_fn(fn):
    """Inject the Silver query function (serving). MUST be called before load_store() when live."""
    global _QUERY_FN
    _QUERY_FN = fn


@dataclass(slots=True)
class PopRow:
    name: Optional[str]
    vertical: Optional[str]
    popularity_pct: float
    recency_date: Optional[date]
    dedup_key: Optional[str]


@dataclass(slots=True)
class Store:
    popularity: Dict[int, PopRow] = field(default_factory=dict)   # property_id -> PopRow (53,614)
    centrality: Dict[int, float] = field(default_factory=dict)    # property_id -> centrality_pct (44,052)

    def popularity_pct(self, pid: int) -> float:
        r = self.popularity.get(pid)
        return r.popularity_pct if r else 0.0

    def centrality_pct(self, pid: int) -> float:
        return self.centrality.get(pid, 0.0)

    def dedup_key(self, pid: int) -> Optional[str]:
        r = self.popularity.get(pid)
        return r.dedup_key if r else None

    def recency_date(self, pid: int) -> Optional[date]:
        r = self.popularity.get(pid)
        return r.recency_date if r else None


def _load_store_live() -> Store:
    """Serving: load the two precompute tables from Silver via the injected query_fn (same shape)."""
    st = Store()
    for r in _QUERY_FN(f"SELECT property_id, name, vertical, popularity_pct, recency_date, dedup_key "
                       f"FROM {_POP_TABLE}"):
        pid = r.get("property_id")
        if pid is None:
            continue
        pp = r.get("popularity_pct")
        st.popularity[int(pid)] = PopRow(name=r.get("name"), vertical=r.get("vertical"),
                                         popularity_pct=float(pp) if pp is not None else 0.0,
                                         recency_date=r.get("recency_date"), dedup_key=r.get("dedup_key"))
    try:                                                # centrality = a graph (GDS PageRank) precompute, fast-follow
        for r in _QUERY_FN(f"SELECT property_id, centrality_pct FROM {_CENT_TABLE}"):
            pid = r.get("property_id")
            cp = r.get("centrality_pct")
            if pid is not None:
                st.centrality[int(pid)] = float(cp) if cp is not None else 0.0
    except Exception as e:                              # table absent -> neutral centrality (ranking weight absorbs it)
        print(f"[store] centrality table {_CENT_TABLE} unavailable ({str(e)[:80]}); using neutral centrality", flush=True)
    return st


def load_store() -> Store:
    if _LIVE and _QUERY_FN is not None:                 # Silver (serving) — no Postgres
        return _load_store_live()
    con = psycopg2.connect(dbname=config.PG_DB, host=config.PG_HOST, port=config.PG_PORT,
                           user=config.PG_USER, password=config.PG_PASSWORD)
    st = Store()
    try:
        with con.cursor() as c:
            c.execute("SELECT property_id, name, vertical, popularity_pct, recency_date, dedup_key "
                      "FROM property_popularity")
            for pid, name, vert, pp, rd, dk in c.fetchall():
                st.popularity[int(pid)] = PopRow(name=name, vertical=vert,
                                                 popularity_pct=float(pp) if pp is not None else 0.0,
                                                 recency_date=rd, dedup_key=dk)
            c.execute("SELECT property_id, centrality_pct FROM entity_centrality")
            for pid, cp in c.fetchall():
                st.centrality[int(pid)] = float(cp) if cp is not None else 0.0
    finally:
        con.close()
    return st
