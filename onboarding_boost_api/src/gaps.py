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
import os
import re
import sys
from collections import Counter, defaultdict

# shared/identity.py is FROZEN — import, never edit. It is the ONE place the platform derives the
# composite (profile_key + media_source_guid) from an entity_id, so the boost response can emit the
# stable post-migration key. Pure functions, no I/O. (Repo root on sys.path -> `shared.identity`.)
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)
from shared.identity import (composite_of, composite_fields, make_entity_id,  # noqa: E402
                             profile_key_for)

# ── UC8 blend weights (spec §2 — MUST sum to 1.0) ───────────────────────────────
W_POP = 0.35    # S5 popularity  (DOMINANT — safe cross-vertical pick for a new user)
W_CENT = 0.20   # S4 centrality  (well-connected hubs seed richer later discovery)
W_REL = 0.18    # S1 relevance   (semantic similarity seed -> candidate)
W_MOMENT = 0.16  # S7 moment richness (active-feed guarantee)
W_TREND = 0.07  # S3 trending    (light freshness)
W_REC = 0.04    # S2 recency     (near-zero — boost builds a durable follow graph)
assert abs(W_POP + W_CENT + W_REL + W_MOMENT + W_TREND + W_REC - 1.0) < 1e-9


# ── Blend weights — DEFAULT (no env) = ENHANCED taste-led: pop 0.18 / cent 0.20 / rel 0.35 ─────────
# The single documented fallback flag E8_LEGACY_BASELINE=1 restores the ORIGINAL team weights
# (pop 0.35 / cent 0.20 / rel 0.18) in full. richness/trending/recency are ALWAYS fixed at 0.16/0.07/0.04
# (richness is the spec's active-feed guarantee — never touched). The variable triple (rel/pop/cent) always
# renormalizes to (1 - fixed) = 0.73 so the six weights sum to exactly 1.0. Granular E8X_W_REL/POP/CENT
# overrides remain for A/B. This changes ONLY the weighting — no scoring-math shape, gate, or selection change.
ENH_W_POP, ENH_W_CENT, ENH_W_REL = 0.18, 0.20, 0.35   # enhanced default (taste-led)


def _legacy():
    return os.environ.get("E8_LEGACY_BASELINE", "0") == "1"


# ── Per-vertical richness floor (env-gated, reversible) ─────────────────────────────────────────
# The richness gate (richness >= floor, default 0.5) is applied PER VERTICAL, so a vertical whose
# richness is near-constant can be given its own floor WITHOUT touching the others. This is a GATE change
# only (which candidates are eligible) — it changes NO weight and NO scoring math. Default OFF: with no
# env set, every vertical uses the request-level `richness_floor` exactly as before (byte-identical).
#   E8_PODCAST_RICHNESS_FLOOR   podcast-only floor override (e.g. 0.0). Motivated by the current substrate:
#     7,169/8,170 podcasts sit at richness≈0.497 (re-keyed podcast moments lost the availability stream ->
#     near-constant velocity -> tie-collapsed percentile), so the 0.5 floor passes only 6.5% of podcasts.
#   E8_VERTICAL_RICHNESS_FLOOR  general form "vert=floor,vert=floor" (e.g. "podcast=0.0,tv=0.4"); takes
#     precedence over the podcast-specific var for any vertical it names.
def _vertical_floor(vertical, base_floor):
    """Resolve the effective richness floor for `vertical`. Returns `base_floor` unless an env override
    names this vertical (then that override wins). moment_count>0 stays a HARD gate regardless."""
    spec = os.environ.get("E8_VERTICAL_RICHNESS_FLOOR")
    if spec:
        for part in spec.split(","):
            if "=" in part:
                v, _, f = part.partition("=")
                if v.strip().lower() == vertical:
                    try:
                        return float(f)
                    except ValueError:
                        pass
    if vertical == "podcast":
        pf = os.environ.get("E8_PODCAST_RICHNESS_FLOOR")
        if pf is not None:
            try:
                return float(pf)
            except ValueError:
                pass
    return base_floor


def _weights():
    er, ep, ec = os.environ.get("E8X_W_REL"), os.environ.get("E8X_W_POP"), os.environ.get("E8X_W_CENT")
    if er is None and ep is None and ec is None:
        if _legacy():
            return W_POP, W_CENT, W_REL, W_MOMENT, W_TREND, W_REC       # legacy -> original team weights
        rel, pop, cen = ENH_W_REL, ENH_W_POP, ENH_W_CENT               # DEFAULT (no env) -> enhanced (W2)
    else:
        rel = float(er) if er is not None else ENH_W_REL               # partial A/B override on the enhanced base
        pop = float(ep) if ep is not None else ENH_W_POP
        cen = float(ec) if ec is not None else ENH_W_CENT
    fixed = W_MOMENT + W_TREND + W_REC                                  # 0.27, held constant
    s = rel + pop + cen
    if s > 0:
        k = (1.0 - fixed) / s                                           # renormalize the triple -> 0.73
        rel, pop, cen = rel * k, pop * k, cen * k
    return pop, cen, rel, W_MOMENT, W_TREND, W_REC


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
        # ROW-aligned (via row_meta): meta[pid] collapses the ~321 colliding guids to one vertical, so the
        # second twin's row would otherwise inherit the first twin's name and be dropped by the name-dedup.
        rm = getattr(data, "meta_row", None)
        if rm:
            norm = [_norm_name(rm[r].get("name")) for r in range(len(data.pids))]
            fran = [_franchise(rm[r].get("name")) for r in range(len(data.pids))]
        else:
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
    `seeds` are ROW indices (twin-correct); read popularity/name by row. Backend-agnostic (RAM arrays only)."""
    if not seeds:
        return "A popular pick to round out your feed"
    ranked = sorted(seeds, key=lambda r: float(data.popularity[r]) if 0 <= r < len(data.popularity) else 0.0,
                    reverse=True)
    names = [data.row_meta(r).get("name") or f"Property {r}" for r in ranked[:2]]
    return f"Popular with fans of {' and '.join(names)}"


# broad, cross-cutting genres — deprioritized in the truthful why_string so a SPECIFIC shared genre wins
# (e.g. prefer "supernatural"/"soulslike" over "action"). Used only for readability; truthfulness comes
# from the intersection itself (the tag is on BOTH the candidate and the seed by construction).
_BROAD_GENRES = {"action", "adventure", "drama", "comedy", "indie", "animation", "family"}


def _fmt_tag(t):
    """Display-normalize a genre tag: lowercase a plain Capitalized word ('Fantasy'->'fantasy') for natural
    mid-sentence reading, but preserve proper nouns / camelCase / multi-word tags ('FromSoftware',
    'Feudal Japan', 'science fiction') as-is."""
    t = t.strip()
    return t.lower() if (t[:1].isupper() and t[1:].islower()) else t


def _why_truthful(data, cand_row, nseed_row):
    """Truthful, seed-referencing why_string for the ENHANCED (max_any_seed) config. The nearest seed is the
    one that GAVE the winning max-to-any cosine in retrieval (passed in — NOT recomputed as a centroid).
    Rule: shared = candidate genres present ALSO on that seed, in candidate order (bm25_keywords are genre-
    salience-ordered) with pure-numeric tags (years) dropped; the most-specific shared tag = first NON-broad,
    else the earliest shared. Never asserts popularity or a trait not on both; no overlap -> bare seed ref.
    BOTH candidate and seed genres read by ROW (row_meta) so a collided twin cites its OWN genres/name."""
    sname = data.row_meta(nseed_row).get("name")
    if not sname:
        return "A pick to round out your feed"
    cand_g = data.row_meta(cand_row).get("genres") or []
    seed_g = {str(g).lower() for g in (data.row_meta(nseed_row).get("genres") or [])}
    shared = [g for g in cand_g if str(g).lower() in seed_g and not str(g).strip().isdigit()]
    if shared:
        non_broad = [g for g in shared if str(g).lower() not in _BROAD_GENRES]
        tag = _fmt_tag(str((non_broad or shared)[0]))
        art = "An" if tag[:1].lower() in "aeiou" else "A"
        return f"{art} {tag} pick, like {sname}"
    return f"Because you follow {sname}"   # no shared genre -> reference the seed by name, no fabricated reason


def build_boost(data, store, *, followed, target_per_vertical, total_cap, gap_threshold,
                exclude_verticals, exclude_ids, richness_floor, id_space="auto",
                deepen_covered=True, deepen_per_vertical=None, debug=False):
    """Return (context_dict, payload_groups, debug_dict|None). payload_groups: list of
    {vertical, vertical_label, properties:[...]} grouped by gap vertical.

    Seeds/excludes may arrive in the PUBLIC or EXTERNAL id space; id_space in {auto, public, external}
    controls translation. Internally everything is EXTERNAL (property_vectors); each output item carries
    both property_id (external) and public_property_id so the client can use whichever it needs."""
    norm_names, franchises = _name_arrays(data)

    # `followed`/`exclude_ids` are already-resolved ROW INDICES (api._resolve_inbound_ids did the twin-correct
    # entity_id/composite/bare-guid resolution). We do NOT re-resolve: data.resolve int-casts its input, which
    # would mis-read a row index as a guid. Seeds are ROWS end-to-end -> twin-correct taste/exclude/candidates.
    all_followed = {r for r in (followed or []) if r is not None and 0 <= r < len(data.pids)}
    seeds = list(dict.fromkeys(all_followed))
    seed_vert = Counter()
    for r in all_followed:
        v = data.row_meta(r).get("vertical")
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

    exclude = set(all_followed) | {r for r in (exclude_ids or []) if r is not None and 0 <= r < len(data.pids)}
    exclude_norm = {norm_names[r] for r in exclude if 0 <= r < len(norm_names)}     # exclude = ROWS (row-aligned)
    exclude_norm.discard("")

    # ── collect gated candidates per gap vertical via the vector store (pass 1) ──
    # store.candidates already applies the vertical + active gates (moment_count>0, richness>=floor) and
    # id-exclusion; here we only add the name-dedup guard and read the SCORING signals from RAM arrays.
    vert_set = {v for v, _, _ in gaps}
    pool = {v: [] for v in vert_set}    # vertical -> [{pid,row,pop,cen,rel_raw,rich,trd,rec}]
    floors_used = {}                    # vertical -> effective floor (for debug/observability)
    for v in vert_set:
        floor_v = _vertical_floor(v, floor)    # per-vertical gate (env-gated; == floor unless overridden)
        floors_used[v] = floor_v
        for pid, row, cosine, nseed in store.candidates(taste, v, floor_v, exclude, seed_rows=seeds):
            if row is None or norm_names[row] in exclude_norm:   # row = the UNAMBIGUOUS served row from the store
                continue
            pool[v].append({"pid": pid, "row": row, "pop": float(data.popularity[row]),
                            "cen": float(data.centrality[row]), "rel_raw": max(0.0, float(cosine)),
                            "rich": float(data.richness[row]), "trd": float(data.trending[row]),
                            "rec": float(data.recency[row]), "nseed": nseed})

    # ── score (pass 2): relevance is WITHIN-VERTICAL percentile of seed cosine, so the 18% weight
    # actually discriminates. Cross-vertical raw cosine is compressed into a narrow band (~0.02–0.48),
    # which would otherwise wash relevance out entirely while centrality/richness/trending (already
    # percentile-normalized) dominate. Popularity stays RAW — it is genuine absolute social proof.
    w_pop, w_cent, w_rel, w_mom, w_trd, w_rec = _weights()   # team weights when E8X_W_* unset (byte-identical)
    rel_raw_mode = os.environ.get("E8X_REL_RAW", "0") == "1"  # C1 side-test (default OFF): raw cosine vs percentile
    ranked = {}                         # vertical -> [(blend, pid, row, components)]
    for v, cands in pool.items():
        rel_pct = _rank_percentile([c["rel_raw"] for c in cands])
        scored = []
        for c, rp in zip(cands, rel_pct):
            rel_term = c["rel_raw"] if rel_raw_mode else rp   # OFF -> percentile (byte-identical)
            blend = (w_pop * c["pop"] + w_cent * c["cen"] + w_rel * rel_term + w_mom * c["rich"]
                     + w_trd * c["trd"] + w_rec * c["rec"])
            scored.append((blend, c["pid"], c["row"], {"popularity": c["pop"], "centrality": c["cen"],
                           "relevance": rp, "relevance_cosine": round(c["rel_raw"], 4),
                           "richness": c["rich"], "trending": c["trd"], "recency": c["rec"],
                           "nseed": c["nseed"]}))
        scored.sort(key=lambda t: t[0], reverse=True)
        ranked[v] = scored

    # desired count per gap vertical
    desired = {}
    kinds = {}
    for v, kind, need in gaps:
        kinds[v] = kind
        desired[v] = tgt if kind == "absent" else int(need)

    # ── select with franchise-cap + name-dedup, then fair round-robin under total_cap ──
    picked = defaultdict(list)          # vertical -> [(blend, pid, row, components)]
    used_norm = set(exclude_norm)
    fr_count = defaultdict(Counter)     # vertical -> franchise -> n

    def _take_one(v):
        """Pull the next eligible candidate for vertical v into picked[v]; True if one was taken."""
        for cand in ranked[v]:
            blend, pid, row, comp = cand
            if any(row == c[2] for c in picked[v]):          # dedup on ROW -> the ~321 twins are independently pickable
                continue
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
    # why_string — DEFAULT (no env) = the truthful seed-referencing builder (emitted when a nearest seed is
    # available, i.e. max_any_seed retrieval, the default). E8_LEGACY_BASELINE=1 restores the original
    # "Popular with fans of…" string; E8X_WHY_TRUTHFUL=0 disables it for A/B. Centroid picks (no nearest
    # seed) always use the original string. This changes only the why_string TEXT — never ranking.
    truthful_why = (not _legacy()) and (os.environ.get("E8X_WHY_TRUTHFUL", "1") != "0")
    groups = []
    gap_detected = []
    deepen_detected = []
    total_suggested = 0
    for v, kind, _ in gaps:
        (deepen_detected if kind == "deepen" else gap_detected).append(v)
        props = []
        for blend, pid, row, comp in picked[v]:
            m = data.row_meta(row)                       # UNAMBIGUOUS row meta (twin-correct entity_id/name/vertical)
            # ── COMPOSITE KEY (post-migration stable identity) ──────────────────────────
            # entity_id is the universal survivor ("Movie:119163"); derive the composite from it via the
            # FROZEN shared.identity. media_source_guid == source_id == the bare `property_id` below, but as
            # a STRING and — crucially — paired with profile_key it is UNAMBIGUOUS across the ~321 guids that
            # collide across verticals (Game:119163 vs Movie:119163). Fall back to (vertical, guid) if the
            # entity_id is absent/unrecognised so a served row always carries a profile_key.
            _raw_eid = m.get("entity_id")
            if _raw_eid:
                entity_id = str(_raw_eid)
                try:
                    _comp = composite_of(entity_id)
                except ValueError:
                    _comp = composite_fields(v, pid)   # unrecognised prefix -> derive from vertical + guid
            else:
                # no entity_id on the row -> build it from (vertical, guid); pid IS the source_id/guid
                entity_id = make_entity_id(v, pid)
                _comp = composite_fields(v, pid)
            props.append({
                "type": "property",
                # NOTE (client-contract): `property_id` here is the bare source_id / media_source_guid — it is
                # VERTICAL-AMBIGUOUS post-migration (collides across verticals). Kept for backward-compat; the
                # unambiguous key is (profile_key, media_source_guid) / entity_id. Prefer those.
                "property_id": pid,
                # DEPRECATED — the OLD public property_id (public_properties.id) is GONE from the new graph and
                # is NOT reconstructable; data.public_id() returns None under the default id_space. Retained as
                # an explicit null so existing clients don't KeyError; remove once no client reads it.
                "public_property_id": data.public_id(pid),
                "entity_id": entity_id,
                "profile_key": _comp["profile_key"],           # NEW — composite half 1 (per-vertical constant)
                "media_source_guid": _comp["media_source_guid"],  # NEW — composite half 2 (STRING; == source_id)
                "name": m.get("name"),
                "vertical": v,
                "genres": m.get("genres", [])[:6],
                "thumbnail_url": None,                  # not in the 44k-qwen set (UMI store resolves client-side)
                # TODO(client-contract, sign-off): the bare-guid deep_link is vertical-AMBIGUOUS (a shared guid
                # could resolve to the game or the movie). Proposed composite form: f"feeds://property/{entity_id}"
                # or f"feeds://{_comp['profile_key']}/{_comp['media_source_guid']}". Kept as-is until Michelle/
                # Viaduct sign off so the current client keeps working.
                "deep_link": f"feeds://property/{pid}",
                "score": round(float(blend), 4),
                "moment_richness_score": round(comp["richness"], 4),
                "popularity_score": round(comp["popularity"], 4),   # honest social-proof signal we DO have
                "follower_count": None,                 # resolved client-side from UMI store (spec open Q)
                "why_string": (_why_truthful(data, row, comp.get("nseed"))
                               if (truthful_why and comp.get("nseed") is not None) else _why(data, seeds)),
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
               "retrieval_mode": (os.environ.get("E8X_RETRIEVAL_MODE").lower() if os.environ.get("E8X_RETRIEVAL_MODE")
                                  else ("centroid" if _legacy() else "max_any_seed")),
               "per_seed_m": int(os.environ.get("E8X_PER_SEED_M", "10")),
               "richness_floor": floor, "richness_floor_per_vertical": floors_used,
               "weights": {"popularity": round(w_pop, 4), "centrality": round(w_cent, 4),
               "relevance": round(w_rel, 4), "moment_richness": round(w_mom, 4), "trending": round(w_trd, 4), "recency": round(w_rec, 4)}}
    return ctx, groups, dbg


_VLABEL = {"game": "Games", "movie": "Movies & Film", "tv": "TV & Shows", "podcast": "Podcasts",
           "music": "Music"}
