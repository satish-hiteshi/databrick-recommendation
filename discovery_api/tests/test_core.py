"""Discovery-API CORE unit tests (P3). Self-running (pytest is not installed):

    .venv/bin/python discovery_api/tests/test_core.py

Loads the REAL dev CSVs once. The substrate is MOCKED by default (no live :8000/:8010 calls); a final
optional block runs a tiny LIVE probe only if the services are up. Functions are named test_* so pytest
can also discover them.
"""

import sys
from collections import Counter
from pathlib import Path

# allow `python discovery_api/tests/test_core.py` from anywhere (repo root on path for the package import)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import config, timeutil
from discovery_api.src.data_access import CsvDataSource, SubstrateClient
from discovery_api.src.ranking import PopularityIndex
from discovery_api.src.feed import build_profile
from discovery_api.src.candidates import (RequestContext, SimilarToFollowed, FreshMoments,
    TrendingGlobal, PopularWithFansOf, NewInGenre, NewOnPlatform, dedupe, excluded_entity_ids)

NOW = timeutil.parse_ts("2026-06-18T00:00:00Z")     # fixed reference over the June-2026 dev data
EXPECTED_ROWS = {
    "entities_dev.csv": 57443, "property_bridge_dev.csv": 57443, "moments_dev.csv": 141374,
    "moment_ctas_dev.csv": 141006, "follows_dev.csv": 330, "reactions_dev.csv": 31,
    "podcast_categories_dev.csv": 19029, "users_dev.csv": 267, "lookups_dev.csv": 82,
    "gds_signals_dev.csv": 57443,
}

# ── shared fixtures (loaded once) ───────────────────────────────────────
print("loading CsvDataSource (real dev CSVs)…", flush=True)
DS = CsvDataSource().load()
POP = PopularityIndex.from_data_source(DS)
COLD_USER = next(u for u in DS._users if not DS.get_followed_property_ids(u) and not DS.get_user_reactions(u))
# NOTE (data reality, see report): the NOMINAL "202-follow account" 11208 follows only UNSERVED
# property_ids (10000198+, outside the 57,443 catalogue) → 0 resolve → it is cold_start in dev.
# The ACTUAL resolved-signal fixture is 12305 (24 follows + 12 reactions resolve to served entities).
POWER_USER = 11208
PERSONALIZED_USER = 12305


class FakeSubstrate:
    """Deterministic mock: returns real entity_ids of the requested vertical (NOT anchors), and — to
    exercise the providers' OWN exclusion filter — deliberately echoes back the first exclude_id."""
    def __init__(self, ds): self.ds = ds
    def _sample(self, vertical, exclude, anchors, top_k):
        out = []
        for e in self.ds._by_vertical.get(vertical, []):
            if e in anchors:
                continue
            out.append(e)
            if len(out) >= top_k:
                break
        # inject a should-be-filtered id (an exclude_id) to prove the provider filters it locally
        inj = [x for x in (exclude or []) if x not in anchors][:1]
        return inj + out
    def vector_neighbors(self, anchor_ids, exclude_ids=None, vertical=None, top_k=20):
        v = vertical or "movie"
        ids = self._sample(v, exclude_ids, set(anchor_ids), top_k)
        return [{"entity_id": e, "name": (self.ds.get_entity(e).name if self.ds.get_entity(e) else ""),
                 "vertical": v, "score": round(1.0 - i * 0.001, 4)} for i, e in enumerate(ids)]
    def graph_similar(self, entity_id, top_k=10, vertical=None):
        v = vertical or "game"
        ids = self._sample(v, [], {entity_id}, top_k)
        return [{"entity_id": e, "name": "", "vertical": v, "final_score": round(0.5 - i * 0.01, 4)}
                for i, e in enumerate(ids)]

FAKE = FakeSubstrate(DS)


def ctx(**kw):
    kw.setdefault("now", NOW)
    return RequestContext(**kw)


# ── tests ───────────────────────────────────────────────────────────────

def test_config_loads():
    s = config.summary()
    assert s["data_source_mode"] == "csv"
    assert isinstance(config.W_POPULARITY, float) and isinstance(config.MOMENT_CAP_PER_PROPERTY, int)
    assert config.MOMENT_CAP_PER_PROPERTY == 3 and config.GLOBAL_REFRESH_SECONDS == 900
    assert config.POSITIVE_REACTION_TYPE_IDS == (1, 2, 3)


def test_csv_row_counts():
    rc = DS.row_counts()
    for fname, exp in EXPECTED_ROWS.items():
        assert rc[fname] == exp, f"{fname}: {rc[fname]} != {exp}"


def test_bridge_resolves():
    # integer(entity_id) == property_id for ALL entities
    bad = 0
    for eid in DS.all_entity_ids():
        pid = DS.entity_id_to_property_id(eid)
        if pid is None or int(eid.split(":")[-1]) != pid:
            bad += 1
    assert bad == 0, f"{bad} entity_id↔property_id mismatches"
    # round-trip a sample
    e = "Movie:88177"
    assert DS.property_id_to_entity_id(DS.entity_id_to_property_id(e)) == e


def test_popularity_percentiles():
    stats = POP.vertical_stats()
    for v in ("game", "movie", "tv", "podcast"):
        nm = stats[v]["norm_median"]
        assert 0.45 <= nm <= 0.55, f"{v} norm_median {nm} not ~0.5"
    # podcast heavy tail (raw_max ~6.46) is CLIPPED: its normalized max is < 1.0 and far below raw scale
    pod = stats["podcast"]
    assert pod["raw_max"] > 3.5, f"expected podcast heavy tail, got {pod['raw_max']}"
    assert pod["norm_max"] < 1.0
    # the 6.46 outlier maps to the SAME normalized value as a huge value (both clamped to p95)
    assert round(POP._rank("podcast", 1e9), 4) == pod["norm_max"], "podcast tail not clipped at p95"


def test_profile_cold_start():
    p = build_profile(COLD_USER, DS)
    assert p.mode == "cold_start"
    assert p.signal_strength == 0.0
    assert p.followed_entity_ids == [] and p.positively_reacted_entity_ids == []
    # dormant fields present + empty
    assert p.blocked_entity_ids == [] and p.not_interested_entity_ids == [] and p.user_prefs == {}


def test_profile_personalized():
    p = build_profile(PERSONALIZED_USER, DS)
    assert p.mode == "personalized"
    assert len(p.followed_entity_ids) > 10, f"resolved only {len(p.followed_entity_ids)} follows"
    assert p.positively_reacted_entity_ids, "expected resolved reactions for the fixture user"
    assert p.signal_strength == 1.0   # >= SIGNAL_STRENGTH_FULL signals → saturated


def test_profile_202_account_resolves_to_cold_start():
    # the NOMINAL 202-follow account follows only UNSERVED property_ids → 0 resolve → cold_start in dev.
    # This proves the bridge correctly filters follows to SERVED entities (per spec).
    p = build_profile(POWER_USER, DS)
    assert len(p.followed_property_ids) == 202        # raw follows exist
    assert p.followed_entity_ids == []                # but none resolve to a served entity
    assert p.mode == "cold_start" and p.signal_strength == 0.0


def test_exclusion_helper():
    p = build_profile(PERSONALIZED_USER, DS)
    followed_pid = next(pid for pid in p.followed_property_ids if DS.property_id_to_entity_id(pid))
    seen_eid = "Movie:88177"
    c = ctx(seen_entity_ids={seen_eid}, excluded_property_ids={followed_pid})
    excl = excluded_entity_ids(p, c, DS)
    assert seen_eid in excl
    assert DS.property_id_to_entity_id(followed_pid) in excl
    for fe in p.followed_entity_ids:
        assert fe in excl


def _assert_capped_and_deduped(cands, cap=3):
    assert len(dedupe(cands)) == len(cands), "duplicate candidate keys"
    per_prop = Counter(c.entity_id for c in cands if c.moment_id is not None)
    if per_prop:
        assert max(per_prop.values()) <= cap, f"per-property cap exceeded: {max(per_prop.values())}"


def _assert_excludes(cands, profile, context):
    excl = excluded_entity_ids(profile, context, DS)
    for c in cands:
        assert c.entity_id not in excl, f"{c.entity_id} should have been excluded"


def test_fresh_moments():
    p = build_profile(COLD_USER, DS)
    fresh = FreshMoments(DS, popularity=POP).generate(p, ctx(limit=200))
    assert len(fresh) > 50, f"only {len(fresh)} fresh moments"
    _assert_capped_and_deduped(fresh)
    assert all(c.moment_id is not None for c in fresh)        # moment-level
    assert all("recency" in c.raw_signals for c in fresh)
    # power user: followed properties excluded
    pp = build_profile(PERSONALIZED_USER, DS)
    c2 = ctx(limit=200)
    fresh2 = FreshMoments(DS, popularity=POP).generate(pp, c2)
    _assert_excludes(fresh2, pp, c2)


def test_trending_global():
    prov = TrendingGlobal(DS, popularity=POP)
    p = build_profile(COLD_USER, DS)
    c = ctx(limit=50)
    t1 = prov.generate(p, c)
    t2 = prov.generate(build_profile(PERSONALIZED_USER, DS), c)   # different user, SAME cadence window
    assert len(t1) == 50 and len(t2) == 50
    assert prov.compute_count == 1, f"global pool recomputed {prov.compute_count}× (should cache to 1)"
    assert all("influence_norm" in x.raw_signals and "velocity" in x.raw_signals for x in t1)
    _assert_excludes(t2, build_profile(PERSONALIZED_USER, DS), c)   # power user's follows excluded


def test_new_in_genre():
    p = build_profile(COLD_USER, DS)
    prov = NewInGenre(DS, popularity=POP)
    cands = prov.generate(p, ctx(limit=200))
    assert len(cands) > 50
    _assert_capped_and_deduped(cands)
    assert any(c.raw_signals.get("genres") for c in cands)
    groups = prov.group_by_genre(p, ctx(limit=200))
    assert len(groups) > 3, f"only {len(groups)} genres"


def test_new_on_platform():
    p = build_profile(COLD_USER, DS)
    prov = NewOnPlatform(DS, popularity=POP)
    cands = prov.generate(p, ctx(limit=200))
    assert len(cands) > 50
    _assert_capped_and_deduped(cands)
    groups = prov.group_by_platform(p, ctx(limit=200))
    assert len(groups) >= 1


def test_similar_to_followed():
    # cold-start → empty
    cold = build_profile(COLD_USER, DS)
    assert SimilarToFollowed(DS, substrate=FAKE, popularity=POP).generate(cold, ctx()) == []
    # personalized → non-empty, excludes followed (incl. the injected exclude_id)
    p = build_profile(PERSONALIZED_USER, DS)
    c = ctx(limit=50)
    cands = SimilarToFollowed(DS, substrate=FAKE, popularity=POP).generate(p, c)
    assert len(cands) > 0
    _assert_excludes(cands, p, c)
    assert all(c2.entity_id is not None and c2.moment_id is None for c2 in cands)  # property-level


def test_popular_with_fans_of():
    cold = build_profile(COLD_USER, DS)
    assert PopularWithFansOf(DS, substrate=FAKE, popularity=POP).generate(cold, ctx()) == []
    p = build_profile(PERSONALIZED_USER, DS)
    c = ctx(limit=50)
    cands = PopularWithFansOf(DS, substrate=FAKE, popularity=POP).generate(p, c)
    assert len(cands) > 0
    _assert_excludes(cands, p, c)


# ── runner ──────────────────────────────────────────────────────────────
def _run_all():
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    npass = nfail = 0
    for t in tests:
        try:
            t(); print(f"  PASS  {t.__name__}"); npass += 1
        except Exception as e:
            import traceback
            print(f"  FAIL  {t.__name__}: {type(e).__name__}: {e}")
            traceback.print_exc()
            nfail += 1
    print(f"\n{npass} passed, {nfail} failed (of {len(tests)})")
    return nfail


def live_probe():
    sc = SubstrateClient()
    if not sc.is_up():
        print("\n[live probe] substrate :8000/:8010 not up — SKIPPED (unit tests mock it).")
        return
    print("\n[live probe] substrate up — running one REAL SimilarToFollowed for the power user…")
    p = build_profile(PERSONALIZED_USER, DS)
    cands = SimilarToFollowed(DS, substrate=sc, popularity=POP).generate(p, ctx(limit=10))
    print(f"  live SimilarToFollowed returned {len(cands)} candidates; sample:",
          [(c.entity_id, round(c.raw_signals.get('semantic') or 0, 3)) for c in cands[:3]])


if __name__ == "__main__":
    nfail = _run_all()
    live_probe()
    sys.exit(1 if nfail else 0)
