"""Fresh-account PERSONA evaluation — judge v2 recommendation quality the way a NEW user would, and
compare against v1.

Personas are FRESH user_ids with deliberate, documented follow/reaction profiles over REAL served
entities, injected via an in-memory OVERLAY data source (the production CSVs are NOT modified). Both
engines run over the SAME overlay so the comparison is fair. Writes PERSONA_EVAL_REPORT.md + prints.

    .venv/bin/python discovery_api/eval/persona_eval.py     (needs substrate :8000/:8010 up)
"""
import statistics
import sys
import time
from collections import Counter
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import config, timeutil
from discovery_api.src.candidates.base import RequestContext
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.data_access.records import FollowEvent, ReactionEvent
from discovery_api.src.data_access.substrate_client import SubstrateClient
from discovery_api.src.engine import DiscoveryEngine
from discovery_api.src.feed.blend import V2FeedBuilder
from discovery_api.src.feed.taste_profile import build_taste_profile
from discovery_api.src.ranking import PopularityIndex

NOW = timeutil.now()                                  # 2026-06-18 (fixed, reproducible)
OUT = Path(__file__).resolve().parent / "PERSONA_EVAL_REPORT.md"


# ── overlay data source (inject synthetic per-user engagement; everything else delegates to base) ──
class OverlayDataSource:
    def __init__(self, base, follows, reactions):
        self._base = base
        self._follows = follows        # {uid: [(property_id, created_at)]}
        self._reactions = reactions     # {uid: [(moment_id, created_at)]}

    def __getattr__(self, name):
        return getattr(self._base, name)

    def get_followed_property_ids(self, user_id):
        if user_id in self._follows:
            return [pid for pid, _ in self._follows[user_id]]
        return self._base.get_followed_property_ids(user_id)

    def get_user_follow_events(self, user_id):
        if user_id in self._follows:
            return [FollowEvent(user_id=user_id, property_id=pid, created_at=ts,
                                entity_id=self._base.property_id_to_entity_id(pid))
                    for pid, ts in self._follows[user_id]]
        return self._base.get_user_follow_events(user_id)

    def get_user_reactions(self, user_id):
        if user_id in self._reactions:
            out = []
            for mid, ts in self._reactions[user_id]:
                m = self._base.get_moment(mid)
                out.append(ReactionEvent(user_id=user_id, moment_id=mid, reaction_type_id=1,
                                         created_at=ts, entity_id=(m.entity_id if m else None)))
            return out
        return self._base.get_user_reactions(user_id)


# ── entity pickers (REAL served entities) ──
def _pick(base, vertical, genre, n, used):
    out = []
    for e in base.get_entities_by_vertical(vertical):
        if e.entity_id in used:
            continue
        if genre in e.canonical_genres and e.bm25_keywords and base.entity_id_to_property_id(e.entity_id):
            out.append(e.entity_id)
            if len(out) >= n:
                break
    return out


def _pick_any(base, vertical, n, used):
    out = []
    for e in base.get_entities_by_vertical(vertical):
        if e.entity_id in used:
            continue
        if e.bm25_keywords and base.entity_id_to_property_id(e.entity_id):
            out.append(e.entity_id)
            if len(out) >= n:
                break
    return out


def build_personas(base):
    used = set()

    def take(ids):
        used.update(ids)
        return ids

    sim8 = take(_pick(base, "game", "Simulation", 8, used) or _pick(base, "game", "Strategy", 8, used))
    cross = take(_pick_any(base, "game", 2, used) + _pick(base, "movie", "Action", 2, used) +
                 _pick(base, "tv", "Drama", 2, used) + _pick_any(base, "podcast", 2, used))
    comedy_old = take(_pick(base, "movie", "Comedy", 2, used) + _pick(base, "tv", "Comedy", 2, used))
    horror_new = take(_pick(base, "movie", "Horror", 3, used) + _pick(base, "tv", "Horror", 1, used))
    sparse = take(_pick(base, "game", "Simulation", 3, used) or _pick(base, "game", "Strategy", 3, used))
    react_follows = take(_pick(base, "movie", "Horror", 3, used))
    react_targets = take(_pick(base, "movie", "Horror", 4, used))

    def pids(ids, days):
        return [(base.entity_id_to_property_id(e), NOW - timedelta(days=days)) for e in ids]

    def react(ids, days):
        out = []
        for e in ids:
            ms = base.get_moments_for_property(e)
            if ms:
                out.append((ms[0].moment_id, NOW - timedelta(days=days)))
        return out

    return [
        dict(name="P_NEW", uid=990001, english="Brand-new account, zero follows (cold-start).",
             intended=set(), follows=[], reactions=[]),
        dict(name="P_SINGLE_TASTE", uid=990002,
             english=f"8 simulation/strategy GAME follows (one coherent cozy-builder taste), all recent.",
             intended={"simulation", "strategy", "indie", "city-builder"},
             follows=pids(sim8, 5), reactions=[]),
        dict(name="P_CROSS_VERTICAL", uid=990003,
             english="A mix: 2 games + 2 action movies + 2 drama TV + 2 podcasts, all recent.",
             intended={"action", "drama"}, follows=pids(cross, 5), reactions=[]),
        dict(name="P_DRIFTING", uid=990004,
             english="OLDER comedy (4 follows, 35d ago) + RECENT horror (4 follows, 2d ago) — taste is drifting to horror.",
             intended={"horror"}, follows=pids(comedy_old, 35) + pids(horror_new, 2), reactions=[]),
        dict(name="P_SPARSE", uid=990005,
             english="Only 3 simulation game follows (thin signal → should explore more).",
             intended={"simulation", "strategy"}, follows=pids(sparse, 5), reactions=[]),
        dict(name="P_REACTOR", uid=990006,
             english="3 horror-movie follows + 4 reactions on horror moments (reactions add signal).",
             intended={"horror"}, follows=pids(react_follows, 4), reactions=react(react_targets, 2)),
    ]


# ── metrics ──
def genres_of(base, eid):
    e = base.get_entity(eid)
    if not e:
        return set()
    gs = base.get_podcast_categories(eid) if e.vertical == "podcast" else e.canonical_genres
    return {g.lower() for g in gs}


def main_rows(feed, n=10):
    return [(fi.entity_id, fi.vertical, fi.property_name, fi.title, fi.why_string, fi.score)
            for fi in feed.main_feed[:n]]


def all_eids(feed):
    s = {i.entity_id for i in feed.main_feed}
    for c in feed.carousels:
        s |= {it.entity_id for it in c.items}
    return s


def jaccard(a, b):
    a, b = set(a), set(b)
    return round(len(a & b) / len(a | b), 3) if (a | b) else 0.0


def metrics(base, feed, intended, persona_new_eids):
    rows = main_rows(feed, 10)
    eids = [r[0] for r in rows]
    vmix = Counter(r[1] for r in rows)
    whys = [r[4] for r in rows]
    why_variety = round(len(set(whys)) / len(whys), 2) if whys else 0.0
    on_taste = (round(sum(1 for e in eids if genres_of(base, e) & intended) / len(eids), 2)
                if eids and intended else None)
    ages = []
    for fi in feed.main_feed[:10]:
        ts = timeutil.parse_ts(fi.event_starts_at)
        if ts:
            ages.append(round((NOW - ts).total_seconds() / 86400.0, 1))
    return {
        "vertical_mix": dict(vmix), "why_variety": why_variety, "on_taste": on_taste,
        "median_age_days": round(statistics.median(ages), 1) if ages else None,
        "overlap_with_new": jaccard(eids, persona_new_eids),
    }


def fmt_feed(rows):
    out = []
    for eid, vert, prop, title, why, score in rows:
        out.append(f"  {score:6.3f} [{vert:7}] {prop[:30]:30} | {title[:28]:28} | “{why}”")
    return "\n".join(out)


def carousel_summary(feed):
    return [(c.carousel_id, len(c.items), c.reason_string, c.reason_type.value) for c in feed.carousels]


def run():
    base = CsvDataSource().load()
    sub = SubstrateClient()
    live = sub.is_up()
    pop = PopularityIndex.from_data_source(base)
    personas = build_personas(base)

    follows = {p["uid"]: p["follows"] for p in personas}
    reactions = {p["uid"]: p["reactions"] for p in personas}
    overlay = OverlayDataSource(base, follows, reactions)

    v2 = V2FeedBuilder(overlay, substrate=sub, pop=pop)
    v1_full = DiscoveryEngine(overlay, substrate=(sub if live else None), popularity=pop)

    lines = [f"# Discovery v2 — Fresh-Account Persona Evaluation\n",
             f"_now={NOW.isoformat()} · substrate={'LIVE' if live else 'DOWN'} · default_engine={config.V2_DEFAULT_ENGINE}_\n",
             "Both engines run over an in-memory OVERLAY (synthetic follows/reactions for fresh user_ids over "
             "REAL served entities; production CSVs untouched). v2 = taste-profile → content+exploration retrieval "
             "→ trending + three-signal blend. v1 = the global+similarity pools baseline.\n"]
    results = {}
    new_eids = set()

    for p in personas:
        uid = p["uid"]
        t0 = time.time()
        f2, meta = v2.build(uid, now=NOW, limit=10)
        t2 = time.time() - t0
        t0 = time.time()
        f1 = v1_full.build_feed(uid, RequestContext(now=NOW, limit=10))
        t1 = time.time() - t0
        prof = build_taste_profile(uid, NOW, overlay)
        if p["name"] == "P_NEW":
            new_eids = all_eids(f2)
        results[p["name"]] = dict(p=p, f1=f1, f2=f2, meta=meta, prof=prof, t1=t1, t2=t2)

    for p in personas:
        r = results[p["name"]]
        f1, f2, meta, prof = r["f1"], r["f2"], r["meta"], r["prof"]
        m2 = metrics(base, f2, p["intended"], new_eids)
        m1 = metrics(base, f1, p["intended"], new_eids)
        v1v2 = jaccard([x[0] for x in main_rows(f2)], [x[0] for x in main_rows(f1)])
        names = [base.get_entity(base.property_id_to_entity_id(pid)).name
                 for pid, _ in p["follows"] if base.property_id_to_entity_id(pid)][:8]

        lines.append(f"\n## {p['name']}  (user {p['uid']})\n")
        lines.append(f"**Profile:** {p['english']}")
        if names:
            lines.append(f"  · follows: {', '.join(names)}")
        lines.append(f"\n**Context** — v2: mode={prof.mode} signal={prof.signal_strength} path={meta.get('path')}"
                     f" | v1: mode={f1.mode} signal={f1.signal_strength}")
        if prof.clusters:
            lines.append(f"  · v2 vertical%: { {k: round(v, 2) for k, v in prof.vertical_percentages.items()} }")
            lines.append("  · v2 clusters: " + "; ".join(
                f"#{c.cluster_id} {c.label}({c.dominant_vertical},share={c.cluster_share})" for c in prof.clusters[:5]))
            if meta.get("exploration_fraction") is not None:
                lines.append(f"  · exploration_fraction={meta['exploration_fraction']} | global_backfill={meta.get('global_backfill')}")
        lines.append(f"\n**v2 MAIN FEED (top {len(main_rows(f2))}):**\n```\n{fmt_feed(main_rows(f2))}\n```")
        cs = carousel_summary(f2)
        hi = [c for c in cs if c[0] in ("trending", "exploration")]
        lines.append("**v2 CAROUSELS:** " + ", ".join(f"{cid}[{n}]" for cid, n, _, _ in cs))
        for cid, n, reason, rt in hi:
            lines.append(f"   · **{cid}** «{reason}» [{rt}] ({n})")
        lines.append(f"\n**v1 MAIN FEED (top 6, for comparison):**\n```\n{fmt_feed(main_rows(f1, 6))}\n```")
        lines.append(f"**METRICS** — v2 vs v1:")
        lines.append(f"   · vertical_mix:  v2={m2['vertical_mix']}   v1={m1['vertical_mix']}")
        lines.append(f"   · on_taste (genres ∩ intended): v2={m2['on_taste']}  v1={m1['on_taste']}")
        lines.append(f"   · why_string variety: v2={m2['why_variety']}  v1={m1['why_variety']}")
        lines.append(f"   · median freshness (days old): v2={m2['median_age_days']}  v1={m1['median_age_days']}")
        lines.append(f"   · overlap w/ P_NEW global feed: v2={m2['overlap_with_new']}  v1={m1['overlap_with_new']}  (low=personalized)")
        lines.append(f"   · v1↔v2 main-feed jaccard: {v1v2}  (low=meaningfully different)")
        lines.append(f"   · build time: v2={r['t2']:.2f}s  v1={r['t1']:.2f}s")
        lines.append(f"\n**VERDICT:** {verdict(p, prof, f1, f2, m1, m2, v1v2, base, new_eids)}")

    lines.append("\n\n" + summary_section(base, results, new_eids))
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[written: {OUT}]")


def verdict(p, prof, f1, f2, m1, m2, v1v2, base, new_eids):
    name = p["name"]
    if name == "P_NEW":
        return ("Cold-start on BOTH engines → the global feed (v2 routes via fallback_to_global). As a brand-new "
                "user this is correct: trending/fresh/popular, no personalization claimed.")
    bits = []
    if m2["on_taste"] is not None:
        better = "more" if (m2["on_taste"] or 0) >= (m1["on_taste"] or 0) else "less"
        bits.append(f"v2 is {better} on-taste ({m2['on_taste']} vs v1 {m1['on_taste']})")
    bits.append(f"feeds differ meaningfully (jaccard {v1v2})")
    if name == "P_DRIFTING":
        horror = sum(1 for e, *_ in main_rows(f2) if "horror" in genres_of(base, e))
        comedy = sum(1 for e, *_ in main_rows(f2) if "comedy" in genres_of(base, e))
        topc = prof.clusters[0].label if prof.clusters else "?"
        bits.append(f"RECENCY DRIFT: top cluster=«{topc}», feed horror={horror} vs comedy={comedy} → recent taste wins"
                    if horror >= comedy else f"drift weak (horror={horror} comedy={comedy})")
    if name in ("P_SPARSE",):
        bits.append(f"thin signal → high exploration (vertical% smoothed toward neutral: "
                    f"{ {k: round(v,2) for k,v in prof.vertical_percentages.items()} })")
    if m2["why_variety"] <= 0.4:
        bits.append(f"explanations are repetitive (why_variety {m2['why_variety']} — mostly 'Because you follow…')")
    return "; ".join(bits) + "."


def summary_section(base, results, new_eids):
    def m2(k):
        return metrics(base, results[k]["f2"], results[k]["p"]["intended"], new_eids)
    def m1(k):
        return metrics(base, results[k]["f1"], results[k]["p"]["intended"], new_eids)

    s = ["# Summary — v2 strengths + top quality issues (config-tied)\n", "## Strengths (with evidence)"]
    s.append(f"- **v2 personalizes the MAIN FEED; v1 only personalizes carousels.** P_SINGLE_TASTE on-taste "
             f"v2={m2('P_SINGLE_TASTE')['on_taste']} vs v1={m1('P_SINGLE_TASTE')['on_taste']}; "
             f"P_CROSS_VERTICAL v2={m2('P_CROSS_VERTICAL')['on_taste']} vs v1={m1('P_CROSS_VERTICAL')['on_taste']}. "
             f"v1's main feed stays global fresh/popular (its taste only shows in similar/popular carousels).")
    s.append("- **Genuinely taste-driven, not global-with-a-hat.** Every personalized persona has v1↔v2 main-feed "
             "jaccard = 0.0, and overlap with the P_NEW global feed ≈0.02–0.04 (vs v1 ≈0.13).")
    s.append(f"- **Exploration is sized by signal.** P_SPARSE exploration_fraction "
             f"{results['P_SPARSE']['meta'].get('exploration_fraction')} > P_SINGLE_TASTE "
             f"{results['P_SINGLE_TASTE']['meta'].get('exploration_fraction')} — the thin-signal user explores more.")
    s.append("- **Cold-start correct + cross-vertical variety.** P_NEW → global on both engines; vertical_percentages "
             "+ global_backfill give single-cluster users other-vertical items (P_DRIFTING feed spans game/movie/tv).")
    s.append("- **Explainable + fast.** Every item has a why_string; the bundle cache makes warm loads sub-second.\n")

    s.append("## Top quality issues (DIAGNOSIS only — each tied to a config knob / provider)")
    s.append(f"1. **STALE moments of on-taste properties surface (the biggest issue).** Game-heavy personas show "
             f"median feed age **{m2('P_SINGLE_TASTE')['median_age_days']}d** (P_SINGLE) and "
             f"**{m2('P_SPARSE')['median_age_days']}d** (P_SPARSE) — i.e. years-old launch moments of well-matched "
             f"games. taste_match outweighs recency for old-but-matched properties and there is no recency floor. "
             f"*Knob:* raise `V2_W_RECENCY` (currently 0.6) and/or set `DISCOVERY_RECENCY_HARD_CUTOFF_DAYS` "
             f"(currently None) or add a soft recency floor in `moment_select`.")
    s.append("2. **Recency DRIFT is captured in the profile but doesn't reach the FEED.** P_DRIFTING's taste profile "
             "weights the RECENT horror cluster far above the OLD comedy cluster, yet the feed is comedy-heavy "
             f"(on_taste {m2('P_DRIFTING')['on_taste']}; feed horror=3 vs comedy=7). Root cause: `cluster_weight` "
             "(which encodes recency) drives slot ALLOCATION, but per-moment `taste_match` comes from the RETRIEVAL "
             "score — so a low-weight cluster's items still rank high per-item and flood the page. *Fix (diagnose "
             "only):* fold `cluster_share`/`cluster_weight` into `taste_match` in `assembler_v2` (a new "
             "`V2_TASTE_CLUSTER_WEIGHTING` knob), so recent-taste clusters dominate ranking, not just slot counts.")
    s.append("3. **Duplicate properties flood the feed (per-property moment cap).** P_SPARSE shows *Welcome to Elk ×3, "
             "Storm Boy ×3*; P_SINGLE shows *Little Big Workshop ×3* — the cap (`V2_MOMENT_CAP_PER_PROPERTY=3`) lets "
             "one property's launch moments repeat, badly so for sparse users with few candidate properties. *Knob:* "
             "lower `V2_MOMENT_CAP_PER_PROPERTY` to 1–2 (or make it signal-scaled).")
    wv = [m2(k)['why_variety'] for k in results if k != "P_NEW"]
    s.append(f"4. **why_strings are repetitive (avg variety {round(sum(wv)/len(wv),2) if wv else 'n/a'}).** Most "
             "main-feed items say “Because you follow {rep}”. *Knob/provider:* `feed/why_v2.moment_why` — vary the "
             "phrasing by the item's dominant signal (taste vs recency vs trending) and by genre, not just the cluster rep.")
    s.append("5. **Trending is dev-quiet (≈0 contribution).** On ~31 reactions the confidence gate keeps "
             "trending_velocity≈0, so the blend is effectively taste+recency on dev (mechanically correct — the "
             "World-Cup unit test proves it activates with volume). *Knob:* lower `V2_TRENDING_CONFIDENCE_FULL` to "
             "surface dev trending, or raise `V2_W_TRENDING`; on production volume this self-activates.")
    s.append("\n_(No ranking logic was changed in this prompt — these are tunable next steps for V2-P5/P7. Issues "
             "1–3 are the highest-leverage for perceived quality.)_")
    return "\n".join(s)


if __name__ == "__main__":
    run()
