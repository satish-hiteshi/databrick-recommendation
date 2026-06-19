# `discovery_api/` — Endpoint 2: the personalised discovery feed

> **Scaffold only.** The data is downloaded and validated; **no engine logic is built yet** (later
> prompts build it). This README captures intent and the source layout so the build can start cleanly.

## What Endpoint 2 is (and how it differs from Endpoint 1)
A **personalised discovery FEED**, not a query→results recommender. The user just opens the feed —
input is structured (`user_id`, interest context, `seen_ids`, sort/filter params, and a `property_ids`
**EXCLUSION** list — the opposite of Endpoint 1's id *inclusion* seed). It surfaces content the user
does **not** already follow, personalised to what they like/follow plus what is trending/fresh.

Output is two layers:
- a **MAIN FEED** of fresh "moments" (dated content events) from unfollowed properties, and
- **CAROUSELS** of properties ("New in horror", "Popular with fans of X", "Trending"),

each item carrying an endpoint-generated **`why_string`** templated from the signal that ranked it.
**No LLM on the hot path** — ranking is deterministic.

## It REUSES the shared substrate (no re-embedding, no re-enrichment)
Same vector index + same Neo4j graph as Endpoint 1, via [`../shared/`](../shared/README.md):
nearest-neighbour + cosine from the **vector** service (:8000), GDS signals (influence/community/
SIMILAR_TO) from the **graph** service (:8010), and the id convention from `../shared/identity.py`.

## Dev data (built/validated; see the top-level report)
`data/dev/` — 9 dev CSVs. Properties (57,443) vs moments (141,374) are different record types: a
**property** is the followable entity (one vector each); a **moment** is a dated event on a property
(NO embedding, never graph-loaded). Recency keys on `moment.event_starts_at` (NOT `published_at`/`views`).
Reactions are **positive-only**; cold-start dominates (only ~80 of 330 follows resolve, 16 users have
any). Region/platform are first-class (`media_platform_id`, CTA `region_id`).

## Source scaffold (`src/` — empty packages, no logic yet)
- `data_access/` — the **one interface, two implementations** seam: a **CSV reader** (local dev/testing,
  reads `data/dev/`) and a **live-query reader** (deployment; live per-request personal signals +
  a refreshed cache for global trending). Build the interface here; only the CSV reader to start.
- `feed/` — the main moment feed (fresh moments from unfollowed properties; cap per-property contribution).
- `carousels/` — property carousels ("New in X", "Popular with fans of Y", "Trending").
- `ranking/` — deterministic scoring (global popularity/influence + recency + centrality; personalisation
  as a confidence-weighted overlay). Negative/done/preference paths: configurable, tested, **DORMANT**.
- `why/` — templated `why_string` generation from the ranking signal.
