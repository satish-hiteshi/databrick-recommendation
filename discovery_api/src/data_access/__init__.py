"""data_access — ONE interface (DataSource), TWO implementations (CSV now, live later) + the substrate
HTTP client. The dev-vs-deploy seam: `get_data_source()` returns CsvDataSource or LiveDataSource based
on config.DATA_SOURCE_MODE. The substrate (vector/graph) is reached via SubstrateClient, NOT duplicated.
"""

from __future__ import annotations

from typing import Optional

from .. import config
from .base import DataSource
from .csv_source import CsvDataSource
from .live_source import LiveDataSource
from .records import Cta, Entity, GdsSignal, Lookups, Moment, ReactionEvent, User
from .substrate_client import SubstrateClient, SubstrateError, run_concurrent

__all__ = ["DataSource", "CsvDataSource", "LiveDataSource", "SubstrateClient", "SubstrateError",
           "run_concurrent", "get_data_source", "Entity", "Moment", "Cta", "GdsSignal",
           "ReactionEvent", "User", "Lookups"]


def get_data_source(mode: Optional[str] = None, **kwargs) -> DataSource:
    """Return the configured DataSource. mode defaults to config.DATA_SOURCE_MODE ('csv' | 'live')."""
    mode = (mode or config.DATA_SOURCE_MODE).lower()
    if mode == "csv":
        return CsvDataSource(**kwargs)
    if mode == "live":
        return LiveDataSource(**kwargs)
    raise ValueError(f"unknown DISCOVERY_DATA_SOURCE={mode!r} (expected 'csv' or 'live')")
