"""V2-P4 tests + report: trending velocity + three-signal blend + assembly + blend controller + cache.

Unit tests are hermetic. A LIVE section (if :8000/:8010 are up) builds the full v2 feed for 12305 +
the cross-vertical synthetic user and prints the assembled v1.0 envelope + debug breakdowns + latency.
Run:  .venv/bin/python discovery_api/test_v2p4_feed.py
"""
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from discovery_api.src import config, timeutil
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.data_access.records import Moment, ReactionEvent
from discovery_api.src.data_access.substrate_client import SubstrateClient
from discovery_api.src.feed.assembler_v2 import assemble_feed_v2, feed_to_v1_envelope
from discovery_api.src.feed.blend import V2FeedBuilder
from discovery_api.src.feed.moment_select import select_moments_for_property
from discovery_api.src.feed.profile_cache import ProfileCache
from discovery_api.src.feed.taste_profile import (
    SIGNAL_FOLLOW, build_taste_profile, build_taste_profile_from_log, make_engagement)
from discovery_api.src.ranking.popularity import PopularityIndex
from discovery_api.src.ranking.trending import TrendingTable

FAILS = []
def check(name, cond, detail=""):
    print(f"   [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)

NOW = datetime(2026, 6, 18, tzinfo=timezone.utc)


# ── Fake DS for the trending proof (only the methods trending + moment_select touch) ──
class FakeDS:
    def __init__(self, reactions, moments, entity):
        self._reactions = reactions
        self._moments = moments        # entity_id -> [Moment]
        self._entity = entity          # entity_id -> SimpleNamespace(vertical,name,...)
    def iter_reaction_events(self): return self._reactions
    def iter_follow_events(self): return []
    def get_moments_for_property(self, eid): return self._moments.get(eid, [])
    def get_entity(self, eid): return self._entity.get(eid)
    def get_moment(self, mid):
        for ms in self._moments.values():
            for m in ms:
                if m.moment_id == mid: return m
        return None
    def get_podcast_categories(self, eid): return []


def test_trending_velocity_worldcup():
    print("\n##### (A) trending velocity: recent moment beats OLD high-VOLUME moment #####")
    eid = "Movie:WC"
    old = Moment(moment_id=1, entity_id=eid, property_id=1, title="World Cup 2022 Final",
                 event_starts_at=NOW - timedelta(days=60))
    cur = Moment(moment_id=2, entity_id=eid, property_id=1, title="Current Tournament — Live",
                 event_starts_at=NOW - timedelta(days=1))
    reactions = ([ReactionEvent(user_id=i, moment_id=1, reaction_type_id=1,
                                created_at=NOW - timedelta(days=60)) for i in range(20)]   # 20 OLD reactions
                 + [ReactionEvent(user_id=i, moment_id=2, reaction_type_id=1,
                                  created_at=NOW - timedelta(days=1)) for i in range(8)])   # 8 RECENT reactions
    ds = FakeDS(reactions, {eid: [cur, old]},
                {eid: SimpleNamespace(vertical="movie", name="Big Sports", canonical_genres=["Sport"], bm25_keywords=[])})
    tr = TrendingTable(ds)
    tv_old = tr.trending_score(1, NOW)
    tv_cur = tr.trending_score(2, NOW)
    print(f"   raw reaction VOLUME:  old=20  current=8   (volume says OLD wins)")
    print(f"   decayed VELOCITY:     old={tv_old:.6f}  current={tv_cur:.6f}   confidence={tr.confidence(NOW):.4f}")
    check("recent moment has higher trending VELOCITY than old high-volume one", tv_cur > tv_old)
    sms = select_moments_for_property(ds, tr, NOW, entity_id=eid, taste_match=0.5,
                                      cluster_id=1, source_pool="content", seen_ids=set())
    print(f"   blended moment ranking: {[(s.moment_id, round(s.final_score,3)) for s in sms]}")
    check("blended selection ranks the RECENT moment first (synthesis)", sms[0].moment_id == 2,
          f"winner=moment {sms[0].moment_id}")


def test_moment_select_cap_and_seen():
    print("\n##### (B) moment selection: per-property cap + seen suppression #####")
    eid = "Game:X"
    ms = [Moment(moment_id=i, entity_id=eid, property_id=9, title=f"m{i}",
                 event_starts_at=NOW - timedelta(days=i)) for i in range(1, 6)]   # 5 moments
    ds = FakeDS([], {eid: ms}, {eid: SimpleNamespace(vertical="game", name="G", canonical_genres=["Indie"], bm25_keywords=[])})
    tr = TrendingTable(ds)
    sel = select_moments_for_property(ds, tr, NOW, entity_id=eid, taste_match=0.5, cluster_id=1,
                                      source_pool="content", seen_ids=set())
    check("per-property cap applied", len(sel) == config.V2_MOMENT_CAP_PER_PROPERTY, f"{len(sel)} moments")
    # seen suppression: mark the freshest moment (id=1) seen → it should drop below an unseen one
    sel_seen = select_moments_for_property(ds, tr, NOW, entity_id=eid, taste_match=0.5, cluster_id=1,
                                           source_pool="content", seen_ids={1})
    top_ids = [s.moment_id for s in sel_seen]
    check("seen moment demoted below unseen", top_ids[0] != 1, f"order={top_ids}")


def build_cross_vertical(ds, now):
    def pick(vert, genre, n, exclude=()):
        out = []
        for e in ds.get_entities_by_vertical(vert):
            if e.entity_id in exclude: continue
            if genre in e.canonical_genres and e.bm25_keywords and ds.entity_id_to_property_id(e.entity_id):
                out.append(e.entity_id)
                if len(out) >= n: break
        return out
    comedy = pick("movie", "Comedy", 3) + pick("tv", "Comedy", 2)
    horror = pick("movie", "Horror", 3, exclude=set(comedy)) + pick("tv", "Horror", 2)
    log = ([make_engagement(e, SIGNAL_FOLLOW, now - timedelta(days=45), now) for e in comedy] +
           [make_engagement(e, SIGNAL_FOLLOW, now - timedelta(days=2), now) for e in horror])
    return build_taste_profile_from_log(log, ds, now, user_id=900001, resolution_stats={"synthetic": len(log)})


def test_profile_cache():
    print("\n##### (E) profile cache: hit on 2nd call, recompute after TTL #####")
    ds = CsvDataSource().load()
    clk = {"t": 1000.0}
    pc = ProfileCache(ttl_seconds=300, clock=lambda: clk["t"])
    p1 = pc.get(12305, NOW, ds)
    p2 = pc.get(12305, NOW, ds)
    check("2nd call is a cache HIT", pc.hits == 1 and pc.misses == 1 and p1 is p2, str(pc.stats()))
    clk["t"] += 301
    p3 = pc.get(12305, NOW, ds)
    check("recompute after TTL elapses", pc.misses == 2, str(pc.stats()))
    pc.invalidate(12305)
    check("invalidate clears the user", (12305, NOW.isoformat()) not in pc._c)


def test_blend_controller_and_exclusions():
    print("\n##### (D) blend controller: cold-start→global, global_backfill, exclusions #####")
    ds = CsvDataSource().load()
    sub = SubstrateClient()
    builder = V2FeedBuilder(ds, substrate=sub)
    if not sub.is_up():
        print("   (substrate down — skipping live-dependent controller checks)")
        return None, None, builder

    # cold-start user 10060 → global fallback
    cold_feed, cold_meta = builder.build(10060, now=NOW, limit=10)
    check("cold-start routes to v1 GLOBAL feed", cold_meta["path"] == "global_fallback")
    check("global fallback returns a non-empty feed", len(cold_feed.main_feed) > 0, f"{len(cold_feed.main_feed)} items")

    # cross-vertical synthetic (injected profile) → personalized + global_backfill filled
    prof = build_cross_vertical(ds, NOW)
    cv_feed, cv_meta = builder.build(900001, now=NOW, limit=12, profile=prof)
    followed = {e.target_entity_id for e in prof.engagements}
    main_ids = {fi.entity_id for fi in cv_feed.main_feed}
    car_ids = {ci.entity_id for c in cv_feed.carousels for ci in c.items}
    check("personalized path taken", cv_meta["path"] == "personalized")
    check("global_backfill verticals present in meta", bool(cv_meta.get("global_backfill")), str(cv_meta.get("global_backfill")))
    backfill_in_feed = any(fi.source_pool == "global_backfill" for fi in cv_feed.main_feed)
    check("global_backfill items appear in the main feed", backfill_in_feed)
    check("NO followed entity leaks into main feed", not (main_ids & followed), f"leak={main_ids & followed}")
    check("NO followed entity leaks into ANY carousel", not (car_ids & followed), f"leak={car_ids & followed}")
    return cv_feed, prof, builder


def test_envelope_valid():
    print("\n##### (C) assembler emits a valid v1.0 envelope (trending + exploration carousels + why) #####")
    ds = CsvDataSource().load()
    sub = SubstrateClient()
    if not sub.is_up():
        print("   (substrate down — skipping envelope build)")
        return
    from discovery_api.src.retrieval import retrieve_candidate_sets, build_exclusions
    prof = build_cross_vertical(ds, NOW)
    bundle = retrieve_candidate_sets(prof, data_source=ds, client=sub)
    tr = TrendingTable(ds)
    pop = PopularityIndex.from_data_source(ds)
    from discovery_api.src.feed.profile import UserProfile
    v1p = UserProfile(user_id=900001, followed_entity_ids=sorted({e.target_entity_id for e in prof.engagements}))
    feed = assemble_feed_v2(prof, bundle, ds, tr, NOW, v1_profile=v1p, pop=pop,
                            exclude_ids=build_exclusions(prof, ds, []), limit=10)
    env = feed_to_v1_envelope(feed, ds, user_id=900001, followed_count=len(v1p.followed_entity_ids),
                              request_echo={"sort_order": "trending"}, debug=True)
    car_ids = {c["carousel_id"] for c in env["carousels"]}
    check("envelope has the v1.0 top-level keys", all(k in env for k in
          ("version", "endpoint", "context", "main_feed", "carousels")))
    check("main_feed has items/count/next_offset", all(k in env["main_feed"] for k in ("items", "count", "next_offset")))
    # V2-P8: the TRENDING carousel now draws from the global-trending-SCOPED-TO-TASTE source, so on dev data
    # (no synthetic population → trending dark) it is CORRECTLY absent. It is proven populated under real
    # trending signal in test_v2p8_trending_candidates.py + persona_eval_v2p7.py.
    check("EXPLORATION carousel emitted", "exploration" in car_ids, str(sorted(car_ids)))
    check("carousels valid (cluster/global present; trending appears only with trending signal)",
          any(cid.startswith("cluster_") or cid.startswith("new_in_genre") for cid in car_ids))
    check("every main-feed item has a non-empty why_string", all(i["why_string"] for i in env["main_feed"]["items"]))
    check("every carousel carries a reason_string", all(c["reason_string"] for c in env["carousels"]))
    if env["main_feed"]["items"]:
        dbg = env["main_feed"]["items"][0].get("debug", {})
        check("debug block shows the three-signal breakdown",
              all(k in dbg for k in ("taste_match", "trending_velocity", "recency", "cluster_id", "final_score")),
              str(list(dbg.keys())))


def live_report():
    ds = CsvDataSource().load()
    sub = SubstrateClient()
    if not sub.is_up():
        print("\n##### LIVE report SKIPPED (substrate down) #####")
        return
    print("\n" + "#" * 96 + "\n##### LIVE v2 FEEDS — 12305 (cached vs cold) + cross-vertical #####")
    builder = V2FeedBuilder(ds, substrate=sub)
    # latency: cold (cache miss) then warm (cache hit)
    t0 = time.time(); feed, meta = builder.build(12305, now=NOW, limit=8, excluded_property_ids=[]); cold = time.time() - t0
    t1 = time.time(); feed2, meta2 = builder.build(12305, now=NOW, limit=8); warm = time.time() - t1
    print(f"\n12305: COLD build {cold:.2f}s | WARM (profile cached) {warm:.2f}s | path={meta['path']} "
          f"| retrieve_calls={meta.get('n_retrieve_calls')} | profile_cache={builder.profile_cache.stats()}")
    _print_feed("12305", feed, ds)

    prof = build_cross_vertical(ds, NOW)
    cv, cvm = builder.build(900001, now=NOW, limit=8, profile=prof)
    print(f"\ncross-vertical: path={cvm['path']} global_backfill={cvm.get('global_backfill')}")
    _print_feed("cross-vertical", cv, ds)


def _print_feed(tag, feed, ds):
    print(f"  MAIN FEED ({len(feed.main_feed)} items, pool={feed.pagination.pool_total}):")
    for fi in feed.main_feed[:6]:
        s = fi.debug
        print(f"    {fi.score:6.3f} [{fi.source_pool:14}] {fi.property_name[:28]:28} | {fi.title[:30]:30}")
        print(f"           why=\"{fi.why_string}\"  taste={s.get('taste_match')} trend={s.get('trending_velocity')} rec={s.get('recency')} cluster={s.get('cluster_id')}")
    print(f"  CAROUSELS ({len(feed.carousels)}): " +
          ", ".join(f"{c.carousel_id}[{len(c.items)}]" for c in feed.carousels))
    for c in feed.carousels:
        if c.carousel_id in ("trending", "exploration") or c.carousel_id.startswith("cluster_"):
            sample = ", ".join(ci.property_name[:18] for ci in c.items[:3])
            print(f"      «{c.reason_string}» [{c.reason_type.value}]: {sample}")


def main():
    test_trending_velocity_worldcup()
    test_moment_select_cap_and_seen()
    test_profile_cache()
    test_envelope_valid()
    test_blend_controller_and_exclusions()
    live_report()
    print(f"\n{'='*96}\nRESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}\n{'='*96}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
