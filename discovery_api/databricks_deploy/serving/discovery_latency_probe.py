"""discovery_latency_probe.py — measure the DEPLOYED discovery endpoint's latency + smoke its output.

Mirror of the agent-recs latency_probe.py, but for Endpoint 2: hits discovery-api-staging's /invocations
directly, times each call (client wall-clock), and parses the v1.0 envelope so each scenario self-reports
mode / signal / feed-size / carousels / error. Per-stage breakdown is read from the envelope's debug block
if the endpoint surfaces one (TIMING_BREAKDOWN=1); otherwise wall-clock only.

Databricks notebook:
    import discovery_latency_probe as dp
    TOKEN = dbutils.notebook.entry_point.getDbutils().notebook().getContext().apiToken().get()
    dp.run(token=TOKEN, host="https://<staging-host>")              # serial p50/p90/p95 per scenario
    dp.run(token=TOKEN, host="...", concurrency=5)                  # parallel-callers test

Stdlib only (urllib) — nothing to install in the notebook.
"""

import json
import os
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ENDPOINT = "discovery-api-staging"

# representative scenarios — each exercises a different engine path (personalized / cold-start /
# pagination / date filter / exclusion). user_id 13 is a real game-follower on staging.
DEFAULT_SCENARIOS = [
    ("personalized (user 13)", {"user_id": 13, "limit": 20}),
    ("cold-start (anon)",       {"user_id": None, "limit": 20}),
    ("paginated (page 2)",      {"user_id": 13, "limit": 20, "offset": 20}),
    ("date-filtered (last_7d)", {"user_id": 13, "limit": 20, "time_window": "last_7d"}),
    ("with exclusions",         {"user_id": 13, "limit": 20, "property_ids": [15150, 105049]}),
]


def _percentile(xs, p):
    if not xs:
        return None
    xs = sorted(xs)
    k = (len(xs) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    return round(xs[lo] + (xs[hi] - xs[lo]) * (k - lo), 1)


def _call(url, token, payload, timeout=300):
    body = json.dumps({"dataframe_records": [payload]}).encode()
    req = urllib.request.Request(url, data=body, headers={
        "Authorization": f"Bearer {token}", "Content-Type": "application/json"})
    t0 = time.perf_counter()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload_out = json.loads(r.read())
        wall = (time.perf_counter() - t0) * 1000.0
        feed = payload_out["predictions"][0]
        feed = feed if isinstance(feed, dict) else json.loads(feed)
        ctx = feed.get("context", {}) or {}
        mf = feed.get("main_feed", {}) or {}
        dbg = feed.get("debug") or {}
        return {"wall_ms": wall, "mode": ctx.get("mode"), "signal": ctx.get("signal_strength"),
                "count": mf.get("count"), "carousels": len(feed.get("carousels", []) or []),
                "error": feed.get("error"),
                "breakdown": (dbg.get("timing_breakdown") if isinstance(dbg, dict) else None)}
    except Exception as e:
        return {"wall_ms": (time.perf_counter() - t0) * 1000.0, "mode": None, "signal": None,
                "count": None, "carousels": None, "error": f"{type(e).__name__}: {str(e)[:120]}",
                "breakdown": None}


def smoke(token=None, host=None, url=None):
    """One representative personalized call → print the envelope shape + verdict (for the smoke report)."""
    token = token or os.environ["DATABRICKS_TOKEN"]
    url = url or os.environ.get("DISCOVERY_URL") or \
        host.rstrip("/") + f"/serving-endpoints/{ENDPOINT}/invocations"
    s = _call(url, token, {"user_id": 13, "limit": 8, "debug": True})
    ok = s["error"] is None and s["mode"] is not None
    print(f"=== discovery smoke (user 13) ===\n  status      : {'UP ✓' if ok else 'FAIL ✗'}\n"
          f"  wall_ms     : {s['wall_ms']:.0f}\n  mode        : {s['mode']}  | signal: {s['signal']}\n"
          f"  main_feed   : {s['count']} items  | carousels: {s['carousels']}\n  error       : {s['error']}")
    return s


def run(token=None, host=None, url=None, scenarios=None, n=5, concurrency=1, warmup=True):
    token = token or os.environ["DATABRICKS_TOKEN"]
    url = url or os.environ.get("DISCOVERY_URL") or \
        host.rstrip("/") + f"/serving-endpoints/{ENDPOINT}/invocations"
    scenarios = scenarios or DEFAULT_SCENARIOS

    if warmup:
        w = _call(url, token, scenarios[0][1])               # exclude cold-start from the stats
        print(f"warmup: wall={w['wall_ms']:.0f}ms err={w['error']}")

    rows, all_walls = [], []
    for label, payload in scenarios:
        if concurrency > 1:
            with ThreadPoolExecutor(max_workers=concurrency) as ex:
                samples = list(ex.map(lambda _: _call(url, token, payload), range(n)))
        else:
            samples = [_call(url, token, payload) for _ in range(n)]
        walls = [s["wall_ms"] for s in samples if not s["error"]]
        all_walls += walls
        ok = next((s for s in samples if not s["error"]), samples[0])
        rows.append({"label": label, "mode": ok["mode"], "count": ok["count"],
                     "n_ok": len(walls), "errs": [s["error"] for s in samples if s["error"]],
                     "p50": _percentile(walls, 50), "p90": _percentile(walls, 90),
                     "p95": _percentile(walls, 95),
                     "bd": next((s["breakdown"] for s in samples if s["breakdown"]), None)})

    mode = f"concurrency={concurrency}" if concurrency > 1 else "serial"
    print(f"\n=== discovery latency: {len(scenarios)} scenarios × {n} ({mode}) ===")
    print(f"{'p50':>7}{'p90':>7}{'p95':>7}  {'mode':<13}{'feed':>5}  scenario")
    for r in rows:
        flag = "" if not r["errs"] else f"  ⚠{len(r['errs'])} err"
        print(f"{str(r['p50']):>7}{str(r['p90']):>7}{str(r['p95']):>7}  {str(r['mode']):<13}"
              f"{str(r['count']):>5}  {r['label']}{flag}")
        if r["bd"]:                                          # per-stage (only if the envelope surfaces it)
            print(f"{'breakdown →':>21}  {r['bd']}")

    print(f"\nOVERALL wall — p50 {_percentile(all_walls,50)} | p90 {_percentile(all_walls,90)} | "
          f"p95 {_percentile(all_walls,95)} | max {round(max(all_walls),1) if all_walls else None}  "
          f"(over 3s: {sum(w>3000 for w in all_walls)}/{len(all_walls)})")
    return rows


if __name__ == "__main__":
    run()
