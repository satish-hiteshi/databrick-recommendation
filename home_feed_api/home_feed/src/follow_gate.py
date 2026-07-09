"""The follow-gate — the ONE rule that makes E3 different from E2.

E2 (discovery): engaged entities (follows ∪ reactions) are the hard *never-return* set; the main feed
shows UNFOLLOWED content. E3 (home): INVERTED for the MAIN stream — it shows moments ONLY from
properties the user actively follows. The set returned here IS that hard boundary; nothing outside it
may ever enter the main stream.

Identity resolution plugs in here: the followed-set is keyed by the resolved follow_user_id, so when
reaction-identity lands (identity.resolve_user) nothing in this module changes.
"""

from __future__ import annotations

from typing import Set

from . import identity
from .follow_source import FollowKey, FollowSource


def resolve_followed_property_ids(user_id: int, follow_source: FollowSource) -> Set[FollowKey]:
    """Active RAW follow keys for the user (deleted_at IS NULL) — entity_id strings (preferred) or legacy
    bare source_id ints. The caller (build_candidate_pool) resolves them to SERVED entity_ids via the
    graph. The main-stream whitelist.

    Goes through identity.resolve_user so the follower↔reaction mapping has exactly one insertion point.
    """
    resolved = identity.resolve_user(user_id)
    return follow_source.active_followed_property_ids(resolved.follow_user_id)


def is_followed(entity_id: str, followed: Set[str]) -> bool:
    """Main-stream include-gate: True iff this property (entity_id) is followed (its moments may enter the
    stream). POST composite-key migration the whitelist is keyed on entity_id, not the gone property_id."""
    return entity_id in followed
