# 05 — Deploying to Databricks

How Endpoint 2 maps onto the deployment pattern already used for Endpoint 1, what is the same, what differs,
and the items that **must be confirmed with the platform team (Satish / Alex)** rather than guessed.

> **Precedent:** Endpoint 1's deployment approach is documented in the repo at
> [`docs/03_DATABRICKS_DEPLOYMENT.md`](../../docs/03_DATABRICKS_DEPLOYMENT.md) (and its sibling docs 00–02 +
> `docs/DEPLOYMENT_CHECKLIST.md`). Read that first — Endpoint 2 is **another service on the same substrate**,
> so most of it applies unchanged.

---

## 1. The precedent (Endpoint 1), in one paragraph

Per `docs/03_DATABRICKS_DEPLOYMENT.md`: the PoC is hosted as **FastAPI/uvicorn services** with the **LLM on a
Databricks Foundation Model serving endpoint** (Llama 3.3 70B, OpenAI-compatible, via `DATABRICKS_TOKEN` +
`DATABRICKS_LLM_ENDPOINT`). Two stages are described — **Stage A "lift the PoC"** (host the code as-is — the
three APIs as containers/VM, the DBs as Docker or managed, the LLM on Databricks; **no code changes, only
config**), and **Stage B "production target"** (swap to managed **Databricks Vector Search** + **Neo4j
AuraDS** behind a single serving contract). Secrets come from a secret store injected as env vars; **nothing
is written to the Databricks workspace** by the running services beyond read-only model-inference calls.

---

## 2. How Endpoint 2 fits — same substrate, one more service

Endpoint 2 is the **discovery-api** — **a fourth uvicorn service** (`:8030`) alongside Endpoint 1's router
(`:8020`), vector (`:8000`), and graph (`:8010`). It deploys with the **same Stage-A pattern**: run the
service, point it at the substrate, inject config via env vars.

**What's the SAME as Endpoint 1:**
- It's a FastAPI app run by uvicorn; containerize it like the others (`docs/03` §3 Stage A step 4).
- It uses the **same secret-management** approach (env vars from a secret store; `os.getenv` everywhere).
- It can use the **same Databricks Foundation Model endpoint** — but **only optionally** (§4).

**What's DIFFERENT from Endpoint 1 (important):**
| | Endpoint 1 (router) | Endpoint 2 (discovery-api) |
|---|---|---|
| LLM dependency | **Hard** — every query makes a Databricks LLM call (intent extraction) | **Optional** — only if `V2_STRING_COMPOSER=llm`; default `deterministic` needs **no LLM** |
| New DB load | The deployment includes **loading** Neo4j + the vector index | **None** — reuses the already-loaded substrate read-only (doc 03) |
| Primary data | enrichment + substrate | **tabular behavioural data** (entities/moments/follows/reactions/gds) — **CSV today, live = stub** (doc 02) |
| Caller contract | `POST /router/search {query}` (NL) | `POST /discovery/feed {user_id, …}` (structured, no NL) |

So Endpoint 2's **hard runtime dependencies** are the **vector service + graph service** (read-only) and its
**tabular data source** — **not** the Databricks LLM.

---

## 3. Packaging & run specifics

- **Run command:** `uvicorn discovery_api.src.api:app --host 0.0.0.0 --port 8030`, executed **from the repo
  root** so the `discovery_api.src` package resolves (the code uses **relative imports** — it must run as a
  package module, NOT `--app-dir`, NOT from inside `discovery_api/`). See doc 01 §3.
- **Image contents:** Python 3.10 + the repo venv deps (`fastapi, uvicorn, httpx, pydantic, python-dotenv,
  numpy`) + the `discovery_api/` package on `PYTHONPATH` (repo root). Light image; no DB drivers required for
  the CSV mode.
- **Data in the image (CSV mode):** while `DISCOVERY_DATA_SOURCE=csv`, the **dev CSVs** in
  `discovery_api/data/dev/` must be **present** (baked into the image or mounted as a volume). They are
  git-ignored, so they are **not** in the cloned repo — supply them out of band. *(For a real deployment you
  implement `LiveDataSource` instead and stop shipping CSVs — doc 02.)*
- **Config via env vars:** set the doc-04 MUST-SET vars (`VECTOR_API_URL`, `GRAPH_API_URL`,
  `DISCOVERY_DEFAULT_ENGINE=v2`, `DISCOVERY_NOW_ISO=""`, `DISCOVERY_DATA_SOURCE`).
- **Restart on code change; set restart policy** (mirror `--restart unless-stopped`). Caches are in-process.
- **Health/readiness probe:** `GET /discovery/health` (doc 01 §6).

### Connectivity the deployed endpoint needs
- **Outbound to the vector service** (`VECTOR_API_URL`) and **graph service** (`GRAPH_API_URL`) — the only
  hard network dependencies. Those services in turn reach Neo4j, Postgres, and Voyage (their concern).
- **Outbound to the Databricks LLM endpoint** — **only if** `V2_STRING_COMPOSER=llm` (else none).
- **Outbound to the live data store** (Lakehouse/Postgres) — **only once `LiveDataSource` is implemented.**

---

## 4. Service principal, permissions, CICD

- **Service principal / token:** if the optional LLM composer is enabled, use a **service-principal**
  `DATABRICKS_TOKEN` scoped to the serving endpoint (same as Endpoint 1, `docs/03` §4). The live data binding
  (once built) will need its own **read** credentials to the Lakehouse/Silver tables — scope to read-only.
- **CICD:** **in-progress / not yet established for this repo** — treat CICD wiring (build image, run tests,
  deploy) as an open task to set up with the platform team. The test/eval suites in doc 06 are the natural
  CI gate.
- **Permissions:** the discovery-api needs **read** access to the substrate services and (later) the live
  data; it needs **no write** permission to Neo4j, the vector index, or any DB (doc 03 confirms it writes
  nothing).

---

## 5. Items to CONFIRM WITH THE PLATFORM TEAM (Satish / Alex) — not inferable from the repo

The repo hosts the PoC as **uvicorn FastAPI services** (the Endpoint-1 precedent does **not** wrap them as
MLflow/Model-Serving models). The following Databricks-specific choices are **not determined by the code** and
must be decided with the platform team — **do not assume**:

1. **Hosting form on Databricks** — run the discovery-api as a **container service / VM / cluster job**, as a
   **Databricks App**, or wrapped as a **Model Serving custom endpoint**? The repo's pattern is "host the
   FastAPI service"; which Databricks primitive that maps to is **to confirm**.
2. **The live data binding** — exactly how `LiveDataSource` reads production data (JDBC to Postgres? Spark/Delta
   over Lakehouse Silver tables? a serving-layer API?) and the connection/secret mechanism — **to confirm**
   (this is also the doc-02 go-live gap).
3. **Networking** between the discovery-api and the substrate (`:8000`/`:8010`) in the Databricks environment
   (same VPC / private link / service URLs) — **to confirm**.
4. **Secret injection** mechanism (Databricks Secrets scope vs cloud secret manager) and which identity the
   service runs as — **to confirm**.
5. Whether the production target adopts **Stage B** (managed Vector Search + AuraDS) for the substrate — a
   **client-architecture decision** (`docs/03` §3) that Endpoint 2 is agnostic to, as long as the `:8000`/`:8010`
   read contracts are preserved.

> Where this doc cannot confirm a Databricks-specific detail from the repository, it is marked **"to confirm"**
> above rather than invented.
