"""The SINGLE seam through which Endpoint 4 (Search) imports E2/E3 — mirrors E3's reuse.py pattern.

E4 REUSES (does not re-implement):
  - the property_id<->entity_id BRIDGE: endpoint_3 graph_moments.GraphMoments (the verified
    (:Entity {property_id, entity_id}) 1:1 mapping + HAS_GENRE edges, read-only on :7688),
  - the Qwen doc-vector PARQUET loader shape: endpoint_3 vectors.VectorStore (same file the deploy uses),
  - the FOLLOWS path: endpoint_3 follow_source.CsvFollowSource (active = deleted_at IS NULL),
  - E2's timeutil (parse_ts / now) via E3's own reuse seam.

DO NOT modify any E2/E3 module — this file only *imports* from them. Importing endpoint_3's config
transitively bootstraps endpoint_2's path (E3's own reuse.py does it), so both packages resolve.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Put the E3 (`home_feed`) + E2 (`discovery_api`) packages on sys.path. Try the DEV repo layout AND this
# deploy bundle's vendored `_e3/`/`_e2/` (siblings of `search_api` in the serving artifact) — whichever
# exists — so `import home_feed.src.*` / `import discovery_api.src.*` resolve in both. (Mirrors E3's reuse.)
_HERE = Path(__file__).resolve()
_PATH_CANDIDATES = (
    _HERE.parents[4] / "endpoint_3_home_feed" / "local_code",    # dev: <repo>/endpoint_3_home_feed/local_code
    _HERE.parents[4] / "endpoint_2_discovery_api" / "local_code",# dev: <repo>/endpoint_2_discovery_api/local_code
    _HERE.parents[2] / "_e3",                                    # deploy bundle: search_api/_e3
    _HERE.parents[2] / "_e2",                                    # deploy bundle: search_api/_e2
)
for _p in _PATH_CANDIDATES:
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ── reused surfaces (import paths verified against the E3 package) ──
from home_feed.src.graph_moments import GraphMoments            # noqa: E402  property_id<->entity_id bridge
from home_feed.src.vectors import VectorStore                   # noqa: E402  Qwen parquet loader (entity_id-keyed)
from home_feed.src.follow_source import (CsvFollowSource,       # noqa: E402  active follows (dev CSV)
                                         FollowSource, LiveFollowSource)  # LiveFollowSource = Silver deploy seam
from home_feed.src import config as e3_config                   # noqa: E402  (VECTOR_PARQUET, NEO4J_*, FOLLOWERS_CSV)

try:
    from discovery_api.src import timeutil                      # noqa: E402  (parse_ts, now) — E2, via E3 bootstrap
except Exception:                                               # pragma: no cover - defensive
    timeutil = None

__all__ = ["GraphMoments", "VectorStore", "CsvFollowSource", "FollowSource", "LiveFollowSource",
           "e3_config", "timeutil"]
