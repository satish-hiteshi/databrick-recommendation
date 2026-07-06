# Databricks notebook source
# MAGIC %md
# MAGIC # E8 — Onboarding Boost smoke test
# MAGIC Exercises the deployed `onboarding-boost` endpoint end-to-end: a **boost** from a seed set
# MAGIC (gap-fill + deepen), the UC8 acceptance checks (report §9), and the **stateless confirm / skip**.
# MAGIC
# MAGIC Set `seeds` to EXTERNAL property_ids that exist in the parquet, spanning **1–2 verticals** so the
# MAGIC other verticals are gaps to fill and the covered one(s) get deepened. Point `endpoint` at your env
# MAGIC (`onboarding-boost-dev` / `-staging`).

# COMMAND ----------
dbutils.widgets.text("endpoint", "onboarding-boost-staging", "Serving endpoint name")
dbutils.widgets.text("seeds", "1877,52189", "Seed follows — EXTERNAL property_ids (comma-sep; default = 2 games)")
EP    = dbutils.widgets.get("endpoint")
SEEDS = [int(x) for x in dbutils.widgets.get("seeds").replace(" ", "").split(",") if x.strip().lstrip("-").isdigit()]

import requests, time
HOST  = "https://" + spark.conf.get("spark.databricks.workspaceUrl")
TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
HDR   = {"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"}
print(f"endpoint: {EP} | seeds: {SEEDS}")

def call(rec):
    r = requests.post(f"{HOST}/serving-endpoints/{EP}/invocations", headers=HDR,
                      json={"dataframe_records": [rec]}, timeout=300)
    r.raise_for_status()
    return r.json()["predictions"][0]

# COMMAND ----------
# ===================== 1. BOOST — gap-fill + deepen from the seed set =====================
t0 = time.time()
pred = call({"op": "boost", "session_id": "smoke", "user_id": 1,
             "followed_property_ids": SEEDS, "id_space": "external", "debug": True})
dt = (time.time() - t0) * 1000
groups  = pred.get("boost_payload", []) or []
ctx     = pred.get("context", {}) or {}
offered = pred.get("offered_property_ids", []) or []
props   = [p for g in groups for p in g.get("properties", [])]

print(f"seeds={SEEDS} | error={pred.get('error') or pred.get('detail')} | {dt:.0f}ms")
print(f"context: {ctx}")
print(f"payload: {len(groups)} vertical group(s), {len(props)} picks, {len(offered)} offered\n")
for g in groups:
    ps = g.get("properties", [])
    print(f"  ── {str(g.get('vertical')):8} [{g.get('kind') or g.get('reason') or '?'}]  {len(ps)} ──")
    for p in ps[:6]:
        print(f"     {str(p.get('name'))[:34]:34} score={p.get('score')} "
              f"pop={p.get('popularity_score')} rich={p.get('moment_richness_score')} "
              f"moments={p.get('moment_count')} {p.get('badge') or ''}")

# COMMAND ----------
# ===================== 2. ACCEPTANCE CHECKS (UC8 report §9) =====================
seed_set = set(SEEDS)
def _m(p): return p.get("moment_count", p.get("moments")) or 0
checks = {
    "returned a non-empty payload":       len(props) > 0,
    "never suggests an already-followed": all(p.get("property_id") not in seed_set for p in props),
    "every pick is active (moment > 0)":  all(_m(p) > 0 for p in props),
    "response under 3s":                  dt < 3000,
    "no error":                           not pred.get("error"),
}
print("acceptance checks:")
for k, ok in checks.items():
    print(f"  {'✅' if ok else '❌'} {k}")

# COMMAND ----------
# ===================== 3. STATELESS CONFIRM + SKIP =====================
conf = call({"op": "confirm", "session_id": "smoke", "user_id": 1, "action": "confirm",
             "followed_property_ids": offered, "id_space": "external"})
skip = call({"op": "confirm", "session_id": "smoke", "user_id": 1, "action": "skip"})
print(f"confirm: written={conf.get('written')} err={conf.get('error')}")
print(f"skip:    written={skip.get('written')} (expect 0)")

assert not pred.get("error") and all(checks.values()), f"E8 smoke failed: {pred}"
print("\nSMOKE OK ✓  (if 0 picks: set seeds to external ids present in the parquet, spanning 1–2 verticals)")
