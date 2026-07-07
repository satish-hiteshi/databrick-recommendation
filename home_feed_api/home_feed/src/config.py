"""Endpoint 3 (Home Feed) configuration.

House style mirrors E1/E2 config: every value reads from the environment with a local-dev default,
no magic numbers elsewhere. E3 INHERITS E2's knobs by importing E2 config through the reuse seam
(substrate URLs, recency half-life, taste weights, the three-signal blend weights) and adds only the
genuinely-new HOME-FEED knobs below. Nothing here re-declares an E2 value; we import it.

SCAFFOLD: the E3-specific knobs below are PLACEHOLDERS so the seam exists — the assembler/scorer that
read them are built in PROMPT 2+.
"""

import os
from pathlib import Path

from .reuse import e2_config  # E2's full config object (reuse its defaults verbatim)

_PKG_DIR = Path(__file__).resolve().parents[1]   # .../home_feed/  (src/ → home_feed/)
_ENDPOINT_DIR = Path(__file__).resolve().parents[3]  # .../endpoint_3_home_feed/ (holds data/)

# ── Inherit E2 defaults (re-export the ones E3 reads, so call sites import from one place) ──
VECTOR_API_URL = e2_config.VECTOR_API_URL          # shared/vector :8000
GRAPH_API_URL = e2_config.GRAPH_API_URL            # shared/graph  :8010
DATA_SOURCE_MODE = e2_config.DATA_SOURCE_MODE      # csv (dev) | live (deploy)
VERTICALS = e2_config.VERTICALS

# Dev data: REUSE E2's dev CSVs by default (one source of truth — do not duplicate the 11 CSVs).
# Override DISCOVERY_DEV_DATA_DIR to point elsewhere; E3 reads the same follows/reactions/moments.
DEV_DATA_DIR = e2_config.DEV_DATA_DIR

# ── E3-NEW: the follow-gate + home-feed shaping (PLACEHOLDERS — wired in PROMPT 2+) ──
# The MAIN moment stream is HARD-GATED to followed properties only. Unfollowed content can appear
# ONLY in interspersed discovery carousels (reused from E2). These knobs shape that.
HOME_MAIN_FEED_PAGE_SIZE = int(os.getenv("HOME_MAIN_FEED_PAGE_SIZE", "20"))      # moments per page in the main stream
HOME_MOMENT_CAP_PER_PROPERTY = int(os.getenv("HOME_MOMENT_CAP", "1"))           # avoid one followed property flooding the stream
HOME_CAROUSEL_EVERY_N_MOMENTS = int(os.getenv("HOME_CAROUSEL_EVERY_N", "5"))     # intersperse a discovery carousel after every N moments
HOME_MAX_DISCOVERY_CAROUSELS = int(os.getenv("HOME_MAX_DISCOVERY_CAROUSELS", "4"))  # cap interspersed carousels per page
# Recency vs taste in the main-stream blend reuses E2's weights (V2_W_TASTE / V2_W_RECENCY / ...).
# The full E3 weight blend arrives in a later prompt; declared-as-seam only here.

API_PORT = int(os.getenv("HOME_FEED_PORT", "8040"))   # E1=:8020, E2=:8030, E3=:8040

# ─────────────────────────────────────────────────────────────────────────────
# ── E3-P1: candidate-pool front half (follow-gate → traversal → suppression → cap) ──
# ─────────────────────────────────────────────────────────────────────────────
# Moments live on the 44k graph (:7688), NOT on E2's substrate (:8010 → 57k, no moments). E3 traverses
# this graph DIRECTLY (the E1 pattern), since the shared graph service neither points here nor knows
# :Moment. Read-only. Creds via env (same names E1 uses); local-dev throwaway defaults.
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7688")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")   # set via env / a gitignored .env — never commit the real value
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Followers source (public_property_followers: user_id INT, property_id INT, deleted_at). Dev reads a
# CSV via the SAME csv-or-live seam pattern E2 uses (no direct Databricks). Active = deleted_at IS NULL.
FOLLOWERS_CSV = os.getenv("HOME_FOLLOWERS_CSV", str(_PKG_DIR / "data" / "dev" / "followers_dev.csv"))
# The moments CSV that was loaded into the graph (consolidated under the endpoint dir).
MOMENTS_CSV = os.getenv("HOME_MOMENTS_CSV", str(_ENDPOINT_DIR / "data" / "moments_staging_44k.csv"))

# "now" for the future-date suppression. Default = wall clock (real now) so future-dated moments are
# genuinely future; set HOME_NOW_ISO for reproducible dev runs (e.g. the dry run pins it).
HOME_NOW_ISO = os.getenv("HOME_NOW_ISO", "")          # "" → wall clock UTC

# FUTURE-DATE SUPPRESSION (the "today and not-yet" cut). A moment is suppressed when
# event_starts_at > now + HOME_FUTURE_GRACE_HOURS. Default 0 → anything from now forward is dropped
# (covers the next-24h window AND the junk 2028 tail). The FULL recency clamp (junk vs genuine future)
# is the NEXT prompt; here we only keep the stream to already-started moments.
HOME_FUTURE_GRACE_HOURS = float(os.getenv("HOME_FUTURE_GRACE_HOURS", "0"))

# PER-PROPERTY CAP — one followed property cannot flood the pool (fan-out is uneven: avg ~6.7, max 933).
# Applied to the candidate pool here (front half). NOTE: once ranking exists (next prompt) this cap
# should move to AFTER scoring, so we keep a property's BEST N moments, not just its most-recent N.
HOME_PER_PROPERTY_CAP = int(os.getenv("HOME_PER_PROPERTY_CAP", "10"))

# ─────────────────────────────────────────────────────────────────────────────
# ── E3-P4: ranking (recency clamp + proximity + property-level taste + stubs + blend) ──
# ─────────────────────────────────────────────────────────────────────────────
# Property vectors are NOT on the graph node (Step 0) — they live in the Qwen parquet, entity_id-keyed,
# dim 1024. Taste reads them live (no precomputed table). Path defaults to the repo-root deploy parquet.
VECTOR_PARQUET = os.getenv("HOME_VECTOR_PARQUET", str(_ENDPOINT_DIR.parent / "embeddings.parquet"))

# RECENCY — smooth past decay (~30-day-dominant), reusing E2 timeutil's exp-decay shape for the past arm.
HOME_RECENCY_HALFLIFE_DAYS = float(os.getenv("HOME_RECENCY_HALFLIFE_DAYS", "30"))
HOME_RECENCY_NULL = float(os.getenv("HOME_RECENCY_NULL", "0.0"))     # null event_starts_at → no recency (defensive)
HOME_RECENCY_FUTURE = float(os.getenv("HOME_RECENCY_FUTURE", "0.0")) # a future event is not "recent" — proximity owns it

# FUTURE HORIZON / TODAY WINDOW — the coordination with prompt-3 suppression. Suppression now drops the
# calendar window [now, now+TODAY_WINDOW] AND junk-future (event_starts_at > now+HORIZON); near-future in
# (TODAY_WINDOW, HORIZON] SURVIVES for proximity. One horizon shared by the recency clamp + proximity taper.
HOME_TODAY_WINDOW_HOURS = float(os.getenv("HOME_TODAY_WINDOW_HOURS", "24"))
HOME_FUTURE_HORIZON_DAYS = float(os.getenv("HOME_FUTURE_HORIZON_DAYS", "30"))

# PROXIMITY — near-future bump: ramp 0→1 over [0,LO], plateau 1 over [LO,HI], taper 1→0 over [HI,HORIZON].
HOME_PROXIMITY_PEAK_LO_DAYS = float(os.getenv("HOME_PROXIMITY_PEAK_LO_DAYS", "1"))
HOME_PROXIMITY_PEAK_HI_DAYS = float(os.getenv("HOME_PROXIMITY_PEAK_HI_DAYS", "7"))

# TASTE — property-level follow-set affinity. cosine(property vec, mean-of-followed vec). Secondary
# attribute-overlap is weighted LOW (a coherent follow set overlaps heavily — gentle ordering, not gating).
HOME_TASTE_ATTR_OVERLAP_WEIGHT = float(os.getenv("HOME_TASTE_ATTR_OVERLAP_WEIGHT", "0.15"))  # within the taste signal
HOME_TASTE_MISSING_VEC = float(os.getenv("HOME_TASTE_MISSING_VEC", "0.5"))   # property without a parquet vector → neutral cosine

# BLEND WEIGHTS — launch profile from the plan (all config; retune without code change). The stub signals
# sit in the formula at LOW weight, ready to activate when their real source lands.
HOME_W_TASTE = float(os.getenv("HOME_W_TASTE", "35"))
HOME_W_RECENCY = float(os.getenv("HOME_W_RECENCY", "30"))
HOME_W_PROXIMITY = float(os.getenv("HOME_W_PROXIMITY", "15"))
HOME_W_TRENDING = float(os.getenv("HOME_W_TRENDING", "8"))      # STUB — real source: moment_features_v1 (pending Michelle)
HOME_W_RICHNESS = float(os.getenv("HOME_W_RICHNESS", "5"))      # STUB — real source: moment_type taxonomy (pending Michelle)
HOME_W_DWELL = float(os.getenv("HOME_W_DWELL", "0"))           # STUB — no dwell data yet (off)
HOME_W_CENTRALITY = float(os.getenv("HOME_W_CENTRALITY", "0")) # STUB — pagerank exists on :Entity; off at launch
HOME_W_POPULARITY = float(os.getenv("HOME_W_POPULARITY", "0")) # STUB — views all-null (off)

# STUB neutral values — constant across candidates → present in the blend but NO ordering effect until real.
HOME_TRENDING_STUB = float(os.getenv("HOME_TRENDING_STUB", "0.5"))
HOME_RICHNESS_STUB = float(os.getenv("HOME_RICHNESS_STUB", "0.5"))

# SORT MODES — "relevance" (full blend, default) | "recent" (near-pure recency, still gated+suppressed).
HOME_SORT_MODE = os.getenv("HOME_SORT_MODE", "relevance").lower()

# ── E3-E1: cross-property diversity interleave (feed assembly: AFTER cap, BEFORE serialize) ──
# Fixes the monopoly problem (one chatty property flooding the first screen). Reorders the post-cap
# ranked list across properties; never re-scores. Default score_only (baseline) until the numbers pick.
#   score_only          — pure score order (the phase-1 baseline control).
#   strict_round_robin  — one moment per property per cycle (best-of-each, then 2nd-of-each, …). Max spread.
#   weighted_interleave — round-robin, but a candidate beating the next RR pick by > MARGIN may jump its turn.
# E2 adopted: freshness_tiered (junk gate ON, weighted-within-band) is the committed default (never-empty,
# Story 4). baseline_freshness_tiered is saved with the E3 fairness quota OFF (factor 0).
HOME_INTERLEAVE_MODE = os.getenv("HOME_INTERLEAVE_MODE", "freshness_tiered").lower()
HOME_INTERLEAVE_MARGIN = float(os.getenv("HOME_INTERLEAVE_MARGIN", "0.05"))   # weighted: blended-score gap to jump

# ── E3-E2: junk-date HARD GATE (correctness) + freshness-aware RELAXING-FLOOR interleave ──
# HARD GATE: EXCLUDE (not just floor) moments older than this — true junk (1938/1989, decade-old
# "Launched on X"). Generous so it never empties a realistic feed (every persona keeps recent content);
# the relaxing floor handles fresh-first ORDERING within the gate. 0/empty → off. Composes with
# future-suppression in ONE pass (calendar window + future-beyond-horizon + ancient), no double-handling.
HOME_MAX_MOMENT_AGE_DAYS = float(os.getenv("HOME_MAX_MOMENT_AGE_DAYS", "1095") or 0)   # 3y; 0 → off

# FRESHNESS-AWARE INTERLEAVE (mode "freshness_tiered"): spread WITHIN freshness bands, freshest band first,
# so a stale moment is NEVER promoted above a fresh one across properties (the rule weighted@0.05 broke).
# The bands ARE the relaxing floor: the feed fills from the freshest non-empty band down — if nothing
# clears band 0 (the floor), it relaxes to the next band (graceful fresh→less-fresh), never empty. Within
# a band the band already bounds freshness, so we spread maximally (reuses the E1 strict/weighted machinery).
HOME_FRESHNESS_FLOOR_DAYS = float(os.getenv("HOME_FRESHNESS_FLOOR_DAYS", "30"))   # = band 0 upper bound
HOME_FRESHNESS_BANDS_DAYS = [float(x) for x in os.getenv("HOME_FRESHNESS_BANDS_DAYS", "30,90,365").split(",") if x.strip()]
# within-band spread: weighted_interleave PRESERVES taste (core stays ahead); strict maximizes spread but
# INVERTS taste-centrality (peripheral above core) — measured E2 guardrail breach, so weighted is the default.
HOME_FRESHNESS_BAND_MODE = os.getenv("HOME_FRESHNESS_BAND_MODE", "weighted_interleave").lower()

# ── E3-E3: per-property FAIRNESS QUOTA (Story 1 composition; Story 3 quota-not-penalty; Story 4 thin-safe) ──
# Bounds how many moments ONE property may contribute to each visible window of the ASSEMBLED feed, WITHOUT
# touching scores (Story 3) — a chatty property's fresh moments are spread DOWN the feed (later windows), not
# clustered at the top. Distinct from the per-property CAP (which bounds eligible moments BEFORE ranking).
# FOLLOW-COUNT-AWARE (Story 4): quota = max(MIN, ceil(window / active_properties * FACTOR)); DISABLED entirely
# below DISABLE_BELOW_FOLLOWS so thin users (3-5 follows) see all their recent moments and never near-empty.
# Never drops a moment (deferred to a later window), so presence is never traded for fairness (degen guard).
# factor multiplies the fair share (window/active_properties). 1.0 = exact fair share (aggressive — clamps
# even balanced feeds); higher = looser (clamps only egregious hogs, gentler on taste/freshness). The
# measured sweep: 1.0 fixes superfan but inverts dominant taste hard (−8.9); 1.5 fixes superfan with a
# milder taste cost (−5.8) — chosen as the gentler default. 0 → quota OFF (= baseline_freshness_tiered).
HOME_FAIRNESS_QUOTA_FACTOR = float(os.getenv("HOME_FAIRNESS_QUOTA_FACTOR", "1.5"))
HOME_FAIRNESS_MIN_QUOTA = int(os.getenv("HOME_FAIRNESS_MIN_QUOTA", "1"))               # quota never below this
HOME_FAIRNESS_WINDOW = int(os.getenv("HOME_FAIRNESS_WINDOW", str(HOME_MAIN_FEED_PAGE_SIZE)))   # the visible window
# E4: the quota SMOOTHLY SCALES with ACTIVE-property count (no cliff) — quota = ceil(window/active·factor).
# Fewer active properties → larger quota → looser (thin users barely constrained, Story 4); more → tighter.
# The old disable-below-8-follows CLIFF (which flooded the 7-follow generalist) is removed; the quota is
# only fully disabled when there is nothing to spread (active <= this floor, default 1 = single property).
HOME_FAIRNESS_FREE_BELOW_ACTIVE = int(os.getenv("HOME_FAIRNESS_FREE_BELOW_ACTIVE", "1"))

# ── E3-E4: serve-time near-DUPLICATE collapse ──
# Removes near-identical moments of the SAME property before assembly (e.g. "Yogurt Shop S1E5" ×3), keeping
# the best (highest-scored, freshest on tie). Reuses the harness's title-Jaccard logic (src/dedup.py).
# Sits AFTER cap, BEFORE the quota/interleave so duplicates don't waste a property's quota slots. Conservative
# threshold removes obvious dupes without merging genuinely distinct moments; never removes a property's only
# moment (presence preserved).
HOME_DEDUP_ENABLED = os.getenv("HOME_DEDUP_ENABLED", "true").lower() in ("1", "true", "yes")
HOME_DEDUP_SIMILARITY = float(os.getenv("HOME_DEDUP_SIMILARITY", "0.8"))   # title-token Jaccard ≥ this → near-dup

# ─────────────────────────────────────────────────────────────────────────────
# ── E3-P5: serialization (UC3 v1.0 home-feed envelope) ──
# ─────────────────────────────────────────────────────────────────────────────
# Static context labels (UC3 context block).
HOME_CONTEXT_MODE = os.getenv("HOME_CONTEXT_MODE", "personalized")
HOME_ENGINE_LABEL = os.getenv("HOME_ENGINE_LABEL", "v2")
HOME_PATH_LABEL = os.getenv("HOME_PATH_LABEL", "home_feed")
HOME_VERSION = os.getenv("HOME_VERSION", "1.0")
HOME_ENDPOINT_LABEL = os.getenv("HOME_ENDPOINT_LABEL", "home-feed")

# PAGINATION defaults (UC3: limit 20, offset 0).
HOME_DEFAULT_LIMIT = int(os.getenv("HOME_DEFAULT_LIMIT", str(HOME_MAIN_FEED_PAGE_SIZE)))
HOME_DEFAULT_OFFSET = int(os.getenv("HOME_DEFAULT_OFFSET", "0"))

# signal_strength = min(1, follow_count / FULL). Saturating proxy for personalization confidence —
# thin follows → low strength. Honest + simple (follow coverage, not a learned quantity).
HOME_SIGNAL_STRENGTH_FULL_FOLLOWS = int(os.getenv("HOME_SIGNAL_STRENGTH_FULL_FOLLOWS", "10"))

# badge "NEW" — a moment whose event_starts_at is within this many days BEFORE now (genuinely fresh past).
# Only "NEW" is emitted (no LIVE — no live signal; no TRENDING — trending is a stub).
HOME_BADGE_NEW_DAYS = float(os.getenv("HOME_BADGE_NEW_DAYS", "7"))


def summary() -> dict:
    """Non-secret config view (for /health)."""
    return {
        "data_source_mode": DATA_SOURCE_MODE,
        "dev_data_dir": str(DEV_DATA_DIR),
        "vector_api_url": VECTOR_API_URL,
        "graph_api_url": GRAPH_API_URL,
        "neo4j_uri": NEO4J_URI,
        "followers_csv": FOLLOWERS_CSV,
        "home_now_iso": HOME_NOW_ISO or "(wall clock)",
        "home_future_grace_hours": HOME_FUTURE_GRACE_HOURS,
        "home_per_property_cap": HOME_PER_PROPERTY_CAP,
        "home_main_feed_page_size": HOME_MAIN_FEED_PAGE_SIZE,
        "api_port": API_PORT,
    }
