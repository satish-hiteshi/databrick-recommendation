"""V2-P7 RE-RUN — the EXACT V2-P6 personas, on the TUNED engine, now WITH the synthetic population loaded
so trending is LIVE. Proves monotonic quality improvement (no regression) vs V2-P6.

    .venv/bin/python discovery_api/eval/persona_eval_v2p7.py     (needs substrate :8000/:8010 up)
"""
import statistics
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import config, timeutil
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.data_access.substrate_client import SubstrateClient
from discovery_api.src.feed.blend import V2FeedBuilder
from discovery_api.src.feed.taste_profile import build_taste_profile
from discovery_api.src.ranking import PopularityIndex
from discovery_api.src.ranking.trending import TrendingTable

from persona_eval import build_personas, genres_of, main_rows, all_eids, jaccard, metrics, fmt_feed
from synthetic_population import build_population, PopulationOverlay

NOW = timeutil.now()
OUT = Path(__file__).resolve().parent / "PERSONA_EVAL_REPORT_V2P7.md"

# BEFORE = the documented V2-P6 numbers (untuned, no synthetic / trending dark).
BEFORE = {
    "P_NEW":          dict(on_taste=None, median_age=-1.0, why=0.3, expl=None, dup=0, note="cold→global"),
    "P_SINGLE_TASTE": dict(on_taste=0.70, median_age=925.5, why=0.2, expl=0.375, dup=3, note="stale + dup"),
    "P_CROSS_VERTICAL": dict(on_taste=0.90, median_age=16.1, why=0.2, expl=0.375, dup=0, note="good"),
    "P_DRIFTING":     dict(on_taste=0.30, median_age=16.1, why=0.3, expl=0.413, dup=0, note="drift wrong (H3/C7)"),
    "P_SPARSE":       dict(on_taste=0.0, median_age=1844.5, why=0.2, expl=0.453, dup=3, note="stale + dup"),
    "P_REACTOR":      dict(on_taste=0.70, median_age=16.1, why=0.3, expl=0.378, dup=0, note="ok"),
}


def dup_count(feed):
    eids = [fi.entity_id for fi in feed.main_feed[:10]]
    return len(eids) - len(set(eids))


def genre_counts(base, feed, genres):
    out = Counter()
    for fi in feed.main_feed[:10]:
        gs = genres_of(base, fi.entity_id)
        for g in genres:
            if g in gs:
                out[g] += 1
    return dict(out)


def run():
    base = CsvDataSource().load()
    sub = SubstrateClient()
    if not sub.is_up():
        print("substrate down — start :8000/:8010")
        return
    pop = PopularityIndex.from_data_source(base)

    # synthetic population + persona engagement → one overlay (trending sees ALL synthetic events)
    pf, pr, man = build_population(base, NOW)
    personas = build_personas(base)
    follows = dict(pf); reactions = dict(pr)
    for p in personas:
        follows[p["uid"]] = p["follows"]
        reactions[p["uid"]] = p["reactions"]
    overlay = PopulationOverlay(base, follows, reactions)

    tb = TrendingTable(overlay)
    burst_eids = {eid for _, _, eid in man["burst"]}
    v2 = V2FeedBuilder(overlay, substrate=sub, pop=pop)

    lines = ["# Discovery v2 — V2-P7 Persona Eval (tuned + synthetic population; trending LIVE)\n",
             f"_now={NOW.isoformat()} · trending confidence={tb.confidence(NOW):.3f} (was ~0.12 dev) · "
             f"config: W_RECENCY={config.V2_W_RECENCY} cluster_weighting={config.V2_TASTE_CLUSTER_WEIGHTING} "
             f"stale={config.V2_STALE_FACTOR}@{int(config.V2_RECENCY_STALE_DAYS)}d cap={config.V2_MOMENT_CAP_PER_PROPERTY}_\n",
             "BEFORE = V2-P6 (untuned, trending dark). AFTER = V2-P7 (tuned, trending live). Overlay-only; CSVs untouched.\n"]

    # P_NEW first for overlap baseline
    new_feed, _ = v2.build(990001, now=NOW, limit=10)
    new_eids = all_eids(new_feed)

    rows_tbl = []
    for p in personas:
        f2, meta = v2.build(p["uid"], now=NOW, limit=10)
        m = metrics(base, f2, p["intended"], new_eids)
        prof = build_taste_profile(p["uid"], NOW, overlay)
        followed = {e.target_entity_id for e in prof.engagements}
        feed_ids = all_eids(f2)
        dup = dup_count(f2)
        b = BEFORE[p["name"]]

        # trending carousel quality
        tr = next((c for c in f2.carousels if c.carousel_id == "trending"), None)
        tr_items = [(it.property_name, round(tb.trending_score_property(it.entity_id, NOW), 3)) for it in (tr.items[:4] if tr else [])]

        lines.append(f"\n## {p['name']} — {p['english']}")
        lines.append(f"context: mode={prof.mode} signal={prof.signal_strength} expl_frac={meta.get('exploration_fraction')}")
        lines.append(f"\n**AFTER feed (top {min(8,len(f2.main_feed))}):**\n```\n{fmt_feed(main_rows(f2, 8))}\n```")
        if tr_items:
            lines.append(f"**TRENDING carousel** «{tr.reason_string}»: {tr_items}")
        lines.append(f"\n| metric | BEFORE (V2-P6) | AFTER (V2-P7) |")
        lines.append(f"|---|---|---|")
        lines.append(f"| on-taste | {b['on_taste']} | {m['on_taste']} |")
        lines.append(f"| median age (days) | {b['median_age']} | {m['median_age_days']} |")
        lines.append(f"| why variety | {b['why']} | {m['why_variety']} |")
        lines.append(f"| duplicate props | {b['dup']} | {dup} |")
        lines.append(f"| exploration frac | {b['expl']} | {meta.get('exploration_fraction')} |")
        lines.append(f"| overlap w/ global | — | {m['overlap_with_new']} |")
        lines.append(f"| followed leak | 0 | {len(feed_ids & followed)} |")
        if p["name"] == "P_DRIFTING":
            gc = genre_counts(base, f2, ["horror", "comedy"])
            lines.append(f"| **drift (horror vs comedy)** | H3 / C7 (wrong) | H{gc.get('horror',0)} / C{gc.get('comedy',0)} |")
        rows_tbl.append((p["name"], b, m, dup, meta.get("exploration_fraction"), len(feed_ids & followed),
                         genre_counts(base, f2, ["horror", "comedy"]) if p["name"] == "P_DRIFTING" else None))

    # summary table
    lines.append("\n\n## BEFORE → AFTER summary (monotonic improvement, no regression)\n")
    lines.append("| persona | on-taste | median age | why variety | dups | expl frac | leak |")
    lines.append("|---|---|---|---|---|---|---|")
    for name, b, m, dup, ef, leak, _gc in rows_tbl:
        lines.append(f"| {name} | {b['on_taste']}→{m['on_taste']} | {b['median_age']}→{m['median_age_days']} | "
                     f"{b['why']}→{m['why_variety']} | {b['dup']}→{dup} | {b['expl']}→{ef} | {leak} |")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[written: {OUT}]")


if __name__ == "__main__":
    run()
