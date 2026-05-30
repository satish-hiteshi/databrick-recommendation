"""
Deterministic reasoning engine for Feeds.ai.
Generates human-readable explanations for why each recommendation was shown.
No technical terms (vector, BM25, embedding, cosine, semantic) allowed.
"""

import random
from pipeline import entity_store

# ── Generic keywords to deprioritize (too vague to be interesting) ────
GENERIC_KW = {
    "action", "adventure", "indie", "drama", "thriller", "fantasy",
    "science fiction", "horror", "animation", "platform",
}

# ── Lazy-loaded lookups (avoids circular import with reranker) ────────
_kw_cache = None
_franchise_cache = None

def _ensure_cache():
    global _kw_cache, _franchise_cache
    if _kw_cache is None:
        entities = entity_store.get_all()
        _kw_cache = {e["entity_id"]: [k.lower() for k in e["bm25_keywords"]] for e in entities}
        _franchise_cache = {e["entity_id"]: e.get("franchise") for e in entities}

def _get_kw(eid):
    _ensure_cache()
    return _kw_cache.get(eid, [])

def _get_franchise(eid):
    _ensure_cache()
    return _franchise_cache.get(eid)


def _pick_distinctive_keywords(shared_kw, n=3):
    """Pick the most distinctive shared keywords, deprioritizing generic ones."""
    specific = [k for k in shared_kw if k not in GENERIC_KW]
    generic = [k for k in shared_kw if k in GENERIC_KW]
    picked = (specific + generic)[:n]
    return [k.replace("_", " ") for k in picked] if picked else []


# ══════════════════════════════════════════════════════════════════════
# TEMPLATE POOL — 80+ templates across 10 categories
# ══════════════════════════════════════════════════════════════════════

TEMPLATES = {

    # ── Single anchor, shared genres/keywords ─────────────────────
    "single_genre": [
        "If you enjoyed {anchor}, you'll find a similar {kw1} and {kw2} sensibility here",
        "Shares the {kw1} energy and {kw2} atmosphere that makes {anchor} compelling",
        "{result} captures a similar blend of {kw1} and {kw2} to what draws people to {anchor}",
        "The {kw1} elements here echo what works so well in {anchor}",
        "Much like {anchor}, this leans into {kw1} with a strong dose of {kw2}",
        "Fans of {anchor} will recognise the {kw1} roots and {kw2} undertones",
        "Built on the same {kw1} foundation that makes {anchor} stand out",
        "A natural companion to {anchor} — both thrive on {kw1} and {kw2}",
        "Carries the same {kw1} spirit that defines {anchor}",
        "Rooted in the {kw1} tradition that {anchor} exemplifies",
    ],

    # ── Single anchor, thematic overlap ───────────────────────────
    "single_theme": [
        "The {kw1} and {kw2} themes here run parallel to what makes {anchor} distinctive",
        "Both {anchor} and this share a core thread of {kw1} woven through {kw2}",
        "If the {kw1} quality of {anchor} hooked you, this delivers a similar pull",
        "Taps into the same {kw1} atmosphere that gives {anchor} its edge",
        "Where {anchor} thrives on {kw1}, this finds its own path through the same territory",
        "Explores {kw1} with the kind of intensity that fans of {anchor} appreciate",
        "Channels the {kw1} mood that makes {anchor} memorable",
        "Cut from the same cloth as {anchor} when it comes to {kw1}",
    ],

    # ── Single anchor, minimal overlap but experiential match ─────
    "single_vibe": [
        "Evokes a similar mood and intensity to {anchor}",
        "Hits the same emotional notes as {anchor}, even if the surface looks different",
        "Something about this carries the same weight as {anchor}",
        "Occupies a similar creative space to {anchor}",
        "The overall feel here mirrors what makes {anchor} resonate",
        "Appeals to the same instincts that draw people to {anchor}",
    ],

    # ── Multi anchor, overlap ─────────────────────────────────────
    "multi_overlap": [
        "Sits at the intersection of what you love about {anchor1} and {anchor2}",
        "Combines the {kw1} quality of {anchor1} with the {kw2} feel of {anchor2}",
        "If {anchor1} and {anchor2} are both in your favourites, this belongs alongside them",
        "Bridges the gap between {anchor1}'s {kw1} intensity and {anchor2}'s {kw2} depth",
        "Where {anchor1} meets {anchor2} — this lives in that overlap",
        "Draws from both {anchor1} and {anchor2} in ways that feel intentional",
        "Picked up signals from both {anchor1} and {anchor2} in your taste",
        "A strong fit for someone who values both {anchor1} and {anchor2}",
        "The {kw1} of {anchor1} and the {kw2} of {anchor2} converge here",
        "Resonates with fans of both {anchor1} and {anchor2}",
    ],

    # ── Multi anchor, single anchor match ─────────────────────────
    "multi_single_hit": [
        "Closely aligned with {anchor1} — sharing its {kw1} identity",
        "Especially connected to {anchor1} through their shared {kw1} approach",
        "Strongest connection is to {anchor1} and its {kw1} sensibility",
        "Primarily echoes {anchor1}, particularly in its {kw1} elements",
        "Your love for {anchor1} is the main thread here, especially the {kw1}",
        "Leans closest to {anchor1} among your picks, driven by its {kw1} core",
        "The {kw1} DNA of {anchor1} is what connects these two most strongly",
        "If {anchor1} is your favourite of the bunch, this is its closest sibling",
        "Mirrors {anchor1}'s {kw1} identity more than any other result",
        "The {kw1} hallmarks of {anchor1} are unmistakable here",
    ],

    # ── Franchise connection ──────────────────────────────────────
    "franchise": [
        "Part of the {franchise} universe you already enjoy",
        "Another chapter in the {franchise} world",
        "Extends the {franchise} experience into a new direction",
        "Continues the {franchise} story you're already invested in",
        "More from the {franchise} world — a natural next step",
    ],

    # ── Theme-based (no anchor entity) ────────────────────────────
    "theme_match": [
        "Matches the {kw1} and {kw2} atmosphere you're looking for",
        "Strong {kw1} content with the {kw2} quality you described",
        "Exactly the kind of {kw1}, {kw2} experience you asked about",
        "Delivers on the {kw1} front with genuine {kw2} depth",
        "A prime example of {kw1} done with {kw2} conviction",
        "Nails the {kw1} mood you're after, with rich {kw2} elements",
        "Built around {kw1} and {kw2} — right in your described wheelhouse",
        "Leans heavily into the {kw1} and {kw2} space you're exploring",
        "Pure {kw1} through and through, with notable {kw2} flavour",
        "If {kw1} is what you crave, this brings it with plenty of {kw2}",
        "Fully committed to the {kw1} experience, bolstered by {kw2}",
        "A textbook example of compelling {kw1} layered with {kw2}",
        "Dripping with {kw1} atmosphere and grounded in {kw2}",
        "Goes all in on {kw1} — the {kw2} adds real texture",
        "Checks the {kw1} box emphatically, with {kw2} adding nuance",
        "The {kw1} here is front and centre, supported by strong {kw2}",
        "Lives and breathes {kw1}, with a undercurrent of {kw2}",
        "Unmistakably {kw1}, and the {kw2} dimension gives it extra weight",
        "One of the stronger {kw1} picks, enriched by its {kw2} elements",
        "Takes {kw1} seriously and wraps it in a satisfying layer of {kw2}",
    ],

    # ── Descriptive (derived keywords) ────────────────────────────
    "descriptive_match": [
        "Captures the {kw1} quality you're looking for",
        "Aligns with your interest in {kw1} and {kw2}",
        "Fits the {kw1} profile you described, with {kw2} woven throughout",
        "Matches your description — strong {kw1} with {kw2} undertones",
        "This is the {kw1}, {kw2} content you had in mind",
        "Delivers the {kw1} experience you outlined",
        "Right in line with your taste for {kw1} and {kw2}",
        "The kind of {kw1} experience your description points toward",
        "Squarely in the {kw1} space — packed with {kw2}",
        "A solid {kw1} pick that also brings {kw2} into the mix",
        "Hits the {kw1} notes you described and adds some {kw2} flavour",
        "Exactly what comes to mind when you say {kw1} and {kw2}",
        "Nails the {kw1} side of what you're after",
        "Think {kw1} meets {kw2} — this is that intersection",
        "Heavy on {kw1}, with a satisfying thread of {kw2} running through it",
        "If {kw1} is the headline, {kw2} is the undertone — and both land here",
    ],

    # ── Cross-vertical discovery ──────────────────────────────────
    "cross_vertical": [
        "A different medium, same emotional DNA as {anchor}",
        "What {anchor} does for {anchor_vert}, this does for {result_vert}",
        "Translates the {anchor} experience into {result_vert} form",
        "If you want the {anchor} feeling in a {result_vert}, this is it",
        "Carries {anchor}'s spirit into the world of {result_vert}",
        "The {result_vert} equivalent of what {anchor} offers",
    ],

    # ── Negative filter survived ──────────────────────────────────
    "negative_survived": [
        "Notably different from {neg} in tone and approach",
        "Steers clear of the {neg_kw} elements you wanted to avoid",
        "Avoids the {neg_kw} territory — this goes in a different direction",
        "Nothing like {neg} — this takes a distinctly different path",
        "Well outside the {neg_kw} zone you flagged",
    ],

    # ── Fallback (always usable) ──────────────────────────────────
    "fallback": [
        "A strong match based on your overall taste profile",
        "Well-suited to the kind of content you gravitate toward",
        "Fits the pattern of what you enjoy",
        "Aligns well with your stated preferences",
        "Recommended based on the combination of qualities you value",
        "A natural recommendation given everything you've described",
    ],
}


# ══════════════════════════════════════════════════════════════════════
# TEMPLATE SELECTION (avoids repetition within a query)
# ══════════════════════════════════════════════════════════════════════

def _select_template(category, used_set):
    """Pick a template from the category pool, avoiding recently used ones."""
    pool = TEMPLATES.get(category, TEMPLATES["fallback"])
    available = [t for t in pool if t not in used_set]
    if not available:
        available = pool  # All used — allow re-use from full pool
    chosen = random.choice(available)
    used_set.add(chosen)
    return chosen


# ══════════════════════════════════════════════════════════════════════
# REASONING GENERATOR
# ══════════════════════════════════════════════════════════════════════

def generate_reasoning(result, anchor_entities, nlu_output, used_templates):
    """
    Generate human-readable reasoning for a single result.

    Args:
        result: dict with entity_id, name, vertical, shared_keywords, etc.
        anchor_entities: list of resolved positive entity dicts
        nlu_output: full NLU output with query_mode, keywords, negatives, etc.
        used_templates: set — shared across all results in one query for dedup

    Returns:
        (reasoning_short, reasoning_long)
    """
    mode = nlu_output.get("query_mode", "")
    add_kw = nlu_output.get("additional_keywords", [])
    desc_kw = nlu_output.get("description_derived_keywords", [])
    neg_entities = nlu_output.get("negative_entities", [])
    all_kw = add_kw + desc_kw
    shared = result.get("shared_keywords", [])
    result_name = result["name"]
    result_vert = result["vertical"]
    result_vert_label = {"game": "games", "movie": "movies", "tv": "TV shows"}.get(result_vert, result_vert)

    cand_kw = _get_kw(result.get("entity_id", ""))
    cand_franchise = _get_franchise(result.get("entity_id", ""))

    # ── Determine primary signal ──────────────────────────────────

    # 1. Franchise match (highest priority)
    anchor_franchises = {
        e.get("franchise"): e["name"]
        for e in anchor_entities if e.get("franchise")
    }
    if cand_franchise and cand_franchise in anchor_franchises:
        tmpl = _select_template("franchise", used_templates)
        text = tmpl.format(franchise=cand_franchise, result=result_name)
        return _make_short_long(text)

    # 2. Multi-anchor overlap
    if len(anchor_entities) >= 2 and result.get("appeared_in_searches", 1) > 1:
        kws = _pick_distinctive_keywords(shared, 2)
        a1, a2 = anchor_entities[0]["name"], anchor_entities[1]["name"]
        kw1 = kws[0] if kws else "intensity"
        kw2 = kws[1] if len(kws) > 1 else "depth"
        tmpl = _select_template("multi_overlap", used_templates)
        text = tmpl.format(anchor1=a1, anchor2=a2, kw1=kw1, kw2=kw2, result=result_name)
        return _make_short_long(text)

    # 3. Cross-vertical discovery
    if anchor_entities and mode in ("entity_single", "entity_multi"):
        anchor = anchor_entities[0]
        if anchor["vertical"] != result_vert:
            kws = _pick_distinctive_keywords(shared, 2)
            anchor_vert_label = {"game": "games", "movie": "movies", "tv": "TV shows"}.get(anchor["vertical"], anchor["vertical"])
            tmpl = _select_template("cross_vertical", used_templates)
            text = tmpl.format(
                anchor=anchor["name"], anchor_vert=anchor_vert_label,
                result_vert=result_vert_label, result=result_name,
                kw1=kws[0] if kws else "", kw2=kws[1] if len(kws) > 1 else "",
            )
            return _make_short_long(text)

    # 4. Single anchor with shared keywords
    if anchor_entities and shared:
        anchor = anchor_entities[0]
        kws = _pick_distinctive_keywords(shared, 2)
        kw1 = kws[0] if kws else "intensity"
        kw2 = kws[1] if len(kws) > 1 else "depth"

        if len(anchor_entities) >= 2:
            tmpl = _select_template("multi_single_hit", used_templates)
            text = tmpl.format(anchor1=anchor["name"], kw1=kw1, kw2=kw2, result=result_name)
        elif len(kws) >= 2:
            tmpl = _select_template("single_genre", used_templates)
            text = tmpl.format(anchor=anchor["name"], kw1=kw1, kw2=kw2, result=result_name)
        else:
            tmpl = _select_template("single_theme", used_templates)
            text = tmpl.format(anchor=anchor["name"], kw1=kw1, kw2=kw2, result=result_name)
        return _make_short_long(text)

    # 5. Single anchor, vibe match (no shared keywords)
    if anchor_entities:
        anchor = anchor_entities[0]
        tmpl = _select_template("single_vibe", used_templates)
        text = tmpl.format(anchor=anchor["name"], result=result_name)
        return _make_short_long(text)

    # 6. Theme-based (no anchor entity)
    if mode == "theme_based" and all_kw:
        kws = [k for k in all_kw if k.lower() not in GENERIC_KW] or all_kw
        kw1 = kws[0] if kws else "this genre"
        kw2 = kws[1] if len(kws) > 1 else (cand_kw[0] if cand_kw else "quality")
        tmpl = _select_template("theme_match", used_templates)
        text = tmpl.format(kw1=kw1, kw2=kw2, result=result_name)
        return _make_short_long(text)

    # 7. Descriptive (derived keywords)
    if mode == "descriptive" and desc_kw:
        kw1 = desc_kw[0]
        kw2 = desc_kw[1] if len(desc_kw) > 1 else (cand_kw[0] if cand_kw else "quality")
        tmpl = _select_template("descriptive_match", used_templates)
        text = tmpl.format(kw1=kw1, kw2=kw2, result=result_name)
        return _make_short_long(text)

    # 8. Mixed with keywords (theme component of mixed mode)
    if mode == "mixed" and all_kw:
        kws = [k for k in all_kw if k.lower() not in GENERIC_KW] or all_kw
        kw1 = kws[0]
        kw2 = kws[1] if len(kws) > 1 else "quality"
        tmpl = _select_template("theme_match", used_templates)
        text = tmpl.format(kw1=kw1, kw2=kw2, result=result_name)
        return _make_short_long(text)

    # 9. Fallback
    tmpl = _select_template("fallback", used_templates)
    text = tmpl.format(result=result_name)
    return _make_short_long(text)


def _make_short_long(text):
    """Split a reasoning text into short (≤80 chars) and long (≤200 chars) versions."""
    text = text.strip()
    if len(text) <= 80:
        return text, text
    # Short: truncate at last word boundary before 77 chars, add "..."
    short = text[:77].rsplit(" ", 1)[0] + "..."
    # Long: full text, capped at 200
    long = text[:200]
    return short, long


# ══════════════════════════════════════════════════════════════════════
# BATCH REASONING (call from reranker)
# ══════════════════════════════════════════════════════════════════════

def attach_reasoning(results, anchor_entities, nlu_output):
    """
    Attach reasoning_short and reasoning_long to each result in a list.
    Uses a shared used_templates tracker to prevent repetition within one query.
    """
    used = set()
    for r in results:
        short, long = generate_reasoning(r, anchor_entities, nlu_output, used)
        r["reasoning_short"] = short
        r["reasoning_long"] = long
