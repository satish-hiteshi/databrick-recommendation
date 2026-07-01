# _e2 — minimal vendored copy of E2 (discovery_api) for E3's reuse seam

E3 (`home_feed/src/reuse.py`) reuses E2 for exactly two modules on the serving path: `config` and
`timeutil`. Only those are vendored here (not all of E2). If the Phase-2 carousel assembler
(`feed/home_assembler.py`) is implemented, it pulls the heavier E2 surface (feed_models/moment_select/
scorer/substrate_client) — vendor those then and restore reuse.py's full import list.
Source of truth: <deploy-repo>/discovery_api/src/{config.py,timeutil.py}.
