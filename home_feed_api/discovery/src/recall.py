"""recall.py — user-aware candidate generation (Phase 4 recall layer).

Five recall sources, each returns a list of (property_id, source_score in 0..1). The user's PROFILE
(profile.UserProfile) supplies the signals; the underlying engines stay generic — the vector matrix
is queried with the profile's interest vector, Neo4j is seeded with the profile's entities. This is
the Postgres -> User Profile -> Recall path: the engines never read user tables directly.

  vector_recall   : nearest neighbours of the user's interest_vec over the embedding matrix
  graph_recall    : Neo4j :SIMILAR_TO neighbours of the user's followed/liked entities (by name)
  trending_recall : top entity_scores.trending_score (from user_events via trends.py)
  popular_recall  : top entity_scores.popularity_score, falling back to Neo4j influence
  fresh_recall    : newest moments (recency)

All sources exclude the user's already-engaged / disliked properties so recall surfaces new items.
"""
import numpy as np


def _exclude_set(profile):
    return set(profile.liked) | set(profile.followed) | set(profile.disliked)


def vector_recall(profile, data, k=50):
    """Top-k properties by cosine(interest_vec, embedding). Engine-agnostic: the profile owns the
    query vector, this just does a generic NN over data.emb (the vector store stays user-blind)."""
    if profile.interest_vec is None or data.emb is None:
        return []
    sims = data.emb @ profile.interest_vec               # (N,) cosines, emb is L2-normalized
    excl = _exclude_set(profile)
    # map row -> pid via the inverse of emb_row_by_pid
    if not hasattr(data, "_pid_by_row"):
        data._pid_by_row = {row: pid for pid, row in data.emb_row_by_pid.items()}
    order = np.argsort(-sims)
    out = []
    for row in order:
        pid = data._pid_by_row.get(int(row))
        if pid is None or pid in excl:
            continue
        out.append((pid, float(sims[row])))
        if len(out) >= k:
            break
    # min-max to 0..1 for fair mixing
    if out:
        lo = out[-1][1]
        hi = out[0][1]
        rng = (hi - lo) or 1.0
        out = [(pid, (s - lo) / rng) for pid, s in out]
    return out


def graph_recall(profile, data, k=50, per_seed=10):
    """Neo4j :SIMILAR_TO neighbours of the user's followed+liked entities, matched by name.

    The post-dump staging graph keys on node name/node_key (not Vertical:pid), so we bridge by name:
    seed entity -> name -> graph node -> SIMILAR_TO neighbours -> names -> back to property_ids.
    Returns [] (gracefully) if Neo4j is unreachable or names don't match. Reports nothing here; the
    caller can inspect coverage.
    """
    seeds = list(profile.liked) + list(profile.followed)
    if not seeds or not getattr(data, "graph_ok", False):
        # still attempt even if influence wasn't loaded; only skip if we have no seeds
        if not seeds:
            return []
    # name <-> pid index (lowercased); first pid wins on collision
    if not hasattr(data, "_pid_by_name"):
        idx = {}
        for pid, p in data.properties.items():
            nm = (p.get("name") or "").strip().lower()
            if nm and nm not in idx:
                idx[nm] = pid
        data._pid_by_name = idx
    excl = _exclude_set(profile)
    scores = {}
    try:
        from data import neo_cypher
    except Exception:
        return []
    for spid in seeds[:25]:                                # cap seeds for latency
        p = data.properties.get(spid)
        if not p:
            continue
        name = p.get("name")
        if not name:
            continue
        try:
            rows = neo_cypher(
                "MATCH (e {name:$nm})-[r:SIMILAR_TO]->(n) "
                "RETURN n.name AS name, r.score AS score ORDER BY r.score DESC LIMIT $k",
                {"nm": name, "k": per_seed}, timeout=30,
            )
        except Exception:
            continue
        for r in rows:
            nm = r["row"][0]
            sc = r["row"][1]
            if nm is None:
                continue
            pid = data._pid_by_name.get(str(nm).strip().lower())
            if pid is None or pid in excl:
                continue
            scores[pid] = max(scores.get(pid, 0.0), float(sc) if sc is not None else 0.5)
    if not scores:
        return []
    items = sorted(scores.items(), key=lambda kv: -kv[1])[:k]
    hi = items[0][1] or 1.0
    return [(pid, s / hi) for pid, s in items]


def _from_entity_scores(data, field, k, exclude):
    es = getattr(data, "entity_scores", None) or {}
    items = [(pid, v.get(field, 0.0)) for pid, v in es.items() if pid not in exclude and v.get(field, 0.0) > 0]
    items.sort(key=lambda kv: -kv[1])
    return items[:k]


def trending_recall(profile, data, k=50):
    """Top properties by engagement-velocity trending_score (computed from user_events)."""
    return _from_entity_scores(data, "trending", k, _exclude_set(profile))


def popular_recall(profile, data, k=50):
    """Globally-popular properties: broad Neo4j PageRank (influence) pool — the classic 'popular'
    catalogue, identical for every user — which the profile-driven ranker then personalizes.
    Engagement popularity (entity_scores) is folded in as a boost when present."""
    excl = _exclude_set(profile)
    infl = getattr(data, "influence_by_pid", {}) or {}
    ranked = sorted(((pid, v) for pid, v in infl.items() if pid not in excl), key=lambda kv: -kv[1])[:k]
    if ranked:
        hi = ranked[0][1] or 1.0
        out = {pid: v / hi for pid, v in ranked}
    else:
        out = {}
    # fold engagement-popularity in (boost items that are both PageRank-popular AND engaged)
    for pid, sc in _from_entity_scores(data, "popularity", k, excl):
        out[pid] = max(out.get(pid, 0.0), sc)
    items = sorted(out.items(), key=lambda kv: -kv[1])[:k]
    return items


def fresh_recall(profile, data, k=50):
    """Newest properties by their most-recent moment epoch (recency)."""
    excl = _exclude_set(profile)
    newest = {}
    for m in data.moments:
        pid = m["property_id"]
        if pid in excl:
            continue
        e = m.get("_event_epoch")
        if e is None:
            continue
        if pid not in newest or e > newest[pid]:
            newest[pid] = e
    if not newest:
        return []
    items = sorted(newest.items(), key=lambda kv: -kv[1])[:k]
    lo = items[-1][1]
    hi = items[0][1]
    rng = (hi - lo) or 1.0
    return [(pid, (e - lo) / rng) for pid, e in items]


def all_sources(profile, data, k=50):
    """Run every recall source; return {source_name: [(pid, score), ...]}."""
    return {
        "vector": vector_recall(profile, data, k),
        "graph": graph_recall(profile, data, k),
        "trending": trending_recall(profile, data, k),
        "popular": popular_recall(profile, data, k),
        "fresh": fresh_recall(profile, data, k),
    }
