"""V2-P8 validation — trending as a FIRST-CLASS CANDIDATE SOURCE + independent axes + adaptive weighting.

Controlled scenarios (a FakeDS + a real TrendingTable over synthetic reactions) that EXPOSE the gap the fix
closes, so the proof is isolated from substrate-dependent retrieval:
  • core gap   — a trending, on-taste property the TASTE path missed now SURFACES (before vs after)
  • taste-gate — an OFF-taste viral property does NOT enter (trending is scoped to taste)
  • niche      — a few users surging on niche content activates trending (LOW absolute threshold)
  • old-trend  — old-published + recent-reaction-burst → high trending / low recency; recent ranks above old
  • thin       — no trending in taste → falls back to taste+recency
  • axes       — trending and recency are independent; exclusions never leak
Run:  .venv/bin/python discovery_api/test_v2p8_trending_candidates.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery_api.src import config
from discovery_api.src.data_access.records import Moment, ReactionEvent
from discovery_api.src.feed.assembler_v2 import assemble_feed_v2
from discovery_api.src.feed.clustering import TasteCluster
from discovery_api.src.feed.moment_select import BlendWeights
from discovery_api.src.ranking.trending import TrendingTable
from discovery_api.src.retrieval.candidates import AllocationPlan, Candidate, CandidateBundle, ClusterCandidateSet
from discovery_api.src.retrieval.pipeline import _merge_trending_into_clusters
from discovery_api.src.retrieval.trending_candidates import build_trending_candidates
from discovery_api.src import timeutil

NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)
FAILS = []
def check(name, cond, detail=""):
    print(f"   [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


# ── controlled fake data source ──────────────────────────────────────────────
class FakeDS:
    def __init__(self):
        self.entities = {}      # eid -> ns(vertical,name,canonical_genres,bm25_keywords)
        self.moments = {}       # eid -> [Moment]
        self.reactions = []     # [ReactionEvent]
    def add_entity(self, eid, vertical, genres, keywords):
        self.entities[eid] = SimpleNamespace(entity_id=eid, vertical=vertical, name=eid.split(":")[-1],
                                             canonical_genres=genres, bm25_keywords=keywords)
    def add_moment(self, mid, eid, days_old):
        m = Moment(moment_id=mid, entity_id=eid, property_id=mid, title=f"{eid} m{mid}",
                   event_starts_at=NOW - timedelta(days=days_old))
        self.moments.setdefault(eid, []).append(m)
    def add_reactions(self, mid, eid, n, days_ago):
        for i in range(n):
            self.reactions.append(ReactionEvent(user_id=10_000 + i, moment_id=mid, reaction_type_id=1,
                                                created_at=NOW - timedelta(days=days_ago, hours=i % 12), entity_id=eid))
    # DataSource surface used by the trending source + assembler
    def iter_reaction_events(self): return self.reactions
    def iter_follow_events(self): return []
    def get_entity(self, eid): return self.entities.get(eid)
    def get_moment(self, mid):
        for ms in self.moments.values():
            for m in ms:
                if m.moment_id == mid: return m
        return None
    def get_moments_for_property(self, eid):
        return sorted(self.moments.get(eid, []), key=lambda m: m.event_starts_at, reverse=True)
    def get_podcast_categories(self, eid): return []


def horror_cluster(members):
    return TasteCluster(cluster_id=1, label="Horror", member_entity_ids=members,
                        top_representative_member_entity_ids=members[:1], dominant_vertical="movie",
                        dominant_verticals=[("movie", 1.0)], top_genres=[("Horror", 1.0), ("Mystery", 0.5)],
                        top_keywords=[("horror", 1.0), ("supernatural", 0.8)], cluster_weight=5.0,
                        cluster_share=1.0, size=len(members), recency_summary={})


def make_profile(cluster, engaged=()):
    eng = [SimpleNamespace(target_entity_id=e, signal_type="follow") for e in engaged]
    return SimpleNamespace(user_id=900800, mode="personalized", signal_strength=0.5, clusters=[cluster],
                           top_genres=[("Horror", 1.0)], engagements=eng,
                           vertical_percentages={"movie": 1.0, "game": 0.0, "tv": 0.0, "podcast": 0.0})


def make_bundle(profile, content_candidates, trend_flat, trend_conf, trend_mom_vel):
    cs = ClusterCandidateSet(cluster_id=1, label="Horror", dominant_vertical="movie", phrase="", composer="deterministic",
                             cluster_share=1.0, slot_quota=20, candidates=list(content_candidates))
    alloc = AllocationPlan(total_budget=240, content_slots=200, exploration_slots=0, exploration_fraction=0.0,
                           by_vertical={"movie": 200, "game": 0, "tv": 0, "podcast": 0}, by_cluster={1: 200},
                           global_backfill={}, alloc_mode="vertical_then_cluster")
    return CandidateBundle(user_id=900800, mode="personalized", signal_strength=0.5, fallback_to_global=False,
                           allocation=alloc, clusters=[cs], exploration=[], excluded_entity_count=0,
                           n_retrieve_calls=0, n_substrate_calls=0, timing_ms={},
                           trending=trend_flat, trend_confidence=trend_conf, trend_moment_velocity=trend_mom_vel)


def feed_eids(feed): return [fi.entity_id for fi in feed.main_feed]
def feed_mids(feed): return [fi.moment_id for fi in feed.main_feed]


# ══════════════════════════════════════════════════════════════════════════════
def test_axes_independent():
    print("\n##### (2) trending & recency are INDEPENDENT axes #####")
    ds = FakeDS()
    ds.add_entity("Movie:OLD", "movie", ["Horror"], ["horror"])
    ds.add_entity("Movie:NEW", "movie", ["Horror"], ["horror"])
    ds.add_moment(1, "Movie:OLD", days_old=900)   # published long ago
    ds.add_moment(2, "Movie:NEW", days_old=1)      # just published
    ds.add_reactions(1, "Movie:OLD", n=12, days_ago=1)   # OLD moment, RECENT reaction burst
    # NEW moment: no reactions
    tr = TrendingTable(ds)
    tv_old = tr.raw_moment_velocity(1, NOW); tv_new = tr.raw_moment_velocity(2, NOW)
    rec_old = timeutil.recency_score(ds.get_moment(1).event_starts_at, NOW)
    rec_new = timeutil.recency_score(ds.get_moment(2).event_starts_at, NOW)
    print(f"   OLD moment: trending(raw velocity)={tv_old:.3f}  recency={rec_old:.3f}")
    print(f"   NEW moment: trending(raw velocity)={tv_new:.3f}  recency={rec_new:.3f}")
    check("OLD+burst → HIGH trending, LOW recency", tv_old > 0 and rec_old < 0.1)
    check("NEW+quiet → LOW trending, HIGH recency", tv_new == 0 and rec_new > 0.9)


def test_trending_generates_candidates_and_gates():
    print("\n##### (1) trending GENERATES candidates (on-taste) + GATES off-taste #####")
    ds = FakeDS()
    ds.add_entity("Movie:A", "movie", ["Horror"], ["horror", "supernatural"])     # on-taste, quiet
    ds.add_entity("Movie:B", "movie", ["Horror"], ["horror", "supernatural"])     # on-taste, TRENDING
    ds.add_entity("Movie:C", "movie", ["Comedy"], ["comedy", "slapstick"])        # OFF-taste, viral
    for eid, mid in [("Movie:A", 1), ("Movie:B", 2), ("Movie:C", 3)]:
        ds.add_moment(mid, eid, days_old=30)
    ds.add_reactions(2, "Movie:B", n=10, days_ago=2)    # B trending (on-taste)
    ds.add_reactions(3, "Movie:C", n=30, days_ago=1)    # C MORE viral but OFF-taste
    prof = make_profile(horror_cluster(["Movie:seed"]))
    tr = TrendingTable(ds)
    per_cluster, conf, mom_vel, flat = build_trending_candidates(prof, tr, ds, NOW, exclude_ids=set())
    ids = {c.entity_id for c in flat}
    check("trending GENERATES the on-taste trending property (B)", "Movie:B" in ids)
    check("off-taste viral property (C) is GATED OUT (scoped to taste)", "Movie:C" not in ids, f"flat={sorted(ids)}")
    check("trending confidence activated (>0)", conf > 0, f"conf={conf}")


def test_core_gap_before_after():
    print("\n##### (1+4) CORE PROOF: a trending on-taste property the TASTE path MISSED now surfaces #####")
    ds = FakeDS()
    ds.add_entity("Movie:A", "movie", ["Horror"], ["horror", "supernatural"])   # taste path SELECTS this (quiet)
    ds.add_entity("Movie:B", "movie", ["Horror"], ["horror", "supernatural"])   # taste path MISSES this (trending)
    ds.add_moment(1, "Movie:A", days_old=20)
    ds.add_moment(2, "Movie:B", days_old=400)        # B's trending moment is OLD-published
    ds.add_reactions(2, "Movie:B", n=12, days_ago=2)  # ...but a RECENT reaction burst
    prof = make_profile(horror_cluster(["Movie:seed"]))
    tr = TrendingTable(ds)
    # taste path selected ONLY A (B was never retrieved on taste)
    A = Candidate(entity_id="Movie:A", name="A", vertical="movie", score=1.0, source_pool="content", cluster_id=1)

    # BEFORE the fix: no trending candidate path → B can't surface
    before = make_bundle(prof, [A], trend_flat=[], trend_conf=0.0, trend_mom_vel={})
    feed_before = assemble_feed_v2(prof, before, ds, tr, NOW, v1_profile=None, pop=None, include_global=False, limit=10)
    check("BEFORE: trending property B is ABSENT from the feed", "Movie:B" not in feed_eids(feed_before))

    # AFTER the fix: trending candidate path generates B, merges into the cluster, assembler surfaces it
    per_cluster, conf, mom_vel, flat = build_trending_candidates(prof, tr, ds, NOW, exclude_ids=set())
    after = make_bundle(prof, [A], trend_flat=flat, trend_conf=conf, trend_mom_vel=mom_vel)
    _merge_trending_into_clusters(after.clusters, per_cluster, conf)
    feed_after = assemble_feed_v2(prof, after, ds, tr, NOW, v1_profile=None, pop=None, include_global=False, limit=10)
    print(f"   AFTER feed: {[(fi.entity_id, fi.why_string) for fi in feed_after.main_feed]}")
    check("AFTER: trending property B now SURFACES", "Movie:B" in feed_eids(feed_after))
    check("AFTER: B surfaces via its TRENDING moment (id 2)", 2 in feed_mids(feed_after))
    # trending carousel now populated from the scoped-to-taste source
    tr_car = next((c for c in feed_after.carousels if c.carousel_id == "trending"), None)
    check("AFTER: TRENDING carousel populated (B present)", tr_car is not None and any(i.entity_id == "Movie:B" for i in tr_car.items))


def test_niche_activates():
    print("\n##### (3) NICHE: a FEW users surging on niche content activates trending #####")
    ds = FakeDS()
    ds.add_entity("Movie:NICHE", "movie", ["Horror"], ["horror", "folk"])
    ds.add_moment(5, "Movie:NICHE", days_old=200)
    ds.add_reactions(5, "Movie:NICHE", n=4, days_ago=2)   # only 4 users — a niche surge
    prof = make_profile(horror_cluster(["Movie:seed"]))
    tr = TrendingTable(ds)
    per_cluster, conf, mom_vel, flat = build_trending_candidates(prof, tr, ds, NOW, exclude_ids=set())
    print(f"   niche surge (4 users): global trending confidence={tr.confidence(NOW):.4f}  "
          f"niche-relative confidence={conf:.3f}")
    check("niche trending activates at LOW threshold (conf>0)", conf > 0)
    check("niche content surfaces as a trending candidate", "Movie:NICHE" in {c.entity_id for c in flat})


def test_old_but_trending_recency_tiebreak():
    print("\n##### (2+3) OLD-BUT-TRENDING + recency tiebreak between two trending+tasteful items #####")
    ds = FakeDS()
    ds.add_entity("Movie:TR_OLD", "movie", ["Horror"], ["horror"])
    ds.add_entity("Movie:TR_NEW", "movie", ["Horror"], ["horror"])
    ds.add_moment(1, "Movie:TR_OLD", days_old=300)   # old-published
    ds.add_moment(2, "Movie:TR_NEW", days_old=2)      # recent-published
    ds.add_reactions(1, "Movie:TR_OLD", n=10, days_ago=2)   # both equally trending now
    ds.add_reactions(2, "Movie:TR_NEW", n=10, days_ago=2)
    prof = make_profile(horror_cluster(["Movie:seed"]))
    tr = TrendingTable(ds)
    per_cluster, conf, mom_vel, flat = build_trending_candidates(prof, tr, ds, NOW, exclude_ids=set())
    bundle = make_bundle(prof, [], trend_flat=flat, trend_conf=conf, trend_mom_vel=mom_vel)
    _merge_trending_into_clusters(bundle.clusters, per_cluster, conf)
    feed = assemble_feed_v2(prof, bundle, ds, tr, NOW, v1_profile=None, pop=None, include_global=False, limit=10)
    order = feed_eids(feed)
    print(f"   feed order: {order}")
    check("OLD-but-trending surfaces despite low recency", "Movie:TR_OLD" in order)
    check("between two trending+tasteful, the RECENT one ranks higher (recency tiebreaker)",
          order.index("Movie:TR_NEW") < order.index("Movie:TR_OLD") if ("Movie:TR_NEW" in order and "Movie:TR_OLD" in order) else False)


def test_thin_fallback():
    print("\n##### (3) THIN trending → falls back to taste+recency #####")
    ds = FakeDS()
    ds.add_entity("Movie:Q1", "movie", ["Horror"], ["horror"])
    ds.add_entity("Movie:Q2", "movie", ["Horror"], ["horror"])
    ds.add_moment(1, "Movie:Q1", days_old=2)     # recent
    ds.add_moment(2, "Movie:Q2", days_old=300)    # old
    # NO reactions anywhere → no trending in the user's taste
    prof = make_profile(horror_cluster(["Movie:seed"]))
    tr = TrendingTable(ds)
    per_cluster, conf, mom_vel, flat = build_trending_candidates(prof, tr, ds, NOW, exclude_ids=set())
    check("THIN: no trending candidates generated", len(flat) == 0)
    check("THIN: trending confidence ~0 → w_trending≈0", conf == 0.0)
    Q1 = Candidate("Movie:Q1", "Q1", "movie", 1.0, "content", cluster_id=1)
    Q2 = Candidate("Movie:Q2", "Q2", "movie", 1.0, "content", cluster_id=1)
    bundle = make_bundle(prof, [Q1, Q2], trend_flat=[], trend_conf=conf, trend_mom_vel={})
    feed = assemble_feed_v2(prof, bundle, ds, tr, NOW, v1_profile=None, pop=None, include_global=False, limit=10)
    order = feed_eids(feed)
    print(f"   feed order (taste+recency): {order}")
    check("THIN: feed still sensible; recent on-taste (Q1) ranks above old (Q2)",
          order and order.index("Movie:Q1") < order.index("Movie:Q2"))


def test_exclusions():
    print("\n##### exclusions: followed/excluded never enter the trending path #####")
    ds = FakeDS()
    ds.add_entity("Movie:FOLLOWED", "movie", ["Horror"], ["horror"])
    ds.add_moment(1, "Movie:FOLLOWED", days_old=10)
    ds.add_reactions(1, "Movie:FOLLOWED", n=15, days_ago=1)   # trending, on-taste — but FOLLOWED
    prof = make_profile(horror_cluster(["Movie:seed"]), engaged=["Movie:FOLLOWED"])
    tr = TrendingTable(ds)
    per_cluster, conf, mom_vel, flat = build_trending_candidates(prof, tr, ds, NOW, exclude_ids={"Movie:FOLLOWED"})
    check("followed property never becomes a trending candidate", "Movie:FOLLOWED" not in {c.entity_id for c in flat})


def main():
    test_axes_independent()
    test_trending_generates_candidates_and_gates()
    test_core_gap_before_after()
    test_niche_activates()
    test_old_but_trending_recency_tiebreak()
    test_thin_fallback()
    test_exclusions()
    print(f"\n{'='*78}\nRESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}\n{'='*78}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
