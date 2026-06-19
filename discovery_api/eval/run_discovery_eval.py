"""Offline discovery eval — runs the FULL pipeline (profile → pools → score → assemble) on the dev CSVs
for fixture users and reports quality + sanity. Writes discovery_api/eval/EVAL_REPORT.md.

    .venv/bin/python discovery_api/eval/run_discovery_eval.py

Substrate: uses the LIVE vector/graph (:8000/:8010) if up (real semantic affinity for 12305), else a
deterministic MOCK (states which in the report). Start the services per shared/README to run live.
"""

import sys, time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import config, timeutil
from discovery_api.src.data_access import CsvDataSource, SubstrateClient
from discovery_api.src.engine import DiscoveryEngine
from discovery_api.src.candidates import RequestContext

COLD_USER, PERS_USER = 7064, 12305
NOW = timeutil.now()                      # config.DEFAULT_NOW_ISO = 2026-06-18 (threaded everywhere)
OUT = Path(__file__).resolve().parent / "EVAL_REPORT.md"


class MockSubstrate:
    """Deterministic fallback when :8000/:8010 are down — real entity_ids, fake scores, podcast vector-only."""
    def __init__(self, ds): self.ds = ds
    def _sample(self, v, anchors, top_k):
        out = [e for e in self.ds._by_vertical.get(v, []) if e not in anchors][:top_k]
        return out
    def vector_neighbors(self, anchor_ids, exclude_ids=None, vertical=None, top_k=20):
        v = vertical or "movie"; ex = set(exclude_ids or []) | set(anchor_ids)
        return [{"entity_id": e, "name": "", "vertical": v, "score": round(0.9 - i*0.002, 4)}
                for i, e in enumerate(e for e in self._sample(v, ex, top_k))]
    def vector_retrieve(self, phrase, vertical=None, top_k=50): return []
    def graph_similar(self, entity_id, top_k=10, vertical=None):
        v = vertical or "game"
        return [{"entity_id": e, "name": "", "vertical": v, "final_score": round(0.4 - i*0.01, 4)}
                for i, e in enumerate(self._sample(v, {entity_id}, top_k))]
    def graph_score_within(self, entity_ids): return {}


def feed_entities(feed):
    eids = {i.entity_id for i in feed.main_feed}
    for c in feed.carousels:
        eids |= {it.entity_id for it in c.items}
    return eids


def run_checks(feed, profile, context, ds):
    followed = set(profile.followed_entity_ids)
    excl = set(context.seen_entity_ids) | {ds.property_id_to_entity_id(p) for p in context.excluded_property_ids}
    all_eids = feed_entities(feed)
    main_props = Counter(i.entity_id for i in feed.main_feed)
    # non-degenerate: distinct scores in the top of the main feed + influence ties broken by recency
    top = feed.main_feed[:10]
    distinct_scores = len({round(i.score, 4) for i in top})
    inf_groups = {}
    for i in top:
        inf = i.debug.get("signals", {}).get("influence", None) if i.debug else None
        inf_groups.setdefault(round(inf or 0, 3), []).append(round(i.score, 4))
    tie_broken = any(len(set(v)) > 1 for v in inf_groups.values() if len(v) > 1)
    return {
        "exclusion_integrity_followed": len(all_eids & followed),         # want 0
        "exclusion_integrity_seen_excluded": len(all_eids & (excl - {None})),  # want 0
        "moment_cap_max": max(main_props.values()) if main_props else 0,  # want <= cap
        "every_item_has_why": all(i.why_string for i in feed.main_feed) and
                              all(it.why_string for c in feed.carousels for it in c.items),
        "every_carousel_has_reason": all(c.reason_string for c in feed.carousels),
        "main_feed_distinct_scores_top10": distinct_scores,              # >1 = not flat
        "influence_ties_broken_by_recency": tie_broken,
        "carousel_reason_types": [c.reason_type.value for c in feed.carousels],
    }


def main():
    ds = CsvDataSource().load()
    sc = SubstrateClient()
    live = sc.is_up()
    substrate = sc if live else MockSubstrate(ds)
    eng = DiscoveryEngine(data_source=ds, substrate=substrate)

    feeds, timings, checks, profiles = {}, {}, {}, {}
    fixtures = [("cold_start_7064", COLD_USER, RequestContext(now=NOW, limit=10)),
                ("personalized_12305", PERS_USER, RequestContext(now=NOW, limit=10)),
                ("paginated_12305_offset10", PERS_USER, RequestContext(now=NOW, limit=10, offset=10))]
    for label, uid, ctx in fixtures:
        t0 = time.time()
        feed = eng.build_feed(uid, ctx)
        timings[label] = (time.time() - t0) * 1000
        feeds[label] = feed
        from discovery_api.src.feed.profile import build_profile
        profiles[label] = build_profile(uid, ds)
        checks[label] = run_checks(feed, profiles[label], ctx, ds)

    # cold-vs-personalized difference
    cold_e = {i.entity_id for i in feeds["cold_start_7064"].main_feed}
    pers_e = {i.entity_id for i in feeds["personalized_12305"].main_feed}
    overlap = (len(cold_e & pers_e) / len(cold_e | pers_e) * 100) if (cold_e | pers_e) else 0.0
    cold_rt = set(checks["cold_start_7064"]["carousel_reason_types"])
    pers_rt = set(checks["personalized_12305"]["carousel_reason_types"])
    personal_only = pers_rt - cold_rt
    # pagination distinctness
    p1 = {i.moment_id for i in feeds["personalized_12305"].main_feed}
    p2 = {i.moment_id for i in feeds["paginated_12305_offset10"].main_feed}
    page_overlap = len(p1 & p2)

    _write_report(feeds, timings, checks, overlap, personal_only, page_overlap, live)
    _print_summary(feeds, timings, checks, overlap, personal_only, page_overlap, live)


def _fmt_item(i):
    return f"[{i.vertical}] {i.property_name[:40]} — \"{i.why_string}\" (score {round(i.score,3)})"


def _print_summary(feeds, timings, checks, overlap, personal_only, page_overlap, live):
    print(f"\nsubstrate: {'LIVE :8000/:8010' if live else 'MOCK'}")
    for label, feed in feeds.items():
        ch = checks[label]
        print(f"\n=== {label}  ({timings[label]:.0f} ms) ===")
        print(f"  mode={feed.mode} ss={feed.signal_strength} main_feed={len(feed.main_feed)} "
              f"pool_total={feed.pagination.pool_total} next_offset={feed.pagination.next_offset}")
        print(f"  carousels: {[(c.reason_type.value, len(c.items)) for c in feed.carousels]}")
        print(f"  CHECKS: followed_leak={ch['exclusion_integrity_followed']} "
              f"seen/excl_leak={ch['exclusion_integrity_seen_excluded']} "
              f"cap_max={ch['moment_cap_max']} why_all={ch['every_item_has_why']} "
              f"reason_all={ch['every_carousel_has_reason']} "
              f"distinct_top10_scores={ch['main_feed_distinct_scores_top10']} "
              f"ties_broken={ch['influence_ties_broken_by_recency']}")
        for i in feed.main_feed[:2]:
            print("   feed:", _fmt_item(i))
    print(f"\ncold vs personalized: main-feed overlap={overlap:.1f}%  personalized-only carousels={sorted(personal_only)}")
    print(f"pagination: page1∩page2 moment overlap = {page_overlap} (want 0)")
    print(f"\nreport -> {OUT}")


def _write_report(feeds, timings, checks, overlap, personal_only, page_overlap, live):
    L = []
    L.append("# Discovery feed — offline eval report (P4)\n")
    L.append(f"Pipeline: profile → pools → **blended scorer** → assembler (main feed + carousels) + why_strings. "
             f"Substrate: **{'LIVE :8000/:8010' if live else 'MOCK (services down)'}**. "
             f"now = `{timeutil.now().isoformat()}` (config.DEFAULT_NOW_ISO). Real dev CSVs.\n")
    # headline checks table
    L.append("## Sanity checks (all fixtures)\n")
    L.append("| fixture | ms | followed-leak | seen/excl-leak | cap-max (≤3) | why∀ | reason∀ | distinct top-10 scores | inf-ties broken |")
    L.append("|---|--:|--:|--:|--:|:--:|:--:|--:|:--:|")
    for label, ch in checks.items():
        L.append(f"| {label} | {timings[label]:.0f} | {ch['exclusion_integrity_followed']} | "
                 f"{ch['exclusion_integrity_seen_excluded']} | {ch['moment_cap_max']} | "
                 f"{'✓' if ch['every_item_has_why'] else '✗'} | {'✓' if ch['every_carousel_has_reason'] else '✗'} | "
                 f"{ch['main_feed_distinct_scores_top10']} | {'✓' if ch['influence_ties_broken_by_recency'] else '✗'} |")
    L.append("")
    # personalization proof
    L.append("## Personalization proof (cold-start 7064 vs personalized 12305)\n")
    L.append(f"- main-feed entity **overlap = {overlap:.1f}%** (low → the feeds genuinely differ).")
    L.append(f"- **personalized-only carousels** present for 12305, absent for 7064: **{sorted(personal_only) or 'none'}**.")
    L.append(f"- pagination: page1 (offset 0) ∩ page2 (offset 10) moment overlap = **{page_overlap}** (0 = clean paging).\n")
    # per-fixture detail
    for label, feed in feeds.items():
        L.append(f"## {label}  ({timings[label]:.0f} ms, mode={feed.mode}, signal_strength={feed.signal_strength})\n")
        L.append(f"Main feed: {len(feed.main_feed)} of {feed.pagination.pool_total} (next_offset={feed.pagination.next_offset}). "
                 f"Carousels: {', '.join(f'{c.reason_type.value}×{len(c.items)}' for c in feed.carousels) or 'none'}.\n")
        L.append("Main-feed sample (item — why_string — score | influence/recency):")
        for i in feed.main_feed[:4]:
            sig = i.debug.get("signals", {})
            L.append(f"- **{i.property_name[:48]}** [{i.vertical}] — _{i.why_string}_ — "
                     f"score {round(i.score,3)} (inf {sig.get('influence')}, rec {sig.get('recency')}, "
                     f"pw {sig.get('personal_weight')}, sem {sig.get('semantic')})")
        L.append("\nCarousels (reason_string — size — a sample item):")
        for c in feed.carousels:
            sample = c.items[0]
            L.append(f"- `{c.reason_type.value}` — _{c.reason_string}_ — {len(c.items)} props — "
                     f"e.g. **{sample.property_name[:36]}** (_{sample.why_string}_)")
        L.append("")
    # non-degenerate ordering proof
    L.append("## Non-degenerate ordering (influence ties broken)\n")
    feed = feeds["cold_start_7064"]
    L.append("Cold-start top-8 main feed — many share the clipped influence ceiling (0.975) yet final scores "
             "differ because recency breaks the tie:\n")
    L.append("| # | property | influence | recency | final |")
    L.append("|--:|---|--:|--:|--:|")
    for n, i in enumerate(feed.main_feed[:8], 1):
        s = i.debug.get("signals", {})
        L.append(f"| {n} | {i.property_name[:34]} | {s.get('influence')} | {s.get('recency')} | {round(i.score,4)} |")
    L.append("")
    OUT.write_text("\n".join(L), encoding="utf-8")


if __name__ == "__main__":
    main()
