# Databricks notebook source
# MAGIC %md
# MAGIC # Redeploy Endpoint 1 — Agent-Recs (optimized router · Qwen 44k) — 2026-06-26
# MAGIC **What changed in this redeploy**
# MAGIC - **Optimized router code** (`engines/router_src/`): negation recovery (G37/G38), deterministic
# MAGIC   **recency** (`recency.py` — new/newest/latest + epoch date window), graceful **overconstrain
# MAGIC   relaxation** (`MIN_RESULTS=3`), LLM **no-signal/gibberish** fallback (`no_signal.py` — new),
# MAGIC   PROMPT2 fixes (raw-query embedding, `RERANK=auto`, verbatim Capital-prefixed ids).
# MAGIC - **New corpus parquet**: `embeddings.parquet` (Qwen 1024-dim, Capital-prefixed
# MAGIC   ids, carries `release_date_ts`). **Freshly-restored graph** (Aura, from dump) — done out of band.
# MAGIC
# MAGIC **Self-configuring · job-runnable.** Derives repo path + workspace host, registers the collapsed
# MAGIC model (engines + parquet), **creates OR updates** the endpoint, waits READY, runs the acceptance
# MAGIC smoke battery. Override any value via job `base_parameters` / widgets.
# MAGIC
# MAGIC **Do NOT `%pip install mlflow`** — the runtime's MLflow is integrated; reinstalling it breaks registration.
# MAGIC
# MAGIC > ✅ **Recency (fully wired):** `vector_search/vs_store.py` range-filters `release_date_ts` (epoch),
# MAGIC > and the router's `recency.py` window (new/newest/latest + today-clamp) is now passed **straight
# MAGIC > through** `inprocess_engines._vec_query`→`query_engine.process_query` (it overrides the vector
# MAGIC > NLU's own date guess). Works **iff the `entities`/`entities_vs` index is rebuilt from the new
# MAGIC > parquet carrying `release_date_ts`** — verify H5. Gates: `VS_DATE_FILTER=0` disables the filter;
# MAGIC > `VS_RELEASE_DATE_COL` overrides the column name.

# COMMAND ----------
# MAGIC %md
# MAGIC ## ⚠️ BEFORE YOU RUN — sync the fixed code into THIS workspace folder
# MAGIC `register.main()` (Step 2) bundles the code that lives **next to this notebook on Databricks**
# MAGIC (`serving/`, `engines/`) — **NOT your laptop**. Local edits to `blocks.py` / `vs_store.py` reach the
# MAGIC served model ONLY after you sync them here, e.g.:
# MAGIC - **Databricks Git Repo:** commit + push locally, then **Pull** in the Repos UI.
# MAGIC - **Asset Bundle:** `databricks bundle deploy -t staging`.
# MAGIC
# MAGIC This is the #1 reason a redeploy can still serve the OLD code (e.g. the `None`-concept crash persists).
# MAGIC Then set **`rebuild_index=1`** so `entities_vs` is rebuilt from the new Qwen parquet. Skipping either =
# MAGIC old code and/or a stale index.

# COMMAND ----------
# MAGIC %md
# MAGIC ## Setup — install the Vector Search client (run FIRST)
# MAGIC `databricks-vectorsearch` (used by Step 1.5's index rebuild) is not bundled on serverless / fresh
# MAGIC clusters. `%pip install` + `restartPython()` reset Python state (widgets persist), so this runs first.
# MAGIC Safe to skip if your cluster already has the package. Do NOT add `mlflow` here — the runtime's is integrated.

# COMMAND ----------
# MAGIC %pip install databricks-vectorsearch

# COMMAND ----------
dbutils.library.restartPython()

# COMMAND ----------
# ===================== 0. AUTO-DERIVE repo location + workspace host (no hardcoding) =====================
import os
HOST = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
_nb = dbutils.notebook.entry_point.getDbutils().notebook().getContext().notebookPath().get()
if not _nb.startswith("/Workspace"):
    _nb = "/Workspace" + _nb
SERVING = os.path.dirname(_nb) + "/serving"          # <this notebook's dir>/serving (parrot bundle)
print("HOST    :", HOST)
print("SERVING :", SERVING)

# COMMAND ----------
# ===================== 1. CONFIG (widgets — a Job can override via base_parameters) =====================
_defaults = {
    "catalog":       "stg_feeds_silver",
    "schema":        "ml",
    "endpoint":      "parrot-api-staging",            # client copy defaults to parrot-api-staging-v2
    "scope":         "feeds-default-scope",               # Databricks secret scope (neo4j_password, databricks_token)
    "parquet":       "/Volumes/stg_feeds_silver/ml/feedsai_src/embeddings.parquet",  # NEW corpus
    "vs_endpoint":   "feedsai-staging-vs",
    "vs_index":      "stg_feeds_silver.ml.entities_vs",
    "neo4j_uri":     "neo4j+s://17aa0e8d.databases.neo4j.io",
    "llm_endpoint":  "llama_v3_3_70b_instruct",       # LLM serving-endpoint NAME (URL built from HOST)
    "qwen_embed":    "databricks-qwen3-embedding-0-6b",
    "workload_size": "Medium",
    "enable_timing": "1",                             # "1" → TIMING_BREAKDOWN (source for per-stage latency)
    "rerank":        "none",                          # none|learned|cross_encoder|auto. OFF to match local (local runs
                                                      #   with no cross-encoder installed, so its "auto" no-ops → effectively off).
                                                      #   "auto" = selective cross-encoder if installed (needs sentence-transformers
                                                      #   +torch); "learned" = LLM reranker (no heavy deps, +1 LLM call).
    "vector_backend":"databricks",                    # "databricks" → Databricks Vector Search (entities_vs). Anything else
                                                      #   (e.g. "qdrant") → in-memory Qdrant built from the bundled parquet —
                                                      #   the SAME engine as the local stack; needs no entities_vs index.
    # ── observability (OTLP → Grafana Cloud, H1.6) ──
    "otel_service":  "agent-recs",                    # OTEL_SERVICE_NAME
    "enable_otel":   "0",                             # "1" → push telemetry (needs the grafana_otlp_headers secret)
    "otel_endpoint": "https://otlp-gateway-prod-us-east-3.grafana.net/otlp",
    "otel_secret":   "grafana_otlp_headers",            # secret key in <scope> holding the base64 OTLP token
    "otel_sampler":  "0.15",                          # fraction of requests traced (metrics stay 100%)
    # ── data sync (Step 1.5) ──
    "rebuild_index": "0",                             # "1" → rebuild ml.entities + entities_vs from `parquet` (carries release_date_ts)
    "run_full_test": "0",                             # "1" → run the 50-query acceptance set (Section 5, ~3 min)
}
for k, v in _defaults.items():
    dbutils.widgets.text(k, v)
C = {k: dbutils.widgets.get(k) for k in _defaults}
MODEL_NAME = f"{C['catalog']}.{C['schema']}.{C['endpoint']}"
print("model:", MODEL_NAME, "| endpoint:", C["endpoint"], "| parquet:", C["parquet"])

# COMMAND ----------
# ===================== 1.5 (OPTIONAL) REBUILD entities table + entities_vs from the parquet =====================
# MAGIC %md
# MAGIC Gated by the **`rebuild_index`** widget. parquet → `<catalog>.<schema>.entities` Delta table
# MAGIC (carrying `release_date_ts`) → **recreate** the `entities_vs` Delta-Sync index (delete + create, so it
# MAGIC picks up `release_date_ts` and the Qwen vectors). Required whenever the corpus/parquet changed — this
# MAGIC is what makes `vs_store`'s recency filter (and correct Qwen retrieval) actually work.

# COMMAND ----------
if C["rebuild_index"] != "1":
    print("rebuild_index=0 → skipping entities/entities_vs rebuild (set the widget to 1 to run it).")
else:
    TABLE = f"{C['catalog']}.{C['schema']}.entities"
    # (1) read the parquet with an EXPLICIT schema. Some Spark/serverless sessions honor the parquet's
    # embedded Spark schema (which can omit release_date_ts) over the physical columns; passing the schema
    # forces Spark to read the physical release_date_ts. If a session STILL drops it, use the PyArrow
    # fallback just below — PyArrow always reads the physical columns.
    from pyspark.sql.types import (StructType, StructField, StringType, ArrayType, FloatType, LongType)
    _schema = StructType([
        StructField("entity_id", StringType()),           StructField("name", StringType()),
        StructField("vertical", StringType()),            StructField("bm25_keywords", ArrayType(StringType())),
        StructField("embedding", ArrayType(FloatType())), StructField("release_date_ts", LongType()),
    ])
    df = spark.read.schema(_schema).parquet(C["parquet"])
    # ── PyArrow fallback (uncomment these 5 lines + comment the line above if Spark still drops the column) ──
    # import pyarrow.parquet as pq, pandas as pd
    # _pdf = pq.read_table(C["parquet"]).to_pandas()
    # _pdf["embedding"] = _pdf["embedding"].apply(lambda v: [float(x) for x in v])
    # _pdf["bm25_keywords"] = _pdf["bm25_keywords"].apply(lambda v: [str(x) for x in (v if v is not None else [])])
    # _pdf["release_date_ts"] = _pdf["release_date_ts"].apply(lambda v: None if pd.isna(v) else int(v))
    # df = spark.createDataFrame(_pdf[["entity_id","name","vertical","bm25_keywords","embedding","release_date_ts"]], _schema)
    print("parquet rows:", df.count()); df.printSchema()
    _missing = {"entity_id", "name", "vertical", "embedding", "release_date_ts"} - set(df.columns)
    assert not _missing, f"parquet missing required columns: {_missing}"
    _dim = len(df.select("embedding").first()["embedding"])
    assert _dim == 1024, f"embedding dim {_dim} != 1024 — wrong parquet/model (Qwen embeds are 1024)?"
    print(f"schema OK — {len(df.columns)} cols, embedding dim {_dim}, release_date_ts present.")
    # (2) parquet → Delta table (+ Change Data Feed, required for a Delta-Sync index)
    (df.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(TABLE))
    spark.sql(f"ALTER TABLE {TABLE} SET TBLPROPERTIES (delta.enableChangeDataFeed = true)")
    print("entities table rows:", spark.table(TABLE).count())
    display(spark.sql(f"SELECT vertical, count(*) n, "
                      f"sum(CASE WHEN release_date_ts IS NULL THEN 1 ELSE 0 END) null_dates "
                      f"FROM {TABLE} GROUP BY vertical"))
    # (3) recreate the VS index (delete + create → picks up release_date_ts + the Qwen vectors).
    #     A plain .sync() would NOT add a new column or swap the embedding source — recreate is required.
    from databricks.vector_search.client import VectorSearchClient
    vsc = VectorSearchClient(disable_notice=True)
    _existing = [i["name"] for i in (vsc.list_indexes(C["vs_endpoint"]).get("vector_indexes") or [])]
    if C["vs_index"] in _existing:
        print("deleting stale index…"); vsc.delete_index(C["vs_endpoint"], C["vs_index"])
    vsc.create_delta_sync_index_and_wait(
        endpoint_name=C["vs_endpoint"], index_name=C["vs_index"], source_table_name=TABLE,
        pipeline_type="TRIGGERED", primary_key="entity_id",
        embedding_dimension=1024, embedding_vector_column="embedding",   # self-managed (precomputed) Qwen vectors
        # if your workspace requires explicit column selection, add:
        # columns_to_sync=["entity_id", "name", "vertical", "release_date_ts"],
    )
    # (4) verify the date filter actually works on the index
    idx = vsc.get_index(C["vs_endpoint"], C["vs_index"])
    _sample = spark.table(TABLE).select("embedding").limit(1).collect()[0]["embedding"]
    _chk = idx.similarity_search(query_vector=list(_sample), columns=["entity_id", "name", "vertical"],
            filters={"release_date_ts >=": 1704067200}, num_results=3)   # >= 2024-01-01 UTC
    print("date-filtered sample:", (_chk.get("result", {}).get("data_array") or [])[:3])
    print("entities + entities_vs rebuilt and date filter verified ✓")

# COMMAND ----------
# ===================== 2. REGISTER (bundle optimized engines + new Qwen parquet → UC model) =====================
import mlflow, sys, importlib
mlflow.set_registry_uri("databricks-uc")             # runtime mlflow; do NOT pip-install it
os.environ["UC_MODEL_NAME"]          = MODEL_NAME
os.environ["EMBEDDINGS_PARQUET_SRC"] = C["parquet"]  # the in-memory store rebuilds from THIS parquet at register
sys.modules.pop("register", None)                    # ensure THIS bundle's register is loaded
sys.path.insert(0, SERVING)
import register; importlib.reload(register)
register.main()
from mlflow.tracking import MlflowClient
ver = str(max(int(v.version) for v in MlflowClient().search_model_versions(f"name='{MODEL_NAME}'")))
print("registered version:", ver)

# COMMAND ----------
# ===================== 3. CREATE-OR-UPDATE the endpoint (full env) + WAIT FOR READY =====================
from datetime import timedelta
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import (EndpointCoreConfigInput, ServedEntityInput, TrafficConfig, Route)
wc = WorkspaceClient()

def sec(k): return "{{" + f"secrets/{C['scope']}/{k}" + "}}"
ENV = {
    "ROUTER_ENGINE_MODE": "inprocess",                # collapse: blocks._post/_get dispatch in-process
    "LLM_PROVIDER": "databricks",
    "DATABRICKS_LLM_ENDPOINT": f"{HOST}/serving-endpoints/{C['llm_endpoint']}/invocations",
    "DATABRICKS_HOST": HOST, "DATABRICKS_TOKEN": sec("databricks_token"),
    "QUERY_EMBED_ENDPOINT": C["qwen_embed"],           # queries embed via Qwen (instruction-prefixed; matches corpus)
    "VECTOR_BACKEND": C["vector_backend"],             # databricks=Vector Search · else=in-memory Qdrant from bundled parquet
    "VS_ENDPOINT_NAME": C["vs_endpoint"], "VS_INDEX_NAME": C["vs_index"],   # (ignored on the qdrant backend)
    "NEO4J_URI": C["neo4j_uri"], "NEO4J_USER": "neo4j",
    "NEO4J_PASSWORD": sec("neo4j_password"), "NEO4J_DATABASE": "neo4j",
}
if C["enable_timing"] == "1":
    ENV["TIMING_BREAKDOWN"] = "1"
ENV["RERANK"] = C["rerank"]                            # rerank strategy — drives open-ended (vector) ranking quality

# ── observability (H1.6): OTEL_SERVICE_NAME is always safe; the OTLP push is gated on enable_otel
# (the secret must exist in the scope, else the endpoint create fails on an unresolvable secret ref). ──
ENV["OTEL_SERVICE_NAME"] = C["otel_service"]
if C["enable_otel"] == "1":
    ENV["OTEL_EXPORTER_OTLP_ENDPOINT"] = C["otel_endpoint"]
    ENV["OTEL_EXPORTER_OTLP_PROTOCOL"] = "http/protobuf"
    ENV["OTEL_EXPORTER_OTLP_HEADERS"]  = "Authorization=Basic%20" + sec(C["otel_secret"])  # %20 = space (literal space 401s)
    ENV["OTEL_TRACES_SAMPLER_ARG"]     = C["otel_sampler"]

entities = [ServedEntityInput(name="router", entity_name=MODEL_NAME, entity_version=ver,
            workload_size=C["workload_size"], scale_to_zero_enabled=False, environment_vars=ENV)]
traffic = TrafficConfig(routes=[Route(served_model_name="router", traffic_percentage=100)])
exists = any(e.name == C["endpoint"] for e in wc.serving_endpoints.list())
print(("updating" if exists else "creating") + f" {C['endpoint']} → v{ver} … waiting for READY (~15 min warm-up)")
if exists:
    wc.serving_endpoints.update_config_and_wait(name=C["endpoint"], served_entities=entities,
        traffic_config=traffic, timeout=timedelta(minutes=50))
else:
    wc.serving_endpoints.create_and_wait(name=C["endpoint"],
        config=EndpointCoreConfigInput(served_entities=entities, traffic_config=traffic),
        timeout=timedelta(minutes=50))
print("endpoint state:", wc.serving_endpoints.get(C["endpoint"]).state)

# COMMAND ----------
# ===================== 4. ACCEPTANCE SMOKE BATTERY (REVIEW_CHECKLIST H-battery) =====================
import requests, json
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"

def ask(query, agent="morgan", uid="13", top_k=10):
    body = {"dataframe_records": [{"user_id": uid, "query": query, "requesting_agent": agent, "top_k": top_k}]}
    r = requests.post(URL, headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
                      json=body, timeout=120)
    r.raise_for_status()
    inner = r.json()["predictions"][0]
    resp = inner.get("response"); resp = resp if isinstance(resp, dict) else json.loads(resp)
    return resp, (resp.get("router", {}) or {})

def show(tag, query, resp, rt):
    res = resp.get("results") or []
    print(f"\n[{tag}] {query!r}")
    print(f"   error={resp.get('error')} count={resp.get('count')} path={rt.get('path_taken') or rt.get('universe_establisher')} "
          f"timing_ms={rt.get('timing_ms')}")
    for it in res[:6]:
        print(f"     - {str(it.get('vertical')):7} {str(it.get('entity_id')):>14}  {str(it.get('name'))[:42]}")
    return res

_PREFIXES = {"Game", "Movie", "TV", "Podcast"}
def check_id_prefix(res):
    """REVIEW_CHECKLIST block B (HARD): entity_ids must be Capital-prefixed verbatim (else feeds-api
    drops non-game rows). Catches the lowercase/mangled-id silent regression."""
    bad = [it.get("entity_id") for it in res if str(it.get("entity_id", "")).split(":")[0] not in _PREFIXES]
    print(f"   ↳ id-prefix (block B): {'OK — all Capital-prefixed' if not bad else 'FAIL → ' + str(bad[:5])}")

# H1 — franchise (graph establish): Final Fantasy
resp, rt = ask("Final Fantasy games"); r1 = show("H1 franchise", "Final Fantasy games", resp, rt)
assert resp.get("error") is None and (resp.get("count") or 0) > 0, "H1 failed"
check_id_prefix(r1)

# H3 — negation, RUN TWICE (extraction varies — the G38 lesson): games but not horror → expect 0 horror
for run in (1, 2):
    resp, rt = ask("games but not horror"); show(f"H3 negation run{run}", "games but not horror", resp, rt)
    assert resp.get("error") is None and (resp.get("count") or 0) > 0, f"H3 run{run} failed"
print("   ↳ MANUALLY VERIFY: 0 horror titles in BOTH runs (response carries no genre — eyeball names/ids).")

# H5 — recency: new sci-fi movies (see the recency caveat in the header)
resp, rt = ask("new sci-fi movies"); show("H5 recency", "new sci-fi movies", resp, rt)
assert resp.get("error") is None, "H5 errored"
print("   ↳ VERIFY recency filtered (recent only). If all-eras appear → entities_vs lacks release_date_ts (rebuild index from new parquet).")

# H9 — gibberish → no_signal fallback (low confidence, not junk/empty)
resp, rt = ask("asdfghjkl qwerty zxcvb"); show("H9 gibberish", "asdfghjkl qwerty zxcvb", resp, rt)
print(f"   ↳ expect no_signal_fallback / low-confidence (path={rt.get('path_taken')}).")

# H10 — over-constrained → graceful relaxation (keeps vertical + negation, result_type=relaxed)
resp, rt = ask("cozy non-violent farming roguelike horror games from 2027"); show("H10 overconstrain", "…2027 over-constrained", resp, rt)
assert resp.get("error") is None, "H10 errored"

print("\nSMOKE BATTERY DONE — review H3 (0 horror ×2) and H5 (recency window) manually per REVIEW_CHECKLIST.")

# COMMAND ----------
# ===================== 5. FULL 50-QUERY ACCEPTANCE SET (vs the documented test results) =====================
# MAGIC %md
# MAGIC Fires the 50 queries from **Endpoint_1_Test_Set_and_Results** at the endpoint and captures the top-10
# MAGIC per query. Set the **`run_full_test`** widget to `1` to run (~3 min). It prints a readable per-query
# MAGIC block AND a compact JSON at the very bottom — paste that JSON back for a query-by-query comparison
# MAGIC against the documented results (overall 72.1%; franchise/recency/negation should match tightest).

# COMMAND ----------
if C["run_full_test"] != "1":
    print("run_full_test=0 → skipping the 50-query set (set the widget to 1 to run it).")
else:
    QUERIES = [
        ("Q1","A","open world RPG games"), ("Q2","A","a sci-fi action movie"),
        ("Q3","A","a crime drama tv series"), ("Q4","A","a true crime podcast"),
        ("Q5","A","a survival horror game"), ("Q6","A","a historical drama movie"),
        ("Q7","B","a cozy game"), ("Q8","B","a dark psychological thriller"),
        ("Q9","B","a feel-good comedy movie"), ("Q10","B","something relaxing to play"),
        ("Q11","B","an atmospheric horror movie"), ("Q12","B","an uplifting documentary"),
        ("Q13","C","games like Hades"), ("Q14","C","movies like Inception"),
        ("Q15","C","shows like Breaking Bad"), ("Q16","C","games like Stardew Valley"),
        ("Q17","C","movies like The Notebook"), ("Q18","C","shows like The Office"),
        ("Q19","D","Star Wars games"), ("Q20","D","Final Fantasy games"),
        ("Q21","D","Marvel movies"), ("Q22","D","Lego games"),
        ("Q23","D","Pokemon games"), ("Q24","D","Call of Duty games"),
        ("Q25","E","games from 2025"), ("Q26","E","recent sci-fi movies"),
        ("Q27","E","thrillers from the last 2 years"), ("Q28","E","new horror movies"),
        ("Q29","E","recent indie games"), ("Q30","E","tv shows from 2025"),
        ("Q31","F","recent co-op games but not horror"), ("Q32","F","female-led sci-fi movies"),
        ("Q33","F","open world rpg with crafting"), ("Q34","F","a 2025 comedy movie"),
        ("Q35","F","relaxing farming games"), ("Q36","F","dark fantasy games not turn-based"),
        ("Q37","G","a comedy but not romantic"), ("Q38","G","games but not horror"),
        ("Q39","G","movies but not violent"), ("Q40","G","an action game but nothing fantasy"),
        ("Q41","G","tv shows but not reality tv"), ("Q42","H","something to relax to"),
        ("Q43","H","something funny"), ("Q44","H","something scary"),
        ("Q45","H","something epic"), ("Q46","I","a warm hug of a movie"),
        ("Q47","I","something epic and sweeping"), ("Q48","I","a game to lose yourself in"),
        ("Q49","I","a mind-bending sci-fi"), ("Q50","I","a cozy mystery to unwind with"),
    ]
    import requests as _rq, json as _json, time as _time
    _TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    _URL = f"{HOST}/serving-endpoints/{C['endpoint']}/invocations"

    def _ask(q):
        body = {"dataframe_records": [{"user_id": "13", "query": q, "requesting_agent": "morgan", "top_k": 10}]}
        r = _rq.post(_URL, headers={"Authorization": f"Bearer {_TOKEN}", "Content-Type": "application/json"},
                     json=body, timeout=120)
        r.raise_for_status()
        inner = r.json()["predictions"][0]
        resp = inner.get("response"); resp = resp if isinstance(resp, dict) else _json.loads(resp)
        return resp

    _out = {}
    for _qid, _cat, _q in QUERIES:
        try:
            _resp = _ask(_q); _res = _resp.get("results") or []
            _rows = [{"name": it.get("name"), "vertical": it.get("vertical"), "id": it.get("entity_id")}
                     for it in _res[:10]]
            _out[_qid] = {"cat": _cat, "query": _q, "count": _resp.get("count"),
                          "error": _resp.get("error"), "top10": _rows}
            print(f"\n{_qid} [{_cat}] {_q!r}  count={_resp.get('count')} error={_resp.get('error')}")
            for _i, _it in enumerate(_rows, 1):
                print(f"  {_i:2d}. {str(_it['vertical']):7} {_it['name']}")
        except Exception as _e:
            _out[_qid] = {"cat": _cat, "query": _q, "error": f"{type(_e).__name__}: {_e}", "top10": []}
            print(f"\n{_qid} [{_cat}] {_q!r}  REQUEST FAILED: {type(_e).__name__}: {_e}")
        _time.sleep(0.3)

    print("\n\n========== COPY EVERYTHING BELOW THIS LINE AND PASTE BACK FOR COMPARISON ==========")
    print(_json.dumps({k: {"q": v["query"], "names": [r["name"] for r in v["top10"]]}
                       for k, v in _out.items()}, ensure_ascii=False))
