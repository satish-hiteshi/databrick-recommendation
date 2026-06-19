"""P5 API tests — FastAPI TestClient over the discovery-api envelope. Substrate is MOCKED (deterministic;
no live :8000/:8010). Cold-start = 7064, personalized = 12305.

    .venv/bin/python discovery_api/tests/test_p5_api.py
"""

import sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from fastapi.testclient import TestClient
from discovery_api.src import api
from discovery_api.src.engine import DiscoveryEngine

NOW = "2026-06-18T00:00:00Z"


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


def _setup():
    """Build the API state once, then inject the mock substrate (forces engine_full + substrate-up)."""
    st = api._state()
    mock = MockSub(st.ds)
    st.counter = api._CountingSubstrate(mock)
    st.engine_full = DiscoveryEngine(st.ds, substrate=st.counter, popularity=st.pop)
    st.substrate_up = lambda: True
    return TestClient(api.app)


print("building API state (loads CSVs once)…", flush=True)
CLIENT = _setup()


def _feed(**body):
    body.setdefault("now", NOW)
    r = CLIENT.post("/discovery/feed", json=body)
    assert r.status_code == 200, r.text
    return r.json()


def _carousel_types(env):
    return {c["reason_type"] for c in env["carousels"]}


def _main_eids(env):
    return [i["entity_id"] for i in env["main_feed"]["items"]]


# ── tests ─────────────────────────────────────────────────────────────────

def test_health():
    r = CLIENT.get("/discovery/health")
    assert r.status_code == 200
    j = r.json()
    assert j["status"] == "ok" and j["port"] == 8030 and j["data_source_mode"] == "csv"
    assert j["entities"] == 57443


def test_contract_and_envelope_shape():
    env = _feed(user_id=7064, limit=10)
    assert env["version"] == "1.0" and env["endpoint"] == "discovery-api"
    assert env["user_id"] == 7064 and isinstance(env["user_id"], int)
    for k in ("generated_at", "context", "request_echo", "main_feed", "carousels", "debug"):
        assert k in env
    assert set(env["context"]) >= {"mode", "followed_count", "signal_strength"}
    assert set(env["main_feed"]) >= {"items", "count", "next_offset"}
    assert env["debug"] is None                                   # debug defaults off
    it = env["main_feed"]["items"][0]
    assert it["type"] == "moment" and it["moment_id"] and it["entity_id"] and it["why_string"]


def test_cold_start():
    env = _feed(user_id=7064, limit=10)
    assert env["context"]["mode"] == "cold_start" and env["context"]["signal_strength"] == 0.0
    rt = _carousel_types(env)
    assert "trending" in rt and ("new_in_genre" in rt or "new_on_platform" in rt)
    assert "similar_to_followed" not in rt and "popular_with_fans_of" not in rt   # absent for cold-start
    assert all(i["why_string"] for i in env["main_feed"]["items"])
    assert all(c["reason_string"] for c in env["carousels"])


def test_personalized_present_and_differs():
    cold = _feed(user_id=7064, limit=10)
    pers = _feed(user_id=12305, limit=10)
    assert pers["context"]["mode"] == "personalized" and pers["context"]["followed_count"] > 10
    rt = _carousel_types(pers)
    assert "similar_to_followed" in rt and "popular_with_fans_of" in rt          # PRESENT for 12305
    # feed visibly differs from cold-start
    overlap = set(_main_eids(cold)) & set(_main_eids(pers))
    assert len(overlap) < len(_main_eids(cold)), "personalized feed should differ from cold-start"


def test_pagination():
    p1 = _feed(user_id=7064, limit=10, offset=0)
    p2 = _feed(user_id=7064, limit=10, offset=10)
    assert p1["main_feed"]["next_offset"] == 10
    ids1 = {i["moment_id"] for i in p1["main_feed"]["items"]}
    ids2 = {i["moment_id"] for i in p2["main_feed"]["items"]}
    assert ids1.isdisjoint(ids2) and len(ids1) == 10 and len(ids2) == 10


def test_exclusion_property_ids():
    base = _feed(user_id=7064, limit=20)
    victim_eid = base["main_feed"]["items"][0]["entity_id"]
    victim_pid = int(victim_eid.split(":")[-1])
    env = _feed(user_id=7064, limit=20, property_ids=[victim_pid])
    appear = {i["entity_id"] for i in env["main_feed"]["items"]}
    for c in env["carousels"]:
        appear |= {it["entity_id"] for it in c["items"]}
    assert victim_eid not in appear, "excluded property must never appear"
    assert env["request_echo"]["excluded_property_ids"] == 1


def test_seen_ids_suppressed():
    base = _feed(user_id=7064, limit=10)
    seen_mid = base["main_feed"]["items"][0]["moment_id"]
    env = _feed(user_id=7064, limit=10, seen_ids=[seen_mid])
    assert seen_mid not in {i["moment_id"] for i in env["main_feed"]["items"]}
    assert env["request_echo"]["seen_ids"] == 1


def test_sort_order_reweights():
    recent = _feed(user_id=7064, sort_order="recent", limit=10)
    popular = _feed(user_id=7064, sort_order="popular", limit=10)
    trending = _feed(user_id=7064, sort_order="trending", limit=10)
    # recency-dominant vs popularity-dominant must order the main feed differently
    assert _main_eids(recent)[:8] != _main_eids(popular)[:8], "recent vs popular must differ"
    assert recent["request_echo"]["sort_order"] == "recent"
    # debug shows the weights actually changed
    d_recent = _feed(user_id=7064, sort_order="recent", debug=True)["debug"]["weights_used"]
    d_pop = _feed(user_id=7064, sort_order="popular", debug=True)["debug"]["weights_used"]
    assert d_recent["W_RECENCY"] > d_pop["W_RECENCY"] and d_pop["W_POPULARITY"] > d_recent["W_POPULARITY"]


def test_debug_block():
    off = _feed(user_id=12305, limit=5)
    assert off["debug"] is None
    on = _feed(user_id=12305, limit=5, debug=True)
    d = on["debug"]
    assert d is not None
    for k in ("pools_built", "weights_used", "timing_ms", "substrate_calls", "substrate_reachable"):
        assert k in d
    item_dbg = on["main_feed"]["items"][0]["debug"]
    assert item_dbg["source_pool"] and "final_score" in item_dbg
    assert set(item_dbg["raw_signals"]) == {"semantic", "recency", "normalized_influence", "velocity", "suppression"}
    # also works as a query param
    qp = CLIENT.post("/discovery/feed?debug=true", json={"user_id": 7064, "now": NOW}).json()
    assert qp["debug"] is not None


def test_anonymous_cold_start():
    env = _feed(user_id=None, limit=5)
    assert env["user_id"] is None and env["context"]["mode"] == "cold_start"


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
