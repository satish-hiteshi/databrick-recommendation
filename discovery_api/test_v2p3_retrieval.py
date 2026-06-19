"""V2-P3 tests + report: content-based retrieval (Source 2) + exploration (Source 3).

Unit tests run on a MOCKED substrate (hermetic). A final LIVE section (only if :8000/:8010 are up) measures
12305's personalized retrieval wall-time and prints the candidate bundle for the report.
Run:  .venv/bin/python discovery_api/test_v2p3_retrieval.py
"""
import sys
import time
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from discovery_api.src import config, timeutil
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.data_access.substrate_client import SubstrateClient
from discovery_api.src.feed.clustering import TasteCluster
from discovery_api.src.feed.taste_profile import (
    SIGNAL_FOLLOW, build_taste_profile, build_taste_profile_from_log, make_engagement)
from discovery_api.src.retrieval import (
    allocate, build_content_candidates, build_exploration, compose_query, retrieve_candidate_sets)

FAILS = []
def check(name, cond, detail=""):
    print(f"   [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


def make_cluster(cid, label, vertical, share, genres, keywords, reps):
    return TasteCluster(
        cluster_id=cid, label=label, member_entity_ids=list(reps),
        top_representative_member_entity_ids=list(reps), dominant_vertical=vertical,
        dominant_verticals=[(vertical, 1.0)], top_genres=[(g, w) for g, w in genres],
        top_keywords=[(k, w) for k, w in keywords], cluster_weight=share * 10, cluster_share=share,
        size=len(reps), recency_summary={})


def stub_profile(clusters, vpct, signal=0.5, genre_weights=None, comms=None, engaged=()):
    eng = [SimpleNamespace(target_entity_id=e, signal_type=SIGNAL_FOLLOW) for e in engaged]
    return SimpleNamespace(
        user_id=42, mode="personalized", signal_strength=signal, clusters=clusters,
        vertical_percentages=vpct, genre_weights=genre_weights or {}, community_support=comms or [],
        engagements=eng)


# ── Mock substrate ───────────────────────────────────────────────────────────
class FakeClient:
    """Deterministic canned substrate. Records calls. Returns include a FOLLOWED id + an OVERLAP id."""
    def __init__(self):
        self.calls = []

    def vector_retrieve(self, phrase, vertical=None, top_k=50):
        self.calls.append(("vector_retrieve", vertical))
        v = (vertical or "movie").title()
        return [{"entity_id": f"{v}:V1", "name": "Vec One", "vertical": vertical, "score": 0.60},
                {"entity_id": f"{v}:OV", "name": "Overlap", "vertical": vertical, "score": 0.55},
                {"entity_id": f"{v}:F1", "name": "Followed!", "vertical": vertical, "score": 0.54},  # must be excluded
                {"entity_id": f"{v}:V2", "name": "Vec Two", "vertical": vertical, "score": 0.50}]

    def graph_structured(self, vertical=None, genre=None, keyword=None, concept=None, franchise=None, top_k=10):
        self.calls.append(("graph_structured", vertical, tuple(genre or [])))
        v = (vertical or "movie").title()
        return [{"entity_id": f"{v}:OV", "name": "Overlap", "vertical": vertical, "score": 3.0},   # dedupe w/ vector
                {"entity_id": f"{v}:G1", "name": "Graph One", "vertical": vertical, "score": 2.0}]

    def graph_similar(self, entity_id, top_k=10, vertical=None):
        self.calls.append(("graph_similar", entity_id))
        v = (vertical or "movie").title()
        return [{"entity_id": f"{v}:S1", "name": "Sim One", "vertical": vertical, "score": 0.9}]

    def graph_score_within(self, entity_ids):
        self.calls.append(("graph_score_within", len(entity_ids)))
        return {}


def test_composer():
    print("\n##### composer #####")
    c = make_cluster(1, "Horror + Mystery", "movie", 0.9,
                     [("Horror", 4.6), ("Mystery", 1.8)], [("horror", 1.0), ("supernatural", 0.8)], ["Movie:1"])
    phrase, which = compose_query(c, composer="deterministic")
    check("deterministic composer puts genres+keywords in phrase",
          "Horror" in phrase and "supernatural" in phrase and which == "deterministic", phrase)
    check("genre canonical capitalisation preserved", "Horror" in phrase and "horror," in phrase.lower())


def test_content_merge_exclusions_dedupe():
    print("\n##### per-cluster retrieval: merge + provenance + exclusions + dedupe #####")
    clusters = [make_cluster(1, "Horror", "movie", 0.7, [("Horror", 4.0)], [("horror", 1.0)], ["Movie:R1", "Movie:R2"]),
                make_cluster(2, "Strategy", "game", 0.3, [("Strategy", 2.0)], [("isometric", 1.0)], ["Game:R1"])]
    fc = FakeClient()
    exclude = {"Movie:F1", "Game:F1", "Movie:R1", "Movie:R2", "Game:R1"}   # followed + the cluster seeds
    sets, n_ret, n_sub = build_content_candidates(stub_profile(clusters, {}), fc, exclude)
    all_ids = {c.entity_id for cs in sets for c in cs.candidates}
    check("n_retrieve_calls == n_clusters (latency fix)", n_ret == 2, f"{n_ret}")
    check("followed id never leaks into candidates", "Movie:F1" not in all_ids and "Game:F1" not in all_ids)
    # provenance + dedupe: OV returned by BOTH vector and graph_structured → ONE candidate, two paths
    movie_set = next(cs for cs in sets if cs.cluster_id == 1)
    ov = [c for c in movie_set.candidates if c.entity_id == "Movie:OV"]
    check("overlap candidate deduped to one entry", len(ov) == 1)
    check("provenance records BOTH paths on overlap", ov and set(ov[0].paths) == {"vector", "graph_structured"},
          str(ov[0].paths) if ov else "missing")
    check("both-path candidate scored highest (vector+graph+bonus)",
          movie_set.candidates[0].entity_id == "Movie:OV", movie_set.candidates[0].entity_id)
    check("every content candidate tagged source_pool=content + cluster_id",
          all(c.source_pool == "content" and c.cluster_id in (1, 2) for cs in sets for c in cs.candidates))


def test_allocation():
    print("\n##### percentage allocation (vertical_percentages × cluster_share) #####")
    clusters = [make_cluster(1, "Horror", "movie", 0.5, [("Horror", 1)], [("horror", 1)], ["Movie:1"]),
                make_cluster(2, "Comedy", "movie", 0.1, [("Comedy", 1)], [("comedy", 1)], ["Movie:2"]),
                make_cluster(3, "Strategy", "game", 0.4, [("Strategy", 1)], [("rts", 1)], ["Game:1"])]
    vpct = {"movie": 0.6, "game": 0.4, "tv": 0.0, "podcast": 0.0}
    # give them candidates so slot_quota truncation is observable
    for c in clusters:
        pass
    sets, *_ = build_content_candidates(stub_profile(clusters, vpct, signal=1.0), FakeClient(),
                                        {"Movie:1", "Movie:2", "Game:1"})
    plan = allocate(stub_profile(clusters, vpct, signal=1.0), sets)
    check("low exploration at high signal (frac≈MIN)", abs(plan.exploration_fraction - config.V2_EXPLORE_FRAC_MIN) < 1e-6,
          f"frac={plan.exploration_fraction}")
    check("content+exploration == budget", plan.content_slots + plan.exploration_slots == config.V2_CANDIDATE_BUDGET)
    check("movie gets more vertical budget than game (0.6 vs 0.4)", plan.by_vertical["movie"] > plan.by_vertical["game"])
    check("within movie, Horror(0.5) outslots Comedy(0.1)", plan.by_cluster[1] > plan.by_cluster[2])
    check("every cluster >= MIN_CLUSTER_SLOTS", all(q >= config.V2_MIN_CLUSTER_SLOTS for q in plan.by_cluster.values()))
    check("no global_backfill when every funded vertical has a cluster", not plan.global_backfill)
    # exploration sizing by signal
    plan_low = allocate(stub_profile(clusters, vpct, signal=0.1), sets)
    check("exploration grows as signal falls", plan_low.exploration_slots > plan.exploration_slots,
          f"{plan_low.exploration_slots} > {plan.exploration_slots}")


def test_exploration_adjacency():
    print("\n##### exploration: structured adjacency (shared+new), sized, excludes followed #####")
    clusters = [make_cluster(1, "Horror", "movie", 1.0, [("Horror", 1)], [("horror", 1)], ["Movie:SEED"])]
    prof = stub_profile(clusters, {"movie": 1.0, "game": 0, "tv": 0, "podcast": 0},
                        genre_weights={"Horror": 1.0}, comms=[(100, 1.0)])

    class FC2(FakeClient):
        def graph_structured(self, vertical=None, genre=None, keyword=None, concept=None, franchise=None, top_k=10):
            return [{"entity_id": "Movie:SAME", "name": "Same Community", "vertical": "movie", "score": 1},
                    {"entity_id": "Movie:NEWC", "name": "New Community", "vertical": "movie", "score": 1},
                    {"entity_id": "Movie:FOLLOWED", "name": "Followed", "vertical": "movie", "score": 1}]
        def graph_similar(self, entity_id, top_k=10, vertical=None):
            return [{"entity_id": "Movie:NEWG", "name": "New Genre Neighbor", "vertical": "movie", "score": 1},
                    {"entity_id": "Movie:IDENT", "name": "Identical Genres", "vertical": "movie", "score": 1}]
        def graph_score_within(self, entity_ids):
            return {  # genres lowercase (as the real /graph/score_within returns)
                "Movie:SAME":  {"genres": ["horror"], "community": 100, "influence": 0.9},   # same comm → reject (A)
                "Movie:NEWC":  {"genres": ["horror"], "community": 777, "influence": 0.8},   # new comm  → accept (A)
                "Movie:NEWG":  {"genres": ["horror", "war"], "community": 5, "influence": 0.7},  # new genre → accept (B)
                "Movie:IDENT": {"genres": ["horror"], "community": 5, "influence": 0.6},     # no new genre → reject (B)
            }
    explore, _ = build_exploration(prof, FC2(), {"Movie:FOLLOWED", "Movie:SEED"}, explore_slots=10)
    ids = {c.entity_id for c in explore}
    check("accepts shared-genre NEW-community (rule A)", "Movie:NEWC" in ids)
    check("rejects shared-genre SAME-community", "Movie:SAME" not in ids)
    check("accepts neighbour with a NEW genre (rule B)", "Movie:NEWG" in ids)
    check("rejects neighbour with NO new genre", "Movie:IDENT" not in ids)
    check("excluded/followed never appears", "Movie:FOLLOWED" not in ids)
    check("EVERY exploration cand is adjacent-not-identical (shared>=1 AND new>=1)",
          all(len(c.shared_attrs) >= 1 and len(c.new_attrs) >= 1 for c in explore))
    check("EVERY exploration cand tagged with its adjacency rule",
          all(c.source_pool == "exploration" and c.adjacency_rule for c in explore))
    newc = next(c for c in explore if c.entity_id == "Movie:NEWC")
    check("rule-A provenance: shares the genre, new attr is the community",
          newc.shared_attrs == ["Horror"] and newc.new_attrs == ["community:777"], f"{newc.shared_attrs}/{newc.new_attrs}")
    newg = next(c for c in explore if c.entity_id == "Movie:NEWG")
    check("rule-B provenance: shares 'horror', introduces 'war'",
          "horror" in newg.shared_attrs and "war" in newg.new_attrs, f"{newg.shared_attrs}/{newg.new_attrs}")


def build_cross_vertical(ds, now):
    def pick(vert, genre, n, exclude=()):
        out = []
        for e in ds.get_entities_by_vertical(vert):
            if e.entity_id in exclude:
                continue
            if genre in e.canonical_genres and e.bm25_keywords and ds.entity_id_to_property_id(e.entity_id):
                out.append(e.entity_id)
                if len(out) >= n:
                    break
        return out
    comedy = pick("movie", "Comedy", 3) + pick("tv", "Comedy", 2)
    horror = pick("movie", "Horror", 3, exclude=set(comedy)) + pick("tv", "Horror", 2)
    log = ([make_engagement(e, SIGNAL_FOLLOW, now - timedelta(days=45), now) for e in comedy] +
           [make_engagement(e, SIGNAL_FOLLOW, now - timedelta(days=2), now) for e in horror])
    return build_taste_profile_from_log(log, ds, now, user_id=900001, resolution_stats={"synthetic": len(log)})


def live_report(ds, now):
    client = SubstrateClient()
    if not client.is_up():
        print("\n##### LIVE section SKIPPED (substrate :8000/:8010 down) #####")
        return
    print("\n" + "#" * 96 + "\n##### LIVE retrieval — 12305 + cross-vertical (composer=%s) #####" % config.V2_STRING_COMPOSER)
    for tag, prof in [("12305", build_taste_profile(12305, now, ds)),
                      ("cross-vertical", build_cross_vertical(ds, now))]:
        followed = {e.target_entity_id for e in prof.engagements}
        t0 = time.time()
        bundle = retrieve_candidate_sets(prof, data_source=ds, client=client,
                                         excluded_property_ids=[], seen_ids=[])
        wall = time.time() - t0
        print(f"\n===== {tag}: signal={prof.signal_strength} mode={prof.mode} =====")
        print(f"  WALL-TIME {wall:.2f}s | /api/retrieve calls={bundle.n_retrieve_calls} | "
              f"substrate calls={bundle.n_substrate_calls} | timing_ms={bundle.timing_ms}")
        a = bundle.allocation
        print(f"  ALLOCATION: budget={a.total_budget} content={a.content_slots} exploration={a.exploration_slots} "
              f"(frac={a.exploration_fraction}) by_vertical={a.by_vertical}")
        print(f"              by_cluster={a.by_cluster} global_backfill={a.global_backfill}")
        for cs in bundle.clusters:
            top = cs.candidates[:5]
            print(f"  cluster #{cs.cluster_id} «{cs.label}» ({cs.dominant_vertical}, quota={cs.slot_quota}, "
                  f"cand={len(cs.candidates)}, composer={cs.composer})")
            print(f'      phrase: "{cs.phrase}"')
            for c in top:
                print(f"        {c.score:.3f} {c.entity_id:14} {c.name[:34]:34} paths={c.paths}")
        print(f"  EXPLORATION ({len(bundle.exploration)}):")
        for c in bundle.exploration[:6]:
            print(f"        {c.entity_id:14} {c.name[:30]:30} rule={c.adjacency_rule} "
                  f"shared={c.shared_attrs[:3]} new={c.new_attrs[:2]}")
        # exclusion proof (live)
        cand_ids = set(bundle.all_candidate_ids())
        check(f"[{tag}] NO followed entity leaks into ANY candidate set", not (cand_ids & followed),
              f"leak={cand_ids & followed}")
        check(f"[{tag}] no duplicate entity_id across the whole bundle",
              len(cand_ids) == len(bundle.all_candidate_ids()))
        check(f"[{tag}] every exploration cand adjacent-not-identical + excludes followed",
              all(c.shared_attrs and c.new_attrs and c.entity_id not in followed for c in bundle.exploration))


def main():
    ds = CsvDataSource().load()
    now = timeutil.now()
    test_composer()
    test_content_merge_exclusions_dedupe()
    test_allocation()
    test_exploration_adjacency()
    live_report(ds, now)
    print(f"\n{'='*96}\nRESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}\n{'='*96}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
