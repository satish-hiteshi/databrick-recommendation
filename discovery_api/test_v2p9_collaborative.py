"""V2-P9 validation — COLLABORATIVE FILTERING (Source 4): the bubble-escape, proven in isolation.

Controlled multi-user scenarios (a FakeDS with per-user follows/reactions + the REAL CollaborativeIndex)
that EXPOSE what content similarity CANNOT find and behavioral overlap CAN:
  • bubble-escape — similar users' CROSS-ATTRIBUTE content (a strategy game shared by a horror cohort)
                    surfaces for a target horror user — and would NOT via taste or trending (both content-scoped).
  • niche        — a SMALL neighborhood (a few similar users) still activates collaborative (LOW threshold).
  • thin         — a user with NO similar neighbors → w_collaborative≈0, feed falls back to taste+recency.
  • exclusion    — collaborative NEVER surfaces already-followed/engaged/excluded content.
  • endorsement  — a single-endorser item is gated out (≥ MIN_ENDORSERS distinct neighbors required), but
                    the gate is ENDORSEMENT, not taste (cross-attribute is allowed).
Run:  .venv/bin/python discovery_api/test_v2p9_collaborative.py
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from discovery_api.src import config
from discovery_api.src.data_access.records import FollowEvent, Moment, ReactionEvent
from discovery_api.src.feed.assembler_v2 import assemble_feed_v2
from discovery_api.src.feed.clustering import TasteCluster
from discovery_api.src.ranking.collaborative import CollaborativeIndex
from discovery_api.src.retrieval.candidates import AllocationPlan, Candidate, CandidateBundle, ClusterCandidateSet
from discovery_api.src.retrieval.collaborative_candidates import build_collaborative_candidates

NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)
FAILS = []


def check(name, cond, detail=""):
    print(f"   [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


# ── controlled multi-user fake data source ───────────────────────────────────
class FakeDS:
    def __init__(self):
        self.entities = {}
        self.moments = {}        # eid -> [Moment]
        self.follows = []        # [FollowEvent]
        self.reactions = []      # [ReactionEvent]

    def add_entity(self, eid, vertical, genres, keywords):
        self.entities[eid] = SimpleNamespace(entity_id=eid, vertical=vertical, name=eid.split(":")[-1],
                                             canonical_genres=genres, bm25_keywords=keywords)

    def add_moment(self, mid, eid, days_old):
        m = Moment(moment_id=mid, entity_id=eid, property_id=mid, title=f"{eid} m{mid}",
                   event_starts_at=NOW - timedelta(days=days_old))
        self.moments.setdefault(eid, []).append(m)

    def follow(self, uid, eid, days_ago=10):
        self.follows.append(FollowEvent(user_id=uid, property_id=hash(eid) % 10_000, created_at=NOW - timedelta(days=days_ago), entity_id=eid))

    def react(self, uid, eid, mid, days_ago=2):
        self.reactions.append(ReactionEvent(user_id=uid, moment_id=mid, reaction_type_id=1, created_at=NOW - timedelta(days=days_ago), entity_id=eid))

    # DataSource surface used by the collaborative index + assembler
    def iter_reaction_events(self): return self.reactions
    def iter_follow_events(self): return self.follows
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
                        dominant_verticals=[("movie", 1.0)], top_genres=[("Horror", 1.0)],
                        top_keywords=[("horror", 1.0), ("supernatural", 0.8)], cluster_weight=4.0,
                        cluster_share=1.0, size=len(members), recency_summary={})


def make_profile(uid, engaged, genre_w=None, keyword_w=None, cluster=None):
    eng = [SimpleNamespace(target_entity_id=e, signal_type="follow") for e in engaged]
    return SimpleNamespace(
        user_id=uid, mode="personalized", signal_strength=0.5,
        clusters=[cluster or horror_cluster(list(engaged))],
        genre_weights=genre_w or {"Horror": 1.0},
        keyword_weights=keyword_w or {"horror": 0.6, "supernatural": 0.4},
        top_genres=[(g, w) for g, w in (genre_w or {"Horror": 1.0}).items()],
        engagements=eng, vertical_percentages={"movie": 1.0, "game": 0.0, "tv": 0.0, "podcast": 0.0})


def make_bundle(profile, content, collab_flat, collab_conf, collab_score, neighborhood=None):
    cs = ClusterCandidateSet(cluster_id=1, label="Horror", dominant_vertical="movie", phrase="",
                             composer="deterministic", cluster_share=1.0, slot_quota=20, candidates=list(content))
    alloc = AllocationPlan(total_budget=240, content_slots=200, exploration_slots=0, exploration_fraction=0.0,
                           by_vertical={"movie": 200, "game": 0, "tv": 0, "podcast": 0}, by_cluster={1: 200},
                           global_backfill={}, alloc_mode="vertical_then_cluster")
    return CandidateBundle(user_id=profile.user_id, mode="personalized", signal_strength=0.5, fallback_to_global=False,
                           allocation=alloc, clusters=[cs], exploration=[], excluded_entity_count=0,
                           n_retrieve_calls=0, n_substrate_calls=0, timing_ms={},
                           collaborative=collab_flat, collab_confidence=collab_conf, collab_score=collab_score,
                           collab_neighborhood=neighborhood)


def feed_eids(feed): return [fi.entity_id for fi in feed.main_feed]


def _horror_cohort(ds, movies, users, react_mid=None):
    """`users` horror users each follow all `movies` (shared horror taste)."""
    for u in users:
        for e in movies:
            ds.follow(u, e, days_ago=8)
        if react_mid is not None:
            ds.react(u, movies[0], react_mid, days_ago=3)


# ══════════════════════════════════════════════════════════════════════════════
def test_neighborhood_and_niche_confidence():
    print("\n##### (1) USER-SIMILARITY: a taste neighborhood forms; niche-relative LOW-threshold confidence #####")
    ds = FakeDS()
    movies = ["Movie:H1", "Movie:H2", "Movie:H3", "Movie:H4"]
    for e in movies:
        ds.add_entity(e, "movie", ["Horror"], ["horror", "supernatural"])
    _horror_cohort(ds, movies, users=[201, 202, 203])          # only 3 similar users — a NICHE neighborhood
    prof = make_profile(101, engaged=movies)
    collab = CollaborativeIndex(ds)
    nb = collab.neighborhood(prof, NOW, exclude_ids=set(movies))
    print(f"   neighbors found={nb.n_neighbors}  density(mass)={nb.mass}  confidence={nb.confidence}")
    check("a FEW similar users form a neighborhood (n_neighbors==3)", nb.n_neighbors == 3, f"n={nb.n_neighbors}")
    check("niche neighborhood activates at a LOW threshold (confidence>0)", nb.confidence > 0, f"conf={nb.confidence}")
    check("target is excluded from its own neighborhood", 101 not in {u for u, _ in nb.neighbor_ids})


def test_bubble_escape_core_proof():
    print("\n##### (4) THE CORE PROOF — bubble-escape: similar users' CROSS-ATTRIBUTE content surfaces #####")
    ds = FakeDS()
    movies = ["Movie:H1", "Movie:H2", "Movie:H3", "Movie:H4"]
    for e in movies:
        ds.add_entity(e, "movie", ["Horror"], ["horror", "supernatural"])
    ds.add_entity("Movie:H5", "movie", ["Horror"], ["horror", "supernatural"])   # an on-taste content pick (not followed)
    ds.add_moment(105, "Movie:H5", days_old=12)
    # the CROSS-ATTRIBUTE property: a strategy GAME — shares NO genre/keyword with horror
    ds.add_entity("Game:STRAT", "game", ["Strategy"], ["strategy", "warfare", "tactics"])
    ds.add_moment(900, "Game:STRAT", days_old=20)

    # a horror cohort of 6 users follow the 4 horror movies; 5 of them ALSO follow the strategy game
    cohort = [201, 202, 203, 204, 205, 206]
    _horror_cohort(ds, movies, users=cohort)
    for u in cohort[:5]:                                         # 5 endorsers of the cross-attribute game
        ds.follow(u, "Game:STRAT", days_ago=6)

    # target: a horror user who follows the 4 horror movies but has NOT discovered the strategy game
    prof = make_profile(101, engaged=movies)
    collab = CollaborativeIndex(ds)
    exclude = set(movies)
    per_cluster, flat, conf, collab_score, nb = build_collaborative_candidates(prof, collab, ds, NOW, exclude)
    ids = {c.entity_id for c in flat}
    strat = next((c for c in flat if c.entity_id == "Game:STRAT"), None)
    print(f"   collaborative candidates: {sorted(ids)}  conf={conf}  STRAT endorsers={strat.collab_endorsers if strat else 'N/A'}")
    check("collaborative GENERATES the cross-attribute game (behavioral overlap finds it)", "Game:STRAT" in ids)
    check("the cross-attribute game is CROSS-attribute (cluster_id=None, taste proxy 0)",
          strat is not None and strat.cluster_id is None and strat.score == 0.0)
    check("endorsement provenance present (≥5 similar users endorse it)", strat is not None and strat.collab_endorsers >= 5)

    # CONTENT-SCOPED paths can NEVER find it: assemble WITHOUT collaborative → the game is absent
    H5 = Candidate("Movie:H5", "H5", "movie", 1.0, "content", cluster_id=1)
    before = make_bundle(prof, [H5], collab_flat=[], collab_conf=0.0, collab_score={})
    feed_off = assemble_feed_v2(prof, before, ds, None, NOW, v1_profile=None, pop=None, include_global=False, limit=10)
    check("BEFORE (collaborative OFF): the cross-attribute game is ABSENT (taste/trending can't reach it)",
          "Game:STRAT" not in feed_eids(feed_off))

    # WITH collaborative → it surfaces in the feed AND the collaborative carousel
    after = make_bundle(prof, [H5], collab_flat=flat, collab_conf=conf, collab_score=collab_score, neighborhood=nb)
    feed_on = assemble_feed_v2(prof, after, ds, None, NOW, v1_profile=None, pop=None, include_global=False, limit=10)
    print(f"   AFTER feed: {[(fi.entity_id, fi.why_string) for fi in feed_on.main_feed]}")
    check("AFTER (collaborative ON): the cross-attribute game SURFACES in the feed", "Game:STRAT" in feed_eids(feed_on))
    co_car = next((c for c in feed_on.carousels if c.carousel_id == "collaborative"), None)
    check("collaborative CAROUSEL populated with the cross-attribute game",
          co_car is not None and any(i.entity_id == "Game:STRAT" for i in co_car.items))
    check("on-taste content (H5) still present (collaborative ADDS, doesn't replace)", "Movie:H5" in feed_eids(feed_on))
    # social-proof why-string (NOT a genre/taste claim — the item is off-genre)
    gi = next((fi for fi in feed_on.main_feed if fi.entity_id == "Game:STRAT"), None)
    check("cross-attribute item carries a SOCIAL-PROOF why-string", gi is not None and "taste" in gi.why_string.lower() or (gi is not None and "people" in gi.why_string.lower()),
          f"why='{gi.why_string if gi else None}'")


def test_thin_neighborhood_fallback():
    print("\n##### (4) THIN/NO neighborhood → w_collaborative≈0, graceful fallback (no regression) #####")
    ds = FakeDS()
    ds.add_entity("Movie:UNIQ", "movie", ["Horror"], ["horror", "supernatural"])
    ds.add_moment(1, "Movie:UNIQ", days_old=5)
    # a totally different cohort (cozy GAME fans) — NO taste overlap with the horror target
    ds.add_entity("Game:COZY", "game", ["Simulation"], ["cozy", "farming"])
    for u in (301, 302, 303):
        ds.follow(u, "Game:COZY", days_ago=5)
    prof = make_profile(101, engaged=["Movie:UNIQ"])
    collab = CollaborativeIndex(ds)
    per_cluster, flat, conf, collab_score, nb = build_collaborative_candidates(prof, collab, ds, NOW, {"Movie:UNIQ"})
    print(f"   no similar neighbors: n_neighbors={nb.n_neighbors if nb else 0}  confidence={conf}  candidates={len(flat)}")
    check("THIN: no similar-taste neighbors found", (nb is None) or nb.n_neighbors == 0)
    check("THIN: no collaborative candidates generated", len(flat) == 0)
    check("THIN: collaborative confidence ~0 → w_collaborative≈0 (feed leans taste+recency)", conf == 0.0)


def test_already_known_exclusion():
    print("\n##### (4) ALREADY-KNOWN exclusion: collaborative never surfaces followed/engaged content #####")
    ds = FakeDS()
    movies = ["Movie:H1", "Movie:H2", "Movie:H3", "Movie:H4"]
    for e in movies:
        ds.add_entity(e, "movie", ["Horror"], ["horror", "supernatural"])
    ds.add_entity("Game:STRAT", "game", ["Strategy"], ["strategy", "warfare"])
    cohort = [201, 202, 203, 204, 205]
    _horror_cohort(ds, movies, users=cohort)
    for u in cohort:
        ds.follow(u, "Game:STRAT", days_ago=6)
    # target ALREADY follows the strategy game (it's in their engaged set) → must never be recommended back
    prof = make_profile(101, engaged=movies + ["Game:STRAT"])
    collab = CollaborativeIndex(ds)
    exclude = set(movies) | {"Game:STRAT"}
    _pc, flat, conf, _cs, _nb = build_collaborative_candidates(prof, collab, ds, NOW, exclude)
    check("already-followed cross-attribute item is NEVER a collaborative candidate",
          "Game:STRAT" not in {c.entity_id for c in flat}, f"flat={sorted(c.entity_id for c in flat)}")


def test_endorsement_gate_not_taste_gate():
    print("\n##### (3) ENDORSEMENT gate (≥MIN_ENDORSERS), NOT a taste gate (cross-attribute allowed) #####")
    ds = FakeDS()
    movies = ["Movie:H1", "Movie:H2", "Movie:H3", "Movie:H4"]
    for e in movies:
        ds.add_entity(e, "movie", ["Horror"], ["horror", "supernatural"])
    ds.add_entity("Game:SOLO", "game", ["Strategy"], ["strategy"])      # endorsed by ONE neighbor → gated OUT
    ds.add_entity("Game:MANY", "game", ["Puzzle"], ["puzzle"])          # endorsed by THREE neighbors → kept (cross-attribute)
    cohort = [201, 202, 203, 204]
    _horror_cohort(ds, movies, users=cohort)
    ds.follow(201, "Game:SOLO", days_ago=5)                              # 1 endorser
    for u in (201, 202, 203):
        ds.follow(u, "Game:MANY", days_ago=5)                           # 3 endorsers
    prof = make_profile(101, engaged=movies)
    collab = CollaborativeIndex(ds)
    _pc, flat, conf, _cs, _nb = build_collaborative_candidates(prof, collab, ds, NOW, set(movies))
    ids = {c.entity_id for c in flat}
    check(f"single-endorser item GATED OUT (< MIN_ENDORSERS={config.V2_COLLAB_MIN_ENDORSERS})", "Game:SOLO" not in ids)
    check("multi-endorser CROSS-attribute item KEPT (endorsement-gated, not taste-gated)", "Game:MANY" in ids,
          f"flat={sorted(ids)}")


def main():
    print("=" * 92)
    print(f"V2-P9 COLLABORATIVE — controlled bubble-escape proofs  (W_COLLABORATIVE={config.V2_W_COLLABORATIVE}, "
          f"SIM_MIN={config.V2_COLLAB_SIM_MIN}, CONF_FULL={config.V2_COLLAB_CONFIDENCE_FULL}, "
          f"MIN_ENDORSERS={config.V2_COLLAB_MIN_ENDORSERS})")
    print("=" * 92)
    test_neighborhood_and_niche_confidence()
    test_bubble_escape_core_proof()
    test_thin_neighborhood_fallback()
    test_already_known_exclusion()
    test_endorsement_gate_not_taste_gate()
    print(f"\n{'='*92}\nRESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}\n{'='*92}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
