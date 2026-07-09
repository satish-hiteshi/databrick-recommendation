"""Discovery-API (Endpoint 2) configuration — ALL tunable knobs in ONE place.

House style mirrors `agent_recs/src/config.py`: every value reads from the environment with a
sensible local-dev default, and `summary()` returns a non-secret view. No magic numbers should live
anywhere else in the engine — import from here.

NOTE: this prompt builds the engine CORE (config, data-access, popularity prep, profile, candidate
pools). The ranking WEIGHTS below are PLACEHOLDERS for the P4 scorer — they are declared here so the
seam exists, but nothing in this prompt blends them into a final score.
"""

import os
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────
_SRC_DIR = Path(__file__).resolve().parent              # discovery_api/src/
_PKG_DIR = _SRC_DIR.parent                              # discovery_api/
DEV_DATA_DIR = Path(os.getenv("DISCOVERY_DEV_DATA_DIR", str(_PKG_DIR / "data" / "dev")))

# ── Data-source mode (the dev-vs-deploy seam) ──────────────────────────
# "csv"  -> CsvDataSource over discovery_api/data/dev/ (the dev default, runs now)
# "live" -> LiveDataSource (a stub here; queries the live Silver tables at deploy)
DATA_SOURCE_MODE = os.getenv("DISCOVERY_DATA_SOURCE", "csv").lower()

# ── Substrate (shared vector + graph HTTP services — reused, never duplicated) ──
VECTOR_API_URL = os.getenv("VECTOR_API_URL", "http://localhost:8000")   # shared/vector
GRAPH_API_URL = os.getenv("GRAPH_API_URL", "http://localhost:8010")     # shared/graph
SUBSTRATE_HTTP_TIMEOUT_S = float(os.getenv("DISCOVERY_HTTP_TIMEOUT_S", "15"))
SUBSTRATE_HTTP_RETRIES = int(os.getenv("DISCOVERY_HTTP_RETRIES", "3"))   # tolerate transient 5xx
# Bounded concurrency for per-seed substrate calls. NOTE (P5.1 measurement): on the dev single-worker
# vector substrate this is roughly NEUTRAL — the bottleneck is the vector server's per-anchor /api/neighbors
# compute (~860ms), not the client serial pattern. Kept modest to avoid contention; raise it only when the
# vector substrate can truly parallelise (multi-worker / faster ANN). See P5.1 report.
SUBSTRATE_MAX_WORKERS = int(os.getenv("DISCOVERY_SUBSTRATE_MAX_WORKERS", "4"))

# ── Ranking WEIGHTS (blended by the P4 scorer — ranking/scorer.py) ──
# W_POPULARITY/W_RECENCY/W_VELOCITY form the GLOBAL component; W_SEMANTIC is the PERSONAL component;
# W_SUPPRESSION penalizes dormant negatives. The global↔personal mix scales with signal_strength.
W_SEMANTIC = float(os.getenv("DISCOVERY_W_SEMANTIC", "1.0"))     # vector similarity to what the user likes
W_RECENCY = float(os.getenv("DISCOVERY_W_RECENCY", "1.0"))       # freshness of the moment
W_POPULARITY = float(os.getenv("DISCOVERY_W_POPULARITY", "1.0")) # normalized per-vertical influence
W_VELOCITY = float(os.getenv("DISCOVERY_W_VELOCITY", "0.5"))     # recent global reaction/follow rate
W_SUPPRESSION = float(os.getenv("DISCOVERY_W_SUPPRESSION", "1.0"))  # penalty multiplier for dormant negatives

# ── TrendingGlobal POOL ordering (global, user-agnostic; NOT the P4 feed scorer) ──
# These order the global trending POOL (one ranked list served to all cold-start users). Distinct from
# the per-user feed blend (P4). Kept separate on purpose so P4 weighting stays unbuilt.
TRENDING_W_INFLUENCE = float(os.getenv("DISCOVERY_TRENDING_W_INFLUENCE", "1.0"))
TRENDING_W_VELOCITY = float(os.getenv("DISCOVERY_TRENDING_W_VELOCITY", "1.0"))   # confidence-scaled (see below)
TRENDING_W_RECENCY = float(os.getenv("DISCOVERY_TRENDING_W_RECENCY", "0.5"))
TRENDING_POOL_SIZE = int(os.getenv("DISCOVERY_TRENDING_POOL_SIZE", "500"))       # how many to keep in the pool

# ── Recency (soft window — rank by recency, NO hard cutoff) ────────────
# Freshness decays smoothly around `now`; nothing is hard-dropped for age. event_starts_at is the ONLY
# recency key (published_at = bulk-ingest garbage; views = 100% null — never used).
RECENCY_HALFLIFE_DAYS = float(os.getenv("DISCOVERY_RECENCY_HALFLIFE_DAYS", "21"))  # soft-window half-life
RECENCY_HARD_CUTOFF_DAYS = os.getenv("DISCOVERY_RECENCY_HARD_CUTOFF_DAYS")          # default None = no cutoff
RECENCY_HARD_CUTOFF_DAYS = float(RECENCY_HARD_CUTOFF_DAYS) if RECENCY_HARD_CUTOFF_DAYS else None
# Reference "now". Default "" → wall clock (the PRODUCTION default; a hardcoded snapshot froze the clock
# ~13 days stale and also collapsed the trending window). Set DISCOVERY_NOW_ISO to a fixed ISO ONLY for
# reproducible dev runs over the (June-2026) dev data.
DEFAULT_NOW_ISO = os.getenv("DISCOVERY_NOW_ISO", "")

# ── Feed / carousel shaping ────────────────────────────────────────────
MOMENT_CAP_PER_PROPERTY = int(os.getenv("DISCOVERY_MOMENT_CAP", "3"))   # episode-heavy podcasts can't flood
CAROUSEL_SIZE = int(os.getenv("DISCOVERY_CAROUSEL_SIZE", "20"))         # return up to 20 (use-case doc: 10-20)
CAROUSEL_MIN_SIZE = int(os.getenv("DISCOVERY_CAROUSEL_MIN_SIZE", "10")) # below this a carousel is dropped (P5)
CANDIDATE_POOL_SIZE = int(os.getenv("DISCOVERY_CANDIDATE_POOL_SIZE", "200"))  # default per-pool generate() cap

# ── Per-vertical influence normalization (popularity prep) ─────────────
# Raw PageRank `influence` scales differ per vertical (games higher; podcasts heavy-tailed, max ~6.46 vs
# ~3.0-3.3). We convert to a per-vertical 0-1 PERCENTILE and clip the upper tail so outliers can't
# dominate. Clip percentile applies to ALL verticals; it matters most for podcasts.
INFLUENCE_CLIP_PCT = float(os.getenv("DISCOVERY_INFLUENCE_CLIP_PCT", "95"))   # clamp raw influence at p95
INFLUENCE_NORM_METHOD = os.getenv("DISCOVERY_INFLUENCE_NORM", "percentile")   # percentile (rank) — the default

# ── Global-feed refresh cadence ────────────────────────────────────────
# Global trending is a RECOMPUTED-AND-CACHED artifact (NOT per-request): computed once per window and
# served to all cold-start users. Should match the upstream Silver-table sync cadence at deploy.
GLOBAL_REFRESH_SECONDS = int(os.getenv("DISCOVERY_GLOBAL_REFRESH_SECONDS", "900"))  # 15 min default

# ── Velocity (global reaction/follow rate) ─────────────────────────────
VELOCITY_WINDOW_DAYS = float(os.getenv("DISCOVERY_VELOCITY_WINDOW_DAYS", "14"))   # window for "recent" counts
# Velocity confidence saturates with how much global signal exists (dev has only 31 reactions / 330
# follows) — when thin, velocity is down-weighted toward 0 so trending leans on influence + recency.
VELOCITY_CONFIDENCE_FULL = int(os.getenv("DISCOVERY_VELOCITY_CONFIDENCE_FULL", "500"))  # events ≈ full confidence

# ── Personalization strength ───────────────────────────────────────────
# signal_strength in [0,1] = how much personalization the ranker may apply; saturates at FULL signals.
SIGNAL_STRENGTH_FULL = int(os.getenv("DISCOVERY_SIGNAL_STRENGTH_FULL", "20"))  # follows+reactions ≈ full
# mode is "cold_start" when total positive signals < this (default 1 → only zero-signal users are cold).
COLD_START_SIGNAL_THRESHOLD = int(os.getenv("DISCOVERY_COLD_START_THRESHOLD", "1"))

# ── P4 scorer: global↔personal interpolation + feed/carousel shaping ───
# personal_weight = PERSONAL_WEIGHT_MAX * signal_strength → cold-start (0) is 100% GLOBAL; 12305 (1.0)
# blends in the PERSONAL (semantic) component. ONE engine, no hard mode switch.
PERSONAL_WEIGHT_MAX = float(os.getenv("DISCOVERY_PERSONAL_WEIGHT_MAX", "0.6"))
COFOLLOW_FULL = int(os.getenv("DISCOVERY_COFOLLOW_FULL", "5"))            # co-follow count ≈ full personal proxy
MAIN_FEED_PAGE_SIZE = int(os.getenv("DISCOVERY_MAIN_FEED_PAGE_SIZE", "20"))   # default main-feed page (context.limit)
TRENDING_TO_FEED = int(os.getenv("DISCOVERY_TRENDING_TO_FEED", "60"))     # trending properties feeding the moment feed
PERSONAL_TO_FEED = int(os.getenv("DISCOVERY_PERSONAL_TO_FEED", "80"))     # personal-pool properties feeding the moment feed
                                                                         # (empty for cold-start → main feed stays global)
NEW_IN_GENRE_MAX_CAROUSELS = int(os.getenv("DISCOVERY_NEW_IN_GENRE_MAX", "4"))
NEW_ON_PLATFORM_MAX_CAROUSELS = int(os.getenv("DISCOVERY_NEW_ON_PLATFORM_MAX", "3"))

# ── DORMANT decay TTLs (negative / seen / done paths — interfaces only, not loaded) ──
# No dislike/not-interested/done signal exists in the data yet. These TTLs configure the eventual
# decay so the dormant paths are testable now. (not-interested contract: app_component_string=
# 'Not interesting' keyed by feeds_user_id + app_element_id — nothing to load today.)
NOT_INTERESTED_TTL_DAYS = int(os.getenv("DISCOVERY_NOT_INTERESTED_TTL_DAYS", "90"))
SEEN_MOMENT_TTL_DAYS = int(os.getenv("DISCOVERY_SEEN_MOMENT_TTL_DAYS", "14"))
SEEN_CAROUSEL_TTL_DAYS = int(os.getenv("DISCOVERY_SEEN_CAROUSEL_TTL_DAYS", "7"))

# ── Media-type / vertical mapping (from lookups_dev.csv) ───────────────
MEDIA_TYPE_TO_VERTICAL = {1: "game", 3: "movie", 4: "tv", 5: "podcast"}
VERTICALS = ("game", "movie", "tv", "podcast")
POSITIVE_REACTION_TYPE_IDS = (1, 2, 3)   # heart / fire / confetti — ALL positive for v1 (no distinct meaning)


# ─────────────────────────────────────────────────────────────────────────────
# ── Discovery v2 (V2-P2): taste profile — engagement log + decay + clusters ──
# ─────────────────────────────────────────────────────────────────────────────
# ADDITIVE namespace (every name prefixed V2_). v1 reads NOTHING below; nothing above is changed.
# All taste-profile knobs live here — no magic numbers in feed/taste_profile.py or feed/clustering.py.
# See discovery_api/V2_STRATEGY.md (Source 1).

# Per-signal base weights (the engagement log is signal-agnostic; each signal type carries its own
# base weight). Follows and reactions are equal positives by default — both independently tunable.
# Future signal types (dwell, not_interested) will add their OWN V2_BASE_WEIGHT_* here; nothing else changes.
V2_BASE_WEIGHT_FOLLOW = float(os.getenv("DISCOVERY_V2_BASE_WEIGHT_FOLLOW", "1.0"))
V2_BASE_WEIGHT_REACTION = float(os.getenv("DISCOVERY_V2_BASE_WEIGHT_REACTION", "1.0"))

# Recency: effective_weight = base_weight * 0.5 ** (age / half_life). Recent engagement outweighs old.
V2_RECENCY_HALFLIFE_DAYS = float(os.getenv("DISCOVERY_V2_RECENCY_HALFLIFE_DAYS", "14"))
# Engagement with a missing timestamp gets this flat decay (rare on dev — every follow/reaction has created_at).
V2_UNKNOWN_TS_DECAY = float(os.getenv("DISCOVERY_V2_UNKNOWN_TS_DECAY", "0.05"))
# Disjoint recency BANDS for the explainability VIEW — each engagement in EXACTLY one band (no double-count).
# (label, upper_bound_seconds); the final band has upper=None (= everything older). Half-open [lower, upper).
V2_RECENCY_BANDS = (
    ("0-6h",   6 * 3600),
    ("6-24h",  24 * 3600),
    ("24-48h", 48 * 3600),
    ("2-7d",   7 * 86400),
    ("7-30d",  30 * 86400),
    ("older",  None),
)

# signal_strength in [0,1] from AMOUNT + RECENCY of resolved signal: total decayed effective weight
# divided by this "full-confidence" target (decay already folds recency in). Saturates at 1.0.
V2_SIGNAL_FULL_EFFECTIVE_WEIGHT = float(os.getenv("DISCOVERY_V2_SIGNAL_FULL_WEIGHT", "20"))
# mode = "cold_start" when RESOLVED engagements < this (default 1 → only zero-signal users are cold).
V2_COLD_START_THRESHOLD = int(os.getenv("DISCOVERY_V2_COLD_START_THRESHOLD", "1"))

# Vertical-percentage SMOOTHING (Dirichlet pseudocount toward a neutral/uniform prior). A sparse user is
# pulled toward neutral so 3 follows don't yield extreme allocations; as effective weight grows the prior
# washes out and percentages sharpen toward the true distribution. The pseudocount IS the smoothing strength.
V2_VERTICAL_SMOOTHING_STRENGTH = float(os.getenv("DISCOVERY_V2_VERTICAL_SMOOTHING_STRENGTH", "8"))

# Taste clustering (group engaged entities by shared genre, refine/merge by keyword overlap; community
# tie-breaks). All knobs configurable — the engine must work for any number of taste shapes.
V2_MAX_CLUSTERS = int(os.getenv("DISCOVERY_V2_MAX_CLUSTERS", "6"))
V2_CLUSTER_MIN_SIZE = int(os.getenv("DISCOVERY_V2_CLUSTER_MIN_SIZE", "2"))        # below this → merged into nearest
V2_CLUSTER_TOP_MEMBERS = int(os.getenv("DISCOVERY_V2_CLUSTER_TOP_MEMBERS", "3"))  # top-weight members = retrieval anchors (V2-P3)
V2_CLUSTER_MERGE_THRESHOLD = float(os.getenv("DISCOVERY_V2_CLUSTER_MERGE_THRESHOLD", "0.34"))  # similarity to merge two clusters
V2_CLUSTER_SIM_W_GENRE = float(os.getenv("DISCOVERY_V2_CLUSTER_SIM_W_GENRE", "0.6"))           # genre cosine weight in similarity
V2_CLUSTER_SIM_W_KEYWORD = float(os.getenv("DISCOVERY_V2_CLUSTER_SIM_W_KEYWORD", "0.4"))       # keyword cosine weight
V2_CLUSTER_COMMUNITY_BONUS = float(os.getenv("DISCOVERY_V2_CLUSTER_COMMUNITY_BONUS", "0.1"))   # same-community tie-break bonus
V2_TOP_ATTRIBUTES_K = int(os.getenv("DISCOVERY_V2_TOP_ATTRIBUTES_K", "8"))        # how many top genres/keywords to surface

# Profile cache TTL — SEAM for V2-P4 (the profile changes slowly). Declared now; not used in V2-P2.
V2_PROFILE_CACHE_TTL_SECONDS = int(os.getenv("DISCOVERY_V2_PROFILE_CACHE_TTL_SECONDS", "600"))

# ─────────────────────────────────────────────────────────────────────────────
# ── Discovery v2 (V2-P3): content-based retrieval (Source 2) + exploration (Source 3) ──
# ─────────────────────────────────────────────────────────────────────────────
# STRING COMPOSER — the vector path composes a TEXT phrase (genre intent rides INSIDE the phrase, since
# /api/retrieve filters only by `vertical`). Swappable so V2-P6 can A/B quality-vs-latency by config flip.
V2_STRING_COMPOSER = os.getenv("DISCOVERY_V2_STRING_COMPOSER", "deterministic").lower()   # deterministic | llm
V2_COMPOSE_TOP_GENRES = int(os.getenv("DISCOVERY_V2_COMPOSE_TOP_GENRES", "3"))     # genres in the phrase
V2_COMPOSE_TOP_KEYWORDS = int(os.getenv("DISCOVERY_V2_COMPOSE_TOP_KEYWORDS", "6")) # keywords in the phrase

# PER-CLUSTER RETRIEVAL depth (the latency fix: #/api/retrieve calls = #clusters, a few — not per-follow).
V2_RETRIEVE_TOP_K = int(os.getenv("DISCOVERY_V2_RETRIEVE_TOP_K", "30"))            # /api/retrieve top_k (vector)
V2_GRAPH_TOP_K = int(os.getenv("DISCOVERY_V2_GRAPH_TOP_K", "20"))                  # /graph/structured + /graph/similar top_k
V2_GRAPH_SIMILAR_SEEDS = int(os.getenv("DISCOVERY_V2_GRAPH_SIMILAR_SEEDS", "2"))   # rep members seeding :SIMILAR_TO (few!)
V2_GRAPH_STRUCTURED_GENRES = int(os.getenv("DISCOVERY_V2_GRAPH_STRUCTURED_GENRES", "2"))  # top genres → /graph/structured
# Merge ranking: a candidate's score blends its best vector cosine + best graph score (each min-max normed per source).
V2_MERGE_W_VECTOR = float(os.getenv("DISCOVERY_V2_MERGE_W_VECTOR", "1.0"))
V2_MERGE_W_GRAPH = float(os.getenv("DISCOVERY_V2_MERGE_W_GRAPH", "0.6"))
V2_MERGE_BOTH_BONUS = float(os.getenv("DISCOVERY_V2_MERGE_BOTH_BONUS", "0.1"))     # hit by BOTH paths → small bonus

# PERCENTAGE ALLOCATION — content budget split by vertical_percentages (per-vertical), then by cluster_share
# (within vertical). A vertical with budget but no cluster becomes global_backfill (V2-P4 fills from global).
V2_CANDIDATE_BUDGET = int(os.getenv("DISCOVERY_V2_CANDIDATE_BUDGET", "240"))       # total slots (content + exploration)
V2_MIN_CLUSTER_SLOTS = int(os.getenv("DISCOVERY_V2_MIN_CLUSTER_SLOTS", "6"))       # floor so a small cluster still contributes
V2_ALLOC_MODE = os.getenv("DISCOVERY_V2_ALLOC_MODE", "vertical_then_cluster").lower()  # vertical_then_cluster | cluster_share

# EXPLORATION FRACTION = f(signal_strength): linear curve, HIGH when signal thin (learn fast), small-but-
# nonzero when rich (keep discovering). frac = MAX - (MAX-MIN)*signal_strength, clamped.
V2_EXPLORE_FRAC_MIN = float(os.getenv("DISCOVERY_V2_EXPLORE_FRAC_MIN", "0.10"))
V2_EXPLORE_FRAC_MAX = float(os.getenv("DISCOVERY_V2_EXPLORE_FRAC_MAX", "0.50"))
# STRUCTURED ADJACENCY (graph-defined, NOT random): candidates share SOME profile attribute but INTRODUCE a
# new one. "distance" = how many shared vs new attrs required.
V2_EXPLORE_TOP_GENRES = int(os.getenv("DISCOVERY_V2_EXPLORE_TOP_GENRES", "3"))     # profile genres seeding adjacency
V2_EXPLORE_PER_RULE_K = int(os.getenv("DISCOVERY_V2_EXPLORE_PER_RULE_K", "25"))    # pulled per rule before adjacency filter
V2_EXPLORE_MIN_SHARED = int(os.getenv("DISCOVERY_V2_EXPLORE_MIN_SHARED", "1"))     # >=1 shared attr (stays adjacent)
V2_EXPLORE_MIN_NEW = int(os.getenv("DISCOVERY_V2_EXPLORE_MIN_NEW", "1"))           # >=1 NEW attr (not identical)

# LLM composer (reuses Endpoint 1's Databricks Foundation Model endpoint; SHORT timeout + deterministic fallback).
V2_LLM_ENDPOINT = os.getenv("DATABRICKS_LLM_ENDPOINT",
                            "https://dbc-f79d5cae-0d05.cloud.databricks.com/serving-endpoints/"
                            "llama_v3_3_70b_instruct_Ishaan/invocations")
V2_LLM_TIMEOUT_S = float(os.getenv("DISCOVERY_V2_LLM_TIMEOUT_S", "8"))             # fail fast → deterministic
V2_LLM_MAX_TOKENS = int(os.getenv("DISCOVERY_V2_LLM_MAX_TOKENS", "50"))

# ─────────────────────────────────────────────────────────────────────────────
# ── Discovery v2 (V2-P4): trending velocity + three-signal blend + assembly + cache ──
# ─────────────────────────────────────────────────────────────────────────────
# TRENDING VELOCITY (§4b) — recency-decayed engagement VELOCITY, NOT volume. SHORTER half-life than the
# taste profile (trending is "now"). An old high-volume item with no recent events → ~0; a currently-active
# one → high. Precomputed+cached per refresh cadence; CONFIDENCE-GATED by recent volume (≈0 on thin dev data).
V2_TRENDING_HALFLIFE_DAYS = float(os.getenv("DISCOVERY_V2_TRENDING_HALFLIFE_DAYS", "3"))
V2_TRENDING_WINDOW_DAYS = float(os.getenv("DISCOVERY_V2_TRENDING_WINDOW_DAYS", "21"))   # events older than this don't count
V2_TRENDING_REACTION_WEIGHT = float(os.getenv("DISCOVERY_V2_TRENDING_REACTION_WEIGHT", "1.0"))
V2_TRENDING_FOLLOW_WEIGHT = float(os.getenv("DISCOVERY_V2_TRENDING_FOLLOW_WEIGHT", "1.0"))
V2_TRENDING_CONFIDENCE_FULL = float(os.getenv("DISCOVERY_V2_TRENDING_CONFIDENCE_FULL", "200"))  # decayed events ≈ full confidence
V2_TRENDING_REFRESH_SECONDS = int(os.getenv("DISCOVERY_V2_TRENDING_REFRESH_SECONDS", "900"))    # precompute/cache cadence

# THREE-SIGNAL BLEND (§4b) — each candidate MOMENT's final score. collaborative wired but 0 (Source 4 = V2-P5).
V2_W_TASTE = float(os.getenv("DISCOVERY_V2_W_TASTE", "1.0"))
V2_W_TRENDING = float(os.getenv("DISCOVERY_V2_W_TRENDING", "1.0"))
V2_W_RECENCY = float(os.getenv("DISCOVERY_V2_W_RECENCY", "1.0"))   # V2-P7: 0.6→1.0 (freshness; balanced vs taste below)
V2_W_COLLABORATIVE = float(os.getenv("DISCOVERY_V2_W_COLLABORATIVE", "0.8"))   # Source 4 (V2-P9) MAX weight —
# scaled by NEIGHBORHOOD-DENSITY confidence in BlendWeights.adaptive; ENDORSEMENT-gated (NOT taste-gated) so it
# can introduce CROSS-ATTRIBUTE content (the bubble-escape). Thin neighborhood → conf≈0 → w_collaborative≈0.
V2_W_SUPPRESSION = float(os.getenv("DISCOVERY_V2_W_SUPPRESSION", "1.0"))       # dormant negatives (empty now)
V2_SEEN_SUPPRESSION = float(os.getenv("DISCOVERY_V2_SEEN_SUPPRESSION", "1.0")) # demote a seen moment by this

# MOMENT SELECTION
V2_MOMENT_CAP_PER_PROPERTY = int(os.getenv("DISCOVERY_V2_MOMENT_CAP", "1"))  # V2-P7: 3→1 (no duplicate-property feeds)

# ASSEMBLY (reuse v1 page/carousel sizes so the v1.0 envelope is identical)
V2_TRENDING_CAROUSEL_SIZE = int(os.getenv("DISCOVERY_V2_TRENDING_CAROUSEL_SIZE", "20"))
V2_EXPLORATION_CAROUSEL_SIZE = int(os.getenv("DISCOVERY_V2_EXPLORATION_CAROUSEL_SIZE", "15"))
V2_CLUSTER_CAROUSEL_SIZE = int(os.getenv("DISCOVERY_V2_CLUSTER_CAROUSEL_SIZE", "15"))
V2_CLUSTER_CAROUSEL_MIN = int(os.getenv("DISCOVERY_V2_CLUSTER_CAROUSEL_MIN", "3"))
V2_GLOBAL_CAROUSEL_MIN = int(os.getenv("DISCOVERY_V2_GLOBAL_CAROUSEL_MIN", str(CAROUSEL_MIN_SIZE)))
V2_MAX_CLUSTER_CAROUSELS = int(os.getenv("DISCOVERY_V2_MAX_CLUSTER_CAROUSELS", "6"))

# THIN-SIGNAL TREND LEAN — thin-signal users may lean more on trending/global (kept simple + config).
V2_THIN_SIGNAL_TREND_BOOST = float(os.getenv("DISCOVERY_V2_THIN_SIGNAL_TREND_BOOST", "0.0"))  # 0 = off (uniform weights)

# ─────────────────────────────────────────────────────────────────────────────
# ── Discovery v2 (V2-P6): engine selector + bundle (retrieval) cache ──
# ─────────────────────────────────────────────────────────────────────────────
# The SAME /discovery/feed endpoint serves v2 (V2FeedBuilder, the validated taste-clustered engine) or v1.
# COMMITTED DEFAULT = v2 (changed from "v1" on 2026-07-09 — v2 is what we evaluated/tuned; v1's main feed is
# largely un-personalized). Single documented fallback flag DISCOVERY_LEGACY_V1=1 restores v1 IN FULL.
# DISCOVERY_DEFAULT_ENGINE stays a granular A/B override ("v1"|"v2"), IGNORED when the legacy flag is set.
# Precedence: DISCOVERY_LEGACY_V1  >  DISCOVERY_DEFAULT_ENGINE  >  default "v2".  (Per-request ?engine=/body
# `engine` still override everything, for explicit A/B — see api.py.)
_LEGACY_V1 = os.getenv("DISCOVERY_LEGACY_V1", "").strip().lower() in ("1", "true", "yes", "on")
V2_DEFAULT_ENGINE = ("v1" if _LEGACY_V1 else os.getenv("DISCOVERY_DEFAULT_ENGINE", "v2")).lower()  # "v1" | "v2"
# BUNDLE CACHE — memoize the V2-P3 CandidateBundle (the ~6 /api/retrieve calls that dominate latency) keyed
# by (user_id, now, excluded_property_ids, composer). seen_ids are applied POST-cache in assembly (they don't
# change retrieval), so a repeat load for the same user/now is sub-second.
V2_BUNDLE_CACHE_TTL_SECONDS = int(os.getenv("DISCOVERY_V2_BUNDLE_CACHE_TTL_SECONDS", "300"))

# ─────────────────────────────────────────────────────────────────────────────
# ── Discovery v2 (V2-P7): quality tuning (measured vs the persona eval) ──
# ─────────────────────────────────────────────────────────────────────────────
# #1 DRIFT → FEED: fold the cluster's share (which encodes recency-drift) into per-item taste_match so a
# recently-weighted cluster's items RANK higher, not just get more slots. 0 = old behaviour (pure retrieval
# score); 1 = full cluster weighting. effective_taste = norm_score · ((1-W) + W · share/max_share).
V2_TASTE_CLUSTER_WEIGHTING = float(os.getenv("DISCOVERY_V2_TASTE_CLUSTER_WEIGHTING", "0.5"))
# #2 STALENESS (balanced): a SOFT recency floor — moments older than STALE_DAYS have their taste+trending
# contribution multiplied by STALE_FACTOR (NOT dropped → on-taste isn't gutted), so fresher on-taste wins.
# Tuned with V2_W_RECENCY (1.0) against BOTH median-age AND on-taste in the eval (neither sacrificed).
V2_RECENCY_STALE_DAYS = float(os.getenv("DISCOVERY_V2_RECENCY_STALE_DAYS", "540"))   # 0/empty → off
V2_STALE_FACTOR = float(os.getenv("DISCOVERY_V2_STALE_FACTOR", "0.6"))               # multiplier for stale moments

# ─────────────────────────────────────────────────────────────────────────────
# ── Discovery v2 (V2-P8): trending as a FIRST-CLASS CANDIDATE SOURCE + adaptive weighting ──
# ─────────────────────────────────────────────────────────────────────────────
# Trending now GENERATES candidates (global trending moments scoped to the user's taste, per cluster),
# not just re-orders taste-selected ones. So a trending, on-taste moment surfaces even if the taste path
# never picked its property. Built for SCALE: the same code spans dev-thin → production-rich trending.
V2_TREND_CAND_SCAN = int(os.getenv("DISCOVERY_V2_TREND_CAND_SCAN", "800"))           # top-K trending moments scanned for candidates
V2_TREND_MATCH_MIN = float(os.getenv("DISCOVERY_V2_TREND_MATCH_MIN", "0.12"))        # min cluster taste-overlap to emit a trending candidate (LOW → niche on-taste surfaces)
V2_TREND_CANDIDATE_MAX = int(os.getenv("DISCOVERY_V2_TREND_CANDIDATE_MAX", "120"))   # cap on trending candidates merged

# NICHE-RELATIVE trending: velocities normalized WITHIN the user's taste niche (a few users surging on niche
# content is a REAL signal there) — NOT against global volume. Confidence gates at a LOW absolute threshold.
V2_TREND_TASTE_CONFIDENCE_FULL = float(os.getenv("DISCOVERY_V2_TREND_TASTE_CONFIDENCE_FULL", "3.0"))  # decayed trending mass in the user's niche ≈ full confidence (a few surging users)
V2_TREND_CONF_EXPONENT = float(os.getenv("DISCOVERY_V2_TREND_CONF_EXPONENT", "0.5"))  # <1 → confidence ramps up FAST (sensitive to niche signal)

# ADAPTIVE recency weight: CARRIES the feed (with taste) when trending is thin; a positive TIEBREAKER when
# trending is present (between two trending+tasteful items, the more recent ranks higher — recency ADDS, not gates).
# w_recency_eff = CARRY·(1−conf) + TIEBREAK·conf ;  w_trending_eff = V2_W_TRENDING·conf ;  w_taste constant.
V2_W_RECENCY_CARRY = float(os.getenv("DISCOVERY_V2_W_RECENCY_CARRY", "1.0"))
V2_W_RECENCY_TIEBREAK = float(os.getenv("DISCOVERY_V2_W_RECENCY_TIEBREAK", "0.35"))
# A trending candidate must share a MAJOR cluster genre (weight ≥ this fraction of the cluster's top genre) —
# so trending stays on the user's PRIMARY taste, not a co-occurring secondary genre (keeps on-taste high).
V2_TREND_GENRE_MIN_FRACTION = float(os.getenv("DISCOVERY_V2_TREND_GENRE_MIN_FRACTION", "0.5"))

# ─────────────────────────────────────────────────────────────────────────────
# ── Discovery v2 (V2-P9): COLLABORATIVE FILTERING (Source 4) — the bubble-escape ──
# ─────────────────────────────────────────────────────────────────────────────
# "What users with a SIMILAR taste profile engage with that THIS user has not found." Mirrors the V2-P8
# trending machinery, swapping GLOBAL velocity for SIMILAR-USER affinity. Unlike trending (taste-gated, on-
# taste only), collaborative is ENDORSEMENT-gated: it is ALLOWED to introduce CROSS-ATTRIBUTE content (a
# horror fan's neighbors who also love a strategy game) — content similarity can never find that; behavioral
# overlap can. Built for SCALE: validated on a synthetic population; real signal comes from production volume.

# USER-SIMILARITY (the taste neighborhood): cosine over recency-decayed genre + keyword taste vectors,
# config-weighted (mirrors the cluster-similarity weights). A user is a "neighbor" at a LOW similarity floor.
V2_COLLAB_SIM_W_GENRE = float(os.getenv("DISCOVERY_V2_COLLAB_SIM_W_GENRE", "0.6"))
V2_COLLAB_SIM_W_KEYWORD = float(os.getenv("DISCOVERY_V2_COLLAB_SIM_W_KEYWORD", "0.4"))
V2_COLLAB_SIM_MIN = float(os.getenv("DISCOVERY_V2_COLLAB_SIM_MIN", "0.10"))            # min taste cosine to be a neighbor (LOW → niche neighborhoods form)
V2_COLLAB_MAX_NEIGHBORS = int(os.getenv("DISCOVERY_V2_COLLAB_MAX_NEIGHBORS", "300"))   # cap neighbors aggregated (scale guard)
V2_COLLAB_HALFLIFE_DAYS = float(os.getenv("DISCOVERY_V2_COLLAB_HALFLIFE_DAYS", "14"))  # recency decay on neighbor taste vectors (= profile half-life)
V2_COLLAB_REFRESH_SECONDS = int(os.getenv("DISCOVERY_V2_COLLAB_REFRESH_SECONDS", "900"))  # index precompute/cache cadence (like trending)

# NICHE-RELATIVE + LOW THRESHOLD (the V2-P8 lesson): a neighborhood of even a FEW genuinely-similar users is a
# real signal. Confidence scales with neighborhood DENSITY (sum of neighbor similarities) and activates LOW.
V2_COLLAB_CONFIDENCE_FULL = float(os.getenv("DISCOVERY_V2_COLLAB_CONFIDENCE_FULL", "3.0"))  # neighbor-similarity mass ≈ full confidence (a few strong neighbors)
V2_COLLAB_CONF_EXPONENT = float(os.getenv("DISCOVERY_V2_COLLAB_CONF_EXPONENT", "0.5"))      # <1 → ramps up FAST (sensitive to a small neighborhood)

# ENDORSEMENT GATE (NOT a taste gate): require ≥ this many DISTINCT neighbors endorsing an item, so a single
# neighbor can't introduce noise — but do NOT require the item to match the target's taste attributes.
V2_COLLAB_MIN_ENDORSERS = int(os.getenv("DISCOVERY_V2_COLLAB_MIN_ENDORSERS", "2"))
V2_COLLAB_CANDIDATE_MAX = int(os.getenv("DISCOVERY_V2_COLLAB_CANDIDATE_MAX", "120"))   # cap collaborative candidates merged into the bundle
V2_COLLAB_CAROUSEL_SIZE = int(os.getenv("DISCOVERY_V2_COLLAB_CAROUSEL_SIZE", "20"))

# SCALING SEAM (documented, NOT over-built): the neighbor search is a direct cosine over users sharing ≥1
# genre (a genre inverted-index prunes the scan). At very large user counts this moves to a precomputed/
# indexed similarity (LSH/ANN over taste vectors, or a similar-user graph). Direct scan is fine at this scale.


def summary() -> dict:
    """Non-secret config view (for /health and logs)."""
    return {
        "data_source_mode": DATA_SOURCE_MODE,
        "dev_data_dir": str(DEV_DATA_DIR),
        "vector_api_url": VECTOR_API_URL,
        "graph_api_url": GRAPH_API_URL,
        "moment_cap_per_property": MOMENT_CAP_PER_PROPERTY,
        "carousel_size": CAROUSEL_SIZE,
        "recency_halflife_days": RECENCY_HALFLIFE_DAYS,
        "recency_hard_cutoff_days": RECENCY_HARD_CUTOFF_DAYS,
        "influence_clip_pct": INFLUENCE_CLIP_PCT,
        "global_refresh_seconds": GLOBAL_REFRESH_SECONDS,
        "velocity_window_days": VELOCITY_WINDOW_DAYS,
        "signal_strength_full": SIGNAL_STRENGTH_FULL,
        "dormant_ttls_days": {"not_interested": NOT_INTERESTED_TTL_DAYS,
                              "seen_moment": SEEN_MOMENT_TTL_DAYS,
                              "seen_carousel": SEEN_CAROUSEL_TTL_DAYS},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(summary(), indent=2))
