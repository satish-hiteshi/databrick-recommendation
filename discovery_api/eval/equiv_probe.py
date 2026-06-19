"""Equivalence + latency probe for the P5.1 substrate/weights refactor.

Captures user 12305's RANKED feed output (main feed + carousels: entity_id, moment_id, score) so
before/after can be diff'd to prove the parallelization changed only SPEED, not results. Two modes:
  --golden  : build with a deterministic MOCK substrate, write tests/_golden_12305.json (reproducible)
  --live    : build with the LIVE substrate, print ids+scores + substrate-call-count + wall-time
  --compare : build with the MOCK substrate, assert it matches the committed golden (the equivalence test)
"""

import json, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import timeutil
from discovery_api.src.data_access import CsvDataSource, SubstrateClient
from discovery_api.src.engine import DiscoveryEngine
from discovery_api.src.ranking import PopularityIndex
from discovery_api.src.candidates import RequestContext

NOW = timeutil.parse_ts("2026-06-18T00:00:00Z")
USER = 12305
GOLDEN = Path(__file__).resolve().parents[1] / "tests" / "_golden_12305.json"


class MockSub:
    """Deterministic mock — same per-seed results regardless of serial/parallel, so a match proves the
    assembly (order/dedupe) is preserved."""
    def __init__(self, ds): self.ds = ds; self.calls = 0
    def _s(self, v, anchors, k): return [e for e in self.ds._by_vertical.get(v, []) if e not in anchors][:k]
    def vector_neighbors(self, anchor_ids, exclude_ids=None, vertical=None, top_k=20):
        self.calls += 1
        v = vertical or "movie"; ex = set(exclude_ids or []) | set(anchor_ids)
        return [{"entity_id": e, "name": "", "vertical": v, "score": round(0.9 - i*0.002, 4)}
                for i, e in enumerate(self._s(v, ex, top_k))]
    def vector_retrieve(self, *a, **k): return []
    def graph_similar(self, entity_id, top_k=10, vertical=None):
        self.calls += 1
        v = vertical or "game"
        return [{"entity_id": e, "name": "", "vertical": v, "final_score": round(0.4 - i*0.01, 4)}
                for i, e in enumerate(self._s(v, {entity_id}, top_k))]
    def graph_score_within(self, ids): return {}


class Counting:
    def __init__(self, inner): self.inner, self.calls = inner, 0
    def vector_neighbors(self, *a, **k): self.calls += 1; return self.inner.vector_neighbors(*a, **k)
    def vector_retrieve(self, *a, **k): self.calls += 1; return self.inner.vector_retrieve(*a, **k)
    def graph_similar(self, *a, **k): self.calls += 1; return self.inner.graph_similar(*a, **k)
    def graph_score_within(self, *a, **k): self.calls += 1; return self.inner.graph_score_within(*a, **k)


def fingerprint(feed, top=30):
    return {
        "mode": feed.mode, "signal_strength": feed.signal_strength,
        "main_feed": [[i.entity_id, i.moment_id, round(i.score, 6)] for i in feed.main_feed[:top]],
        "carousels": [[c.carousel_id, c.reason_type.value,
                       [[it.entity_id, round(it.score, 6)] for it in c.items]] for c in feed.carousels],
    }


def build(substrate, ds, pop, limit=30):
    eng = DiscoveryEngine(ds, substrate=substrate, popularity=pop)
    t0 = time.time()
    feed = eng.build_feed(USER, RequestContext(now=NOW, limit=limit))
    return feed, (time.time() - t0) * 1000


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "--compare"
    ds = CsvDataSource().load()
    pop = PopularityIndex.from_data_source(ds)

    if mode == "--golden":
        feed, ms = build(MockSub(ds), ds, pop)
        GOLDEN.write_text(json.dumps(fingerprint(feed), indent=1))
        print(f"wrote golden {GOLDEN} ({ms:.0f}ms, {len(feed.main_feed)} main, {len(feed.carousels)} carousels)")
    elif mode == "--compare":
        feed, ms = build(MockSub(ds), ds, pop)
        fp = fingerprint(feed)
        golden = json.loads(GOLDEN.read_text())
        same = fp == golden
        print(f"compare vs golden: {'IDENTICAL' if same else 'DIFFERENT'} ({ms:.0f}ms)")
        if not same:
            print("  main_feed match:", fp["main_feed"] == golden["main_feed"])
            print("  carousels match:", fp["carousels"] == golden["carousels"])
        sys.exit(0 if same else 1)
    elif mode == "--live":
        ctr = Counting(SubstrateClient())
        feed, ms = build(ctr, ds, pop)
        fp = fingerprint(feed)
        print(json.dumps({"wall_ms": round(ms), "substrate_calls": ctr.calls,
                          "main_feed_top5": fp["main_feed"][:5],
                          "carousel_reason_types": [c[1] for c in fp["carousels"]]}, indent=1))
        Path("/tmp/equiv_live.json").write_text(json.dumps(fp))


if __name__ == "__main__":
    main()
