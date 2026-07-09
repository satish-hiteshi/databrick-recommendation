"""Local reuse shim — E3 is now FULLY DECOUPLED from Endpoint 2 (discovery_api).

HISTORY: this module used to bootstrap endpoint_2_discovery_api/local_code onto sys.path and import a
broad surface from `discovery_api` (config, timeutil, records, data_access, substrate_client,
taste_profile, profile, scorer, popularity/trending/collaborative, moment_select, feed_models). In
practice E3 only ever USED two of those — `e2_config` (four substrate/data knobs) and `timeutil` (two
pure functions). The rest were declared-but-unused scaffold.

DECOUPLE: the E2 import bootstrap and every `discovery_api` import are removed. `timeutil` is now the
vendored, self-contained copy (`._vendored_timeutil`), and the four `e2_config` knobs live directly in
`config.py`. E3 imports NOTHING from endpoint_2/discovery_api. This shim survives only so the two
existing call sites (`recency.py`, `candidate_pool.py`) can keep doing `from .reuse import timeutil`
unchanged; it re-exports the vendored module.
"""

from __future__ import annotations

from . import _vendored_timeutil as timeutil   # vendored parse_ts / recency_score / age helpers (no E2)

__all__ = ["timeutil"]
