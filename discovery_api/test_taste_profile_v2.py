"""V2-P2 test + report: engagement log + time-decayed clustered taste profile.

Runs the SAME profile math on: a zero-signal user (cold_start), real user 12305, and three SYNTHETIC
users built in-memory over REAL served entities (CSVs are never modified). Proves recency shifts taste
(recent horror > older comedy) and vertical-% smoothing keeps a sparse user moderate (sharpening as
signal grows). Run:  .venv/bin/python discovery_api/test_taste_profile_v2.py
"""
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # repo root on path

from discovery_api.src import config, timeutil
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.feed.taste_profile import (
    SIGNAL_FOLLOW, SIGNAL_REACTION, build_taste_profile, build_taste_profile_from_log, make_engagement,
)

FAILS = []
def check(name, cond, detail=""):
    print(f"   [{'PASS' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")
    if not cond:
        FAILS.append(name)


def pick(ds, vertical, genre, n, exclude=()):
    """First n REAL served entities of (vertical, genre) with keywords + a bridged property_id."""
    out = []
    for e in ds.get_entities_by_vertical(vertical):
        if e.entity_id in exclude:
            continue
        if genre in e.canonical_genres and e.bm25_keywords and ds.entity_id_to_property_id(e.entity_id):
            out.append(e.entity_id)
            if len(out) >= n:
                break
    return out


def show(p, title, n_attr=8):
    print(f"\n{'='*92}\n{title}\n{'='*92}")
    print(f"  mode={p.mode}  signal_strength={p.signal_strength}  "
          f"engagements={p.n_engagements} (follows={p.n_follows}, reactions={p.n_reactions})  "
          f"total_effective_weight={p.total_effective_weight}")
    if p.resolution_stats:
        print(f"  resolution: {p.resolution_stats}")
    if p.mode == "cold_start" and p.n_engagements == 0:
        print(f"  vertical_percentages (smoothed→uniform): "
              f"{ {v: round(x,3) for v,x in p.vertical_percentages.items()} }")
        return
    print(f"  decay-weighted TOP GENRES : " + ", ".join(f"{g}={w:.3f}" for g, w in p.top_genres[:n_attr]))
    print(f"  decay-weighted TOP KEYWORDS: " + ", ".join(f"{k}={w:.3f}" for k, w in p.top_keywords[:n_attr]))
    print(f"  community_support (top): {p.community_support[:4]}   mean_influence={p.mean_influence}")
    print("  BAND VIEW (disjoint; per-engagement, no double-count):")
    for label, _ in config.V2_RECENCY_BANDS:
        b = p.band_view.get(label, {"count": 0, "weight": 0.0})
        if b["count"]:
            print(f"      {label:7} count={b['count']:<3} weight={b['weight']:.3f}")
    print("  VERTICAL allocation:")
    for v in config.VERTICALS:
        print(f"      {v:8} raw={p.raw_vertical_weights[v]:<8} "
              f"true%={p.vertical_percentages_true[v]*100:5.1f}   smoothed%={p.vertical_percentages[v]*100:5.1f}")
    print(f"  TASTE CLUSTERS ({len(p.clusters)}):")
    for c in p.clusters:
        print(f"    #{c.cluster_id} «{c.label}»  weight={c.cluster_weight} (share={c.cluster_share})  "
              f"size={c.size}  dominant_vertical={c.dominant_vertical} {c.dominant_verticals}")
        print(f"        top_genres   : {[(g, w) for g, w in c.top_genres[:5]]}")
        print(f"        top_keywords : {[k for k, _ in c.top_keywords[:6]]}")
        print(f"        reps (anchors→V2-P3): {c.top_representative_member_entity_ids}")
        print(f"        recency      : {c.recency_summary}")


def main():
    ds = CsvDataSource().load()
    now = timeutil.now()
    print(f"now = {now.isoformat()}   half_life={config.V2_RECENCY_HALFLIFE_DAYS}d   "
          f"smoothing_strength={config.V2_VERTICAL_SMOOTHING_STRENGTH}   max_clusters={config.V2_MAX_CLUSTERS}")

    # ── 1. zero-signal user → cold_start empty ──
    print("\n##### TEST 1 — zero-signal user (10060) #####")
    z = build_taste_profile(10060, now, ds)
    show(z, "USER 10060 (zero signal)")
    check("zero-signal → cold_start", z.mode == "cold_start")
    check("zero-signal → no engagements/clusters", z.n_engagements == 0 and not z.clusters)
    check("zero-signal → uniform smoothed verticals (~0.25 each)",
          all(abs(z.vertical_percentages[v] - 0.25) < 1e-6 for v in config.VERTICALS))

    # ── 2. real user 12305 ──
    print("\n##### TEST 2 — real user 12305 #####")
    p = build_taste_profile(12305, now, ds)
    show(p, "USER 12305 (real follows + reactions)")
    check("12305 → personalized", p.mode == "personalized")
    check("12305 → has clusters", len(p.clusters) >= 1)
    check("12305 → vertical % sum ≈ 1", abs(sum(p.vertical_percentages.values()) - 1.0) < 1e-6)

    # ── 3. synthetic CROSS-VERTICAL user: OLDER comedy vs RECENT horror ──
    print("\n##### TEST 3 — synthetic CROSS-VERTICAL user (older comedy vs recent horror) #####")
    older = now - timedelta(days=45)     # comedy follows are OLD
    recent = now - timedelta(days=2)     # horror follows are RECENT
    comedy = ([(e, "movie") for e in pick(ds, "movie", "Comedy", 3)] +
              [(e, "tv") for e in pick(ds, "tv", "Comedy", 2)])
    horror = ([(e, "movie") for e in pick(ds, "movie", "Horror", 3, exclude={e for e, _ in comedy})] +
              [(e, "game") for e in pick(ds, "game", "Horror", 2)] +
              [(e, "tv") for e in pick(ds, "tv", "Horror", 2)])
    print(f"  fixtures: OLDER comedy ({older.date()}): "
          f"{[(e, v, ds.get_entity(e).name) for e, v in comedy]}")
    print(f"            RECENT horror ({recent.date()}): "
          f"{[(e, v, ds.get_entity(e).name) for e, v in horror]}")
    log = ([make_engagement(e, SIGNAL_FOLLOW, older, now) for e, _ in comedy] +
           [make_engagement(e, SIGNAL_FOLLOW, recent, now) for e, _ in horror])
    cv = build_taste_profile_from_log(log, ds, now, user_id=900001,
                                      resolution_stats={"synthetic": len(log)})
    show(cv, "SYNTHETIC cross-vertical user 900001")
    gh, gc = cv.genre_weights.get("Horror", 0.0), cv.genre_weights.get("Comedy", 0.0)
    print(f"\n  >>> RECENCY EFFECT: Horror weight {gh:.3f}  vs  Comedy weight {gc:.3f}  "
          f"(equal follow counts; horror is recent → outweighs older comedy)")
    check("recent horror outweighs older comedy", gh > gc, f"Horror={gh:.3f} > Comedy={gc:.3f}")
    verts_in_clusters = {c.dominant_vertical for c in cv.clusters} | {
        v for c in cv.clusters for v, w in c.dominant_verticals if w > 0}
    check("profile is genuinely cross-vertical", len(verts_in_clusters) >= 2, f"verticals={sorted(verts_in_clusters)}")

    # ── 4. synthetic SPARSE user (2-3 follows) → smoothing keeps % moderate ──
    print("\n##### TEST 4 — synthetic SPARSE user (3 recent comedy movies) #####")
    sparse_e = pick(ds, "movie", "Comedy", 3)
    sp_log = [make_engagement(e, SIGNAL_FOLLOW, now - timedelta(days=3), now) for e in sparse_e]
    sp = build_taste_profile_from_log(sp_log, ds, now, user_id=900002,
                                      resolution_stats={"synthetic": len(sp_log)})
    show(sp, "SYNTHETIC sparse user 900002")
    mv_true, mv_smooth = sp.vertical_percentages_true["movie"], sp.vertical_percentages["movie"]
    print(f"\n  >>> SMOOTHING: movie true%={mv_true*100:.0f}  ->  smoothed%={mv_smooth*100:.0f}  "
          f"(3 follows shouldn't yield a 100% allocation)")
    check("sparse user smoothed movie% is moderate (<60%)", mv_smooth < 0.60, f"{mv_smooth*100:.0f}%")
    check("sparse user true movie% is extreme (==100%)", abs(mv_true - 1.0) < 1e-6)

    # ── 5. synthetic RICH single-taste user → % sharpen as signal grows ──
    print("\n##### TEST 5 — synthetic RICH single-taste user (12 recent horror movies) #####")
    rich_e = pick(ds, "movie", "Horror", 12)
    r_log = [make_engagement(e, SIGNAL_FOLLOW, now - timedelta(days=3), now) for e in rich_e]
    rp = build_taste_profile_from_log(r_log, ds, now, user_id=900003,
                                      resolution_stats={"synthetic": len(r_log)})
    show(rp, "SYNTHETIC rich single-taste user 900003")
    print(f"\n  >>> SHARPENING: sparse movie smoothed%={mv_smooth*100:.0f}  <  "
          f"rich movie smoothed%={rp.vertical_percentages['movie']*100:.0f}  (more signal → sharper)")
    check("rich-user movie% sharper than sparse-user movie%",
          rp.vertical_percentages["movie"] > mv_smooth)
    check("rich single-taste collapses to few clusters", len(rp.clusters) <= 2, f"{len(rp.clusters)} clusters")

    print(f"\n{'='*92}\nRESULT: {'ALL PASS' if not FAILS else 'FAILURES: ' + ', '.join(FAILS)}\n{'='*92}")
    return 1 if FAILS else 0


if __name__ == "__main__":
    sys.exit(main())
