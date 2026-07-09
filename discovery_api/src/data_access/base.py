"""DataSource — the ONE interface the discovery engine reads through.

Two implementations sit behind it (a config flip, `DISCOVERY_DATA_SOURCE`):
  - CsvDataSource  : the dev default — loads discovery_api/data/dev/*.csv into in-memory indexes.
  - LiveDataSource : a STUB with the same signatures — queries the live Silver tables at deploy.

The substrate (vector :8000 / graph :8010) is NOT part of this interface — it is reached over HTTP via
`substrate_client.SubstrateClient`. This interface is the BEHAVIOURAL/relational data only (entities,
moments, follows, reactions, gds signals, lookups).

Identity (POST composite-key migration): the stable identity is the composite (profile_key +
media_source_guid), whose string form is entity_id "Prefix:media_source_guid". The old PUBLIC property_id
is GONE. `property_id_to_entity_id`/`entity_id_to_property_id` remain as a collision-lossy bare-source_id
shim for legacy/display-only paths; `resolve_inbound_id` is the correct way to normalise an inbound
property reference (entity_id | composite | bare source_id) to a served entity_id.
"""

from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Union

from .records import Cta, Entity, FollowEvent, GdsSignal, Lookups, Moment, ReactionEvent, User

# central identity (namespace import from repo root; no I/O).  base → data_access → src → discovery_api → local_code → E2 → ROOT
_REPO_ROOT = Path(__file__).resolve().parents[5]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
from shared import identity as _ident   # noqa: E402


class DataSource(ABC):
    # ── entities ────────────────────────────────────────────────────────
    @abstractmethod
    def get_entity(self, entity_id: str) -> Optional[Entity]: ...

    @abstractmethod
    def get_entities_by_vertical(self, vertical: str) -> List[Entity]: ...

    @abstractmethod
    def all_entity_ids(self) -> List[str]: ...

    # ── identity / bridge (legacy bare-source_id shim; collision-lossy) ──
    @abstractmethod
    def property_id_to_entity_id(self, property_id: int) -> Optional[str]: ...

    @abstractmethod
    def entity_id_to_property_id(self, entity_id: str) -> Optional[int]: ...

    def resolve_inbound_id(self, value: Union[int, str, dict]) -> Optional[str]:
        """Normalise an inbound property reference to a SERVED entity_id (or None). Accepts an entity_id
        string, a composite {profile_key|vertical, media_source_guid}, or a bare source_id (int/str).
        A bare source_id is resolved against the served universe via candidate_entity_ids; if it matches
        MORE THAN ONE vertical it is AMBIGUOUS → None (the caller should send the composite/entity_id).
        Concrete sources MAY override for speed; this default uses get_entity()."""
        eid = _ident.coerce_to_entity_id(value)
        if eid is not None:
            return eid if self.get_entity(eid) is not None else None
        cands = [c for c in _ident.candidate_entity_ids(value) if self.get_entity(c) is not None]
        return cands[0] if len(cands) == 1 else None

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
