"""profile.py — User Profile Service (Phase 3 layer).

THE BRIDGE between stored user activity and recall/ranking. Reads the user's Postgres state
(user_follows / user_reactions / user_events) and produces a structured profile:

  - liked / followed / disliked property-id sets (current state)
  - interest_vec : L2-normalized, recency-decayed centroid of the embeddings of the entities the
                   user engaged with positively (LIKE up-weighted over FOLLOW/WATCH/CLICK)
  - neg_vec      : centroid of disliked entities' embeddings (for Rocchio-style demotion)
  - verticals    : per-vertical affinity weights (game/movie/tv/podcast)

The interest vector is the user's "query" that drives recall — crucially WITHOUT making the vector
engine itself user-aware: the profile builds the vector here, and recall passes it to a generic
nearest-neighbour search. Postgres -> User Profile -> Recall -> Ranking.

Persisted to user_profiles so it survives restarts and is inspectable. Embeddings come from the
Data singleton (the same 57,443x1024 matrix the feed uses).
"""
import math

import numpy as np
import psycopg2

CONN = dict(host="localhost", port=5433, user="postgres", password="postgres",
            dbname="feedsai_discovery")

# positive event-type weights for the interest vector. Production reactions (fire/heart/confetti)
# are ALL positive, weighted by intensity (fire > heart > confetti), aligned with store/ranking/trends.
POS_EVENT_W = {"LIKE": 2.0, "FIRE": 3.0, "HEART": 2.0, "CONFETTI": 1.5,
               "FOLLOW": 1.5, "WATCH": 1.0, "CLICK": 0.5}
LIKE_W = 2.0      # base weight of a liked entity in the interest centroid
FOLLOW_W = 1.5    # base weight of a followed entity
HALF_LIFE_DAYS = 30.0   # recency decay: an interaction's weight halves every 30 days


def _decay(age_days):
    if age_days is None or age_days <= 0:
        return 1.0
    return 0.5 ** (age_days / HALF_LIFE_DAYS)


class UserProfile:
    def __init__(self, user_id, liked, followed, disliked, interest_vec, neg_vec, verticals, counts):
        self.user_id = user_id
        self.liked = liked            # set[int] property_ids
        self.followed = followed
        self.disliked = disliked
        self.interest_vec = interest_vec   # np.float32 (1024,) or None
        self.neg_vec = neg_vec             # np.float32 (1024,) or None
        self.verticals = verticals         # {vertical: weight}
        self.counts = counts               # {likes, follows, dislikes}

    @property
    def has_taste(self):
        return self.interest_vec is not None

    def summary(self):
        topv = sorted(self.verticals.items(), key=lambda kv: -kv[1])[:4]
        return {
            "user_id": self.user_id,
            "counts": self.counts,
            "verticals": {k: round(v, 3) for k, v in topv},
            "interest_vec_dim": (int(self.interest_vec.shape[0]) if self.interest_vec is not None else 0),
            "interest_vec_norm": (round(float(np.linalg.norm(self.interest_vec)), 4)
                                  if self.interest_vec is not None else 0.0),
            "interest_vec_head": ([round(float(x), 4) for x in self.interest_vec[:5]]
                                  if self.interest_vec is not None else []),
            "has_neg_vec": self.neg_vec is not None,
        }


def _centroid(data, weighted_pids):
    """L2-normalized weighted centroid of property embeddings. weighted_pids: iterable of (pid, w)."""
    vecs, ws = [], []
    for pid, w in weighted_pids:
        v = data.embedding_for_pid(pid)
        if v is not None and w > 0:
            vecs.append(v)
            ws.append(float(w))
    if not vecs:
        return None
    M = np.vstack(vecs)
    w = np.asarray(ws, dtype=np.float32).reshape(-1, 1)
    c = (M * w).sum(axis=0) / max(float(w.sum()), 1e-9)
    n = float(np.linalg.norm(c))
    return (c / n).astype(np.float32) if n > 1e-9 else None


def build_profile(user_id, data, persist=True, conn=None):
    """Read user_id's Postgres state -> UserProfile, optionally persisting to user_profiles."""
    own = conn is None
    c = conn or psycopg2.connect(**CONN)
    c.autocommit = True
    cur = c.cursor()

    cur.execute("SELECT property_id FROM user_follows WHERE user_id=%s", (user_id,))
    followed = {int(r[0]) for r in cur.fetchall()}
    cur.execute("SELECT property_id, reaction FROM user_reactions WHERE user_id=%s", (user_id,))
    # Production reaction model is ALL POSITIVE (heart/fire/confetti) — there is NO dislike. Every
    # reaction is a positive taste signal. (Bug fix: the old `rc == "like"` never matched the actual
    # values 'heart'/'fire'/'confetti', so EVERY reaction was wrongly bucketed as a dislike.)
    liked = {int(pid) for pid, _rc in cur.fetchall()}
    disliked = set()

    # recency-decayed positive event weights per property (enrich the base follow/like weights)
    cur.execute(
        "SELECT property_id, event_type, EXTRACT(EPOCH FROM (now()-ts))/86400.0 AS age_days "
        "FROM user_events WHERE user_id=%s AND property_id IS NOT NULL "
        "AND event_type IN ('LIKE','FIRE','HEART','CONFETTI','FOLLOW','WATCH','CLICK')", (user_id,))
    ev_weight = {}
    for pid, et, age in cur.fetchall():
        pid = int(pid)
        ev_weight[pid] = ev_weight.get(pid, 0.0) + POS_EVENT_W.get(et, 0.0) * _decay(float(age) if age is not None else None)

    # positive interest set = followed + liked, with base weights + any event-derived boost
    pos_weighted = {}
    for pid in followed:
        pos_weighted[pid] = pos_weighted.get(pid, 0.0) + FOLLOW_W
    for pid in liked:
        pos_weighted[pid] = pos_weighted.get(pid, 0.0) + LIKE_W
    for pid, w in ev_weight.items():
        pos_weighted[pid] = pos_weighted.get(pid, 0.0) + w

    interest_vec = _centroid(data, pos_weighted.items())
    neg_vec = _centroid(data, [(pid, 1.0) for pid in disliked])

    # vertical affinity (followed+liked count fully; disliked counts a little — domain interest)
    verticals = {}
    for pids, w in ((followed, 1.0), (liked, 1.0), (disliked, 0.4)):
        for pid in pids:
            p = data.properties.get(pid)
            v = (p["vertical"] if p else None) or "other"
            verticals[v] = verticals.get(v, 0.0) + w
    tot = sum(verticals.values())
    if tot > 0:
        verticals = {k: v / tot for k, v in verticals.items()}

    counts = {"likes": len(liked), "follows": len(followed), "dislikes": len(disliked)}
    prof = UserProfile(user_id, liked, followed, disliked, interest_vec, neg_vec, verticals, counts)

    if persist:
        import json
        cur.execute(
            """INSERT INTO user_profiles (user_id, interest_vec, neg_vec, verticals, n_likes, n_follows, n_dislikes, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s, now())
               ON CONFLICT (user_id) DO UPDATE SET
                 interest_vec=EXCLUDED.interest_vec, neg_vec=EXCLUDED.neg_vec, verticals=EXCLUDED.verticals,
                 n_likes=EXCLUDED.n_likes, n_follows=EXCLUDED.n_follows, n_dislikes=EXCLUDED.n_dislikes,
                 updated_at=now()""",
            (user_id,
             interest_vec.tolist() if interest_vec is not None else None,
             neg_vec.tolist() if neg_vec is not None else None,
             json.dumps(verticals), counts["likes"], counts["follows"], counts["dislikes"]),
        )
    if own:
        c.close()
    return prof
