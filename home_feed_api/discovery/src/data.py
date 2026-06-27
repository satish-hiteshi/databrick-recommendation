"""data.py — load layer for the Feeds.ai Discovery demo.

Loads the read-only assets once at startup and exposes them through a single `Data` singleton:
  - public_properties.csv  -> 57,443 catalogue rows (property_id -> name / vertical / entity_id)
  - public_moments.csv     -> ~100,000 published moments (the candidate feed pool)
  - embeddings_qwen_57k.npy + embeddings_qwen_ids.json -> the 57,443x1024 L2-normalized relevance matrix
  - Neo4j (HTTP)           -> per-entity `influence` (popularity) over the SIMILAR_TO graph

Everything keys off `property_id` (int). Our entity_id is `Vertical:property_id` (e.g. Movie:88177).
Vertical casing is normalized everywhere via VERTICAL_BY_MTYPE / canon_vertical().

CSV reads MUST run with PYTHONUTF8=1 (Windows cp1252 default crashes on this data). We also force
utf-8 on open() here as a belt-and-braces guard.
"""
import csv
import json
import os
import sys
import threading
from datetime import datetime, timezone

import numpy as np
import requests
from requests.auth import HTTPBasicAuth

# ──────────────────────────────────────────────────────────────────────────────
# Paths (this file lives in discovery/src/; project root is two levels up)
# ──────────────────────────────────────────────────────────────────────────────
SRC_DIR = os.path.dirname(os.path.abspath(__file__))
DISCOVERY_DIR = os.path.dirname(SRC_DIR)
ROOT = os.path.dirname(DISCOVERY_DIR)

RAW_DIR = os.path.join(DISCOVERY_DIR, "data", "raw")
PROPERTIES_CSV = os.path.join(RAW_DIR, "public_properties.csv")
MOMENTS_CSV = os.path.join(RAW_DIR, "public_moments.csv")
# P2-1 enrichment (Databricks Silver exports) — optional; loaded into separate dicts.
ENRICH_MTYPES_CSV = os.path.join(RAW_DIR, "enrich_moment_types.csv")
ENRICH_MPLATS_CSV = os.path.join(RAW_DIR, "enrich_media_platforms.csv")
ENRICH_MOMENTS_CSV = os.path.join(RAW_DIR, "enrich_moments.csv")
ENRICH_PROPS_CSV = os.path.join(RAW_DIR, "enrich_properties.csv")
# P2-2: moment_type names that must never appear in a public feed (patch/maintenance). Resolved to a
# set of moment_ids ONCE at load time so the ranking candidate filter is an O(1) membership check.
SUPPRESS_MOMENT_TYPES = {"Changes (Non Content)", "Service Health Event"}

VEC_DIR = os.path.join(ROOT, "vector", "data_v2")
EMB_NPY = os.path.join(VEC_DIR, "embeddings_qwen_57k.npy")
EMB_IDS = os.path.join(VEC_DIR, "embeddings_qwen_ids.json")
# Optional parquet source (reuses E1's embeddings_qwen parquet, already on the Volume). It is keyed by
# entity_id "Vertical:media_source_guid" (NOT property_id), so the loader maps each row to property_id
# via the guid→pid bridge built in _load_properties. Set HOME_EMBEDDINGS_PARQUET to use it instead of npy.
EMB_PARQUET = os.getenv("HOME_EMBEDDINGS_PARQUET", os.path.join(VEC_DIR, "embeddings_qwen.parquet"))

# obs.py latency tracing — purely additive; no-op decorators if it's not importable.
sys.path.insert(0, os.path.join(ROOT, "databricks_deploy", "serving"))
try:
    import obs  # noqa: E402
    timed = obs.timed
except Exception:  # pragma: no cover - defensive
    def timed(*a, **k):
        def _d(f):
            return f
        return _d

# ──────────────────────────────────────────────────────────────────────────────
# Neo4j HTTP (same endpoint/auth pattern as vector/pipeline/compare_hybrid.py)
# ──────────────────────────────────────────────────────────────────────────────
NEO = os.getenv("NEO4J_HTTP", "http://localhost:7475/db/neo4j/tx/commit")
NEO_AUTH = HTTPBasicAuth(os.getenv("NEO4J_USER", "neo4j"),
                         os.getenv("NEO4J_PASSWORD", "feedsaiGraphPoC2026"))

# media_type_id -> our canonical (lowercase) vertical and the entity_id prefix casing.
VERTICAL_BY_MTYPE = {1: "game", 3: "movie", 4: "tv", 5: "podcast"}
# entity_id prefixes as they appear in embeddings_qwen_ids.json (mixed case).
PREFIX_BY_VERTICAL = {"game": "Game", "movie": "Movie", "tv": "TV", "podcast": "Podcast"}

# ── Databricks live source (env-gated; INERT for local CSV runs) ───────────────────────────────────
# When HOME_DATA_SOURCE=live the loaders read the Silver lakehouse via an injected query_fn
# (databricks-sql-connector in serving) instead of the local CSVs — SAME record shapes, engine
# byte-unchanged. Mirrors the Silver table map used by Endpoint 2's LiveDataSource. Genres/themes,
# enrichment and entity_scores stay graceful-empty on live for now (additive — cards degrade honestly).
_LIVE = os.getenv("HOME_DATA_SOURCE", "").lower() == "live"
_SILVER_CAT = os.getenv("HOME_SILVER_CATALOG", "stg_feeds_silver")
_SILVER_PG = f"{_SILVER_CAT}.feedspostgres"
_SILVER_ML = f"{_SILVER_CAT}.ml"
_QUERY_FN = None   # set by the serving pyfunc: query_fn(sql) -> list[dict]


def set_query_fn(fn):
    """Inject the Silver query function (serving). MUST be called before Data.load() when live."""
    global _QUERY_FN
    _QUERY_FN = fn


def _guid_of(entity_id):
    """'Movie:11002760' -> 11002760 (int media_source_guid), or None. Used to map the parquet's
    guid-keyed rows to discovery property_id via the bridge built in _load_properties."""
    if entity_id is None:
        return None
    s = str(entity_id)
    if ":" in s:
        s = s.split(":", 1)[1]
    try:
        return int(s.strip())
    except (TypeError, ValueError):
        return None


def canon_vertical(v):
    """Normalize any vertical spelling to lowercase canonical (game/movie/tv/podcast)."""
    if v is None:
        return None
    return str(v).strip().lower()


def _clean(s):
    """Normalize the CSV's literal 'null'/'None'/'' to a real None."""
    if s is None:
        return None
    if not isinstance(s, str):          # live SQL returns native types (int/float/datetime) — pass through
        return s
    s = s.strip()
    if s == "" or s.lower() in ("null", "none"):
        return None
    return s


def _to_int(s, default=None):
    s = _clean(s)
    if s is None:
        return default
    try:
        return int(float(s))
    except (TypeError, ValueError):
        return default


def _epoch(s):
    """ISO-8601 timestamp (with optional trailing 'Z') -> Unix epoch seconds (UTC), or None.

    Parsed ONCE here at load time so the per-request ranking hot path never re-parses timestamps
    (datetime parsing over ~100k moments per request was the dominant feed-latency cost).
    """
    s = _clean(s)
    if s is None:
        return None
    t = s.strip()
    if t.endswith("Z"):
        t = t[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        try:
            dt = datetime.fromisoformat(t[:10])
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


@timed("neo4j", "neo_cypher")
def neo_cypher(stmt, params=None, timeout=120):
    """POST one Cypher statement to the Neo4j HTTP transactional endpoint, return its data rows.

    Mirrors compare_hybrid.neo_cypher. The first call after a cold DB can be slow (~tens of s),
    hence the generous default timeout.
    """
    body = {"statements": [{"statement": stmt, "parameters": params or {}}]}
    r = requests.post(NEO, json=body, auth=NEO_AUTH, timeout=timeout)
    j = r.json()
    if j.get("errors"):
        raise RuntimeError(f"neo4j: {j['errors']}")
    return j["results"][0]["data"]


class Data:
    """Single in-process owner of all read-only assets. Build once via Data.load()."""

    _instance = None
    _lock = threading.Lock()

    def __init__(self):
        # property catalogue
        self.properties = {}          # property_id(int) -> {property_id, name, vertical, entity_id, media_type_id}
        self.entity_id_by_pid = {}    # property_id -> "Vertical:pid"
        self.pid_by_guid = {}         # media_source_guid(int) -> property_id  (bridge for the parquet embeddings)
        # moments
        self.moments = []             # list of moment dicts (the candidate pool)
        self.moments_by_pid = {}      # property_id -> [moment dicts]
        # embeddings
        self.emb = None               # (57443, 1024) float32, L2-normalized
        self.emb_row_by_pid = {}      # property_id -> row index into self.emb
        self.emb_dim = 0
        # graph popularity
        self.influence_by_pid = {}    # property_id -> float influence (raw Neo4j PageRank)
        self.influence_max = 1.0
        self.graph_ok = False
        # engagement-derived scores (Phase 4 trend engine; property_id -> {trending,popularity,freshness})
        self.entity_scores = {}       # filled from Postgres entity_scores; empty -> ranker uses fallbacks
        self.entity_scores_ok = False
        # genre/theme metadata (from the Neo4j graph; property_id -> [names]) for cards + reasoning
        self.genres_by_pid = {}
        self.themes_by_pid = {}
        # P2-1 enrichment (Databricks Silver exports; SEPARATE dicts — existing moment/property dicts
        # are NOT mutated, so existing ranking/response is untouched). Read via moment_extra()/prop_extra().
        self.moment_types = {}        # moment_type_id -> name (richness/is_live source)
        self.media_platforms = {}     # media_platform_id -> name
        self.moment_enrich = {}       # moment_id -> {moment_type_id, moment_type_name, media_platform_id,
                                      #   media_platform_name, hero_image_url, thumbnail_url, cta_button_text}
        self.prop_enrich = {}         # property_id -> {logo_url, cover_url, handle, profile_key}
        self.moment_enrich_ok = False
        self.prop_enrich_ok = False
        self.suppressed_moment_ids = set()   # P2-2: moment_ids of patch/maintenance types (hard-suppressed)
        # bookkeeping
        self.now_iso = None

    # ── public builder ────────────────────────────────────────────────────────
    @classmethod
    def load(cls):
        with cls._lock:
            if cls._instance is None:
                d = cls()
                d._load_properties()
                d._load_embeddings()
                d._load_moments()
                d._load_influence()
                d._load_entity_scores()
                d._load_genres_themes()
                try:
                    d._load_enrichment()   # P2-1: OPTIONAL enrichment — must never brick startup
                except Exception as _e:    # pragma: no cover - defensive (covers pool_mids build + any sub-load)
                    import logging
                    logging.getLogger(__name__).warning("[data] enrichment skipped (non-fatal): %s", _e)
                cls._instance = d
            return cls._instance

    @classmethod
    def get(cls):
        return cls.load()

    # ── loaders ───────────────────────────────────────────────────────────────
    @timed("engine", "load_properties")
    def _load_properties(self):
        if _LIVE and _QUERY_FN is not None:                # Silver: public_properties (keyed by id=property_id)
            rows = _QUERY_FN(
                f"SELECT id AS property_id, media_type_id, name, media_source_guid "
                f"FROM {_SILVER_PG}.public_properties "
                f"WHERE deleted_at IS NULL AND media_type_id IN (1,3,4,5)")
            for r in rows:
                pid = _to_int(r.get("property_id"))
                mt = _to_int(r.get("media_type_id"))
                vert = VERTICAL_BY_MTYPE.get(mt)
                if pid is None or vert is None:
                    continue
                eid = f"{PREFIX_BY_VERTICAL[vert]}:{pid}"
                self.properties[pid] = {
                    "property_id": pid,
                    "name": _clean(r.get("name")) or f"Property {pid}",
                    "vertical": vert,
                    "media_type_id": mt,
                    "entity_id": eid,
                }
                self.entity_id_by_pid[pid] = eid
                guid = _to_int(r.get("media_source_guid"))     # bridge for the parquet (guid-keyed) embeddings
                if guid is not None and guid not in self.pid_by_guid:
                    self.pid_by_guid[guid] = pid
            return
        with open(PROPERTIES_CSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                pid = _to_int(row.get("property_id"))
                if pid is None:
                    continue
                mt = _to_int(row.get("media_type_id"))
                vert = VERTICAL_BY_MTYPE.get(mt)
                if vert is None:
                    continue
                eid = f"{PREFIX_BY_VERTICAL[vert]}:{pid}"
                self.properties[pid] = {
                    "property_id": pid,
                    "name": _clean(row.get("name")) or f"Property {pid}",
                    "vertical": vert,
                    "media_type_id": mt,
                    "entity_id": eid,
                }
                self.entity_id_by_pid[pid] = eid

    @timed("engine", "load_embeddings")
    def _load_embeddings(self):
        if _LIVE and os.path.exists(EMB_PARQUET):       # parquet (guid-keyed) -> property_id via the bridge
            import pyarrow.parquet as _pq
            t = _pq.read_table(EMB_PARQUET, columns=["entity_id", "embedding"])
            eids = t.column("entity_id").to_pylist()
            emb = np.asarray(t.column("embedding").to_pylist(), dtype=np.float32)
            norms = np.linalg.norm(emb, axis=1, keepdims=True)
            emb = emb / np.clip(norms, 1e-9, None)
            self.emb = emb
            self.emb_dim = emb.shape[1] if emb.ndim == 2 else 0
            mapped = 0
            for row, eid in enumerate(eids):
                pid = self.pid_by_guid.get(_guid_of(eid))   # bridge: media_source_guid -> property_id
                if pid is not None:
                    self.emb_row_by_pid[pid] = row
                    mapped += 1
            print(f"[data] embeddings via parquet: {len(eids)} rows, {mapped} mapped to property_id "
                  f"(of {len(self.properties)} properties)", flush=True)
            return
        ids = json.load(open(EMB_IDS, encoding="utf-8"))
        emb = np.load(EMB_NPY).astype(np.float32)
        # The matrix is already L2-normalized; renormalize defensively (cheap, idempotent).
        norms = np.linalg.norm(emb, axis=1, keepdims=True)
        emb = emb / np.clip(norms, 1e-9, None)
        self.emb = emb
        self.emb_dim = emb.shape[1]
        for row, eid in enumerate(ids):
            # eid = "Vertical:integer" -> map by the integer (property_id)
            try:
                pid = int(eid.split(":", 1)[1])
            except (IndexError, ValueError):
                continue
            self.emb_row_by_pid[pid] = row

    @timed("engine", "load_moments")
    def _load_moments(self):
        if _LIVE and _QUERY_FN is not None:                # Silver: public_moments (Published=3)
            rows = _QUERY_FN(
                f"SELECT id AS moment_id, property_id, media_type_id, title, description, "
                f"event_starts_at, created_at FROM {_SILVER_PG}.public_moments "
                f"WHERE moment_status_id = 3 AND deleted_at IS NULL AND property_id IS NOT NULL")
            for r in rows:
                pid = _to_int(r.get("property_id"))
                mid = _to_int(r.get("moment_id"))
                if pid is None or mid is None:
                    continue
                prop = self.properties.get(pid)
                mt = _to_int(r.get("media_type_id"))
                vert = (prop["vertical"] if prop else VERTICAL_BY_MTYPE.get(mt))
                es = r.get("event_starts_at")          # SQL TIMESTAMP -> datetime; CSV -> str
                ca = r.get("created_at")
                es = es.isoformat() if hasattr(es, "isoformat") else _clean(es)
                ca = ca.isoformat() if hasattr(ca, "isoformat") else _clean(ca)
                m = {
                    "moment_id": mid,
                    "property_id": pid,
                    "title": _clean(r.get("title")) or "(untitled)",
                    "description": _clean(r.get("description")),
                    "thumbnail_url": None,          # not on public_moments; comes from enrichment (additive)
                    "url": None,
                    "event_starts_at": es,
                    "media_type_id": mt,
                    "views": 0,
                    "created_at": ca,
                    "vertical": vert,
                    "property_name": (prop["name"] if prop else f"Property {pid}"),
                    "entity_id": (prop["entity_id"] if prop else None),
                }
                ev = _epoch(es)
                m["_event_epoch"] = ev if ev is not None else _epoch(ca)
                self.moments.append(m)
                self.moments_by_pid.setdefault(pid, []).append(m)
            return
        csv.field_size_limit(min(sys.maxsize, 2_000_000_000))
        with open(MOMENTS_CSV, encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                pid = _to_int(row.get("property_id"))
                mid = _to_int(row.get("moment_id"))
                if pid is None or mid is None:
                    continue
                prop = self.properties.get(pid)
                mt = _to_int(row.get("media_type_id"))
                vert = (prop["vertical"] if prop else VERTICAL_BY_MTYPE.get(mt))
                m = {
                    "moment_id": mid,
                    "property_id": pid,
                    "title": _clean(row.get("title")) or "(untitled)",
                    "description": _clean(row.get("description")),
                    "thumbnail_url": _clean(row.get("thumbnail_url")),
                    "url": _clean(row.get("url")),
                    "event_starts_at": _clean(row.get("event_starts_at")),
                    "media_type_id": mt,
                    "views": _to_int(row.get("views"), default=0) or 0,
                    "created_at": _clean(row.get("created_at")),
                    "vertical": vert,
                    "property_name": (prop["name"] if prop else f"Property {pid}"),
                    "entity_id": (prop["entity_id"] if prop else None),
                }
                # Pre-parse the content event time once (event_starts_at, fallback created_at) so the
                # ranking hot path uses cheap epoch arithmetic instead of re-parsing strings per request.
                ev = _epoch(row.get("event_starts_at"))
                m["_event_epoch"] = ev if ev is not None else _epoch(row.get("created_at"))
                self.moments.append(m)
                self.moments_by_pid.setdefault(pid, []).append(m)

    @timed("neo4j", "load_influence")
    def _load_influence(self):
        """Pull per-entity `influence` (PageRank popularity) from Neo4j over HTTP, map to property_id.

        Graceful degradation: if Neo4j is unreachable, popularity falls back to views only (all
        zero in this dataset) and the feed still works on relevance/recency/trending.
        """
        if _LIVE and _QUERY_FN is not None:                # Silver: moment-level PageRank -> property MAX
            try:
                rows = _QUERY_FN(
                    f"SELECT property_id, MAX(pagerank_score) AS infl "
                    f"FROM {_SILVER_ML}.discovery_watchmode_pagerank_moments_v1 "
                    f"WHERE property_id IS NOT NULL GROUP BY property_id")
            except Exception as e:  # pragma: no cover - environment dependent
                print(f"[data] live influence skipped ({str(e)[:100]}); popularity uses views only.",
                      file=sys.stderr, flush=True)
                self.graph_ok = False
                self.influence_max = 1.0
                return
            mx = 0.0
            for r in rows:
                pid = _to_int(r.get("property_id"))
                infl = r.get("infl")
                if pid is None or infl is None:
                    continue
                val = float(infl)
                self.influence_by_pid[pid] = val
                if val > mx:
                    mx = val
            self.graph_ok = bool(self.influence_by_pid)
            self.influence_max = mx if mx > 0 else 1.0
            return
        # Schema A (pre-dump graph): :Entity nodes keyed entity_id="Vertical:pid" with `influence`.
        try:
            rows = neo_cypher(
                "MATCH (n:Entity) WHERE n.influence IS NOT NULL "
                "RETURN n.entity_id AS id, n.influence AS infl"
            )
        except Exception as e:  # pragma: no cover - environment dependent
            print(f"[data] WARNING: Neo4j influence load failed ({type(e).__name__}: {str(e)[:120]}); "
                  f"popularity will use views only.", file=sys.stderr, flush=True)
            self.graph_ok = False
            self.influence_max = 1.0
            return
        mx = 0.0
        for r in rows:
            eid, infl = r["row"][0], r["row"][1]
            if eid is None or infl is None:
                continue
            try:
                pid = int(str(eid).split(":", 1)[1])
            except (IndexError, ValueError):
                continue
            val = float(infl)
            self.influence_by_pid[pid] = val
            if val > mx:
                mx = val

        # Schema B (post-dump staging graph): nodes carry `pagerank` keyed by `name`/`node_key`, NOT
        # entity_id. Bridge by name -> property_id so popularity still works after the graph swap.
        if not self.influence_by_pid:
            try:
                rows = neo_cypher("MATCH (n) WHERE n.pagerank IS NOT NULL "
                                  "RETURN n.name AS name, n.pagerank AS pr")
            except Exception as e:  # pragma: no cover
                print(f"[data] WARNING: pagerank fallback failed ({str(e)[:80]})", file=sys.stderr, flush=True)
                rows = []
            name_to_pid = {}
            for pid, p in self.properties.items():
                nm = (p.get("name") or "").strip().lower()
                if nm and nm not in name_to_pid:
                    name_to_pid[nm] = pid
            for r in rows:
                nm, pr = r["row"][0], r["row"][1]
                if nm is None or pr is None:
                    continue
                pid = name_to_pid.get(str(nm).strip().lower())
                if pid is None:
                    continue
                val = float(pr)
                self.influence_by_pid[pid] = val
                if val > mx:
                    mx = val
            if self.influence_by_pid:
                print(f"[data] influence via pagerank-by-name: {len(self.influence_by_pid)} matched", flush=True)

        self.graph_ok = bool(self.influence_by_pid)
        self.influence_max = mx if mx > 0 else 1.0

    @timed("engine", "load_entity_scores")
    def _load_entity_scores(self):
        """Load precomputed engagement scores (trending/popularity/freshness) from Postgres.

        Graceful degradation: if Postgres or the table is unavailable/empty, `entity_scores` stays
        empty and the ranker falls back to its Neo4j-influence popularity + views-proxy trending
        (i.e. pre-redesign behaviour) — no regression. Set DISCOVERY_PG=0 to skip entirely.
        """
        if os.environ.get("DISCOVERY_PG", "1") == "0":
            return
        try:
            import psycopg2
            c = psycopg2.connect(host="localhost", port=5433, user="postgres", password="postgres",
                                 dbname="feedsai_discovery", connect_timeout=5)
            cur = c.cursor()
            cur.execute("SELECT property_id, trending_score, popularity_score, freshness_score "
                        "FROM entity_scores")
            for pid, tr, pop, fr in cur.fetchall():
                self.entity_scores[int(pid)] = {
                    "trending": float(tr), "popularity": float(pop), "freshness": float(fr),
                }
            c.close()
            self.entity_scores_ok = True
        except Exception as e:  # pragma: no cover - environment dependent
            print(f"[data] entity_scores load skipped ({type(e).__name__}: {str(e)[:100]})",
                  file=sys.stderr, flush=True)
            self.entity_scores_ok = False

    @timed("neo4j", "load_genres_themes")
    def _load_genres_themes(self):
        """Pull per-entity genres + themes from the Neo4j graph (HAS_GENRE / HAS_THEME) for card
        metadata and the 'why' reasoning line. Graceful no-op if Neo4j is unreachable."""
        if _LIVE:                                          # genres/themes via Neo4j not wired for live yet
            return                                          # (additive); cards/why degrade gracefully
        for rel, label, target in (("HAS_GENRE", "Genre", self.genres_by_pid),
                                    ("HAS_THEME", "Theme", self.themes_by_pid)):
            try:
                rows = neo_cypher(
                    f"MATCH (e:Entity)-[:{rel}]->(x:{label}) "
                    f"RETURN e.entity_id AS id, collect(DISTINCT x.name) AS names"
                )
            except Exception as e:  # pragma: no cover - environment dependent
                print(f"[data] {rel} load skipped ({type(e).__name__}: {str(e)[:80]})",
                      file=sys.stderr, flush=True)
                continue
            for r in rows:
                eid, names = r["row"][0], r["row"][1]
                if eid is None or not names:
                    continue
                try:
                    pid = int(str(eid).split(":", 1)[1])
                except (IndexError, ValueError):
                    continue
                target[pid] = [n for n in names if n]

    def reload_entity_scores(self):
        """Re-read entity_scores from Postgres into memory (used by the periodic refresher so a new
        reaction by ANY user is reflected in the live feed without a restart)."""
        self.entity_scores = {}
        self._load_entity_scores()
        return len(self.entity_scores)

    @timed("engine", "load_enrichment")
    def _load_enrichment(self):
        """P2-1: load Databricks Silver enrichment (moment_type / media_platform / images / handle) into
        SEPARATE dicts — existing moment/property dicts are untouched. Each sub-load is fault-isolated: a
        missing or malformed CSV logs a warning and leaves that dict empty rather than bricking startup.
        Only ids present in the ACTIVE pool are kept (dead-weight rows for unserved entities are dropped).
        The CSVs use 'id' as the key column; descriptions contain embedded newlines so newline='' is
        mandatory; rows with non-null _rescued_data (partial Databricks rows) are skipped."""
        import logging
        log = logging.getLogger(__name__)
        csv.field_size_limit(min(sys.maxsize, 2_000_000_000))

        def _load_lookup(path, dest, label):
            try:
                with open(path, encoding="utf-8", newline="") as f:
                    for row in csv.DictReader(f):
                        if _clean(row.get("_rescued_data")) is not None:
                            continue
                        i = _to_int(row.get("id"))
                        nm = _clean(row.get("name"))
                        if i is not None and nm is not None:
                            dest[i] = nm
                log.info("[data] %s loaded %d", label, len(dest))
            except Exception as e:  # pragma: no cover - defensive
                log.warning("[data] %s load failed: %s", label, e)

        # 1) small lookups first (moment_enrich resolves names from these)
        _load_lookup(ENRICH_MTYPES_CSV, self.moment_types, "moment_types")
        _load_lookup(ENRICH_MPLATS_CSV, self.media_platforms, "media_platforms")

        # 2) property enrichment — keyed by 'id'; keep only properties in our active catalogue.
        try:
            with open(ENRICH_PROPS_CSV, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if _clean(row.get("_rescued_data")) is not None:
                        continue
                    pid = _to_int(row.get("id"))
                    if pid is None or pid not in self.properties:   # drop dead weight (~57%)
                        continue
                    self.prop_enrich[pid] = {
                        "logo_url": _clean(row.get("logo_url")),
                        "cover_url": _clean(row.get("cover_url")),
                        "handle": _clean(row.get("nickname")),       # slug handle (profile_key is a source key)
                        "profile_key": _clean(row.get("profile_key")),
                    }
            self.prop_enrich_ok = len(self.prop_enrich) > 0
            log.info("[data] prop_enrich loaded %d (active props=%d)", len(self.prop_enrich), len(self.properties))
            if not self.prop_enrich_ok:
                log.warning("[data] prop_enrich EMPTY — check enrich_properties.csv 'id' column")
        except Exception as e:  # pragma: no cover - defensive
            log.warning("[data] prop_enrich load failed: %s", e)

        # 3) moment enrichment — keyed by 'id'; keep only moments in our active pool.
        pool_mids = {m["moment_id"] for m in self.moments}
        try:
            with open(ENRICH_MOMENTS_CSV, encoding="utf-8", newline="") as f:
                for row in csv.DictReader(f):
                    if _clean(row.get("_rescued_data")) is not None:
                        continue
                    mid = _to_int(row.get("id"))
                    if mid is None or mid not in pool_mids:          # drop dead weight (~40%)
                        continue
                    mtid = _to_int(row.get("moment_type_id"))
                    mpid = _to_int(row.get("media_platform_id"))
                    self.moment_enrich[mid] = {
                        "moment_type_id": mtid,
                        "moment_type_name": self.moment_types.get(mtid),
                        "media_platform_id": mpid,
                        "media_platform_name": self.media_platforms.get(mpid),
                        "hero_image_url": _clean(row.get("hero_image_url")),
                        "thumbnail_url": _clean(row.get("thumbnail_url")),
                        "cta_button_text": _clean(row.get("cta_button_text")),
                    }
            self.moment_enrich_ok = len(self.moment_enrich) > 0
            log.info("[data] moment_enrich loaded %d (pool=%d)", len(self.moment_enrich), len(pool_mids))
            if not self.moment_enrich_ok:
                log.warning("[data] moment_enrich EMPTY — check enrich_moments.csv 'id' column")
        except Exception as e:  # pragma: no cover - defensive
            log.warning("[data] moment_enrich load failed: %s", e)

        # P2-2: patch/maintenance moments must never reach a public feed -> precompute their ids once
        # (O(1) candidate-filter check per request, instead of a second moment_extra() pass).
        # DATA NOTE: 0 such moments in the current pool overlap (these types are absent from
        # public_moments.csv today) — defensive infra that fires automatically if they ever appear.
        self.suppressed_moment_ids = {mid for mid, e in self.moment_enrich.items()
                                      if e.get("moment_type_name") in SUPPRESS_MOMENT_TYPES}
        log.info("[data] suppressed_moment_ids (patch/maintenance): %d", len(self.suppressed_moment_ids))

    # ── lookups used by the ranking layer ─────────────────────────────────────
    def embedding_for_pid(self, pid):
        """Return the (1024,) L2-normalized embedding for a property, or None if absent."""
        row = self.emb_row_by_pid.get(pid)
        if row is None:
            return None
        return self.emb[row]

    def moment_extra(self, mid):
        """P2-1 enrichment for a moment (moment_type/is_live/platform/hero image/cta), or {} if absent."""
        return self.moment_enrich.get(mid, {})

    def prop_extra(self, pid):
        """P2-1 enrichment for a property (logo/cover/handle), or {} if absent."""
        return self.prop_enrich.get(pid, {})

    def stats(self):
        return {
            "properties": len(self.properties),
            "moments": len(self.moments),
            "embeddings": int(self.emb.shape[0]) if self.emb is not None else 0,
            "emb_dim": self.emb_dim,
            "graph_influence_loaded": len(self.influence_by_pid),
            "graph_ok": self.graph_ok,
            "entity_scores_loaded": len(self.entity_scores),
            "entity_scores_ok": self.entity_scores_ok,
            "genres_loaded": len(self.genres_by_pid),
            "themes_loaded": len(self.themes_by_pid),
            "moment_types_loaded": len(self.moment_types),
            "media_platforms_loaded": len(self.media_platforms),
            "moment_enrich_loaded": len(self.moment_enrich),
            "prop_enrich_loaded": len(self.prop_enrich),
            "suppressed_moment_ids": len(self.suppressed_moment_ids),
        }
