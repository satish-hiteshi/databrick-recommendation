"""Taste — the property-level follow-set affinity model (launch).

The user's taste = the set of properties they follow. We build a taste vector as the mean of the
followed properties' stored vectors (Qwen parquet), and score each candidate's PROPERTY by cosine to
it. Every moment of a property inherits that property's taste score; recency does the intra-property
ordering (moments carry no attributes of their own — Step 0).

HONEST LIMITATION: because every followed property is, by definition, something the user chose, taste
cosine is high across the board (typically a narrow ~0.5–0.9 band). Its job at launch is GENTLE
within-feed ordering — which followed properties are most central to the user's taste centroid — NOT
gating. The secondary attribute-overlap component (shared genres/themes with the rest of the follow
set) is weighted LOW for the same reason: a coherent follow set overlaps heavily.

Per-moment attribute scoring (via graph_moment_context) is a FUTURE upgrade — out of scope, pending
Michelle's approval + extension beyond games.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Dict, Iterable, Optional, Tuple

import numpy as np

from . import config
from .candidate import CandidateMoment
from .graph_moments import GraphMoments
from .vectors import VectorStore


@dataclass(slots=True)
class TasteContext:
    taste_vector: Optional[np.ndarray]                 # normalized mean of followed property vectors (or None)
    prop_meta: Dict[str, dict] = field(default_factory=dict)   # entity_id → {entity_id, genres, themes, ...}
    followed_attr_counts: Counter = field(default_factory=Counter)  # genre/theme → #followed props carrying it
    n_followed: int = 0
    n_vectors: int = 0                                 # how many followed props contributed a vector


def _attr_set(meta: dict) -> set:
    # genres + themes (game/movie/tv) + categories (podcasts, whose only attribute edge is HAS_CATEGORY).
    # categories is empty for game/movie/tv, so those verticals' attribute set is unchanged.
    return ({f"g:{g}" for g in (meta.get("genres") or [])}
            | {f"t:{t}" for t in (meta.get("themes") or [])}
            | {f"c:{c}" for c in (meta.get("categories") or [])})


def build_taste_context(followed_entity_ids: Iterable[str], graph: GraphMoments,
                        vectors: VectorStore) -> TasteContext:
    """Resolve followed properties (entity_ids) → their attributes (graph) + vectors (parquet) → the taste
    centroid. Anchored on entity_id post composite-key migration (the old property_id is gone)."""
    eids = [str(e) for e in followed_entity_ids if e]
    meta = graph.property_attributes(eids)
    taste_vec = vectors.mean_vector(m["entity_id"] for m in meta.values())
    counts: Counter = Counter()
    n_vec = 0
    for m in meta.values():
        counts.update(_attr_set(m))
        if vectors.vector_for(m["entity_id"]) is not None:
            n_vec += 1
    return TasteContext(taste_vector=taste_vec, prop_meta=meta, followed_attr_counts=counts,
                        n_followed=len(eids), n_vectors=n_vec)


def attribute_overlap(entity_id: str, ctx: TasteContext) -> float:
    """Secondary signal in [0,1]: fraction of this property's genre/theme attrs ALSO held by some OTHER
    followed property (attribute-centrality within the follow set). No attrs → neutral 0.5. Keyed on entity_id."""
    meta = ctx.prop_meta.get(entity_id)
    if not meta:
        return 0.5
    attrs = _attr_set(meta)
    if not attrs:
        return 0.5
    shared = sum(1 for a in attrs if ctx.followed_attr_counts.get(a, 0) >= 2)   # held by ≥2 followed props (incl. self)
    return shared / len(attrs)


def taste_score(candidate: CandidateMoment, ctx: TasteContext, vectors: VectorStore) -> Tuple[float, float, float]:
    """Return (taste, cosine01, overlap). taste = (1-α)·cosine01 + α·overlap, α low (config)."""
    vec = vectors.vector_for(candidate.entity_id)
    if vec is not None and ctx.taste_vector is not None:
        cosine01 = float((np.dot(vec, ctx.taste_vector) + 1.0) / 2.0)   # [-1,1] → [0,1]
    else:
        cosine01 = config.HOME_TASTE_MISSING_VEC                        # property/centroid without a vector → neutral
    overlap = attribute_overlap(candidate.entity_id, ctx)
    a = config.HOME_TASTE_ATTR_OVERLAP_WEIGHT
    return (1.0 - a) * cosine01 + a * overlap, cosine01, overlap
