"""timing.py — per-stage latency attribution for the collapsed router, surfaced IN the response.

Purpose: turn "we think it's Neo4j" into a measurement. When enabled, the engine seams record elapsed
ms per category (llm · vector · neo4j · engine); model.py resets per request and reads snapshot() into
`response.router.timing_breakdown`, so every call self-reports where its milliseconds went — no local
files, no log scraping (the prod-safe alternative to obs.py's local jsonl tracer).

GATING: off unless TIMING_BREAKDOWN=1, so normal serving pays nothing and carries no risk. Turn it on
only for measurement runs (set it in the endpoint env, redeploy, drive traffic with latency_probe.py).

ACCURACY MODEL (read before trusting the numbers):
  * A module-global accumulator (lock-protected). It is correct when the endpoint is driven ONE request
    at a time — which latency_probe.py does. Under CONCURRENT requests to the same replica the buckets
    can mingle across requests; that's the price of not threading a context object through the whole
    router, and why this is a measurement tool (off by default), not always-on production telemetry.
  * Values are AGGREGATE work-time summed across the parallel multivertical sub-plans
    (assembler._parallel_assemble fans out across threads, all adding here). So a category CAN exceed
    wall-clock timing_ms when verticals run concurrently — that is intended: it shows total work per
    engine, not wall time. Compare the RATIO of neo4j vs vector to attribute latency; compare against
    timing_ms (wall) to see how much parallelism is helping.
"""

import os
import threading
import time
from contextlib import contextmanager

_ENABLED = os.getenv("TIMING_BREAKDOWN", "0") == "1"
_LOCK = threading.Lock()
_MS = {}      # category -> summed milliseconds
_N = {}       # category -> call count


def enabled() -> bool:
    return _ENABLED


def reset():
    """Clear the accumulator — call once at the start of each request (model.py.predict)."""
    if not _ENABLED:
        return
    with _LOCK:
        _MS.clear()
        _N.clear()


def add(category: str, ms: float):
    if not _ENABLED:
        return
    with _LOCK:
        _MS[category] = _MS.get(category, 0.0) + ms
        _N[category] = _N.get(category, 0) + 1


@contextmanager
def span(category: str):
    """Time a block and attribute it to `category`. No-op (zero overhead) when disabled."""
    if not _ENABLED:
        yield
        return
    t0 = time.perf_counter()
    try:
        yield
    finally:
        add(category, (time.perf_counter() - t0) * 1000.0)


def snapshot():
    """{<cat>_ms, <cat>_calls, work_ms} for the response, or None when disabled."""
    if not _ENABLED:
        return None
    with _LOCK:
        out = {f"{k}_ms": round(v, 1) for k, v in _MS.items()}
        out.update({f"{k}_calls": n for k, n in _N.items()})
        out["work_ms"] = round(sum(_MS.values()), 1)   # total engine work (sums parallel sub-plans)
        return out
