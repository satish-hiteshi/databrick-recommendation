"""Follow source — active followed properties per user, from `public_property_followers`.

Mirrors E2's csv-or-live DATA SEAM pattern (dev reads a CSV; deploy reads Silver), but E3 needs the
`deleted_at` semantics E2's follows do not carry, so this is genuinely new (active = deleted_at IS NULL).
We do NOT open a direct Databricks connection — `LiveFollowSource` is the deploy seam, a stub here.

POST composite-key migration — FOLLOW KEY: a follow is keyed on the stable **entity_id** (or composite),
NOT the old PUBLIC property_id. This source returns RAW follow keys; `GraphMoments.resolve_follow_keys`
(called in build_candidate_pool, where the graph is available) normalises them to entity_ids.
  * If the followers CSV carries an `entity_id` column, it is used directly (preferred).
  * Otherwise the legacy `property_id` column (bare source_id) is emitted and resolved against the graph
    with an ambiguity warning — but that value is the old PUBLIC id and DOES NOT resolve on the new graph.
    ⇒ ACTION: the followers CSV/Silver export MUST be re-supplied carrying entity_id (or profile_key +
    media_source_guid). See build_candidate_pool for the resolution seam.

CSV schema (legacy export): user_id(INT), property_id(INT), deleted_at(nullable).
CSV schema (re-supplied):   user_id(INT), entity_id(STR "Prefix:guid"), deleted_at(nullable).
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set, Union

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


class SeededFollowSource(FollowSource):
    """In-memory source for tests / dry runs: {user_id: iterable[follow_key]} (all treated active).
    Follow keys may be entity_id strings (preferred) or legacy bare source_id ints."""

    def __init__(self, follows: Dict[int, Iterable[FollowKey]]):
        self._f = {int(u): {(p if isinstance(p, str) else int(p)) for p in keys}
                   for u, keys in follows.items()}

    def active_followed_property_ids(self, follow_user_id: int) -> Set[FollowKey]:
        return set(self._f.get(int(follow_user_id), set()))


class LiveFollowSource(FollowSource):
    """Deploy seam — queries Silver `public_property_followers` (WHERE deleted_at IS NULL) via an
    injected `query_fn(sql) -> list[dict]` (a databricks-sql-connector query in serving; no direct dev
    connection). The pyfunc passes query_fn + the Silver catalog. One cheap per-user query; no global
    load. Same table + schema E2's LiveDataSource reads (`<catalog>.feedspostgres.public_property_followers`)."""

    def __init__(self, query_fn, catalog: str = "stg_feeds_silver", pg_schema: str = "feedspostgres"):
        self._q = query_fn
        self._pg = f"{catalog}.{pg_schema}"

    def active_followed_property_ids(self, follow_user_id: int) -> Set[int]:
        try:
            # user_id often lands NULL in the typed column (ingestion bug) with the real value in
            # _rescued_data JSON — match on COALESCE(typed, rescued), else a raw `user_id = N` misses
            # every rescued row and the user reads as following nothing (mirrors E2's LiveDataSource).
            rows = self._q(
                f"SELECT property_id FROM {self._pg}.public_property_followers "
                f"WHERE COALESCE(CAST(user_id AS BIGINT), "
                f"CAST(get_json_object(_rescued_data, '$.user_id') AS BIGINT)) = {int(follow_user_id)} "
                f"AND deleted_at IS NULL AND property_id IS NOT NULL")
        except Exception as e:  # never 500 the feed on a follows read failure — degrade to no follows
            print(f"[follow_source] live follows read failed for user {follow_user_id}: {str(e)[:120]}", flush=True)
            return set()
        return {int(r["property_id"]) for r in rows if r.get("property_id") is not None}
