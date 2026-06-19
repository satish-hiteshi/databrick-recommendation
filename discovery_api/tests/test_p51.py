"""P5.1 tests — ranking EQUIVALENCE after the substrate-parallelization refactor + per-request weights
with NO global state (concurrency-safe). Substrate MOCKED (deterministic). Self-running:

    .venv/bin/python discovery_api/tests/test_p51.py
"""

import json, sys
from pathlib import Path
from threading import Thread

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import timeutil
from discovery_api.src.data_access import CsvDataSource
from discovery_api.src.engine import DiscoveryEngine
from discovery_api.src.ranking import PopularityIndex, ScoringWeights, ScoringContext, score_candidate
from discovery_api.src.candidates import RequestContext, Candidate
from discovery_api.src.feed import build_profile
from discovery_api.src.api import WEIGHT_PRESETS

NOW = timeutil.parse_ts("2026-06-18T00:00:00Z")
GOLDEN = Path(__file__).resolve().parent / "_golden_12305.json"

print("loading CsvDataSource…", flush=True)
DS = CsvDataSource().load()
POP = PopularityIndex.from_data_source(DS)


class MockSub:
    def __init__(self, ds): self.ds = ds
    def _s(self, v, anchors, k): return [e for e in self.ds._by_vertical.get(v, []) if e not in anchors][:k]
    def vector_neighbors(self, anchor_ids, exclude_ids=None, vertical=None, top_k=20):
        v = vertical or "movie"; ex = set(exclude_ids or []) | set(anchor_ids)
        return [{"entity_id": e, "name": "", "vertical": v, "score": round(0.9 - i*0.002, 4)}
                for i, e in enumerate(self._s(v, ex, top_k))]
    def vector_retrieve(self, *a, **k): return []
    def graph_similar(self, entity_id, top_k=10, vertical=None):
        v = vertical or "game"
        return [{"entity_id": e, "name": "", "vertical": v, "final_score": round(0.4 - i*0.01, 4)}
                for i, e in enumerate(self._s(v, {entity_id}, top_k))]
    def graph_score_within(self, ids): return {}

MOCK = MockSub(DS)


def _fingerprint(feed, top=30):
    return {"mode": feed.mode, "signal_strength": feed.signal_strength,
            "main_feed": [[i.entity_id, i.moment_id, round(i.score, 6)] for i in feed.main_feed[:top]],
            "carousels": [[c.carousel_id, c.reason_type.value,
                           [[it.entity_id, round(it.score, 6)] for it in c.items]] for c in feed.carousels]}


def _build(uid, weights=None, limit=30):
    eng = DiscoveryEngine(DS, substrate=MOCK, popularity=POP)
    return eng.build_feed(uid, RequestContext(now=NOW, limit=limit), weights=weights)


# ── PROBLEM 1: parallelization preserves the EXACT ranked output ─────────
def test_equivalence_vs_golden():
    """12305's full feed (with the parallelized providers) must match the pre-change golden byte-for-byte."""
    fp = _fingerprint(_build(12305))
    golden = json.loads(GOLDEN.read_text())
    assert fp["main_feed"] == golden["main_feed"], "main feed ranking changed!"
    assert fp["carousels"] == golden["carousels"], "carousel ranking changed!"
    assert fp == golden


# ── PROBLEM 2: per-request weights, identical scores, NO cross-contamination ──
def test_weight_presets_match_p5_numbers():
    t, r, p = WEIGHT_PRESETS["trending"], WEIGHT_PRESETS["recent"], WEIGHT_PRESETS["popular"]
    assert (t.w_popularity, t.w_recency, t.w_velocity) == (1.0, 1.0, 0.5)
    assert (r.w_popularity, r.w_recency, r.w_velocity) == (0.3, 3.0, 0.2)
    assert (p.w_popularity, p.w_recency, p.w_velocity) == (3.0, 0.3, 0.5)


def test_scores_identical_to_config_default():
    """A candidate scored with from_config() weights == the old config-based math (default unchanged)."""
    ctx = RequestContext(now=NOW)
    sctx_default = ScoringContext(DS, POP, ctx)                       # weights=None → from_config
    sctx_explicit = ScoringContext(DS, POP, ctx, ScoringWeights.from_config())
    prof = build_profile(7064, DS)
    eid = DS._by_vertical["movie"][0]
    c = Candidate("trending_global", entity_id=eid, raw_signals={"recency": 0.5})
    assert score_candidate(c, prof, sctx_default).final == score_candidate(c, prof, sctx_explicit).final


def test_concurrent_sort_orders_no_contamination():
    """On ONE SHARED engine (the API singleton scenario), two builds with DIFFERENT weights run
    concurrently must each equal their SEQUENTIAL result — proves no global mutable weight state / lock."""
    eng = DiscoveryEngine(DS, substrate=MOCK, popularity=POP)
    def fp(key):
        return _fingerprint(eng.build_feed(7064, RequestContext(now=NOW, limit=30), weights=WEIGHT_PRESETS[key]))
    seq_recent, seq_popular = fp("recent"), fp("popular")
    assert seq_recent["main_feed"] != seq_popular["main_feed"], "presets should order differently (sanity)"

    out = {}
    def run(key): out[key] = fp(key)
    for _ in range(3):                                                # repeat to shake out any race
        out.clear()
        ts = [Thread(target=run, args=("recent",)), Thread(target=run, args=("popular",))]
        for t in ts: t.start()
        for t in ts: t.join()
        assert out["recent"] == seq_recent, "concurrent 'recent' got contaminated"
        assert out["popular"] == seq_popular, "concurrent 'popular' got contaminated"


def _run():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    npass = nfail = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); npass += 1
        except Exception as e:
            import traceback; print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}"); traceback.print_exc(); nfail += 1
    print(f"\n{npass} passed, {nfail} failed (of {len(tests)})")
    return nfail


if __name__ == "__main__":
    sys.exit(1 if _run() else 0)
