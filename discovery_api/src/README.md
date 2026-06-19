# `discovery_api/src/` — discovery engine CORE (P3)

The personalised-feed engine internals. **This is P3: config, data-access, popularity prep, profile,
and candidate pools. It STOPS before scoring + assembly** — the final per-user feed SCORER/weighting
(P4) and the feed/carousel ASSEMBLER + `why_string` text + HTTP API (P5) are NOT built here.

```
src/
  config.py            ALL tunable knobs (no magic numbers elsewhere). summary() for /health.
  timeutil.py          event_starts_at parsing + soft-recency (the ONLY recency key).
  data_access/         ONE interface, TWO implementations + the substrate client
    base.py            DataSource (ABC) — entities/moments/follows/reactions/gds/lookups reads
    records.py         typed read-models (Entity/Moment/Cta/GdsSignal/ReactionEvent/User/Lookups)
    csv_source.py      CsvDataSource — dev default; loads discovery_api/data/dev/*.csv into indexes
    live_source.py     LiveDataSource — deploy STUB (same signatures; queries Silver tables)
    substrate_client.py SubstrateClient — HTTP to shared vector :8000 / graph :8010 (REUSED, not duplicated)
  ranking/popularity.py  per-vertical influence → 0-1 percentile (podcast tail clipped). NOT the scorer.
  feed/profile.py        build_profile(user_id) → UserProfile (positive signals + signal_strength + mode)
  candidates/            the candidate-pool providers (each generate(profile, context) -> [Candidate])
    base.py            Candidate / RequestContext / CandidateProvider + exclusion/dedupe/fresh-moment helpers
    similar_to_followed.py  fresh_moments.py  trending_global.py  popular_with_fans_of.py
    new_in_genre.py    new_on_platform.py
```

## The seams (read before P4)

**1. dev-vs-deploy (CSV vs live).** Everything reads through `DataSource`. `get_data_source()` returns
`CsvDataSource` (dev, reads `data/dev/`) or `LiveDataSource` (deploy STUB) based on
`DISCOVERY_DATA_SOURCE` (`csv` default). Swapping is a config flip — no engine code changes. At scale the
intended split: LIVE per-request reads for a user's personal signals (follows/reactions), a periodically
REFRESHED cache for global trending.

**2. substrate over HTTP (never duplicated).** The vector index + Neo4j graph are reached only via
`SubstrateClient` (`:8000` / `:8010`, URLs from config) — the SAME substrate Endpoint 1 uses. Methods:
`vector_neighbors`, `vector_retrieve`, `graph_similar`, `graph_score_within`. Hard failures raise
`SubstrateError`; providers catch it and degrade to an empty pool (the feed never crashes on a blip).
**Podcast similarity is vector-only** (the graph returns `no_graph_signal` for podcasts) — providers
route podcast seeds to `vector_neighbors`.

**3. dormant negative/done/prefs.** There is NO dislike / not-interested / done / declared-interest
signal in the data. `UserProfile` carries `blocked_entity_ids`, `done_entity_ids`,
`not_interested_entity_ids`, `user_prefs` — well-typed, **always empty now**, wired into the exclusion
path so they work the moment those signals are instrumented (contract: `app_component_string='Not
interesting'` keyed by `feeds_user_id + app_element_id`). Decay TTLs live in `config` (90/14/7 days).

**4. global-feed cache.** `TrendingGlobal` is a RECOMPUTED-AND-CACHED artifact: the global ranked list is
computed ONCE per `config.GLOBAL_REFRESH_SECONDS` (15 min default; should match the upstream Silver sync)
and served to all cold-start users — not per request. `generate()` just filters the user's exclusions off
the cached list. Its internal order (influence + confidence-weighted velocity + recency) is the GLOBAL
pool order — distinct from the P4 per-user feed blend.

**5. signals are RAW (no blend).** Every provider attaches raw signals (`semantic` / `recency` /
`influence_norm` / `velocity` / …) but computes NO final score. P4 blends them with the `config.W_*`
weights; P5 shapes the feed (per-property moment cap already applied in the pools) + carousels.

**Cold-start vs personalized pools:** `SimilarToFollowed` + `PopularWithFansOf` are EMPTY for cold-start
(no seeds). `FreshMoments`, `TrendingGlobal`, `NewInGenre`, `NewOnPlatform` carry cold-start. Cold-start is
the dominant case on dev. (Note: the nominal 202-follow account 11208 follows only UNSERVED property_ids →
it is cold_start in dev; the resolved-signal fixture is user 12305.)
