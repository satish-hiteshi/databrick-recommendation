"""Serve-time dedup — collapse results sharing the verified composite identity (dedup_key).

dedup_key = media_source_guid:media_source_id|NA:media_type_id (precomputed in property_popularity).
Keep the survivor with the HIGHEST centrality_pct (tie-break: LOWEST property_id). A NULL dedup_key
(null guid → unknown identity) NEVER collapses. We do NOT collapse different names that share only a
guid — different (source_id,type_id) → different dedup_key → kept apart by construction.
"""

from __future__ import annotations

from typing import List, Tuple


def collapse_duplicates(results: List, store) -> Tuple[List, int]:
    """Return (survivors, n_collapsed). Survivor rule: max centrality_pct, then min property_id."""
    survivors = {}           # dedup_key -> result
    passthrough = []         # null-key rows: each its own identity
    collapsed = 0
    for r in results:
        dk = store.dedup_key(r.entity_id)          # entity_id-keyed (collision-safe); source_id tie-break below
        if not dk:
            passthrough.append(r)
            continue
        cur = survivors.get(dk)
        if cur is None:
            survivors[dk] = r
        else:
            collapsed += 1
            # higher centrality wins; tie → lower property_id
            if (r.centrality_pct, -r.property_id) > (cur.centrality_pct, -cur.property_id):
                survivors[dk] = r
    return passthrough + list(survivors.values()), collapsed
