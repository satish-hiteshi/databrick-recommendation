"""User signal-profile builder.

build_profile(user_id) -> UserProfile: the user's POSITIVE signals (follows + reactions, resolved
through the bridge to served entities), a derived signal_strength in [0,1] (how much personalization
the ranker may apply), and a coarse mode ("cold_start" vs "personalized"). Cold-start is the dominant
case on dev (only 16 users have any follows; one 202-follow test account is the personalization fixture).

DORMANT interfaces: blocked / done / not_interested / user_prefs are well-typed and ALWAYS EMPTY for now
— there is no dislike/not-interested/done or declared-interest signal in the data. They are populated when
those signals are instrumented (the not-interested contract: app_component_string='Not interesting'
keyed by feeds_user_id + app_element_id).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from .. import config
from ..data_access.base import DataSource


@dataclass
class UserProfile:
    user_id: int
    # ── POSITIVE signals (v1) ───────────────────────────────────────────
    followed_entity_ids: List[str] = field(default_factory=list)            # resolved + served
    followed_property_ids: List[int] = field(default_factory=list)          # raw (for co-follow)
    positively_reacted_entity_ids: List[str] = field(default_factory=list)  # all 3 reaction types = positive
    onboarding_status: Optional[str] = None
    signal_strength: float = 0.0          # 0..1 — personalization the ranker may apply
    mode: str = "cold_start"              # "cold_start" | "personalized"
    # ── DORMANT (always empty now; populated when instrumented) ─────────
    blocked_entity_ids: List[str] = field(default_factory=list)     # explicit blocks (none in data yet)
    done_entity_ids: List[str] = field(default_factory=list)        # "done with this" (none yet)
    not_interested_entity_ids: List[str] = field(default_factory=list)  # 'Not interesting' button (none yet)
    user_prefs: Dict[str, object] = field(default_factory=dict)     # declared interests (none in data)

    @property
    def personalization_seed_ids(self) -> List[str]:
        """followed ∪ positively-reacted entities — the seeds for similarity pools (dedup, order-stable)."""
        seen, out = set(), []
        for e in list(self.followed_entity_ids) + list(self.positively_reacted_entity_ids):
            if e not in seen:
                seen.add(e); out.append(e)
        return out

    @property
    def total_positive_signals(self) -> int:
        return len(self.followed_entity_ids) + len(self.positively_reacted_entity_ids)


def build_profile(user_id: int, data_source: DataSource) -> UserProfile:
    """Resolve a user's positive signals into a UserProfile (no scoring)."""
    # follows: property_id -> entity_id (bridge), keep only SERVED entities
    followed_props = data_source.get_followed_property_ids(user_id)
    followed_eids, seen_f = [], set()
    for pid in followed_props:
        eid = data_source.property_id_to_entity_id(pid)
        if eid and eid not in seen_f and data_source.get_entity(eid) is not None:
            seen_f.add(eid); followed_eids.append(eid)

    # reactions: moment -> entity (already resolved on the event); all 3 types positive
    reacted_eids, seen_r = [], set()
    for ev in data_source.get_user_reactions(user_id):
        if ev.reaction_type_id not in config.POSITIVE_REACTION_TYPE_IDS:
            continue                                   # (all 3 are positive today; guard for future)
        eid = ev.entity_id
        if eid and eid not in seen_r and data_source.get_entity(eid) is not None:
            seen_r.add(eid); reacted_eids.append(eid)

    user = data_source.get_user(user_id)
    total = len(followed_eids) + len(reacted_eids)
    signal_strength = min(1.0, total / config.SIGNAL_STRENGTH_FULL) if config.SIGNAL_STRENGTH_FULL else 0.0
    mode = "cold_start" if total < config.COLD_START_SIGNAL_THRESHOLD else "personalized"

    return UserProfile(
        user_id=user_id,
        followed_entity_ids=followed_eids,
        followed_property_ids=list(followed_props),
        positively_reacted_entity_ids=reacted_eids,
        onboarding_status=(user.onboarding_status if user else None),
        signal_strength=round(signal_strength, 4),
        mode=mode,
    )
