"""LiveDataSource — deployment STUB (same signatures as CsvDataSource; queries the live Silver tables).

Not implemented in this prompt. Swapping CSV→live is a config flip (DISCOVERY_DATA_SOURCE=live). The
intended split at scale: LIVE per-request reads for a user's personal signals (follows/reactions), and a
periodically-refreshed CACHE for the global trending pool (see TrendingGlobal + config.GLOBAL_REFRESH_SECONDS).
Each method documents the live source table it will query.
"""

from __future__ import annotations

from typing import Dict, Iterable, List, Optional

from .base import DataSource


def _todo(what: str):
    raise NotImplementedError(
        f"LiveDataSource.{what} not implemented — set DISCOVERY_DATA_SOURCE=csv for dev, "
        f"or implement the live query at deploy.")


class LiveDataSource(DataSource):
    """Same interface as CsvDataSource; every read raises NotImplementedError with its target table.
    Wire these to the Silver tables (public_properties, public_moments, public_follows, public_reactions,
    public_moment_ctas, the GDS signal table) at deploy. Return the SAME record dataclasses."""

    def __init__(self, conn=None):
        self.conn = conn  # a DB handle/pool injected at deploy

    # entities  → public_properties (+ enrichment columns)
    def get_entity(self, entity_id): _todo("get_entity")
    def get_entities_by_vertical(self, vertical): _todo("get_entities_by_vertical")
    def all_entity_ids(self): _todo("all_entity_ids")
    # bridge  → integer(entity_id) == public_properties.id
    def property_id_to_entity_id(self, property_id): _todo("property_id_to_entity_id")
    def entity_id_to_property_id(self, entity_id): _todo("entity_id_to_property_id")
    # moments  → public_moments (filter moment_status=3 Published; order by event_starts_at)
    def get_moments_for_property(self, entity_id): _todo("get_moments_for_property")
    def get_moments_for_properties(self, entity_ids): _todo("get_moments_for_properties")
    def get_moment(self, moment_id): _todo("get_moment")
    def get_recent_moments(self, now, limit, vertical=None): _todo("get_recent_moments")
    def get_ctas_for_moment(self, moment_id): _todo("get_ctas_for_moment")
    def get_ctas_for_moments(self, moment_ids): _todo("get_ctas_for_moments")
    # personal signals (LIVE per-request)  → public_follows, public_reactions
    def get_followed_property_ids(self, user_id): _todo("get_followed_property_ids")
    def get_user_follow_events(self, user_id): _todo("get_user_follow_events")  # → public_follows (id, created_at)
    def get_user_reactions(self, user_id): _todo("get_user_reactions")
    # global signals (CACHED, refreshed per cadence)  → aggregate public_reactions / public_follows
    def get_global_reaction_counts(self, window_days=None, now=None): _todo("get_global_reaction_counts")
    def get_global_follow_counts(self, window_days=None, now=None): _todo("get_global_follow_counts")
    def get_followers_of_property(self, property_id): _todo("get_followers_of_property")
    def iter_reaction_events(self): _todo("iter_reaction_events")     # → public_reactions (moment_id, created_at)
    def iter_follow_events(self): _todo("iter_follow_events")         # → public_follows (id, created_at)
    # gds signals  → the periodically-recomputed GDS table (influence + community)
    def get_gds_signal(self, entity_id): _todo("get_gds_signal")
    def iter_gds_signals(self): _todo("iter_gds_signals")
    # podcast categories  → media_source_guid -> podchaser categories
    def get_podcast_categories(self, entity_id): _todo("get_podcast_categories")
    # users + lookups
    def get_user(self, user_id): _todo("get_user")
    def lookups(self): _todo("lookups")
