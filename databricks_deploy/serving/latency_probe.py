"""latency_probe.py — measure the DEPLOYED endpoint's latency (black-box) + read its per-stage breakdown.

Hits parrot-api-hitashi-dev's /invocations directly — what feeds-api experiences minus its own network
leg — times each call, and (when the endpoint runs with TIMING_BREAKDOWN=1) reports where the time went
(neo4j vs vector vs llm) from response.router.timing_breakdown.

Databricks notebook:
    import latency_probe as lp
    TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    lp.run(token=TOKEN, host="https://dbc-f79d5cae-0d05.cloud.databricks.com")      # serial p50/p90/p95
    lp.run(token=TOKEN, host="...", concurrency=5)                                   # parallel-callers test
Script: set PARROT_URL + DATABRICKS_TOKEN in env, then `python latency_probe.py`.

Uses only the stdlib (urllib) so it needs nothing installed in the notebook.
"""

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINT = "parrot-api-hitashi-dev"

# one representative query per router path — keeps a run fast (each call hits Qwen + the LLM live)
DEFAULT_QUERIES = [
    "cozy relaxing games like Stardew Valley",                        # SEED_VECTOR
    "a long narrative-driven single-player RPG with a strong lead",   # VECTOR_CONSTRAIN__GRAPH_RERANK
    "horror games that aren't jump-scare heavy",                      # GRAPH_…NEGATE (graph-heavy)
    "recommend something cozy to watch tonight",                      # MULTIVERTICAL (vector fan-out)
    "thought-provoking sci-fi across games, films, series, podcasts", # MULTIVERTICAL[4] (broadest)
    "true crime podcasts similar to Serial",                          # SEED_VECTOR (podcast)
]


def _percentile(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def _call(url, token, query, top_k=10, timeout=120):
    body = json.dumps({"dataframe_records": [
        {"user_id": "probe", "query": query, "requesting_agent": "morgan", "top_k": top_k}]}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.loads(r.read())
        wall = (time.perf_counter() - t0) * 1000.0
        inner = payload["predictions"][0]["response"]
        inner = inner if isinstance(inner, dict) else json.loads(inner)
        rt = inner.get("router", {}) or {}
        return {"wall_ms": wall, "timing_ms": rt.get("timing_ms"), "path": rt.get("path_taken"),
                "count": inner.get("count"), "error": inner.get("error"),
                "breakdown": rt.get("timing_breakdown")}
    except Exception as e:
        return {"wall_ms": (time.perf_counter() - t0) * 1000.0, "timing_ms": None, "path": None,
                "count": None, "error": f"{type(e).__name__}: {str(e)[:120]}", "breakdown": None}


def run(token=None, host=None, url=None, queries=None, n=5, top_k=10, concurrency=1, warmup=True):
    token = token or os.environ["DATABRICKS_TOKEN"]
    url = url or os.environ.get("PARROT_URL") or \
        host.rstrip("/") + f"/serving-endpoints/{ENDPOINT}/invocations"
    queries = queries or DEFAULT_QUERIES

    if warmup:
        w = _call(url, token, queries[0], top_k)        # exclude cold-start from the stats
        print(f"warmup: wall={w['wall_ms']:.0f}ms err={w['error']}")

    def one(q):
        return _call(url, token, q, top_k)

    rows, all_walls = [], []
    for q in queries:
        if concurrency > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as ex:
                samples = list(ex.map(lambda _: one(q), range(n)))
        else:
            samples = [one(q) for _ in range(n)]
        walls = [s["wall_ms"] for s in samples if not s["error"]]
        rtms = [s["timing_ms"] for s in samples if s["timing_ms"] is not None]
        bd = next((s["breakdown"] for s in samples if s["breakdown"]), None)
        all_walls += walls
        rows.append({"q": q, "path": next((s["path"] for s in samples if s["path"]), "?"),
                     "n_ok": len(walls), "errs": [s["error"] for s in samples if s["error"]],
                     "wall_p50": _percentile(walls, 50), "wall_p95": _percentile(walls, 95),
                     "rt_p50": _percentile(rtms, 50), "rt_p95": _percentile(rtms, 95), "bd": bd})

    mode = f"concurrency={concurrency}" if concurrency > 1 else "serial"
    print(f"\n=== latency: {len(queries)} queries × {n} ({mode}) ===")
    print(f"{'wall_p50':>9}{'wall_p95':>9}{'rt_p50':>8}{'rt_p95':>8}  {'path':<34} query")
    for r in rows:
        flag = "" if not r["errs"] else f"  ⚠{len(r['errs'])} err"
        print(f"{str(r['wall_p50']):>9}{str(r['wall_p95']):>9}{str(r['rt_p50']):>8}{str(r['rt_p95']):>8}  "
              f"{str(r['path']):<34} {r['q'][:36]}{flag}")
        if r["bd"]:                                     # per-stage attribution (TIMING_BREAKDOWN=1)
            parts = [f"{k}={r['bd'][k]}" for k in ("llm_ms", "vector_ms", "nlu_ms", "embed_ms", "vs_ms",
                                                   "neo4j_ms", "engine_ms", "work_ms") if k in r["bd"]]
            print(f"{'breakdown →':>34}  {'  '.join(parts)}")

    print(f"\nOVERALL wall — p50 {_percentile(all_walls,50)} | p90 {_percentile(all_walls,90)} | "
          f"p95 {_percentile(all_walls,95)} | max {round(max(all_walls),1) if all_walls else None}  "
          f"(over 3s: {sum(w>3000 for w in all_walls)}/{len(all_walls)})")
    return rows


def run_by_type(token=None, host=None, url=None, by_type=None, n=1, top_k=10, warmup=True):
    """Run a {type: [queries]} bank and report PER-TYPE latency + the AVERAGE per-stage breakdown.

    n=1 → each query once (50 queries already give 50 samples per type, enough for p50/p95). Every call
    hits Voyage + the LLM live, so a full 7×50 pass is ~350 calls (~12 min serial) — start with n=1, and
    pass a sliced bank (e.g. {k: v[:15] for k, v in QUERIES_BY_TYPE.items()}) for a quick look.
    Reads the per-stage split from response.router.timing_breakdown (needs TIMING_BREAKDOWN=1 deployed).
    """
    token = token or os.environ["DATABRICKS_TOKEN"]
    url = url or os.environ.get("PARROT_URL") or \
        host.rstrip("/") + f"/serving-endpoints/{ENDPOINT}/invocations"
    if by_type is None:
        from latency_queries import QUERIES_BY_TYPE as by_type

    if warmup:
        first = next(iter(by_type.values()))[0]
        w = _call(url, token, first, top_k)
        print(f"warmup: wall={w['wall_ms']:.0f}ms err={w['error']}")

    print(f"\n=== per-type latency (n={n} each, {sum(len(v) for v in by_type.values())} queries total) ===")
    print(f"{'type':<18}{'n_ok':>5}{'wall_p50':>9}{'wall_p95':>9}{'rt_p50':>8}{'rt_p95':>8}"
          f"   avg breakdown (ms)            top path")
    summary = []
    for typ, qs in by_type.items():
        walls, rtms, bds, paths = [], [], [], {}
        for q in qs:
            for _ in range(n):
                s = _call(url, token, q, top_k)
                if s["error"]:
                    continue
                walls.append(s["wall_ms"])
                if s["timing_ms"] is not None:
                    rtms.append(s["timing_ms"])
                if s["breakdown"]:
                    bds.append(s["breakdown"])
                paths[s["path"]] = paths.get(s["path"], 0) + 1
        avg = {}
        for k in ("llm_ms", "vector_ms", "nlu_ms", "embed_ms", "vs_ms", "neo4j_ms", "engine_ms"):
            vals = [b[k] for b in bds if b.get(k) is not None]
            if vals:
                avg[k] = round(sum(vals) / len(vals))
        bdstr = "  ".join(f"{k.replace('_ms', '')}={v}" for k, v in avg.items()) or "(no breakdown)"
        top_path = max(paths, key=paths.get) if paths else "?"
        print(f"{typ:<18}{len(walls):>5}{str(_percentile(walls, 50)):>9}{str(_percentile(walls, 95)):>9}"
              f"{str(_percentile(rtms, 50)):>8}{str(_percentile(rtms, 95)):>8}   {bdstr:<28} {str(top_path)[:34]}")
        summary.append({"type": typ, "n_ok": len(walls), "wall_p50": _percentile(walls, 50),
                        "wall_p95": _percentile(walls, 95), "rt_p50": _percentile(rtms, 50),
                        "rt_p95": _percentile(rtms, 95), "avg_breakdown": avg, "top_path": top_path,
                        "paths": paths})
    return summary


if __name__ == "__main__":
    run()
