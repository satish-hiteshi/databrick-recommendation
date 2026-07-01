"""Follow source — active followed property_ids per user, from `public_property_followers`.

Mirrors E2's csv-or-live DATA SEAM pattern (dev reads a CSV; deploy reads Silver), but E3 needs the
`deleted_at` semantics E2's follows do not carry, so this is genuinely new (active = deleted_at IS NULL).
We do NOT open a direct Databricks connection — `LiveFollowSource` is the deploy seam, a stub here.

CSV schema (public_property_followers export): user_id(INT), property_id(INT), deleted_at(nullable).
"""

from __future__ import annotations

import csv
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


def _is_active(deleted_at: Optional[str]) -> bool:
    """Active follow = deleted_at IS NULL/empty (the CSV uses '' or literal 'null')."""
    return deleted_at is None or str(deleted_at).strip().lower() in ("", "null", "none")


class FollowSource(ABC):
    @abstractmethod
    def active_followed_property_ids(self, follow_user_id: int) -> Set[int]:
        """Return the set of property_ids the user ACTIVELY follows (deleted_at IS NULL)."""
        ...


class CsvFollowSource(FollowSource):
    """Dev source: reads the followers CSV once (lazily) and indexes active follows by user_id."""

    def __init__(self, csv_path: str):
        self.csv_path = csv_path
        self._by_user: Optional[Dict[int, Set[int]]] = None

    def _load(self) -> Dict[int, Set[int]]:
        if self._by_user is not None:
            return self._by_user
        by_user: Dict[int, Set[int]] = {}
        p = Path(self.csv_path)
        if p.is_file():
            with p.open(newline="", encoding="utf-8") as fh:
                for row in csv.DictReader(fh):
                    if not _is_active(row.get("deleted_at")):
                        continue
                    try:
                        uid = int(float(row["user_id"])); pid = int(float(row["property_id"]))
                    except (KeyError, ValueError, TypeError):
                        continue
                    by_user.setdefault(uid, set()).add(pid)
        self._by_user = by_user
        return by_user

    def active_followed_property_ids(self, follow_user_id: int) -> Set[int]:
        return set(self._load().get(int(follow_user_id), set()))


class SeededFollowSource(FollowSource):
    """In-memory source for tests / dry runs: {user_id: iterable[property_id]} (all treated active)."""

    def __init__(self, follows: Dict[int, Iterable[int]]):
        self._f = {int(u): {int(p) for p in pids} for u, pids in follows.items()}

    def active_followed_property_ids(self, follow_user_id: int) -> Set[int]:
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
            rows = self._q(
                f"SELECT property_id FROM {self._pg}.public_property_followers "
                f"WHERE user_id = {int(follow_user_id)} AND deleted_at IS NULL AND property_id IS NOT NULL")
        except Exception as e:  # never 500 the feed on a follows read failure — degrade to no follows
            print(f"[follow_source] live follows read failed for user {follow_user_id}: {str(e)[:120]}", flush=True)
            return set()
        return {int(r["property_id"]) for r in rows if r.get("property_id") is not None}
