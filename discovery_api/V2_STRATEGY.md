# Discovery v2 — A taste-learning recommendation engine

## Philosophy (read first)
- Build for the LIFECYCLE: a user starts with ZERO profile and the engine learns their taste as they follow and react over time. Do NOT design around the current dev snapshot's sparse data — it is not representative. Validate by running FRESH-ACCOUNT personas through the engine and watching their feeds evolve.
- CONFIDENCE-GATED layers: every data-dependent capability activates only when it has enough data, and degrades cleanly when it does not. A brand-new user, a sparse user, and a rich user all get a sensible feed from one engine.
- CONFIG-DRIVEN, no hardcoding: every weight, threshold, percentage, half-life, fraction, and cadence is config. The engine must work for any user and any number of taste shapes.
- HARD CONSTRAINT: NEVER recommend content the user already follows (discovery surfaces the UNFOLLOWED).
- ADDITIVE: v1 remains the working baseline; v2 is a selectable alternative for A/B comparison.

## The four recommendation sources (blended by signal_strength + data density)

### 1. Taste profile (the heart) — built now, active on dev
From the user's follows + reactions (timestamped):
- ENGAGEMENT LOG (signal-agnostic): each engagement = {entity_id, signal_type, base_weight, timestamp}. Built pluggable so future signals (dwell-time, not-interested) append with their own base_weight — NOT built now, just a clean extension point.
- RECENCY-AWARE: weight each engagement by exponential decay on age (config half_life). Provide a disjoint-band VIEW (0-6h/6-24h/24-48h/2-7d/7-30d/older) for explainability — each engagement in exactly one band, NO double-counting. Recent activity outweighs older.
- SPECIFIC-TASTE PINNING: aggregate the engaged entities' attributes — GENRES + KEYWORDS (the rich signals; cast is NOT in the production graph — deferred; themes are sparse — not primary) + community/influence as support. The point is to find the NARROW shared signature (specific keywords), not the broad genre label.
- TASTE CLUSTERS: coherent groups by shared genre + keyword overlap (community as tie-breaker). Each cluster: {member_entity_ids, top representative members (highest-weight, used as retrieval anchors/seeds), dominant_vertical, top_attributes (genres+keywords), cluster_weight}. Cluster identity = shared attributes, not one dominant entity.
- VERTICAL PERCENTAGES: normalize per-vertical effective weight to percentages, SMOOTHED toward a neutral/global distribution when signal_strength is low (so a 3-follow user does not get extreme allocations), sharpening toward true percentages as signal grows.
- signal_strength (0-1) and mode (cold_start | personalized).

### 2. Content-based retrieval — built now, active on dev
- PERCENTAGE ALLOCATION: allocate feed slots across verticals/taste-buckets by the profile's percentages.
- Per bucket, retrieve candidate PROPERTIES two ways IN PARALLEL:
  (a) COMPOSED-STRING VECTOR SEARCH: compose a text query from the bucket's top genres+keywords and embed+search via /api/retrieve WITH a vertical filter. (Genre/theme payload filters do NOT exist on the vector service — the genre intent rides inside the query string instead. This is the same composed-text→/api/retrieve path Endpoint 1 already uses successfully.) The string-composer is SWAPPABLE: deterministic_compose (template from attributes, no LLM, fast, deterministic) vs llm_compose (reuse Endpoint 1's LLM to write a natural phrase) — config-selected, so we A/B quality vs latency.
  (b) INDEPENDENT GRAPH PATH: from the bucket's top genres/keywords/community → /graph/structured (case-sensitive: use canonical capitalization) + :SIMILAR_TO → candidate properties.
- MERGE per bucket. Number of buckets/strings is adaptive (= the user's coherent clusters): one string per coherent cluster, not one blended mega-string (blending distinct tastes dilutes retrieval). A single-taste user collapses to one bucket naturally.
- LATENCY: this yields a few vector calls (one per bucket) instead of one-per-followed-entity. NOTE: /api/neighbors is union-by-max (no centroid); /api/retrieve embeds a phrase. The win comes from few searches, not centroids. HNSW indexing (deferred) further reduces per-search latency later.

### 3. Exploration — built now, active on dev, sized by confidence
- EXPLORATION FRACTION = f(signal_strength): large when signal is thin (learn fast), small but non-zero when rich (keep discovering).
- STRUCTURED ADJACENCY (not random): exploration candidates share SOME of the user's top attributes but introduce a NEW one (graph-defined: same genre/keyword, different community or an added genre). Distance is config-tuned (how many shared vs new attributes). Random injection is avoided — it disengages users and teaches little; structured adjacency probes taste.
- TRACKABLE: explored items are tagged so that, when engagement data exists, the system can learn which explorations converted (feeds the feedback loop). The tracking socket is built now; the learning activates with data.

### 4. Collaborative filtering + feedback loop — built now, DORMANT until data is dense
- COLLABORATIVE: pin this user's specific taste → find users who share it → compute what those users engage with that this user has NOT → surface high-overlap items (escapes the content-similarity bubble; e.g. surfaces warfare games to a specific-horror fan via behavioral overlap). NEVER surfaces already-followed content.
- ACTIVATION: only fires above a configurable data-density threshold (enough co-engaged users to form a taste neighborhood). Below threshold, contributes nothing and the content engine carries the feed. Weight grows with density.
- FEEDBACK LOOP: track engagement (reactions/follows/dwell over time) on recommended/explored/collaborative items; reinforce what gets engagement, decay what is ignored over a config window. Built now as a socket; active on production engagement volume.
- On dev these will essentially not fire (insufficient overlapping user data). They are validated with SYNTHETIC multi-user fixtures (e.g. 50 synthetic users sharing a taste, 30 also liking warfare games → confirm the 51st gets warfare games), then ship ready-and-dormant.

### 4b. Trending velocity + the three-signal blend (the synthesis)
A recommendation should satisfy THREE conditions together, not in isolation: (1) it matches the user's specific taste, (2) it is trending NOW, (3) it is trending among users with a SIMILAR taste profile. These are not three separate lists to choose between — they are three SCORES attached to every candidate, and the recommendation is what scores high on the BLEND. This lets each signal veto by absence: a stale-but-popular item (e.g. an old tournament) scores high on taste-match but ~0 on trending-velocity, so it drops; an off-taste viral item scores high on trending but ~0 on taste-match, so it drops. Only items that clear all three surface — "the recent thing that people like you are into."

- TASTE-MATCH score: from the graph-pinned taste profile (genres/keywords/community overlap) — produced by Sources 1-2.
- TRENDING-VELOCITY score: recent engagement VELOCITY (not volume) on the candidate, computed as reaction/follow counts in a recent window EXPONENTIALLY DECAYED by age (same decay principle as the user profile, applied to CONTENT). Volume alone is wrong — an old World Cup has high total reactions but ~0 recent velocity; a current tournament has high velocity. Trending is keyed primarily at the MOMENT level (moments are the dated events; recency-velocity discriminates between a property's moments), and can roll up to a property-level trending score.
- COLLABORATIVE score: how much users with a SIMILAR profile are engaging with the candidate (Source 4, dormant until data is dense).

WHERE THE DATA LIVES (deliberate decision):
- The universe of follows/reactions stays in POSTGRES (dev: the snapshot CSVs). 
- TRENDING is a time-windowed, recency-decayed AGGREGATION over that event data — computed as a PERIODICALLY-REFRESHED, CACHED table (per moment/property), NOT stored as graph structure (it is a count over time, not a relationship traversal). Refresh cadence is config and should match the upstream data-sync cadence (to confirm with the data team — trending freshness is upper-bounded by how fast reactions land in the readable table).
- COLLABORATIVE ("similar users also engage with X") is the one piece that MIGHT move to the graph (it is a similar-user traversal). Whether it does is an OPEN decision to make with real user-data volume and Michelle's mapping — not now. The graph holds CONTENT relationships; behavioral aggregations (trending) are computed over event data.

THE BLEND (in the scorer): each candidate moment's final score = w_taste·taste_match + w_trending·trending_velocity + w_collaborative·collaborative_fit + w_recency·recency − w_suppression·suppression, all weights CONFIG, each behavioral signal CONFIDENCE-GATED (contributes in proportion to how much data backs it — trending and collaborative stay quiet on thin data and grow with volume). Exploration slots (Source 3) are allocated separately by signal_strength. The "more users see content that is interesting to many" effect emerges: content that is BOTH trending AND taste-matching for a cluster of similar users surfaces to all of them, while respecting each user's profile and the never-recommend-followed rule.

## Blend controller + lifecycle
- Cold-start (no signal): pure GLOBAL feed (trending/popular/fresh/diverse).
- Sparse signal: SOME near (content-based) + MORE exploration (structured adjacency) + some global. High exploration on purpose, to learn.
- Rich signal: mostly content-based exploitation + SMALL exploration + collaborative (if data is dense).
- The mix at each stage is governed by signal_strength and data-density, all config.

## Assembly + cache
- Assemble into the existing v1.0 response envelope.
- Profile recomputed on refresh against the current `now` (tracks drift), cached briefly (config TTL — profile changes slowly). Global/cold-start feed keeps its own cache cadence.

## Build sequence
- V2-P2: engagement log + time-decayed clustered taste profile + vertical percentages. (active on dev)
- V2-P3: content-based retrieval (percentage allocation + composed-string [deterministic+LLM] + independent graph path) + exploration (structured adjacency). (active on dev)
- V2-P4: property→moment selection + assembly into v1.0 envelope + blend controller + profile cache. (active on dev)
- V2-P5: collaborative layer + feedback loop, validated with synthetic multi-user fixtures, dormant-until-dense. 
- V2-P6: wire v2 as a selectable engine path; evaluate v1 vs v2 on fresh-account personas (A/B the deterministic-vs-LLM composer and few-vs-many strings on real output).

## Open questions for Michelle (canonical mapping)
- Canonical popularity/recency fields (where they live in the graph) — reconcile with our computed influence/recency.
- Dwell-time → integer user_id resolution (for the future implicit-interest signal).
- Whether moments get loaded into the graph (possible v3).
