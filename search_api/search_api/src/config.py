"""Endpoint 4 (Search API) configuration — UC4 (in-app Search) + UC7 (Onboarding Thematic Search).

House style mirrors E1/E2/E3: every value reads from the environment with a local-dev default; NOTHING
is a magic number at a call site. The two retrieval paths (name + thematic), the per-(mode,vertical)
ranking weights, the junk-date recency bounds, the cross-vertical fairness cap, and the dedup threshold
are ALL named constants here so the next prompt can tune them without touching logic.
"""

from __future__ import annotations

import os
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[4]   # src → search_api → local_code → endpoint_4_search → ROOT
REPO_ROOT = _REPO_ROOT

# ── Service ──────────────────────────────────────────────────────────────────
API_PORT = int(os.getenv("SEARCH_API_PORT", "8050"))      # E1=:8020 E2=:8030 E3=:8040 E4=:8050
API_HOST = os.getenv("SEARCH_API_HOST", "127.0.0.1")
VERSION = os.getenv("SEARCH_VERSION", "1.0")
ENDPOINT_LABEL = os.getenv("SEARCH_ENDPOINT_LABEL", "search")
ENGINE_LABEL = os.getenv("SEARCH_ENGINE_LABEL", "v1.3")

# ── Postgres (the dedicated endpoint_4_search DB — co-located with property_popularity) ──
PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = int(os.getenv("POSTGRES_PORT", "5432"))
PG_DB = os.getenv("SEARCH_PG_DB", "endpoint_4_search")    # NOT feedsai_poc
PG_USER = os.getenv("POSTGRES_USER", "postgres")
PG_PASSWORD = os.getenv("POSTGRES_PASSWORD", "feedsai123")

# ── Neo4j re-keyed graph — the entity_id ⇄ composite bridge (E3 pattern). READ-ONLY. ──
# POST composite-key migration the bridge keys on entity_id (the PUBLIC property_id is gone); default points
# at the re-keyed local graph. Creds via env.
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7690")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "feedsaiRekeyGraph2026")   # via env for the re-keyed graph
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# ── Qwen vectors + query-embed (the existing deploy embedder; creds from shared/vector/.env) ──
VECTOR_PARQUET = os.getenv("SEARCH_VECTOR_PARQUET", str(_REPO_ROOT / "embeddings.parquet"))
QWEN_ENV_FILE = os.getenv("SEARCH_QWEN_ENV", str(_REPO_ROOT / "shared" / "vector" / ".env"))
QWEN_INSTRUCTION = os.getenv(
    "SEARCH_QWEN_INSTRUCTION",
    "Instruct: Given a search query, retrieve relevant entertainment titles\nQuery: ")  # Qwen native convention
QWEN_EMBED_TIMEOUT = float(os.getenv("SEARCH_QWEN_TIMEOUT", "30"))
EMBED_DIM = int(os.getenv("SEARCH_EMBED_DIM", "1024"))

# ── Retrieval knobs ──────────────────────────────────────────────────────────
THEMATIC_ANN_K = int(os.getenv("SEARCH_THEMATIC_ANN_K", "200"))   # legacy global-scan size (retained as fallback)
# v1.3.2: per-vertical ANN quota — retrieve top-K from EACH vertical, merge, so cross-vertical breadth (UC7
# Story 3) is not capped by what the global nearest-neighbours surface. 50×4 ≈ 200 pool (parity with the old
# global K) but balanced; for a single-vertical request only that vertical is quota'd (→ 50 candidates).
THEMATIC_K_PER_VERTICAL = int(os.getenv("SEARCH_THEMATIC_K_PER_VERTICAL", "50"))
NAME_FUZZY_POOL = int(os.getenv("SEARCH_NAME_FUZZY_POOL", "40"))  # rapidfuzz candidate pool (re-scored + floored)

# ── NAME RELEVANCE — identity-first (the v1.3.1 quality fix) ──────────────────
# Tiered: EXACT tier (normalized string-equality OR token-set equality) → relevance 1.0, ranked ABOVE all
# non-exact regardless of centrality/popularity. FUZZY uses a TOKEN score (max of token_sort/token_set)
# with a LENGTH-AWARE GUARD: a token-set "subset" bonus that the order-sensitive token_sort score does not
# support (gap ≥ GAP and token_sort < GUARD_MIN) is distrusted → falls back to token_sort, so partial-word
# overlap ("Dark Side of the Ring" vs "Elden Ring", token_sort≈0.40) cannot clear the raised floor.
NAME_FUZZY_MIN = float(os.getenv("SEARCH_NAME_FUZZY_MIN", "0.80"))        # raised 0.55→0.80 (battery-justified)
FUZZY_GUARD_SORT_MIN = float(os.getenv("SEARCH_FUZZY_GUARD_SORT_MIN", "0.50"))  # token_sort floor for trusting a set-subset bonus
FUZZY_SET_SORT_GAP = float(os.getenv("SEARCH_FUZZY_SET_SORT_GAP", "0.15"))      # set−sort gap that flags a partial-overlap subset
# QUERY-COVERAGE GATE — the asymmetry fix: token_set is generous when the NAME is a fragment of the QUERY
# ("Stardew Valley"→"Valley", "Elden Ring"→"Ring 2", "horror games"→"#Horror" all score 1.0). Require that
# every query token has a char-close match in the name (so the matched name actually contains what the user
# typed, allowing per-token misspelling). This is what makes name relevance identity-first, not fragment-first.
# v1 finalize: raised 0.80→0.82 to reject the short-query collision anime→"Annie" (ratio 0.80) while KEEPING
# every legit recovery — eldn→elden 0.889, wichter→witcher 0.857, thigns→things 0.833. (0.85 was rejected: it
# would also drop the thigns transposition at 0.833; 0.82 is the minimal-collateral value.)
NAME_COVERAGE_TOKEN_MIN = float(os.getenv("SEARCH_NAME_COVERAGE_TOKEN_MIN", "0.82"))  # per-token char ratio to count as covered
NAME_QUERY_COVERAGE_MIN = float(os.getenv("SEARCH_NAME_QUERY_COVERAGE_MIN", "0.60"))  # fraction of query tokens that must be covered
# v1 finalize: a <2-char query ("a") must not produce a name hit — too little signal for identity. Such queries
# get no name candidates (route thematic / return empty-name gracefully); avoids 1-char fuzzy noise.
NAME_MIN_QUERY_LEN = int(os.getenv("SEARCH_NAME_MIN_QUERY_LEN", "2"))
DEFAULT_LIMIT = int(os.getenv("SEARCH_DEFAULT_LIMIT", "20"))

# ── AUTO-mode routing (name vs thematic vs both) — exact-aware ────────────────
AUTO_NAME_CONFIDENCE = float(os.getenv("SEARCH_AUTO_NAME_CONFIDENCE", "0.85"))  # best name rel ≥this & no exact → NAME
AUTO_AMBIGUOUS_MIN = float(os.getenv("SEARCH_AUTO_AMBIGUOUS_MIN", "0.80"))      # fuzzy rel ≥this counts as a "strong variant"
AUTO_AMBIGUOUS_COUNT = int(os.getenv("SEARCH_AUTO_AMBIGUOUS_COUNT", "3"))       # ≥this many strong variants → run BOTH

# ── RANKING — v1.3 weights with the verified-data podcast adaptation ─────────
# Signals (each normalized 0..1): relevance, centrality, popularity, recency, trending(inert 0), proximity(inert 0).
# PODCAST: attribute-centrality is degenerate (all at the GDS floor — confirmed), so centrality weight → 0 and
# is ADDED to popularity. Implemented as a per-(mode,vertical) table, NOT a special-case branch.
_W_NAME_DEFAULT = {"relevance": .38, "centrality": .30, "popularity": .16, "trending": .08, "recency": .04, "proximity": .04}
_W_NAME_PODCAST = {"relevance": .38, "centrality": .00, "popularity": .46, "trending": .08, "recency": .04, "proximity": .04}
_W_THEM_DEFAULT = {"relevance": .42, "centrality": .18, "popularity": .26, "trending": .08, "recency": .04, "proximity": .02}
_W_THEM_PODCAST = {"relevance": .42, "centrality": .00, "popularity": .44, "trending": .08, "recency": .04, "proximity": .02}
WEIGHTS = {
    ("name", "podcast"): _W_NAME_PODCAST, ("name", "*"): _W_NAME_DEFAULT,
    ("thematic", "podcast"): _W_THEM_PODCAST, ("thematic", "*"): _W_THEM_DEFAULT,
}
SIGNALS = ("relevance", "centrality", "popularity", "recency", "trending", "proximity")
TRENDING_INERT = float(os.getenv("SEARCH_TRENDING", "0.0"))    # reserved placeholder (no source yet)
PROXIMITY_INERT = float(os.getenv("SEARCH_PROXIMITY", "0.0"))  # properties-only → reserved


def weights_for(scoring_mode: str, vertical: str) -> dict:
    """scoring_mode ∈ {name, thematic} (derived from a result's match_type). Per-vertical podcast override."""
    return WEIGHTS.get((scoring_mode, vertical)) or WEIGHTS[(scoring_mode, "*")]


# ── RECENCY — exp decay from recency_date, JUNK-DATE GATED like E3 ───────────
RECENCY_HALFLIFE_DAYS = float(os.getenv("SEARCH_RECENCY_HALFLIFE_DAYS", "365"))
RECENCY_JUNK_MIN_YEAR = int(os.getenv("SEARCH_RECENCY_JUNK_MIN_YEAR", "1980"))   # < this → junk → 0.0
RECENCY_JUNK_MAX_FUTURE_DAYS = float(os.getenv("SEARCH_RECENCY_JUNK_MAX_FUTURE_DAYS", "1095"))  # > now+3y → junk → 0.0

# ── CROSS-VERTICAL FAIRNESS (UC7 Story 3) ────────────────────────────────────
FAIRNESS_MAX_VERTICAL_SHARE = float(os.getenv("SEARCH_FAIRNESS_MAX_SHARE", "0.5"))   # no vertical > ~50% of limit
FAIRNESS_SINGLE_VERTICAL_DOMINANCE = float(os.getenv("SEARCH_FAIRNESS_SINGLE_DOM", "0.9"))  # ≥this of top → single-vertical query
# v1.3.2: ONBOARDING (UC7 Story 3) forces cross-vertical spread — the single-vertical-intent exemption is
# skipped, so even a podcast-clustered query like "cooking shows…" gets capped and spreads. UC4 in-app search
# keeps the exemption (a name/franchise query like "The Daily"/"Battlefield" stays one-vertical, no off-topic
# verticals injected). The 0.5 output cap itself is unchanged; this only gates WHEN the exemption applies.
FAIRNESS_ONBOARDING_FORCES_SPREAD = os.getenv("SEARCH_FAIRNESS_ONBOARDING_SPREAD", "true").lower() in ("1", "true", "yes")

# ── VERTICAL-WORD INTENT (soft boost) ────────────────────────────────────────
# Detect a vertical keyword in the query (case-insensitive, word-boundary), STRIP it from the embed text
# (so relevance is on the real topic — "comedy movies" → embed "comedy"), and BOOST that vertical's results
# so they lead. Longest keyword wins when stripping ("tv show" before "tv"/"show"). Extend by adding to a
# vertical's list. The boost is additive + SOFT: the exact tier still dominates, and it NEVER hard-filters —
# other verticals backfill the tail when the named vertical is thin (graceful fallback, never empty).
VERTICAL_KEYWORDS = {
    "game": ["gaming", "games", "game"],
    "movie": ["movies", "movie", "films", "film"],
    "tv": ["tv shows", "tv show", "shows", "show", "series", "tv"],
    "podcast": ["podcasts", "podcast", "pod"],
}
VERTICAL_WORD_BOOST = float(os.getenv("SEARCH_VERTICAL_WORD_BOOST", "0.2"))  # additive score bump for the named vertical

# ── "MORE LIKE THIS" (mode auto, on a confident single exact match) ──────────
# When auto finds ONE exact match, backfill from that entity's OWN stored Qwen vector (no live embed) and
# soft-boost neighbours that share the matched entity's vertical (Fortnite → other games lead). Softer than
# the vertical-word boost so a standout cross-vertical neighbour (e.g. a great gaming podcast) can still
# appear below. Never a hard filter — other verticals backfill the tail.
MLT_SAME_VERTICAL_BOOST = float(os.getenv("SEARCH_MLT_SAME_VERTICAL_BOOST", "0.15"))

# ── PREFIX MATCHING (search-as-you-type) ─────────────────────────────────────
# An in-memory edge-token PREFIX tier ranked BETWEEN exact and fuzzy (exact > prefix > fuzzy), built at
# startup. match-boolean-prefix: every query token but the last must be a name token; the LAST token is a
# prefix of a name token (single-token query → prefix of the name's LEADING token). Reuses NAME_MIN_QUERY_LEN
# (2) as the floor — no prefix matching under 2 chars.
PREFIX_BASE_RELEVANCE = float(os.getenv("SEARCH_PREFIX_BASE_RELEVANCE", "0.7"))            # prefix is a strong signal (high base)
PREFIX_COMPLETENESS_WEIGHT = float(os.getenv("SEARCH_PREFIX_COMPLETENESS_WEIGHT", "0.3"))  # + how much of the name the query covers
# ADMISSION GATE: a candidate only enters the PREFIX TIER (tier 1, boosted above thematic) if the query covers
# at least this fraction of the matched name (char-based completeness = len(query)/len(name)). This stops a
# SHORT CONCEPT WORD that happens to be a name-prefix from hijacking THEMATIC queries: "sci-fi" covers only
# ≤0.20 of "Old Time Sci-Fi Radio"/"Sci-Fi & Fantasy…" → excluded; but "fortn"→Fortnite (0.625),
# "fortni"→Fortnite (0.75), "elden rin"→Elden Ring (0.90) → admitted. Empirical window is (0.583, 0.625]:
# above the fantasy/space concept cluster (Fantasy Life 0.583, Space Jam 0.556) yet at/below fortn (0.625).
PREFIX_MIN_COMPLETENESS = float(os.getenv("SEARCH_PREFIX_MIN_COMPLETENESS", "0.6"))        # concept-word ≠ name-prefix guard
PREFIX_POOL = int(os.getenv("SEARCH_PREFIX_POOL", "200"))                                  # cap kept prefix candidates (by popularity) — stops a short prefix flooding
PREFIX_MLT_MARGIN = float(os.getenv("SEARCH_PREFIX_MLT_MARGIN", "0.15"))                   # top prefix must beat the runner-up by this (blend) to uniquely resolve → MLT

# ── CONFIDENT-PIN GUARDS (structural; stop auto from confidently mis-pinning a coincidental match) ──
# Root finding: no absolute floor on relevance/completeness/popularity separates a genuine confident pin from a
# coincidental one (the genuine "Elden Ring"→movie sits at pop 0.581, BELOW the wrong "Friends"→Friendship 0.786).
# So we gate more-like-this on STRUCTURE, not tuned score floors:
#   • leading-substring: a PREFIX candidate must be a true leading prefix (name startswith query) — enforced in
#     name_index, kills "The Godfather"→"The Black Godfather" (a token-subset, not a leading prefix).
#   • MLT_MIN_QUERY_LEN: never SEED more-like-this from an ultra-short query. "fo" (2 chars) uniquely-resolves to
#     "Foe" and would amplify it; 2–3 chars carry too little intent to justify amplification. 4 = the shortest
#     length at which a query is a plausible whole word/name (keeps "news"/"halo"; blocks "fo"/"foo").
MLT_MIN_QUERY_LEN = int(os.getenv("SEARCH_MLT_MIN_QUERY_LEN", "4"))
#   • catalog cross-check (PREFIX): suppress a prefix confident pin + MLT when the query EXACTLY matches an
#     UNBRIDGED catalog entity STRICTLY more popular than the pinned bridged match ("Friends"→Friendship while the
#     real Friends is unbridged at 0.996). SIGNAL ONLY: unbridged entities never enter results. Bare comparison.
#   • catalog cross-check (EXACT), Break-1 fix: the exact branch is NOT blanket-spared — suppress the exact pin +
#     MLT when a same-name unbridged twin is MUCH more popular (RELATIVE gap ≥ EXACT_TWIN_GAP_MARGIN). This catches
#     the obscure bridged namesakes ("Game of Thrones"→pop-0 game, "Scent of a Woman"→K-drama; gap 0.87–0.999)
#     while sparing the genuine "Elden Ring"→movie (gap 0.392 < 0.6) and "mine"→"Mine" (no twin). The GAP encodes
#     both conditions at once — the pin is a near-invisible nobody AND a famous twin exists. Proven window
#     (0.407, 0.873]; 0.6 sits mid-window (+0.19 above Tracker, −0.27 below the lowest catch). NOT caught (proven
#     unseparable, documented): "Tracker"/"The Boys" (real mid-pop movie / no twin) — margin is NOT tuned to chase them.
EXACT_TWIN_GAP_MARGIN = float(os.getenv("SEARCH_EXACT_TWIN_GAP_MARGIN", "0.6"))

# ── FUZZY WHOLE-NAME-TYPO PROMOTION (Fix 2, narrow) ───────────────────────────
# A fuzzy hit is promoted ABOVE thematic (its own sub-tier) ONLY when it is a genuine typo of the WHOLE name —
# i.e. the query covers ≥ this fraction of the matched name. "fortnight"→"Fortnite" (completeness 1.0) qualifies;
# a CONCEPT word that is merely a TOKEN inside a longer title ("comedy" ⊂ "Sex is Comedy" = 0.46, "space" ⊂
# "Space Chef" = 0.5) does NOT, so concept queries stay thematic-led. 0.8 sits well above the concept-subset
# cluster (≤0.6) and below any real typo (≈1.0).
FUZZY_TYPO_MIN_COMPLETENESS = float(os.getenv("SEARCH_FUZZY_TYPO_MIN_COMPLETENESS", "0.8"))
# DOMINANCE (Break-3 fix): promote a fuzzy_typo only if it resolves to ONE dominant title. A genuine typo has a
# single distinct candidate name ("fortnight"→Fortnite, "amoung us"→Among Us); a coincidental TOKEN-OVERLAP matches
# SEVERAL distinct titles ("the last of us"→{The Story of Us, The Rest of Us}, "the bear movie"→{X/ABBA/Bluey: The
# Movie}) — demote all of those back to plain fuzzy. If MORE than this many DISTINCT candidate names carry the
# fuzzy_typo mark, none promote. (Edit-distance/popularity can't help here: "witchr"→"Switch" is edit-ratio 0.333 /
# pop 0.867 / 1 name — numerically identical to genuine typos — so it stays a documented false-positive limitation.)
FUZZY_TYPO_MAX_DISTINCT_NAMES = int(os.getenv("SEARCH_FUZZY_TYPO_MAX_DISTINCT_NAMES", "1"))

# ── DEDUP (serve-time composite-identity collapse) ───────────────────────────
DEDUP_ENABLED = os.getenv("SEARCH_DEDUP_ENABLED", "true").lower() in ("1", "true", "yes")

# ── source_context that forces onboarding semantics ──────────────────────────
ONBOARDING_SOURCE_CONTEXT = os.getenv("SEARCH_ONBOARDING_CONTEXT", "onboarding_search")

# ── Follows (exclude_followed) — the vendored CsvFollowSource over E4's own dev export ──
# Standalone: default points at E4's OWN copy of the dev followers CSV (code+fixture vendored, no shared
# path). Deploy overrides SEARCH_FOLLOWERS_CSV / backs it with the live source.
FOLLOWERS_CSV = os.getenv(
    "SEARCH_FOLLOWERS_CSV",
    str(Path(__file__).resolve().parent.parent / "data" / "dev" / "followers_dev.csv"))


def summary() -> dict:
    return {"port": API_PORT, "pg_db": PG_DB, "neo4j_uri": NEO4J_URI, "engine": ENGINE_LABEL,
            "vector_parquet": Path(VECTOR_PARQUET).name}
