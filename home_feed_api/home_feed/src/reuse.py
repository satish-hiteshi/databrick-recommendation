"""The SINGLE seam through which Endpoint 3 (Home Feed) imports Endpoint 2 (Discovery API).

E3 is "E2 + a follow-gate". It REUSES E2's verified logic rather than copy it. This file only
*imports* from E2 — it never modifies E2.

DEPLOY NOTE (this bundle): the serving path uses ONLY E2's `config` + `timeutil` (recency math +
inherited config defaults). The heavier reuse surface (data_access / substrate_client / scorer /
moment_select / feed_models …) is used exclusively by the Phase-2 carousel assembler
(`feed/home_assembler.py`), which is not implemented and not imported on any live path. So this
bundle vendors only `discovery_api/src/{config,timeutil}.py` (under `_e2/`) and imports just those.
When carousels land, vendor the rest of E2 and restore the full import list from the dev copy.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Put E2 (`discovery_api` package) on sys.path. Try the dev repo layout AND this deploy bundle's
# vendored `_e2/` — whichever exists — so `import discovery_api.src.*` resolves in both.
_HERE = Path(__file__).resolve()
_E2_CANDIDATES = (
    _HERE.parents[4] / "endpoint_2_discovery_api" / "local_code",   # dev: <repo>/endpoint_2_discovery_api/local_code
    _HERE.parents[2] / "_e2",                                       # deploy bundle: home_feed_api/_e2
)
for _root in _E2_CANDIDATES:
    if _root.is_dir() and str(_root) not in sys.path:
        sys.path.insert(0, str(_root))

from discovery_api.src import config as e2_config    # noqa: E402  (all E2 knobs/defaults)
from discovery_api.src import timeutil               # noqa: E402  (recency_score, now, parse_ts)

__all__ = ["e2_config", "timeutil"]
