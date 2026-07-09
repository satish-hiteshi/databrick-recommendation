"""Vendored code to make Endpoint 4 (Search) fully STANDALONE — zero imports from endpoint_2/endpoint_3.

This is a CODE COPY (no data). Satish holds all data/vector/neo4j on Databricks; E4 needs only the two
small classes below to run on its own, so they are copied here VERBATIM (behaviour unchanged) rather than
imported cross-endpoint:

  1. CsvFollowSource (+ its FollowSource ABC) — vendored from
     endpoint_3_home_feed/local_code/home_feed/src/follow_source.py (pure stdlib: csv, abc, pathlib).
  2. GraphMomentsBase — the read-only neo4j lifecycle (__init__ / __enter__ / __exit__ / close) that
     SearchBridge subclasses, vendored from
     endpoint_3_home_feed/local_code/home_feed/src/graph_moments.py (class GraphMoments). Only the
     context-manager surface is copied — E4's SearchBridge.full_map() uses only ``self._driver`` +
     ``self._database``; the unused E3 helpers (resolve_follow_keys / property_attributes /
     moments_for_properties, CandidateMoment, shared.identity) are NOT copied. Neo4j creds are always
     passed EXPLICITLY by build_bridge() (E4 config), so no home_feed.config fallback is needed.
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Union

from neo4j import GraphDatabase


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Vendored from endpoint_3_home_feed/.../follow_source.py to make E4 standalone (code copy, no data).
# ═══════════════════════════════════════════════════════════════════════════════════════════════════

# a raw follow key is either an entity_id string ("Movie:119163") or a legacy bare source_id int.
FollowKey = Union[str, int]


def _is_active(deleted_at: Optional[str]) -> bool:
    """Active follow = deleted_at IS NULL/empty (the CSV uses '' or literal 'null')."""
    return deleted_at is None or str(deleted_at).strip().lower() in ("", "null", "none")


class FollowSource(ABC):
    @abstractmethod
    def active_followed_property_ids(self, follow_user_id: int) -> Set[FollowKey]:
        """Return the RAW follow keys the user ACTIVELY follows (deleted_at IS NULL): entity_id strings
        (preferred) or legacy bare source_id ints. Resolved to entity_ids downstream (via the graph)."""
        ...


class CsvFollowSource(FollowSource):
    """Dev source: reads the followers CSV once (lazily) and indexes active follows by user_id.
    Prefers an `entity_id` column; falls back to the legacy bare `property_id` column."""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._by_user: Optional[Dict[int, Set[FollowKey]]] = None

    def _load(self) -> Dict[int, Set[FollowKey]]:
        if self._by_user is not None:
            return self._by_user
        by_user: Dict[int, Set[FollowKey]] = {}
        p = Path(self.csv_path)
        if p.is_file():
            with p.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if not _is_active(row.get("deleted_at")):
                        continue
                    try:
                        uid = int(float(row["user_id"]))
                    except (KeyError, ValueError, TypeError):
                        continue
                    eid = (row.get("entity_id") or "").strip()
                    if eid:                                   # re-supplied CSV: stable entity_id
                        by_user.setdefault(uid, set()).add(eid)
                        continue
                    try:                                      # legacy CSV: bare source_id (resolved via graph)
                        pid = int(float(row["property_id"]))
                    except (KeyError, ValueError, TypeError):
                        continue
                    by_user.setdefault(uid, set()).add(pid)
        self._by_user = by_user
        return by_user

    def active_followed_property_ids(self, follow_user_id: int) -> Set[FollowKey]:
        return set(self._load().get(int(follow_user_id), set()))


# ═══════════════════════════════════════════════════════════════════════════════════════════════════
# Vendored from endpoint_3_home_feed/.../graph_moments.py (class GraphMoments) to make E4 standalone
# (code copy, no data). Only the read-only context-manager lifecycle SearchBridge needs is copied.
# ═══════════════════════════════════════════════════════════════════════════════════════════════════


class GraphMomentsBase:
    """Thin read-only wrapper over the re-keyed graph. Caller owns the lifecycle (use as a context
    manager or call close()). Creds are REQUIRED explicitly (E4 build_bridge always supplies them)."""

    def __init__(self, uri: str, user: str, password: str, database: str):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))
        self._database = database

    def __enter__(self) -> "GraphMomentsBase":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._driver.close()
