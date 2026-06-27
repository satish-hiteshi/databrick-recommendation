"""reco.py — candidate mixer + ranking layer (Phase 4 final stage).

The end of the bridge:  Postgres -> User Profile -> Recall -> [MIX -> RANK] -> Recommendations.

mix()     unions the five recall sources into one candidate set, recording which sources hit each
          property and their per-source scores.
rank()    re-scores every candidate with the USER PROFILE — interest-vector cosine (with Rocchio
          dislike demotion) blended with the source signals and a per-intent weight vector — so the
          SAME query ("popular") yields DIFFERENT results for different users.
recommend() is the one call that runs the whole pipeline for a user and returns ranked, explained
          recommendations plus all intermediate artifacts (for proof/inspection).

The vector store is never told who the user is: personalization enters only through the profile's
interest vector (built in profile.py from Postgres) and the recall/ranking math here.
"""
import numpy as np

import profile as profile_mod
import recall as recall_mod

# per-intent weight vectors over [interest, vector, graph, trending, popular, fresh, follow].
# Every intent keeps a non-trivial `interest` weight -> always personalized, even for "popular".
INTENT_WEIGHTS = {
    "popular":  {"interest": 0.35, "vector": 0.15, "graph": 0.10, "trending": 0.05, "popular": 0.35, "fresh": 0.00, "follow": 0.10},
    "trending": {"interest": 0.30, "vector": 0.15, "graph": 0.10, "trending": 0.40, "popular": 0.05, "fresh": 0.00, "follow": 0.10},
    "fresh":    {"interest": 0.30, "vector": 0.15, "graph": 0.05, "trending": 0.05, "popular": 0.05, "fresh": 0.40, "follow": 0.10},
    "for_you":  {"interest": 0.50, "vector": 0.25, "graph": 0.15, "trending": 0.05, "popular": 0.05, "fresh": 0.00, "follow": 0.10},
}
DEFAULT_INTENT = "popular"
DISLIKE_DEMOTE = 0.6   # Rocchio: subtract this * cosine(item, neg_vec) from the interest score


def mix(sources):
    """Union recall sources -> {pid: {"sources": {name: score}, "n_sources": int}}."""
    cand = {}
    for name, items in sources.items():
        for pid, score in items:
            e = cand.setdefault(pid, {"sources": {}, "n_sources": 0})
            e["sources"][name] = float(score)
            e["n_sources"] = len(e["sources"])
    return cand


def rank(profile, data, candidates, intent="popular", k=10):
    """Score each candidate by the user profile + source signals; return top-k with explanations."""
    w = INTENT_WEIGHTS.get(intent, INTENT_WEIGHTS[DEFAULT_INTENT])
    iv = profile.interest_vec
    nv = profile.neg_vec
    followed = profile.followed
    scored = []
    for pid, info in candidates.items():
        s = info["sources"]
        # interest = cosine(item, interest_vec) - Rocchio dislike; 0 if no taste/embedding
        interest = 0.0
        emb = data.embedding_for_pid(pid)
        if iv is not None and emb is not None:
            interest = float(emb @ iv)
            if nv is not None:
                interest -= DISLIKE_DEMOTE * float(emb @ nv)
            interest = max(0.0, interest)
        final = (w["interest"] * interest
                 + w["vector"]   * s.get("vector", 0.0)
                 + w["graph"]    * s.get("graph", 0.0)
                 + w["trending"] * s.get("trending", 0.0)
                 + w["popular"]  * s.get("popular", 0.0)
                 + w["fresh"]    * s.get("fresh", 0.0)
                 + w["follow"]   * (1.0 if pid in followed else 0.0))
        p = data.properties.get(pid, {})
        scored.append({
            "property_id": pid,
            "name": p.get("name", f"Property {pid}"),
            "vertical": p.get("vertical"),
            "final_score": round(final, 5),
            "interest": round(interest, 4),
            "sources": {kk: round(vv, 3) for kk, vv in s.items()},
            "n_sources": info["n_sources"],
        })
    scored.sort(key=lambda r: -r["final_score"])
    return scored[:k]


def recommend(user_id, data, intent="popular", k=10, recall_k=50, conn=None):
    """Full pipeline for one user. Returns ranked recommendations + all intermediate artifacts."""
    prof = profile_mod.build_profile(user_id, data, persist=True, conn=conn)
    sources = recall_mod.all_sources(prof, data, k=recall_k)
    candidates = mix(sources)
    ranked = rank(prof, data, candidates, intent=intent, k=k)
    return {
        "user_id": user_id,
        "intent": intent,
        "profile": prof.summary(),
        "recall_counts": {name: len(items) for name, items in sources.items()},
        "recall_heads": {name: [(pid, round(sc, 3)) for pid, sc in items[:5]] for name, items in sources.items()},
        "n_candidates": len(candidates),
        "recommendations": ranked,
        "_profile_obj": prof,
    }
