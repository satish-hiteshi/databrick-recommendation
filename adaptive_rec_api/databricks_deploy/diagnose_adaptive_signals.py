# Databricks notebook source
# MAGIC %md
# MAGIC # Diagnose adaptive-rec divergence — vectors vs popularity  (standalone)
# MAGIC Two independent checks to decide how to reconcile the deployed endpoint with the UC6 reference:
# MAGIC 1. **Silver ratings** — does Silver carry per-title `user_rating` / `critic_rating`? (decides whether we
# MAGIC    can rebuild popularity to match the reference's *quality*-based method, vs the deployed hype/percentile.)
# MAGIC 2. **Vector corpus** — recompute the reference's own RELEVANCE numbers on the deployed parquet(s). If they
# MAGIC    match, the vectors are fine and popularity is the only driver; if not, the deployed (prefixed) corpus
# MAGIC    differs from the reference corpus.
# MAGIC
# MAGIC *Standalone version (deploy repo has no `workspace_catalog`): set the `catalog` widget for the target env.*

# COMMAND ----------
dbutils.widgets.text("catalog", "stg_feeds_silver")   # dev_feeds_silver | stg_feeds_silver | prod_feeds_silver
CATALOG = dbutils.widgets.get("catalog")
VOLUME_DIR = f"/Volumes/{CATALOG}/ml/feedsai_src"
print("catalog:", CATALOG, "| volume:", VOLUME_DIR)

# COMMAND ----------
# ===================== CHECK 1 — does Silver have user/critic ratings? =====================
import re
# the Silver source tables the popularity precompute joins (one per vertical)
TABLES = {
    "game (igdb)":          f"{CATALOG}.igdb.core_games_extended",
    "movie/tv (watchmode)": f"{CATALOG}.watchmode.titles_titles_extended",
    "podcast (podchaser)":  f"{CATALOG}.podchaser.core_podcasts_extended",
}
RATING_RX = re.compile(r"rating|score|vote|critic|user|metacritic|imdb|aggregated|combined|hype|popular|power", re.I)
for label, tbl in TABLES.items():
    print(f"\n=== {label}   {tbl} ===")
    try:
        cols = [f.name for f in spark.table(tbl).schema.fields]
        hits = [c for c in cols if RATING_RX.search(c)]
        print("  rating-like columns:", hits or "(none)")
        # show a few non-null sample values for the rating-like columns (first 3 rows)
        if hits:
            display(spark.table(tbl).select(*hits[:8]).limit(3))
    except Exception as e:
        print("  ERROR:", str(e)[:100])
# READ: if user_rating / critic_rating (or aggregated_rating / vote_average / critical_score) exist and are
# populated -> we CAN align adaptive popularity to the reference's quality method. If only hype/percentile/
# powerScore -> the deployed method is the only option (accept + re-baseline the reference).

# COMMAND ----------
# ===================== CHECK 2 — is the deployed vector corpus the divergence? =====================
# Recompute the reference's RELEVANCE (max cosine of the expected pick to the follows) on each deployed
# parquet, and compare to the UC6 report's debug numbers. Whichever parquet reproduces them == the corpus the
# reference was built on.
import os, numpy as np, pyarrow.parquet as pq
VOL = VOLUME_DIR   # /Volumes/<catalog>/ml/feedsai_src
CANDIDATES = [f"{VOL}/embeddings_qwen_44k_prefixed.parquet", f"{VOL}/embeddings_qwen.parquet"]

# reference cases: (label, followed_property_ids, expected pick, reference winner_signals.relevance from UC6 report)
CASES = [
    ("01 GTA V",      [1877, 52189],    134709, 0.829),
    ("02 Halo Inf",   [101440, 317407], 103281, 0.653),
    ("03 RE Village", [279051, 347668], 55163,  0.748),
    ("04 Witcher 3",  [125633, 116530], 1942,   0.657),
]

def _load(path):
    t = pq.read_table(path); c = {n: t.column(n).to_pylist() for n in t.schema.names}
    d = {}
    for e, emb in zip(c["entity_id"], c["embedding"]):
        s = str(e)
        try:
            d[int(s.split(":", 1)[1] if ":" in s else s)] = np.asarray(emb, dtype=np.float64)
        except Exception:
            pass
    return d

def _unit(v):
    n = np.linalg.norm(v); return v / n if n else v

def _rel(bp, pick, foll):
    if pick not in bp:
        return None
    fv = [_unit(bp[f]) for f in foll if f in bp]
    if not fv:
        return None
    p = _unit(bp[pick])
    return float(max(float(p @ f) for f in fv))

for path in CANDIDATES:
    name = os.path.basename(path)
    if not os.path.exists(path):
        print(f"\n(absent) {name}")
        continue
    bp = _load(path); dim = len(next(iter(bp.values())))
    print(f"\n=== {name}   rows={len(bp)}  dim={dim} ===")
    print(f"  {'case':14}{'pick':>8}{'ref_rel':>9}{'this_corpus':>13}{'match?':>8}")
    for lbl, foll, pick, ref in CASES:
        r = _rel(bp, pick, foll)
        ok = r is not None and abs(r - ref) < 0.02
        shown = round(r, 3) if r is not None else "MISSING"
        print(f"  {lbl:14}{pick:>8}{ref:>9.3f}{str(shown):>13}{str(ok):>8}")

# COMMAND ----------
# ===================== CHECK 3 — are the signal tables populated + joinable? (why popularity/centrality = 0.0) =====================
import os as _os, pyarrow.parquet as _pq
_pq_path = f"{VOLUME_DIR}/embeddings_qwen_44k_prefixed.parquet"
_pids = set()
if _os.path.exists(_pq_path):
    for e in _pq.read_table(_pq_path, columns=["entity_id"]).column("entity_id").to_pylist():
        s = str(e)
        try:
            _pids.add(int(s.split(":", 1)[1] if ":" in s else s))
        except Exception:
            pass
print(f"corpus property_ids: {len(_pids)}")
for t in ["adaptive_property_centrality", "adaptive_property_popularity", "adaptive_property_proximity"]:
    tbl = f"{CATALOG}.ml.{t}"
    try:
        df = spark.table(tbl); n = df.count()
        tpids = set(r["property_id"] for r in df.select("property_id").collect())
        print(f"\n{t}:  rows={n}  |  overlap with corpus: {len(_pids & tpids)}/{len(_pids)}")
        display(df.limit(3))
    except Exception as e:
        print(f"\n{t}:  MISSING / ERROR -> {str(e)[:100]}")
# READ:
#  - MISSING       -> the adaptive precompute never ran (or wrote to a different catalog than the endpoint reads).
#  - rows = 0      -> precompute ran but produced nothing (Aura / Silver read failed).
#  - overlap ~ 0   -> property_id space mismatch -> every serving lookup misses -> popularity/centrality = 0.0.
#  - rows>0 & overlap high, yet the ENDPOINT still shows 0.0 -> serving can't read them: verify the endpoint env
#    (ADAPTIVE_DATA_SOURCE=live, ADAPTIVE_SILVER_CATALOG) and the SQL-warehouse query_fn (warehouse id + perms).

# COMMAND ----------
# ===================== VERDICT =====================
print("CHECK 1 → if Silver has real user/critic ratings, aligning popularity to the reference is possible;")
print("          if only hype/percentile/powerScore, the deployed popularity is the only option.")
print("CHECK 2 → the parquet whose 'this_corpus' relevance matches ref_rel is the corpus the reference used.")
print("CHECK 3 → if the tables are MISSING / empty / non-overlapping, THAT is why popularity+centrality are 0.0")
print("          (ranking collapses to relevance-only) — fix that before comparing anything else.")
print("          prefixed matches  -> vectors fine; popularity is the sole divergence.")
print("          non-prefixed matches -> point the adaptive endpoint at the non-prefixed parquet to converge.")
print("          neither matches   -> the reference corpus isn't on this Volume (built from local property_vectors).")
