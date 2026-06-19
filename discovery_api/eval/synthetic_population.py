"""V2-P7 PHASE 1 — realistic SYNTHETIC engagement population (overlay-only; NEVER touches the CSVs).

Why: on dev there are only ~31 reactions, so trending-velocity confidence is ~0.03 (dark) and the three-
signal blend can't be tuned realistically. This builds an IN-MEMORY population of follows + reactions over
REAL served entities, with DELIBERATE, DOCUMENTED patterns, so trending fires and the blend can be tuned:

  • COHORTS: ~280 synthetic users in 6 taste cohorts (cozy games / action movies / horror movies /
    drama TV / true-crime podcasts / comedy), each following an overlapping pool of the cohort's properties
    (+ a crossover cohort) → clustered, overlapping tastes (collaborative signal later).
  • TRENDING-BURST: ~18 properties (3 per cohort) get a BURST of reactions in the last 1–7 days → high
    recency-decayed VELOCITY. Spread across genres/verticals so trending isn't single-genre.
  • STALE-POPULAR: ~18 properties get MANY reactions but ALL 60–180 days old (the "old World Cup"
    analogue) → high TOTAL volume, ~0 velocity. Proves at population scale that VELOCITY (not volume) drives
    trending.
  • Realistic recency spread on cohort follows/reactions (today / this week / this month / older).

Synthetic user_ids live at 700_000_001+ (never collide with real ids, personas 990001+, sessions 800M+).
PopulationOverlay merges this onto the base for per-user reads AND for the GLOBAL trending feed
(iter_reaction_events / iter_follow_events = base + synthetic).
"""
from __future__ import annotations

import random
import sys
from collections import Counter
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from discovery_api.src.data_access.records import FollowEvent, ReactionEvent

_UID0 = 700_000_001

# (vertical, genre|None, n_users, n_pool, follows_per_user)
COHORTS = [
    ("game", "Simulation", 55, 16, 8),
    ("movie", "Action", 55, 16, 8),
    ("movie", "Horror", 55, 16, 8),
    ("tv", "Drama", 50, 14, 7),
    ("podcast", None, 45, 14, 7),
    ("movie", "Comedy", 45, 14, 7),
]
N_CROSSOVER = 30          # users spanning two cohorts (overlapping tastes → collaborative signal later)
BURST_PER_COHORT = 3      # recent reaction burst (1–7d) → high velocity
STALE_PER_COHORT = 3      # old reactions only (60–180d) → high volume, ~0 velocity
BURST_REACTIONS = 45      # synthetic reactors per burst property
STALE_REACTIONS = 55      # synthetic reactors per stale property (MORE volume than burst, on purpose)


def _pool(base, vertical, genre, n, used):
    out = []
    for e in base.get_entities_by_vertical(vertical):
        if e.entity_id in used or not e.bm25_keywords or not base.entity_id_to_property_id(e.entity_id):
            continue
        if genre is None or genre in e.canonical_genres:
            if base.get_moments_for_property(e.entity_id):       # needs a moment to react to
                out.append(e.entity_id)
                used.add(e.entity_id)
                if len(out) >= n:
                    break
    return out


def _latest_mid(base, eid):
    ms = base.get_moments_for_property(eid)
    return ms[0].moment_id if ms else None


def build_population(base, now):
    """Return (follows_by_uid, reactions_by_uid, manifest). Deterministic (fixed seed)."""
    rng = random.Random(7)
    used = set()
    follows: dict = {}
    reactions: dict = {}
    uid = _UID0
    cohort_pools = []
    burst, stale = [], []

    for (vert, genre, n_users, n_pool, fpu) in COHORTS:
        pool = _pool(base, vert, genre, n_pool, used)
        cohort_pools.append({"vertical": vert, "genre": genre, "pool": pool, "n_users": n_users})
        # designate burst + stale properties within this cohort's pool
        b = pool[:BURST_PER_COHORT]
        s = pool[BURST_PER_COHORT:BURST_PER_COHORT + STALE_PER_COHORT]
        burst += [(base.entity_id_to_property_id(e), e) for e in b]
        stale += [(base.entity_id_to_property_id(e), e) for e in s]
        # cohort users: follow a random overlapping subset + react to a few (realistic recency spread)
        for _ in range(n_users):
            fids = rng.sample(pool, min(fpu, len(pool)))
            follows[uid] = [(base.entity_id_to_property_id(e), now - timedelta(days=rng.choice([0, 1, 3, 7, 14, 30, 60])))
                            for e in fids]
            rx = []
            for e in rng.sample(pool, min(3, len(pool))):
                mid = _latest_mid(base, e)
                if mid:
                    rx.append((mid, now - timedelta(days=rng.choice([1, 3, 7, 14, 30]))))
            reactions[uid] = rx
            uid += 1

    # crossover users (two cohorts) → overlapping tastes
    for _ in range(N_CROSSOVER):
        c1, c2 = rng.sample(cohort_pools, 2)
        fids = rng.sample(c1["pool"], min(4, len(c1["pool"]))) + rng.sample(c2["pool"], min(3, len(c2["pool"])))
        follows[uid] = [(base.entity_id_to_property_id(e), now - timedelta(days=rng.choice([0, 1, 3, 7, 14]))) for e in fids]
        reactions[uid] = []
        uid += 1

    # TRENDING-BURST: many recent (1–7d) reactions on each burst property's latest moment
    for pid, eid in burst:
        mid = _latest_mid(base, eid)
        if not mid:
            continue
        for _ in range(BURST_REACTIONS):
            reactions.setdefault(uid, []).append((mid, now - timedelta(days=rng.choice([1, 1, 2, 3, 4, 5, 6, 7]),
                                                                       hours=rng.randint(0, 23))))
            uid += 1

    # STALE-POPULAR: MORE reactions but all OLD (60–180d) → high volume, ~0 velocity
    for pid, eid in stale:
        mid = _latest_mid(base, eid)
        if not mid:
            continue
        for _ in range(STALE_REACTIONS):
            reactions.setdefault(uid, []).append((mid, now - timedelta(days=rng.randint(60, 180))))
            uid += 1

    manifest = {
        "n_users": len(follows) + sum(1 for u in reactions if u not in follows),
        "n_follow_rows": sum(len(v) for v in follows.values()),
        "n_reaction_rows": sum(len(v) for v in reactions.values()),
        "cohorts": [{"vertical": c["vertical"], "genre": c["genre"], "n_users": c["n_users"], "pool_size": len(c["pool"])}
                    for c in cohort_pools],
        "burst": [(pid, base.get_entity(eid).name, eid) for pid, eid in burst],
        "stale": [(pid, base.get_entity(eid).name, eid) for pid, eid in stale],
        "burst_reactions_each": BURST_REACTIONS, "stale_reactions_each": STALE_REACTIONS,
    }
    return follows, reactions, manifest


class PopulationOverlay:
    """Per-user follows/reactions for synthetic + persona users; GLOBAL trending sees base + ALL synthetic."""

    def __init__(self, base, follows, reactions):
        self._base = base
        self._follows = follows
        self._reactions = reactions
        # precompute synthetic global event lists (for trending) ONCE
        self._synth_follow_events = []
        for u, rows in follows.items():
            for pid, ts in rows:
                self._synth_follow_events.append(
                    FollowEvent(user_id=u, property_id=pid, created_at=ts, entity_id=base.property_id_to_entity_id(pid)))
        self._synth_reaction_events = []
        for u, rows in reactions.items():
            for mid, ts in rows:
                m = base.get_moment(mid)
                self._synth_reaction_events.append(
                    ReactionEvent(user_id=u, moment_id=mid, reaction_type_id=1, created_at=ts,
                                  entity_id=(m.entity_id if m else None)))

    def __getattr__(self, name):
        return getattr(self._base, name)

    # per-user
    def get_followed_property_ids(self, user_id):
        if user_id in self._follows:
            return [pid for pid, _ in self._follows[user_id]]
        return self._base.get_followed_property_ids(user_id)

    def get_user_follow_events(self, user_id):
        if user_id in self._follows:
            return [FollowEvent(user_id=user_id, property_id=pid, created_at=ts,
                                entity_id=self._base.property_id_to_entity_id(pid)) for pid, ts in self._follows[user_id]]
        return self._base.get_user_follow_events(user_id)

    def get_user_reactions(self, user_id):
        if user_id in self._reactions:
            out = []
            for mid, ts in self._reactions[user_id]:
                m = self._base.get_moment(mid)
                out.append(ReactionEvent(user_id=user_id, moment_id=mid, reaction_type_id=1, created_at=ts,
                                         entity_id=(m.entity_id if m else None)))
            return out
        return self._base.get_user_reactions(user_id)

    # GLOBAL (trending) — base + synthetic
    def iter_reaction_events(self):
        return list(self._base.iter_reaction_events()) + self._synth_reaction_events

    def iter_follow_events(self):
        return list(self._base.iter_follow_events()) + self._synth_follow_events


# ═══════════════════════════════════════════════════════════════════════════════════════════════
# RICH population (V2-EVAL) — 300-500 COMPLEX users: varied depth, multi-taste, varied recency, overlapping
# cohorts incl. CROSS-ATTRIBUTE overlap, mainstream+niche trending bursts, stale-popular. Overlay-only.
# Additive: does NOT touch build_population (used by V2-P7/P9). Deterministic (fixed seed).
# ═══════════════════════════════════════════════════════════════════════════════════════════════
_RICH_UID0 = 720_000_001        # cohort users
_RICH_TREND_UID0 = 730_000_001  # mainstream/niche burst reactors
_RICH_STALE_UID0 = 735_000_001  # stale-popular reactors

# taste centers spanning all 4 verticals + many genres (the cohorts users are drawn from)
RICH_COHORTS = [
    ("game", "Simulation"), ("game", "Strategy"), ("game", "Adventure"),
    ("movie", "Action"), ("movie", "Horror"), ("movie", "Comedy"), ("movie", "Science Fiction"),
    ("tv", "Drama"), ("tv", "Comedy"), ("podcast", None),
]
RICH_N_USERS = 380


def _age_for_pattern(rng, pattern, cohort_idx, n_cohorts):
    """A realistic engagement age (days, 0-30) for one of a user's recency PATTERNS:
       steady (spread), bursty (clustered), recent_shift (cohort 0 = OLD taste, later = RECENT new taste),
       dormant_active (bimodal: long-dormant then a recent burst)."""
    if pattern == "steady":
        return rng.randint(0, 30)
    if pattern == "bursty":
        c = rng.choice([1, 2, 4, 6, 9, 14, 22])
        return max(0, min(30, c + rng.randint(-2, 2)))
    if pattern == "recent_shift":
        if n_cohorts > 1 and cohort_idx == 0:
            return rng.randint(20, 30)          # the OLD (fading) taste
        return rng.randint(0, 3)                # the NEW (rising) taste
    if pattern == "dormant_active":
        return rng.randint(0, 4) if rng.random() < 0.5 else rng.randint(22, 30)
    return rng.randint(0, 30)


def build_rich_population(base, now):
    """Return (follows, reactions, manifest) for ~380 COMPLEX users over REAL served entities."""
    rng = random.Random(20260619)
    used = set()
    cohorts = []
    for vert, genre in RICH_COHORTS:
        pool = _pool(base, vert, genre, 22, used)
        if len(pool) >= 6:
            cohorts.append({"vertical": vert, "genre": genre, "pool": pool})

    follows, reactions = {}, {}
    uid = _RICH_UID0
    depth_choices = [("shallow", 2, 3), ("medium", 8, 15), ("deep", 25, 35)]
    counts = {"n_tastes": Counter(), "depth": Counter(), "pattern": Counter(), "style": Counter()}

    for _ in range(RICH_N_USERS):
        r = rng.random()
        n_tastes = 1 if r < 0.40 else (2 if r < 0.85 else 3)
        user_cohorts = rng.sample(cohorts, min(n_tastes, len(cohorts)))
        dname, lo, hi = rng.choices(depth_choices, weights=[0.35, 0.45, 0.20])[0]
        total = rng.randint(lo, hi)
        pattern = rng.choice(["steady", "bursty", "recent_shift", "dormant_active"])
        style = rng.choices(["follow_only", "mixed", "reaction_heavy"], weights=[0.40, 0.45, 0.15])[0]
        counts["n_tastes"][n_tastes] += 1; counts["depth"][dname] += 1
        counts["pattern"][pattern] += 1; counts["style"][style] += 1

        per = max(1, total // len(user_cohorts))
        fids = []
        for ci, c in enumerate(user_cohorts):
            for e in rng.sample(c["pool"], min(per, len(c["pool"]))):
                age = _age_for_pattern(rng, pattern, ci, len(user_cohorts))
                fids.append((base.entity_id_to_property_id(e), now - timedelta(days=age)))
        follows[uid] = fids
        rxs = []
        if style != "follow_only":
            n_rx = rng.randint(2, 6) if style == "mixed" else rng.randint(6, 12)
            for _ in range(n_rx):
                c = rng.choice(user_cohorts)
                mid = _latest_mid(base, rng.choice(c["pool"]))
                if mid:
                    rxs.append((mid, now - timedelta(days=_age_for_pattern(rng, pattern, 1, 2))))
        reactions[uid] = rxs
        uid += 1
    n_cohort_users = uid - _RICH_UID0

    # ── CROSS-ATTRIBUTE overlap (bubble-escape basis): a strategy GAME that ~16 HORROR-cohort users also follow ──
    horror = next((c for c in cohorts if c["genre"] == "Horror"), None)
    strat = next((c for c in cohorts if c["genre"] == "Strategy"), None)
    xattr = None
    if horror and strat:
        game_eid = strat["pool"][2] if len(strat["pool"]) > 2 else strat["pool"][0]   # NOT a trending-plant pool[0]/[1]
        game_pid = base.entity_id_to_property_id(game_eid)
        horror_users = [u for u in range(_RICH_UID0, _RICH_UID0 + n_cohort_users)
                        if any(base.property_id_to_entity_id(pid) in horror["pool"] for pid, _ in follows[u])]
        endorsers = horror_users[:16]
        for u in endorsers:
            follows[u].append((game_pid, now - timedelta(days=rng.randint(2, 8))))
        xattr = {"game_eid": game_eid, "game_name": base.get_entity(game_eid).name,
                 "n_endorsers": len(endorsers), "shared_taste": "Horror",
                 "game_genres": base.get_entity(game_eid).canonical_genres}

    # ── TRENDING plants: mainstream surges (big) + niche surges (3-5 users) + stale-popular (old volume) ──
    tuid = _RICH_TREND_UID0
    mainstream, niche, stale = [], [], []
    used_trend = set()

    def _pick_trend(c, skip):
        for e in c["pool"]:
            if e not in skip:
                skip.add(e); return e
        return None

    for c in cohorts[:2]:                         # 2 mainstream bursts (45 reactors, 1-7d)
        e = _pick_trend(c, used_trend); mid = _latest_mid(base, e) if e else None
        if mid:
            for _ in range(45):
                reactions.setdefault(tuid, []).append((mid, now - timedelta(days=rng.choice([1, 2, 3, 4, 5, 6, 7]), hours=rng.randint(0, 23)))); tuid += 1
            mainstream.append((base.get_entity(e).name, e, c["genre"]))
    for c in cohorts[2:5]:                         # 3 NICHE bursts (4 reactors only, 1-4d) — niche-relative signal
        e = _pick_trend(c, used_trend); mid = _latest_mid(base, e) if e else None
        if mid:
            for _ in range(4):
                reactions.setdefault(tuid, []).append((mid, now - timedelta(days=rng.choice([1, 2, 3, 4])))); tuid += 1
            niche.append((base.get_entity(e).name, e, c["genre"]))
    suid = _RICH_STALE_UID0
    for c in cohorts[:3]:                          # 3 stale-popular (55 reactors, all 60-180d) → volume, ~0 velocity
        e = _pick_trend(c, used_trend); mid = _latest_mid(base, e) if e else None
        if mid:
            for _ in range(55):
                reactions.setdefault(suid, []).append((mid, now - timedelta(days=rng.randint(60, 180)))); suid += 1
            stale.append((base.get_entity(e).name, e, c["genre"]))

    manifest = {
        "n_cohort_users": n_cohort_users,
        "n_total_users": len({**follows, **reactions}),
        "n_follow_rows": sum(len(v) for v in follows.values()),
        "n_reaction_rows": sum(len(v) for v in reactions.values()),
        "cohorts": [{"vertical": c["vertical"], "genre": c["genre"], "pool_size": len(c["pool"])} for c in cohorts],
        "distribution": {k: dict(v) for k, v in counts.items()},
        "cross_attribute": xattr, "trending_mainstream": mainstream, "trending_niche": niche, "stale_popular": stale,
    }
    return follows, reactions, manifest


# ── Phase 1 validation (trending goes live) ──
def _raw_reaction_count(events, moment_id):
    return sum(1 for e in events if e.moment_id == moment_id)


if __name__ == "__main__":
    from discovery_api.src import timeutil
    from discovery_api.src.data_access.csv_source import CsvDataSource
    from discovery_api.src.ranking.trending import TrendingTable

    base = CsvDataSource().load()
    now = timeutil.now()
    follows, reactions, man = build_population(base, now)
    overlay = PopulationOverlay(base, follows, reactions)

    print("=" * 92)
    print("PHASE 1 — synthetic population (overlay-only; CSVs untouched)")
    print("=" * 92)
    print(f"  users≈{man['n_users']}  follow_rows={man['n_follow_rows']}  reaction_rows={man['n_reaction_rows']}")
    print(f"  cohorts: {[(c['vertical'], c['genre'], c['n_users']) for c in man['cohorts']]}")
    print(f"  burst props ({len(man['burst'])}): {[n for _, n, _ in man['burst']][:6]} …")
    print(f"  stale props ({len(man['stale'])}): {[n for _, n, _ in man['stale']][:6]} …")

    tb_dev = TrendingTable(base)
    tb_syn = TrendingTable(overlay)
    print("\n  TRENDING CONFIDENCE:")
    print(f"    dev (base only):      {tb_dev.confidence(now):.4f}   (n_events={tb_dev.ensure(now)['n_events']})")
    print(f"    + synthetic population:{tb_syn.confidence(now):.4f}   (n_events={tb_syn.ensure(now)['n_events']})")

    all_events = overlay.iter_reaction_events()
    print("\n  RECENT-BURST vs STALE-POPULAR (velocity, NOT volume):")
    print(f"    {'property':34} {'raw_reactions':>13} {'velocity':>10}")
    for tag, items in [("BURST", man["burst"][:4]), ("STALE", man["stale"][:4])]:
        for pid, name, eid in items:
            mid = _latest_mid(base, eid)
            raw = _raw_reaction_count(all_events, mid)
            vel = tb_syn.trending_score(mid, now)
            print(f"    [{tag}] {name[:27]:27} {raw:>13} {vel:>10.4f}")

    # ranking proof: top trending moments are burst, not stale
    t = tb_syn.ensure(now)
    burst_mids = {_latest_mid(base, eid) for _, _, eid in man["burst"]}
    stale_mids = {_latest_mid(base, eid) for _, _, eid in man["stale"]}
    top = sorted(t["m_norm"].items(), key=lambda kv: -kv[1])[:20]
    n_burst = sum(1 for mid, _ in top if mid in burst_mids)
    n_stale = sum(1 for mid, _ in top if mid in stale_mids)
    print(f"\n  TOP-20 trending moments: {n_burst} are BURST, {n_stale} are STALE  "
          f"→ {'PASS (recent burst dominates)' if n_burst > n_stale else 'FAIL'}")
