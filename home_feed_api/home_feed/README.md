# Endpoint 3 — Home Feed (`home_feed`)

The third endpoint. Conceptually **E2's discovery feed + one hard rule**: the **main moment stream is
follow-gated** — it shows moments only from properties the user actively follows, ranked by a blend of
personal taste and recency. Unfollowed content appears **only** in discovery carousels interspersed in
the stream, never in the main moment list. Everything else (ranking signals, suppression, carousels)
mirrors E2.

Design commitments: **no LLM on the serving path** (the user just opens the app — no query to parse);
**no precomputed ranking tables** (popularity/community/similarity/attributes read live from the
graph + vectors); **reuse E2, don't rewrite**.

## Layout (mirrors E1/E2)
```
endpoint_3_home_feed/
  local_code/home_feed/
    src/
      reuse.py            <- the SINGLE seam importing E2 (sys.path bootstrap + curated re-exports)
      config.py           <- inherits E2 knobs; adds E3 home-feed knobs (port :8040)
      api.py              <- FastAPI :8040, POST /home/feed, GET /home/health
      engine.py           <- HomeFeedEngine.build() orchestrator
      follow_gate.py      <- THE new rule: resolve followed set; main-stream include-gate
      candidates/
        followed_moments.py  <- NEW main-stream source (followed properties only)
      feed/
        home_assembler.py    <- main stream + interspersed discovery carousels (reuses E2 envelope)
    tests/test_scaffold_smoke.py
    deployment/00_DEPLOYMENT_INDEX.md
    eval/
  databricks_code/.gitkeep
```

## What E3 REUSES from E2 (imported via `src/reuse.py`, not copied)
- `data_access` (records, DataSource csv/live seam, `SubstrateClient` → vector :8000 / graph :8010)
- `feed.taste_profile`, `feed.profile` (the personal signal)
- `ranking.scorer` + `ranking.{popularity,trending,collaborative}` (the blend + global signals)
- `feed.moment_select` (per-property three-signal blend — called with `followed=None` so the reused
  followed-assertion does not fire on E3's intentionally-followed properties)
- `timeutil` (recency on `event_starts_at`), `feed.feed_models` (response envelope)
- E2's discovery engine itself, reused **as-is** to produce the interspersed unfollowed carousels.

## What E3 ADDS (new)
`follow_gate.py`, `candidates/followed_moments.py`, `feed/home_assembler.py`, `engine.py`, `api.py`,
the E3 knobs in `config.py`.

## Status
**FULLY BUILT.** The complete E3 pipeline is implemented and deployed: follow-gate → graph moment
traversal (Aura `HAS_MOMENT`) → suppression → ranking (taste + recency + proximity) → the UC3 v1.0
envelope, with moment items carrying the moment's own composite (`moment_profile_key` +
`moment_media_source_guid`) beside the parent property identity. The old scaffold banner was stale.

## Run the smoke test
```bash
cd endpoint_3_home_feed/local_code/home_feed && python -m pytest tests/ -q
```
