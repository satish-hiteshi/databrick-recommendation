from typing import List, Optional

from blocks import _item, _post, VECTOR, Item


def backfill(exact_set: List[Item], intent, top_k: int = 10,
             exclude: Optional[set] = None) -> List[Item]:
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
