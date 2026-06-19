"""DataSource — the ONE interface the discovery engine reads through.

Two implementations sit behind it (a config flip, `DISCOVERY_DATA_SOURCE`):
  - CsvDataSource  : the dev default — loads discovery_api/data/dev/*.csv into in-memory indexes.
  - LiveDataSource : a STUB with the same signatures — queries the live Silver tables at deploy.

The substrate (vector :8000 / graph :8010) is NOT part of this interface — it is reached over HTTP via
`substrate_client.SubstrateClient`. This interface is the BEHAVIOURAL/relational data only (entities,
moments, follows, reactions, gds signals, lookups).

Identity/bridge: integer(entity_id) == property_id (verified 100% on dev). The CSV reader resolves it
from property_bridge_dev.csv; the live reader will resolve it from public_properties.id.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from .records import Cta, Entity, FollowEvent, GdsSignal, Lookups, Moment, ReactionEvent, User


class DataSource(ABC):
    # ── entities ────────────────────────────────────────────────────────
    @abstractmethod
    def get_entity(self, entity_id: str) -> Optional[Entity]: ...

    @abstractmethod
    def get_entities_by_vertical(self, vertical: str) -> List[Entity]: ...

    @abstractmethod
    def all_entity_ids(self) -> List[str]: ...

    # ── identity / bridge (integer(entity_id) == property_id) ───────────
    @abstractmethod
    def property_id_to_entity_id(self, property_id: int) -> Optional[str]: ...

    @abstractmethod
    def entity_id_to_property_id(self, entity_id: str) -> Optional[int]: ...

    # ── moments (recency keys on event_starts_at ONLY) ──────────────────
    @abstractmethod
    def get_moments_for_property(self, entity_id: str) -> List[Moment]:
        """All moments for a property, sorted by event_starts_at DESC (most recent/upcoming first)."""

    @abstractmethod
    def get_moments_for_properties(self, entity_ids: Iterable[str]) -> Dict[str, List[Moment]]: ...

    @abstractmethod
    def get_recent_moments(self, now: datetime, limit: int, vertical: Optional[str] = None) -> List[Moment]:
        """The globally freshest moments (soft-recency around `now`), newest first — the main-feed source.
        No hard age cutoff (config.RECENCY_HARD_CUTOFF_DAYS = None by default)."""

    @abstractmethod
    def get_moment(self, moment_id: int) -> Optional[Moment]:
        """A single moment by id (feed/carousel item building)."""

    @abstractmethod
    def get_ctas_for_moment(self, moment_id: int) -> List[Cta]: ...

    @abstractmethod
    def get_ctas_for_moments(self, moment_ids: Iterable[int]) -> Dict[int, List[Cta]]: ...

    # ── personal signals (per user) ─────────────────────────────────────
    @abstractmethod
    def get_followed_property_ids(self, user_id: int) -> List[int]: ...

    @abstractmethod
    def get_user_reactions(self, user_id: int) -> List[ReactionEvent]:
        """Reactions by a user, each resolved to its entity_id (via the moment). All 3 types positive."""

    @abstractmethod
    def get_user_follow_events(self, user_id: int) -> List[FollowEvent]:
        """Follows by a user as TIMESTAMPED events (property_id + created_at, entity_id resolved via the
        bridge). Powers the Discovery v2 engagement log's recency weighting — v1's
        get_followed_property_ids drops the timestamp. ADDITIVE: v1 is unaffected."""

    # ── global signals (aggregate across ALL users — velocity) ──────────
    @abstractmethod
    def get_global_reaction_counts(self, window_days: Optional[float] = None,
                                   now: Optional[datetime] = None) -> Dict[str, int]:
        """{entity_id: reaction_count} across ALL users within the recent window (None = all-time)."""

    @abstractmethod
    def get_global_follow_counts(self, window_days: Optional[float] = None,
                                 now: Optional[datetime] = None) -> Dict[str, int]:
        """{entity_id: follow_count} across ALL users within the recent window (None = all-time)."""

    @abstractmethod
    def get_followers_of_property(self, property_id: int) -> List[int]:
        """user_ids who follow a property (reverse index — powers co-follow in PopularWithFansOf)."""

    @abstractmethod
    def iter_reaction_events(self) -> List[ReactionEvent]:
        """ALL reaction events (each with moment_id, entity_id, created_at). Powers the v2 trending table
        (recency-decayed engagement velocity at the moment level). ADDITIVE: v1 is unaffected."""

    @abstractmethod
    def iter_follow_events(self) -> List[FollowEvent]:
        """ALL follow events (property_id, entity_id, created_at). Powers v2 trending (property-level
        velocity rollup). ADDITIVE: v1 is unaffected."""

    # ── gds signals (from gds_signals_dev.csv — influence + community) ──
    @abstractmethod
    def get_gds_signal(self, entity_id: str) -> Optional[GdsSignal]: ...

    @abstractmethod
    def iter_gds_signals(self) -> Iterable[GdsSignal]:
        """All gds signals (powers per-vertical popularity normalization prep)."""

    # ── podcast categories (podcast genre source; game/movie/tv use entity.canonical_genres) ──
    @abstractmethod
    def get_podcast_categories(self, entity_id: str) -> List[str]: ...

    # ── users + lookups ─────────────────────────────────────────────────
    @abstractmethod
    def get_user(self, user_id: int) -> Optional[User]: ...

    @abstractmethod
    def lookups(self) -> Lookups: ...
