# 02 — Data & Live Integration (the go-live critical doc)

What data the engine reads, **the live-data gap (CSV today; live source is a stub)**, the trending refresh
requirement, and the user-identifier note. Grounded in
[`data_access/`](../src/data_access/), [`records.py`](../src/data_access/records.py),
[`csv_source.py`](../src/data_access/csv_source.py), [`live_source.py`](../src/data_access/live_source.py),
and [`config.py`](../src/config.py).

---

## 1. Data inputs (the 10 dev CSVs)

The engine reads **tabular behavioural/content data** through **one interface — `DataSource`**
([`base.py`](../src/data_access/base.py), 24 read methods). Today that interface is served by
**`CsvDataSource`**, which loads these files from `discovery_api/data/dev/` into in-memory indexes on first
request:

| Dev CSV | What it is | Upstream (production) source | Key columns the engine uses |
|---|---|---|---|
| `entities_dev.csv` | The 57,443 enriched entities (the catalogue) | `public_properties` + enrichment columns | `entity_id, vertical, name, canonical_genres, themes, franchise, developer, publisher, release_date, bm25_keywords` |
| `property_bridge_dev.csv` | The id bridge | `public_properties.id` | `property_id ↔ entity_id` (verified `int(entity_id) == property_id`, 100% on dev), `media_source_guid, media_type_id` |
| `moments_dev.csv` | Dated content events (the feed items) | `public_moments` (Published, `moment_status=3`) | `moment_id, entity_id, property_id, title, description, **event_starts_at** (the recency key), media_platform_id` |
| `moment_ctas_dev.csv` | Per-moment calls-to-action / platforms | `public_moment_ctas` | `moment_id, region_id, media_platform_id, url` |
| `follows_dev.csv` | User → property follows | `public_follows` | `user_id, property_id, **created_at**` |
| `reactions_dev.csv` | User → moment reactions | `public_reactions` | `user_id, moment_id, reaction_type_id, **created_at**` |
| `podcast_categories_dev.csv` | Podcast genre source | `media_source_guid → Podchaser categories` | `entity_id → categories` (podcasts have empty `canonical_genres`) |
| `users_dev.csv` | User records | the user table | `id, onboarding_status, account_status_id, created_at` |
| `lookups_dev.csv` | Decode tables | lookup/enum tables | `media_platform`, `region`, … id→name |
| `gds_signals_dev.csv` | Graph signals per entity | the **periodically-recomputed GDS table** | `entity_id, vertical, influence` (PageRank), `community` (Louvain) |

Decode constants in config: `MEDIA_TYPE_TO_VERTICAL = {1:game, 3:movie, 4:tv, 5:podcast}`;
`POSITIVE_REACTION_TYPE_IDS = (1,2,3)` (heart/fire/confetti — all treated positive).

> **Data safety:** these CSVs are **git-ignored** and are **not** committed (verified via `git check-ignore`).
> They are dev snapshots, regenerable upstream. The engine **only reads** them — there are **no write
> operations** anywhere in `discovery_api/src` (verified).

---

## 2. ⚠️ THE LIVE-DATA GAP — stated plainly

**Today the engine can only read the dev CSVs. Reading live production data is NOT implemented.**

- `DATA_SOURCE_MODE` (`DISCOVERY_DATA_SOURCE`) selects the implementation: **`csv`** → `CsvDataSource`
  (works now); **`live`** → `LiveDataSource`.
- **`LiveDataSource` is a complete STUB.** [`live_source.py`](../src/data_access/live_source.py): **all 25
  read methods raise `NotImplementedError`** via `_todo(...)`. Setting `DISCOVERY_DATA_SOURCE=live` would make
  the **first data read throw `NotImplementedError`** — the feed cannot be built from live data.

```python
# live_source.py — every method looks like this today:
def get_entity(self, entity_id):            _todo("get_entity")            # → public_properties (+ enrichment)
def get_followed_property_ids(self, user_id): _todo("get_followed_property_ids")  # → public_follows
def iter_reaction_events(self):             _todo("iter_reaction_events")  # → public_reactions (moment_id, created_at)
def iter_gds_signals(self):                 _todo("iter_gds_signals")      # → the GDS signal table
# … 21 more, each documenting its target Silver table
```

### What implementing `LiveDataSource` requires (the go-live work)

`LiveDataSource` must implement the **same 24-method `DataSource` interface**, returning the **same record
dataclasses** (`Entity, Moment, Cta, GdsSignal, ReactionEvent, FollowEvent, User, Lookups` from
[`records.py`](../src/data_access/records.py)), backed by the live Silver tables. The stub already documents
each target table:

| Interface area | Target live source | Notes |
|---|---|---|
| entities + bridge | `public_properties` (+ enrichment columns) | `int(entity_id) == public_properties.id` |
| moments + CTAs | `public_moments` (filter Published `moment_status=3`, order by `event_starts_at`), `public_moment_ctas` | |
| personal signals (per request) | `public_follows`, `public_reactions` | LIVE per-request reads keyed by **integer user_id** |
| global signals (cached) | aggregate `public_reactions` / `public_follows` | powers velocity/trending |
| GDS signals | the periodically-recomputed GDS table | `influence` (PageRank), `community` (Louvain) |
| podcast categories | `media_source_guid → Podchaser categories` | |
| users + lookups | the user table + lookup tables | |

**The intended split (documented in the stub):** **live per-request** reads for a user's personal signals
(follows/reactions), and a **periodically-refreshed cache** for global/trending aggregates. On Databricks the
backing store would be **Lakehouse/Silver tables (or a managed Postgres)** queried per request — **the exact
binding (JDBC/Spark/Delta) is a platform decision to confirm with Satish/Alex** (doc 05).

**This is a hard prerequisite for a real production deployment.** Until `LiveDataSource` is implemented, a
deployment serves only the dev-snapshot catalogue and dev engagement — useful for integration/perf testing,
**not** for real users.

> Honest framing for the client: the *engine* is built and validated; the *live data binding* is the named,
> well-scoped remaining integration. The interface seam (`DataSource`) was designed for exactly this swap —
> it is a config flip plus the `LiveDataSource` implementation, **no engine changes**.

---

## 3. The DATA-REFRESH requirement for trending

The **trending-velocity** signal ([`ranking/trending.py`](../src/ranking/trending.py)) is a
**recency-decayed engagement velocity**, not raw volume:

- It aggregates **reactions + follows within `V2_TRENDING_WINDOW_DAYS` (default 21 days)**, each event
  **exponentially decayed** at half-life `V2_TRENDING_HALFLIFE_DAYS` (default **3 days**), then
  **confidence-gated** by `V2_TRENDING_CONFIDENCE_FULL` (default 200 decayed events ≈ full confidence).
- The table is **precomputed and cached**, recomputed every `V2_TRENDING_REFRESH_SECONDS` (default **900 s /
  15 min**) — set this to match the upstream data-sync cadence.

**Implication for deployment:** trending quality depends on **near-real-time refresh of follows/reactions**
into the readable table. Its freshness is **upper-bounded by how fast reactions land** in whatever
`LiveDataSource` queries.

- **On the current dev data, trending is mechanically correct but QUIET** — only ~31 reactions, giving a
  confidence ≈ 0.12, so the trending term contributes ≈ 0 and the blend is effectively taste + recency.
  This was **proven correct** by lighting it up with a synthetic engagement population
  ([`eval/synthetic_population.py`](../eval/synthetic_population.py)): confidence went 0.12 → 1.0 and recent
  bursts correctly out-ranked stale-but-high-volume content (the "old World Cup vs current tournament" case).
  On real engagement volume it self-activates; tune `V2_TRENDING_CONFIDENCE_FULL` to real volume (doc 04).

---

## 4. The user-identifier note

- The endpoint expects the **internal integer `user_id`** — the same id used in `public_follows.user_id` and
  `public_reactions.user_id`. `FeedRequest.user_id` is typed `int` and the code comment is explicit: **"NOT a
  Frontegg UUID"**.
- **For live data, the caller must pass the resolved integer id.** If the upstream caller only holds a
  **Frontegg UUID**, a **UUID → integer user_id resolution step is required** before calling `/discovery/feed`
  (where this lives — caller vs `LiveDataSource` — is a deployment decision).
- The future **dwell-time** signal (a planned, currently-dormant engagement source, per `V2_STRATEGY.md` §1) is
  keyed by **Frontegg UUID** in RudderStack and therefore **also needs that resolution** before it can feed the
  engagement log. (Dwell-time is **not built** — it is a documented extension point only.)
