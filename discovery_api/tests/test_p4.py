"""P4 unit tests — scorer, assembler, why_strings. Self-running (pytest absent):

    .venv/bin/python discovery_api/tests/test_p4.py

Real dev CSVs; substrate MOCKED. Cold-start = 7064, personalized = 12305 (per P3 fixture reality).
"""

import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import config, timeutil
from discovery_api.src.data_access import CsvDataSource
from discovery_api.src.ranking import PopularityIndex
from discovery_api.src.ranking.scorer import ScoringContext, score_candidate, score_candidates, personal_weight
from discovery_api.src.feed import build_profile
from discovery_api.src.feed.feed_models import ReasonType
from discovery_api.src.candidates import RequestContext, Candidate
from discovery_api.src.engine import DiscoveryEngine
from discovery_api.src.why import why_string, reason_string

NOW = timeutil.parse_ts("2026-06-18T00:00:00Z")
print("loading CsvDataSource…", flush=True)
DS = CsvDataSource().load()
POP = PopularityIndex.from_data_source(DS)
COLD, PERS = 7064, 12305


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


def ctx(**k): k.setdefault("now", NOW); return RequestContext(**k)
def cand(pool, eid=None, mid=None, **sig):
    e = DS.get_entity(eid) if eid else None
    return Candidate(source_pool=pool, entity_id=eid, moment_id=mid,
                     vertical=(e.vertical if e else None),
                     property_id=DS.entity_id_to_property_id(eid) if eid else None, raw_signals=sig)


# ── SCORER ───────────────────────────────────────────────────────────────

def test_personal_weight_interpolation():
    assert personal_weight(0.0) == 0.0                      # cold-start → 0 personal
    assert personal_weight(1.0) == config.PERSONAL_WEIGHT_MAX
    assert 0 < personal_weight(0.5) < config.PERSONAL_WEIGHT_MAX


def test_cold_start_is_100pct_global():
    # a cold-start profile: pw=0 → semantic ignored; same item scores identically with/without semantic
    cold = build_profile(COLD, DS)
    sctx = ScoringContext(DS, POP, ctx())
    eid = DS._by_vertical["movie"][0]
    c_no_sem = cand("trending_global", eid=eid, recency=0.5)
    c_sem = cand("similar_to_followed", eid=eid, recency=0.5, semantic=0.9)
    b1 = score_candidate(c_no_sem, cold, sctx)
    b2 = score_candidate(c_sem, cold, sctx)
    assert b1.personal_weight == 0.0
    assert abs(b1.final - b2.final) < 1e-9, "cold-start must ignore semantic (100% global)"


def test_personalized_uses_semantic():
    pers = build_profile(PERS, DS)
    assert pers.signal_strength == 1.0
    sctx = ScoringContext(DS, POP, ctx())
    eid = DS._by_vertical["movie"][0]
    low = score_candidate(cand("similar_to_followed", eid=eid, recency=0.2, semantic=0.0), pers, sctx)
    high = score_candidate(cand("similar_to_followed", eid=eid, recency=0.2, semantic=0.95), pers, sctx)
    assert high.personal_weight == config.PERSONAL_WEIGHT_MAX > 0
    assert high.final > low.final, "personalized: higher semantic must raise the score"
    assert high.dominant == "semantic"


def test_velocity_confidence_near_zero_on_dev():
    sctx = ScoringContext(DS, POP, ctx())
    # dev has ~tens of events → confidence well below 1; velocity contributes ~nothing
    assert sctx.velocity_confidence < 0.5, f"velocity confidence {sctx.velocity_confidence} too high for dev"
    # the velocity term for any entity is tiny
    eid = DS._by_vertical["movie"][0]
    assert sctx.velocity_cw(eid) < 0.2


def test_ties_broken_by_recency():
    # two high-influence (clipped-ceiling) movies with DIFFERENT recency must get different finals
    cold = build_profile(COLD, DS)
    sctx = ScoringContext(DS, POP, ctx())
    movies = sorted(DS._by_vertical["movie"], key=lambda e: POP.normalized_influence(e) or 0, reverse=True)
    a, b = movies[0], movies[1]
    assert abs((POP.normalized_influence(a) or 0) - (POP.normalized_influence(b) or 0)) < 1e-9  # tie at ceiling
    fa = score_candidate(cand("trending_global", eid=a, recency=0.9), cold, sctx).final
    fb = score_candidate(cand("trending_global", eid=b, recency=0.2), cold, sctx).final
    assert fa > fb, "recency must break the influence tie"


# ── ASSEMBLER ──────────────────────────────────────────────────────────────

def _build(uid, **ctxkw):
    return DiscoveryEngine(data_source=DS, substrate=MOCK, popularity=POP).build_feed(uid, ctx(**ctxkw))


def test_assembler_shape_and_pagination():
    feed = _build(COLD, limit=10)
    assert feed.mode == "cold_start" and len(feed.main_feed) == 10
    assert feed.pagination.next_offset == 10 and feed.pagination.pool_total > 10
    # page 2 is disjoint from page 1
    feed2 = _build(COLD, limit=10, offset=10)
    assert {i.moment_id for i in feed.main_feed}.isdisjoint({i.moment_id for i in feed2.main_feed})
    # every main-feed item has the required fields
    for i in feed.main_feed:
        assert i.type == "moment" and i.moment_id and i.entity_id and i.why_string


def test_assembler_exclusions_and_cap():
    pers = build_profile(PERS, DS)
    followed = set(pers.followed_entity_ids)
    feed = _build(PERS, limit=20)
    all_eids = {i.entity_id for i in feed.main_feed} | {it.entity_id for c in feed.carousels for it in c.items}
    assert all_eids.isdisjoint(followed), "followed entities must never appear"
    cap = Counter(i.entity_id for i in feed.main_feed)
    assert (max(cap.values()) if cap else 0) <= config.MOMENT_CAP_PER_PROPERTY


def test_only_nonempty_personalized_carousels():
    cold = _build(COLD, limit=10)
    pers = _build(PERS, limit=10)
    cold_rt = {c.reason_type for c in cold.carousels}
    pers_rt = {c.reason_type for c in pers.carousels}
    # personalized-only carousels appear for 12305, not for 7064
    assert ReasonType.similar_to_followed not in cold_rt
    assert ReasonType.similar_to_followed in pers_rt or ReasonType.popular_with_fans_of in pers_rt
    # every emitted carousel meets the min size
    for f in (cold, pers):
        for c in f.carousels:
            assert len(c.items) >= config.CAROUSEL_MIN_SIZE


# ── WHY ──────────────────────────────────────────────────────────────────

def test_why_templates():
    assert why_string("trending_global", "popularity", "cold_start", "movie") == "Trending now"
    assert why_string("trending_global", "popularity", "cold_start", "movie", genre="Horror") == "Trending in Horror"
    assert why_string("new_in_genre", "recency", "cold_start", "tv", genre="Drama") == "New in Drama"
    assert why_string("new_on_platform", "recency", "cold_start", "movie", platform_name="Netflix") == "New on Netflix"
    assert why_string("similar_to_followed", "semantic", "personalized", "game",
                      repr_followed_name="Hades") == "Because you follow Hades"
    # cold-start never emits a personal phrasing for a global pool
    assert "follow" not in why_string("trending_global", "popularity", "cold_start", "movie").lower()
    assert reason_string(ReasonType.new_in_genre, genre="Comedy") == "New in Comedy"


def test_every_item_has_text():
    feed = _build(PERS, limit=20)
    assert all(i.why_string for i in feed.main_feed)
    assert all(c.reason_string for c in feed.carousels)
    assert all(it.why_string for c in feed.carousels for it in c.items)


def _run_all():
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
    sys.exit(1 if _run_all() else 0)
