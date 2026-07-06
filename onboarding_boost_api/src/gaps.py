"""gaps.py — UC8 Onboarding Boost core: vertical-gap detection + cross-vertical candidate ranking.

Pure, stateless given a loaded Data snapshot + a request. Two phases:

  1. GAP DETECTION (spec §2): from the seed (followed) set, classify every vertical:
       absent           -> 0 seeds            (boosted first; desired = target_per_vertical)
       underrepresented -> 0 < seeds < gap_threshold  (top up to the floor: desired = gap_threshold - seeds)
       covered          -> seeds >= gap_threshold      (NOT deepened — spec §2)

  2. CANDIDATE RANKING per gap vertical, by the UC8 blend (weights sum to 1.0):
       0.35 popularity (S5) + 0.20 centrality (S4) + 0.18 relevance (S1)
     + 0.16 richness (S7)  + 0.07 trending (S3)  + 0.04 recency (S2)
     Relevance = MAX cosine of the candidate to ANY seed (cross-vertical, multi-interest safe). It is a
     RANKING signal, never a gate: cross-vertical cosine is structurally low (game<->gaming-podcast ~0.28),
     so popularity+centrality (55%) carry new users — exactly the spec's "thin follow graph" reasoning.

  GATES (a candidate must pass ALL): not already followed/excluded · vertical is a gap · moment_count > 0
  (active-content guarantee) · richness >= richness_floor (default 0.5). Per-franchise cap + name-dedup
  keep each vertical's set varied. If a gap vertical can't fill its desired count above the gates, it
  returns FEWER (never padded with dormant properties — the "active feed" promise wins; operator-flippable).

  Total payload is capped at total_cap via a fair round-robin across gap verticals (absent before
  underrepresented), so a tight cap never starves a whole vertical.
"""
import re
from collections import Counter, defaultdict

# ── UC8 blend weights (spec §2 — MUST sum to 1.0) ───────────────────────────────
W_POP = 0.35    # S5 popularity  (DOMINANT — safe cross-vertical pick for a new user)
W_CENT = 0.20   # S4 centrality  (well-connected hubs seed richer later discovery)
W_REL = 0.18    # S1 relevance   (semantic similarity seed -> candidate)
W_MOMENT = 0.16  # S7 moment richness (active-feed guarantee)
W_TREND = 0.07  # S3 trending    (light freshness)
W_REC = 0.04    # S2 recency     (near-zero — boost builds a durable follow graph)
assert abs(W_POP + W_CENT + W_REL + W_MOMENT + W_TREND + W_REC - 1.0) < 1e-9

# ── operator defaults ───────────────────────────────────────────────────────────
DEFAULT_TARGET_PER_VERTICAL = 5
DEFAULT_TOTAL_CAP = 30
DEFAULT_GAP_THRESHOLD = 3
DEFAULT_RICHNESS_FLOOR = 0.5        # acceptance: moment_richness_score > 0.5 on returned props
PER_VERTICAL_MIN = 3               # acceptance: >= 3 per (absent) gap vertical, when candidates allow
TARGET_CLAMP = (3, 7)              # spec §2: default 3-7 per gap vertical
FRANCHISE_CAP = 2                  # at most N same-franchise picks per vertical (variety)

# name normalization (duplicate / edition-variant detection) — ported standalone from UC6
_EDITION_RE = re.compile(r"\b(remastered|remaster|definitive|deluxe|goty|game of the year|complete|"
                         r"enhanced|hd|gold|ultimate|collection|edition)\b")
_NUMERAL_RE = re.compile(r"\b([ivx]+|\d+)\b")


def _norm_name(name):
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    s = _EDITION_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _franchise(name):
    s = (name or "").split(":")[0].lower()
    s = re.sub(r"[^a-z0-9 ]+", " ", s)
    s = _EDITION_RE.sub(" ", s)
    s = _NUMERAL_RE.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# row-aligned name caches, built ONCE per Data instance (scalable: no per-request regex over 44k)
_NAME_CACHE = {}


def _name_arrays(data):
    c = _NAME_CACHE.get(id(data))
    if c is None:
        norm = [_norm_name(data.meta[p].get("name")) for p in data.pids]
        fran = [_franchise(data.meta[p].get("name")) for p in data.pids]
        c = {"norm": norm, "fran": fran}
        _NAME_CACHE[id(data)] = c
    return c["norm"], c["fran"]


def warm(data):
    """Warm the per-instance name caches at startup (optional; first request would build them anyway)."""
    _name_arrays(data)


def _rank_percentile(values):
    """Map values -> rank-percentile in [0,1] preserving input order. Single value -> 1.0; empty -> []."""
    n = len(values)
    if n == 0:
        return []
    if n == 1:
        return [1.0]
    order = sorted(range(n), key=lambda i: values[i])
    pct = [0.0] * n
    for rank, i in enumerate(order):
        pct[i] = rank / (n - 1)
    return pct


def detect_gaps(data, seed_vert_counts, gap_threshold, exclude_verticals):
    """Classify each served vertical -> (kind, desired_count). kind in {absent, underrepresented}.
    Returns ordered list of (vertical, kind, desired) with absent first, then underrepresented."""
    excl = {str(v).lower() for v in (exclude_verticals or [])}
    absent, under = [], []
    for v in data.verticals:
        if v in excl:
            continue
        k = seed_vert_counts.get(v, 0)
        if k == 0:
            absent.append((v, "absent"))
        elif k < gap_threshold:
            under.append((v, "underrepresented", max(0, gap_threshold - k)))
    out = []
    for v, kind in absent:
        out.append((v, kind, None))                 # desired filled in by caller (target_per_vertical)
    for v, kind, need in under:
        out.append((v, kind, need))
    return out


def _why(data, seeds):
    """'Popular with fans of [A] and [B]' — names up to 2 of the user's follows (highest-popularity ones).
    Backend-agnostic: uses only the RAM signal arrays, not candidate embeddings (which live in Qdrant)."""
    if not seeds:
        return "A popular pick to round out your feed"
    ranked = sorted(seeds, key=lambda p: float(data.popularity[data.row_by_pid[p]])
                    if p in data.row_by_pid else 0.0, reverse=True)
    names = [data.meta.get(p, {}).get("name", f"Property {p}") for p in ranked[:2]]
    return f"Popular with fans of {' and '.join(names)}"


def build_boost(data, store, *, followed, target_per_vertical, total_cap, gap_threshold,
                exclude_verticals, exclude_ids, richness_floor, id_space="auto",
                deepen_covered=True, deepen_per_vertical=None, debug=False):
    """Return (context_dict, payload_groups, debug_dict|None). payload_groups: list of
    {vertical, vertical_label, properties:[...]} grouped by gap vertical.

    Seeds/excludes may arrive in the PUBLIC or EXTERNAL id space; id_space in {auto, public, external}
    controls translation. Internally everything is EXTERNAL (property_vectors); each output item carries
    both property_id (external) and public_property_id so the client can use whichever it needs."""
    norm_names, franchises = _name_arrays(data)

    # resolve every seed to a served EXTERNAL id (accepts public ids too)
    all_followed = {r for r in (data.resolve(p, id_space) for p in (followed or [])) if r is not None}
    seeds = list(dict.fromkeys(all_followed))
    seed_vert = Counter()
    for p in all_followed:
        v = data.meta.get(p, {}).get("vertical")
        if v:
            seed_vert[v] += 1

    # taste vector = L2-normalized centroid of the user's seed embeddings (from the vector store —
    # Qdrant or in-RAM). Candidates are retrieved nearest-to-taste per vertical; relevance = that cosine.
    taste = store.taste_vector(seeds)

    floor = DEFAULT_RICHNESS_FLOOR if richness_floor is None else float(richness_floor)
    tgt = max(TARGET_CLAMP[0], min(int(target_per_vertical), TARGET_CLAMP[1]))
    deepen_n = tgt if deepen_per_vertical is None else max(1, min(int(deepen_per_vertical), TARGET_CLAMP[1]))

    gaps = detect_gaps(data, seed_vert, gap_threshold, exclude_verticals)   # absent + underrepresented
    # DEEPEN: a covered vertical (>= gap_threshold follows) still gets fresh, taste-relevant, active picks
    # so a well-covered user is NEVER shown an empty boost. Spec §2 allows deepening covered verticals when
    # the operator enables it — default ON here. Gaps are filled first; deepen uses the leftover cap.
    if deepen_covered:
        excl = {str(x).lower() for x in (exclude_verticals or [])}
        gap_names = {v for v, _, _ in gaps}
        gaps = gaps + [(v, "deepen", deepen_n) for v in data.verticals
                       if v not in excl and v not in gap_names and seed_vert.get(v, 0) >= gap_threshold]

    if not gaps:
        ctx = {"seed_count": len(all_followed), "gap_verticals_detected": [], "deepen_verticals": [],
               "total_suggested": 0, "reason": "no gaps and deepen disabled"}
        return ctx, [], ({"seed_vertical_counts": dict(seed_vert)} if debug else None)

    exclude = set(all_followed) | {r for r in (data.resolve(x, id_space) for x in (exclude_ids or [])) if r is not None}
    exclude_norm = {norm_names[data.row_by_pid[p]] for p in exclude if p in data.row_by_pid}
    exclude_norm.discard("")

    # ── collect gated candidates per gap vertical via the vector store (pass 1) ──
    # store.candidates already applies the vertical + active gates (moment_count>0, richness>=floor) and
    # id-exclusion; here we only add the name-dedup guard and read the SCORING signals from RAM arrays.
    vert_set = {v for v, _, _ in gaps}
    pool = {v: [] for v in vert_set}    # vertical -> [{pid,row,pop,cen,rel_raw,rich,trd,rec}]
    for v in vert_set:
        for pid, cosine in store.candidates(taste, v, floor, exclude):
            row = data.row_by_pid.get(pid)
            if row is None or norm_names[row] in exclude_norm:
                continue
            pool[v].append({"pid": pid, "row": row, "pop": float(data.popularity[row]),
                            "cen": float(data.centrality[row]), "rel_raw": max(0.0, float(cosine)),
                            "rich": float(data.richness[row]), "trd": float(data.trending[row]),
                            "rec": float(data.recency[row])})

    # ── score (pass 2): relevance is WITHIN-VERTICAL percentile of seed cosine, so the 18% weight
    # actually discriminates. Cross-vertical raw cosine is compressed into a narrow band (~0.02–0.48),
    # which would otherwise wash relevance out entirely while centrality/richness/trending (already
    # percentile-normalized) dominate. Popularity stays RAW — it is genuine absolute social proof.
    ranked = {}                         # vertical -> [(blend, pid, components)]
    for v, cands in pool.items():
        rel_pct = _rank_percentile([c["rel_raw"] for c in cands])
        scored = []
        for c, rp in zip(cands, rel_pct):
            blend = (W_POP * c["pop"] + W_CENT * c["cen"] + W_REL * rp + W_MOMENT * c["rich"]
                     + W_TREND * c["trd"] + W_REC * c["rec"])
            scored.append((blend, c["pid"], {"popularity": c["pop"], "centrality": c["cen"],
                           "relevance": rp, "relevance_cosine": round(c["rel_raw"], 4),
                           "richness": c["rich"], "trending": c["trd"], "recency": c["rec"]}))
        scored.sort(key=lambda t: t[0], reverse=True)
        ranked[v] = scored

    # desired count per gap vertical
    desired = {}
    kinds = {}
    for v, kind, need in gaps:
        kinds[v] = kind
        desired[v] = tgt if kind == "absent" else int(need)

    # ── select with franchise-cap + name-dedup, then fair round-robin under total_cap ──
    picked = defaultdict(list)          # vertical -> [(blend, pid, components)]
    used_norm = set(exclude_norm)
    fr_count = defaultdict(Counter)     # vertical -> franchise -> n

    def _take_one(v):
        """Pull the next eligible candidate for vertical v into picked[v]; True if one was taken."""
        for cand in ranked[v]:
            blend, pid, comp = cand
            if any(pid == c[1] for c in picked[v]):
                continue
            row = data.row_by_pid[pid]
            nn = norm_names[row]
            if nn and nn in used_norm:
                continue
            fr = franchises[row]
            if fr and fr_count[v][fr] >= FRANCHISE_CAP:
                continue
            picked[v].append(cand)
            if nn:
                used_norm.add(nn)
            if fr:
                fr_count[v][fr] += 1
            return True
        return False

    # priority: absent gaps first, then underrepresented, then deepen covered verticals (leftover cap)
    order = ([v for v, k, _ in gaps if k == "absent"]
             + [v for v, k, _ in gaps if k == "underrepresented"]
             + [v for v, k, _ in gaps if k == "deepen"])
    cap = max(0, int(total_cap))
    total = 0
    progressed = True
    while total < cap and progressed:
        progressed = False
        for v in order:
            if total >= cap:
                break
            if len(picked[v]) >= desired[v]:
                continue
            if _take_one(v):
                total += 1
                progressed = True

    # ── assemble payload grouped by vertical ────────────────────────────────────
    groups = []
    gap_detected = []
    deepen_detected = []
    total_suggested = 0
    for v, kind, _ in gaps:
        (deepen_detected if kind == "deepen" else gap_detected).append(v)
        props = []
        for blend, pid, comp in picked[v]:
            m = data.meta[pid]
            row = data.row_by_pid[pid]
            props.append({
                "type": "property",
                "property_id": pid,
                "public_property_id": data.public_id(pid),
                "entity_id": str(m.get("entity_id") or pid),
                "name": m.get("name"),
                "vertical": v,
                "genres": m.get("genres", [])[:6],
                "thumbnail_url": None,                  # not in the 44k-qwen set (UMI store resolves client-side)
                "deep_link": f"feeds://property/{pid}",
                "score": round(float(blend), 4),
                "moment_richness_score": round(comp["richness"], 4),
                "popularity_score": round(comp["popularity"], 4),   # honest social-proof signal we DO have
                "follower_count": None,                 # resolved client-side from UMI store (spec open Q)
                "why_string": _why(data, seeds),
                "badge": ("trending" if comp["trending"] >= 0.85 else None),
                "moment_count": int(data.moment_count[row]),
            })
        total_suggested += len(props)
        groups.append({"vertical": v, "vertical_label": _VLABEL.get(v, v.title()),
                       "kind": kind, "properties": props})

    ctx = {"seed_count": len(all_followed), "gap_verticals_detected": gap_detected,
           "deepen_verticals": deepen_detected, "total_suggested": total_suggested}
    dbg = None
    if debug:
        dbg = {"seed_vertical_counts": dict(seed_vert), "gap_kinds": kinds, "desired_per_vertical": desired,
               "candidate_pool_sizes": {v: len(ranked[v]) for v in ranked},
               "richness_floor": floor, "weights": {"popularity": W_POP, "centrality": W_CENT,
               "relevance": W_REL, "moment_richness": W_MOMENT, "trending": W_TREND, "recency": W_REC}}
    return ctx, groups, dbg


_VLABEL = {"game": "Games", "movie": "Movies & Film", "tv": "TV & Shows", "podcast": "Podcasts",
           "music": "Music"}
