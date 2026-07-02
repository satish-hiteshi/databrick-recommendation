"""Identity-resolution seam — the ONE place user-identity is resolved.

Known mismatch we are NOT solving yet: `user_id` is an INT on `public_property_followers` (the follow
source, the primary path for this prompt) but a STRING on `public_user_reactions` (the reaction source,
which feeds taste/suppression NEXT prompt). The mapping that joins them lives behind `AuthProvider_User`
→ `User` and is not yet available.

For THIS prompt the follow-gate is fully functional using the follower `user_id` directly. Everything
that needs identity goes through `resolve_user()` so there is exactly one place to add the
follower↔reaction mapping later. Do NOT invent the mapping here; just leave the seam.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass(slots=True)
class ResolvedUser:
    """The identities a request resolves to.

    follow_user_id   — INT key into public_property_followers (the follow-gate uses THIS; works today).
    reaction_user_keys — STRING keys into public_user_reactions for the SAME human. EMPTY today; the
                         extension point below fills it once AuthProvider_User→User mapping lands, which
                         is what connects reactions to suppression/taste. Until then, reaction-based
                         suppression is driven only by request-supplied moment ids (see suppression.py).
    """
    follow_user_id: int
    reaction_user_keys: List[str] = field(default_factory=list)


def resolve_user(user_id: int) -> ResolvedUser:
    """Resolve a request's user_id to its identities.

    TODAY: passthrough — returns the follower user_id and an EMPTY reaction-key list.

    ── EXTENSION POINT (next prompt) ───────────────────────────────────────────────────────────────
    Replace the empty `reaction_user_keys` with the lookup that maps this follower `user_id` to its
    `public_user_reactions` string user_id(s) via AuthProvider_User→User. That single change wires
    reactions into suppression/taste without touching any caller. Nothing else in E3 resolves identity.
    """
    return ResolvedUser(follow_user_id=int(user_id), reaction_user_keys=[])
