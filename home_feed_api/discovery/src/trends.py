"""trends.py — Phase 4 trend engine. Computes entity_scores from user_events.

Velocity-based, so it detects content going viral REGARDLESS of age (a 20-year-old title that
spikes today is caught — the signal is engagement *growth*, not recency):

  engagement weight per event:  LIKE +3, FOLLOW +5, WATCH +2·watch_frac, CLICK +1,
                                SKIP -1, DISLIKE -3, UNFOLLOW -2
  recent   = Σ weight over the last  W hours
  prior    = Σ weight over the preceding W hours
  velocity = (recent - prior) / (|prior| + K)          # spike -> large; steady -> ~0; fading -> <0
  trending_score   = minmax( log1p(max(0,recent)) · sigmoid(velocity) )    # 0..1 across active pool
  popularity_score = minmax( log1p(max(0, all_time_engagement)) )          # 0..1
  freshness_score  = 1 / (1 + age_days(newest_moment)/30) (+0.15 if <=14d) # 0..1

Writes one row per engaged property into entity_scores (UPSERT). Properties with no events are left
out — the ranker falls back to its existing Neo4j-influence popularity for those (no regression).

When user_events is empty (fresh platform) this is a no-op. Run periodically:
  hot/trending : every 15-60 min  -> python discovery/src/trends.py --window-hours 24
  daily/popular: nightly          -> python discovery/src/trends.py --window-hours 168
"""
import argparse
import math

import psycopg2

CONN = dict(host="localhost", port=5433, user="postgres", password="postgres",
            dbname="feedsai_discovery")

# event_type -> base engagement weight (WATCH additionally scaled by the row's `weight` = watch fraction)
EVENT_WEIGHT_SQL = """
  CASE event_type
    WHEN 'LIKE'     THEN 3.0
    WHEN 'FOLLOW'   THEN 5.0
    WHEN 'FIRE'     THEN 3.0
    WHEN 'HEART'    THEN 2.0
    WHEN 'CONFETTI' THEN 1.5
    WHEN 'CLICK'    THEN 1.0
    WHEN 'WATCH'    THEN 2.0 * COALESCE(weight, 1.0)
    WHEN 'SKIP'     THEN -1.0
    WHEN 'DISLIKE'  THEN -3.0
    WHEN 'UNFOLLOW' THEN -2.0
    ELSE 0.0
  END
"""

FRESHNESS_DAYS = 14
FRESHNESS_BOOST = 0.15


def _sigmoid(x):
    if x < -60:
        return 0.0
    if x > 60:
        return 1.0
    return 1.0 / (1.0 + math.exp(-x))


def _minmax(d):
    """Normalize a {pid: value} dict to 0..1. Constant/empty -> all zeros."""
    if not d:
        return {}
    vals = list(d.values())
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-12:
        return {k: 0.0 for k in d}
    rng = hi - lo
    return {k: (v - lo) / rng for k, v in d.items()}


def compute(window_hours=24, smoothing_k=5.0, verbose=True):
    c = psycopg2.connect(**CONN)
    c.autocommit = False
    cur = c.cursor()

    # 1) engagement aggregates per property: recent window, prior window, all-time
    cur.execute(
        f"""
        WITH base AS (
          SELECT property_id, ({EVENT_WEIGHT_SQL}) AS w, ts
          FROM user_events WHERE property_id IS NOT NULL
        )
        SELECT property_id,
          COALESCE(SUM(w) FILTER (WHERE ts >= now() - %s::interval), 0)                                AS recent,
          COALESCE(SUM(w) FILTER (WHERE ts <  now() - %s::interval
                                    AND ts >= now() - %s::interval), 0)                                 AS prior,
          COALESCE(SUM(w), 0)                                                                            AS all_time
        FROM base GROUP BY property_id
        """,
        (f"{window_hours} hours", f"{window_hours} hours", f"{2 * window_hours} hours"),
    )
    rows = cur.fetchall()
    if not rows:
        if verbose:
            print("no engaged properties (user_events empty for the window) — nothing to write.")
        c.close()
        return 0

    pids = [int(r[0]) for r in rows]

    # 2) freshness inputs: age (days) of each engaged property's newest moment
    cur.execute(
        "SELECT property_id, EXTRACT(EPOCH FROM (now() - MAX(COALESCE(event_starts_at, created_at)))) "
        "FROM moments WHERE property_id = ANY(%s) GROUP BY property_id",
        (pids,),
    )
    age_days = {int(p): (float(secs) / 86400.0 if secs is not None else None) for p, secs in cur.fetchall()}

    # 3) raw signals
    trending_raw, popularity_raw, velocity_by, extras = {}, {}, {}, {}
    for pid, recent, prior, all_time in rows:
        pid = int(pid)
        recent, prior, all_time = float(recent), float(prior), float(all_time)
        velocity = (recent - prior) / (abs(prior) + smoothing_k)
        trending_raw[pid] = math.log1p(max(0.0, recent)) * _sigmoid(velocity)
        popularity_raw[pid] = math.log1p(max(0.0, all_time))
        velocity_by[pid] = velocity
        extras[pid] = (recent, prior, all_time)

    trending_n = _minmax(trending_raw)
    popularity_n = _minmax(popularity_raw)

    def freshness(pid):
        a = age_days.get(pid)
        if a is None:
            return 0.0
        f = 1.0 / (1.0 + max(0.0, a) / 30.0)
        if a <= FRESHNESS_DAYS:
            f = min(1.0, f + FRESHNESS_BOOST)
        return f

    # 4) UPSERT entity_scores
    payload = [
        (pid, trending_n.get(pid, 0.0), popularity_n.get(pid, 0.0), freshness(pid), velocity_by[pid])
        for pid in trending_raw
    ]
    cur.executemany(
        """INSERT INTO entity_scores
             (property_id, trending_score, popularity_score, freshness_score, raw_velocity, updated_at)
           VALUES (%s,%s,%s,%s,%s, now())
           ON CONFLICT (property_id) DO UPDATE SET
             trending_score=EXCLUDED.trending_score,
             popularity_score=EXCLUDED.popularity_score,
             freshness_score=EXCLUDED.freshness_score,
             raw_velocity=EXCLUDED.raw_velocity,
             updated_at=now()""",
        payload,
    )
    c.commit()

    if verbose:
        print(f"window={window_hours}h  engaged_properties={len(payload)}")
        top = sorted(payload, key=lambda r: r[1], reverse=True)[:10]
        print("top trending (pid, trend, pop, fresh, velocity):")
        for pid, tr, pp, fr, vel in top:
            r, pr, at = extras[pid]
            print(f"  pid={pid:<8} trend={tr:.3f} pop={pp:.3f} fresh={fr:.3f} vel={vel:+.2f} "
                  f"(recent={r:+.1f} prior={pr:+.1f} all_time={at:+.1f})")
    c.close()
    return len(payload)


def main():
    ap = argparse.ArgumentParser(description="Compute entity_scores (trending/popularity/freshness).")
    ap.add_argument("--window-hours", type=float, default=24.0, help="rolling window size in hours")
    ap.add_argument("--k", type=float, default=5.0, help="velocity smoothing constant")
    args = ap.parse_args()
    n = compute(window_hours=args.window_hours, smoothing_k=args.k)
    print(f"DONE — {n} entity_scores rows.")


if __name__ == "__main__":
    main()
