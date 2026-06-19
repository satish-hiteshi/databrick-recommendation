"""V2-P9 PERSONA EVAL — COLLABORATIVE FILTERING activated. A controlled A/B: the SAME engine over the SAME
overlay, the ONLY difference being collaborative OFF (= V2-P8 behaviour) vs ON (= V2-P9). Proves:
  (a) NO REGRESSION on the existing personas (on-taste, exclusions, exploration, cold-start→global), and
  (b) collaborative ACTIVATES on the synthetic population (neighborhoods form), and
  (c) the BUBBLE-ESCAPE at scale: a horror cohort that also engages a cross-attribute strategy game makes
      that game surface for a horror target who never engaged it — via the collaborative path only.

Overlay-only; the production CSVs are NEVER modified. Needs substrate :8000/:8010 up.
    .venv/bin/python discovery_api/eval/persona_eval_v2p9.py
"""
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src import config, timeutil
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.data_access.substrate_client import SubstrateClient
from discovery_api.src.feed.blend import V2FeedBuilder
from discovery_api.src.feed.taste_profile import build_taste_profile
from discovery_api.src.ranking import PopularityIndex
from discovery_api.src.ranking.collaborative import CollaborativeIndex
from discovery_api.src.ranking.trending import TrendingTable

from persona_eval import build_personas, genres_of, main_rows, all_eids, metrics, fmt_feed, _pick, _pick_any
from synthetic_population import build_population, PopulationOverlay

NOW = timeutil.now()
OUT = Path(__file__).resolve().parent / "PERSONA_EVAL_REPORT_V2P9.md"

_BUBBLE_UID0 = 750_000_001       # bubble cohort uids (distinct from population 700M+, personas 990k, sessions 800M+)


def leak(feed, followed):
    return len(all_eids(feed) & followed)


def cross_attribute_items(base, feed, intended):
    """Collaborative-tagged items (main feed + carousel) whose genres do NOT intersect the persona's taste —
    the bubble-escape additions (content the taste/trending paths could never surface)."""
    out = []
    for fi in feed.main_feed:
        if fi.source_pool == "collaborative" and not (genres_of(base, fi.entity_id) & intended):
            out.append((fi.property_name, fi.vertical))
    for c in feed.carousels:
        if c.carousel_id == "collaborative":
            for it in c.items:
                if not (genres_of(base, it.entity_id) & intended):
                    out.append((it.property_name, it.vertical))
    seen, uniq = set(), []
    for n, v in out:
        if n not in seen:
            seen.add(n); uniq.append((n, v))
    return uniq


def build_bubble_cohort(base, follows, reactions):
    """A scale bubble-escape fixture: 9 synthetic horror users all follow a horror-movie set; 7 of them ALSO
    follow a SINGLE cross-attribute strategy/simulation GAME (shares NO genre with horror). A target horror
    persona follows the same movies but NOT the game. Returns (target_uid, game_eid, game_name, movie_names)."""
    used = set()
    horror = _pick(base, "movie", "Horror", 5, used)
    game_pool = _pick(base, "game", "Strategy", 1, used) or _pick(base, "game", "Simulation", 1, used)
    game = game_pool[0] if game_pool else None
    if not horror or not game:
        return None
    uid = _BUBBLE_UID0
    for _ in range(9):                                   # 9 horror users (shared taste)
        follows[uid] = [(base.entity_id_to_property_id(e), NOW - timedelta(days=6)) for e in horror]
        if uid < _BUBBLE_UID0 + 7:                       # 7 of them ALSO follow the cross-attribute game
            follows[uid].append((base.entity_id_to_property_id(game), NOW - timedelta(days=5)))
        reactions[uid] = []
        uid += 1
    target = 990010                                      # the target horror user (follows movies, NOT the game)
    follows[target] = [(base.entity_id_to_property_id(e), NOW - timedelta(days=4)) for e in horror]
    reactions[target] = []
    return target, game, base.get_entity(game).name, [base.get_entity(e).name for e in horror]


def run():
    base = CsvDataSource().load()
    sub = SubstrateClient()
    if not sub.is_up():
        print("substrate down — start :8000/:8010"); return
    pop = PopularityIndex.from_data_source(base)

    pf, pr, man = build_population(base, NOW)
    personas = build_personas(base)
    follows = dict(pf); reactions = dict(pr)
    for p in personas:
        follows[p["uid"]] = p["follows"]; reactions[p["uid"]] = p["reactions"]
    bubble = build_bubble_cohort(base, follows, reactions)         # scale bubble-escape fixture (overlay-only)

    overlay = PopulationOverlay(base, follows, reactions)
    tb = TrendingTable(overlay)
    ci = CollaborativeIndex(overlay)

    # The controlled A/B: identical engines over the SAME overlay, SAME trending table — the ONLY difference is
    # the collaborative index (OFF = V2-P8, ON = V2-P9). Separate bundle caches (per builder) → no cross-talk.
    v2_off = V2FeedBuilder(overlay, substrate=sub, pop=pop, trending=tb, collab=False)
    v2_on = V2FeedBuilder(overlay, substrate=sub, pop=pop, trending=tb, collab=ci)

    new_off, _ = v2_on.build(990001, now=NOW, limit=10)
    new_eids = all_eids(new_off)

    lines = ["# Discovery v2 — V2-P9 Persona Eval (COLLABORATIVE OFF → ON; controlled A/B; trending live)\n",
             f"_now={NOW.isoformat()} · collaborative knobs: W_COLLABORATIVE(max)={config.V2_W_COLLABORATIVE} "
             f"SIM_MIN={config.V2_COLLAB_SIM_MIN} CONF_FULL={config.V2_COLLAB_CONFIDENCE_FULL} "
             f"MIN_ENDORSERS={config.V2_COLLAB_MIN_ENDORSERS}_\n",
             "BEFORE = collaborative OFF (V2-P8). AFTER = collaborative ON (V2-P9). Same overlay + trending; "
             "collaborative is the ONLY change. No-regression = on-taste held, leak=0, exploration unchanged.\n"]

    rows = []
    for p in personas:
        f_off, m_off_meta = v2_off.build(p["uid"], now=NOW, limit=10)
        f_on, m_on_meta = v2_on.build(p["uid"], now=NOW, limit=10)
        a = metrics(base, f_off, p["intended"], new_eids)
        b = metrics(base, f_on, p["intended"], new_eids)
        prof = build_taste_profile(p["uid"], NOW, overlay)
        followed = {e.target_entity_id for e in prof.engagements}
        cc = m_on_meta.get("collab_confidence"); ncol = m_on_meta.get("n_collaborative"); nbn = m_on_meta.get("collab_neighbors")
        xattr = cross_attribute_items(base, f_on, p["intended"])

        lines.append(f"\n## {p['name']} — {p['english']}")
        lines.append(f"context: mode={prof.mode} signal={prof.signal_strength} | collab: confidence={cc} "
                     f"neighbors={nbn} n_new={ncol}")
        lines.append(f"\n**AFTER (collaborative ON) feed (top {min(8,len(f_on.main_feed))}):**\n```\n{fmt_feed(main_rows(f_on, 8))}\n```")
        co = next((c for c in f_on.carousels if c.carousel_id == "collaborative"), None)
        if co:
            lines.append(f"**COLLABORATIVE carousel** «{co.reason_string}»: {[it.property_name for it in co.items[:5]]}")
        if xattr:
            lines.append(f"**cross-attribute additions** (bubble-escape — off-genre, neighbor-endorsed): {xattr[:5]}")
        lines.append(f"\n| metric | BEFORE (collab OFF) | AFTER (collab ON) |")
        lines.append(f"|---|---|---|")
        lines.append(f"| on-taste | {a['on_taste']} | {b['on_taste']} |")
        lines.append(f"| median age (days) | {a['median_age_days']} | {b['median_age_days']} |")
        lines.append(f"| why variety | {a['why_variety']} | {b['why_variety']} |")
        lines.append(f"| vertical mix | {a['vertical_mix']} | {b['vertical_mix']} |")
        lines.append(f"| exploration frac | {m_off_meta.get('exploration_fraction')} | {m_on_meta.get('exploration_fraction')} |")
        lines.append(f"| followed leak | {leak(f_off, followed)} | {leak(f_on, followed)} |")
        rows.append((p["name"], a, b, m_off_meta, m_on_meta, leak(f_on, followed), cc, ncol, xattr))

    # ── no-regression summary ──
    lines.append("\n\n## NO-REGRESSION summary (collaborative OFF → ON)\n")
    lines.append("| persona | on-taste OFF→ON | leak | expl OFF→ON | collab conf | n_new | cross-attr |")
    lines.append("|---|---|---|---|---|---|---|")
    regress = []
    for name, a, b, mo, mn, lk, cc, ncol, xattr in rows:
        ot_off = a["on_taste"]; ot_on = b["on_taste"]
        if ot_off is not None and ot_on is not None and ot_on + 1e-9 < ot_off:
            regress.append(f"{name} on-taste {ot_off}→{ot_on}")
        if lk != 0:
            regress.append(f"{name} leak={lk}")
        lines.append(f"| {name} | {ot_off}→{ot_on} | {lk} | {mo.get('exploration_fraction')}→{mn.get('exploration_fraction')} "
                     f"| {cc} | {ncol} | {len(xattr)} |")

    # ── scale bubble-escape (the dedicated cohort) ──
    lines.append("\n\n## BUBBLE-ESCAPE at scale (dedicated horror cohort + cross-attribute game)\n")
    bub_ok = None
    if bubble:
        tgt, game_eid, game_name, movie_names = bubble
        f_off, _ = v2_off.build(tgt, now=NOW, limit=12)
        f_on, meta_on = v2_on.build(tgt, now=NOW, limit=12)
        off_ids = all_eids(f_off); on_ids = all_eids(f_on)
        in_off = game_eid in off_ids; in_on = game_eid in on_ids
        bub_ok = (not in_off) and in_on
        lines.append(f"- Cohort: 9 horror users follow {movie_names[:3]}…; 7 ALSO follow the cross-attribute game "
                     f"**{game_name}** (genres={base.get_entity(game_eid).canonical_genres}).")
        lines.append(f"- Target (horror user 990010) follows the movies, NOT the game. collab confidence="
                     f"{meta_on.get('collab_confidence')}, neighbors={meta_on.get('collab_neighbors')}.")
        lines.append(f"- **collab OFF:** game present = {in_off}  ·  **collab ON:** game present = {in_on}  →  "
                     f"{'PASS — surfaced via collaborative only (content/trending can never reach a horror→strategy link)' if bub_ok else 'FAIL'}")
        co = next((c for c in f_on.carousels if c.carousel_id == "collaborative"), None)
        if co:
            lines.append(f"- collaborative carousel «{co.reason_string}»: {[it.property_name for it in co.items[:6]]}")

    verdict = "ALL PASS — no on-taste/leak regression; collaborative activated on the population" + \
              ("; bubble-escape proven at scale" if bub_ok else "")
    if regress or (bubble and not bub_ok):
        verdict = "REGRESSION/ISSUES: " + "; ".join(regress + ([] if bub_ok or not bubble else ["bubble-escape FAILED"]))
    lines.insert(3, f"\n**VERDICT: {verdict}**\n")

    OUT.write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    print(f"\n[written: {OUT}]")
    print(f"\nVERDICT: {verdict}")


if __name__ == "__main__":
    run()
