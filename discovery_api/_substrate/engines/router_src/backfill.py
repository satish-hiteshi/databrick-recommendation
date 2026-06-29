"""Anchored backfill (CONTEXT.MD §6) — graceful expansion when the exact universe is too small.

THE ANCHORED METHOD (the subtle part — get it exactly right):
  * Do NOT embed the raw query and pull its neighbors (that reintroduces garbage — vector ignores the
    structural constraint and drifts off-theme).
  * Instead: take the EXACT-match entities, fetch THEIR stored vectors (by id, no re-embed), and find
    THEIR nearest vector neighbors (Qdrant), excluding the exact set itself.
  * Because the anchors already embody the full intent, their neighbors stay on-theme — relaxing only
    the structural constraint vectors can't see, not the semantic character.
  * Return them labeled `related`, separate from `exact`.

Wraps the vector engine's `/api/neighbors` hook (neighbors-of-anchors, NOT raw-query neighbors).
"""

from typing import List, Optional

from blocks import _item, _post, VECTOR, Item


def backfill(exact_set: List[Item], intent, top_k: int = 10,
             exclude: Optional[set] = None) -> List[Item]:
    """Return `related` items = nearest vector neighbors OF the exact-match entities (anchored),
    excluding the exact set. Empty if there are no usable anchors (e.g. anchors with no stored vector)."""
    anchor_ids = [it["entity_id"] for it in exact_set if it.get("entity_id")]
    if not anchor_ids:
        return []
    ex = set(exclude or set()) | set(anchor_ids)
    vertical = getattr(intent, "vertical", None)        # relax structure, NOT vertical
    data = _post(f"{VECTOR}/api/neighbors", {
        "anchor_ids": anchor_ids, "exclude_ids": list(ex),
        "vertical": vertical, "top_k": top_k,
    })
    return [_item(n["entity_id"], n["name"], n["vertical"], n["score"],
                  "related: neighbour of an exact match (similar in feel; relaxes the structural "
                  "constraint vectors can't see)", "vector(anchored-backfill)")
            for n in data.get("neighbors", [])]
