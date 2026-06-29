import json
from pathlib import Path

from connection import get_driver, NEO4J_DATABASE
import query as Q

_ROOT = Path(__file__).resolve().parent.parent
OUT = _ROOT / "results" / "rerank_eval.json"

# Default signal weights (exposed/tunable). similar + overlap are the strongest relevance signals;
# influence is a deliberately MILD landmark boost (high influence weight over-boosts popular-but-
# off-topic titles — demonstrated as a failure case below).
DEFAULT_WEIGHTS = {"overlap": 1.0, "similar": 1.0, "proximity": 0.5,
                   "community": 0.5, "influence": 0.3}

_DRIVER = None


def _driver():
    global _DRIVER
    if _DRIVER is None:
        _DRIVER = get_driver()
    return _DRIVER


# ───────────────────────── signal collection ─────────────────────────

_ENTITY_SIGNALS = """
MATCH (seed:Entity {entity_id:$seed})
UNWIND $ids AS cid
MATCH (c:Entity {entity_id:cid})
OPTIONAL MATCH pth = shortestPath(
  (seed)-[:HAS_CONCEPT|HAS_KEYWORD|IN_FRANCHISE|DEVELOPED_BY|PUBLISHED_BY*..6]-(c))
RETURN cid AS entity_id,
  [(seed)-[:HAS_CONCEPT]->(x)<-[:HAS_CONCEPT]-(c) | x.name] AS shared_concepts,
  size([(seed)-[:HAS_KEYWORD]->(x)<-[:HAS_KEYWORD]-(c) | 1]) AS shared_keywords,
  size([(seed)-[:IN_FRANCHISE]->(x)<-[:IN_FRANCHISE]-(c) | 1]) AS shared_franchise,
  CASE WHEN seed.community = c.community THEN 1.0 ELSE 0.0 END AS community,
  c.influence AS influence,
  coalesce([(seed)-[r:SIMILAR_TO]-(c) | r.score][0], 0.0) AS similar,
  length(pth) AS hops
"""

_VIRTUAL_SIGNALS = """
UNWIND $ids AS cid
MATCH (c:Entity {entity_id:cid})
RETURN cid AS entity_id,
  [(c)-[:HAS_CONCEPT]->(x) WHERE x.key IN $qc | x.name] AS shared_concepts,
  size([(c)-[:HAS_KEYWORD]->(x) WHERE toLower(x.name) IN $qk | 1]) AS shared_keywords,
  0 AS shared_franchise, 0.0 AS community, c.influence AS influence, 0.0 AS similar,
  null AS hops
"""


def _collect_signals(session, cand_ids, seed, query_concepts, query_keywords):
    if seed:
        rows = session.run(_ENTITY_SIGNALS, seed=seed, ids=cand_ids)
    else:
        rows = session.run(_VIRTUAL_SIGNALS, ids=cand_ids,
                           qc=[c.lower() for c in (query_concepts or [])],
                           qk=[k.lower() for k in (query_keywords or [])])
    out = {}
    for r in rows:
        hops = r["hops"]
        prox = min(2.0 / hops, 1.0) if hops else 0.0
        out[r["entity_id"]] = {
            "shared_concepts": r["shared_concepts"],
            "overlap_count": len(r["shared_concepts"]) + r["shared_keywords"] + r["shared_franchise"],
            "shared_keywords": r["shared_keywords"], "shared_franchise": r["shared_franchise"],
            "community": float(r["community"]), "influence": float(r["influence"]),
            "similar": float(r["similar"]), "proximity": prox,
        }
    return out


# ───────────────────────── rerank ─────────────────────────

def rerank(candidates, seed=None, weights=None, query_concepts=None, query_keywords=None):
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    cand_ids = [c["entity_id"] for c in candidates if c["entity_id"] != seed]
    base = {c["entity_id"]: c for c in candidates}
    if not cand_ids:
        return []
    with _driver().session(database=NEO4J_DATABASE) as s:
        sig = _collect_signals(s, cand_ids, seed, query_concepts, query_keywords)

    # min-max normalise overlap + influence within the candidate set (similar/proximity/community already 0..1)
    overlaps = [sig[i]["overlap_count"] for i in cand_ids]
    infls = [sig[i]["influence"] for i in cand_ids]
    omax = max(overlaps) or 1
    imin, imax = min(infls), max(infls)
    irange = (imax - imin) or 1.0

    out = []
    for cid in cand_ids:
        g = sig[cid]
        norm = {
            "overlap": g["overlap_count"] / omax,
            "similar": g["similar"],
            "proximity": g["proximity"],
            "community": g["community"],
            "influence": (g["influence"] - imin) / irange,
        }
        comp = {k: round(w[k] * norm[k], 4) for k in norm}
        score = round(sum(comp.values()), 4)
        item = dict(base[cid])
        item["first_pass_score"] = item.get("score")
        item["rerank_score"] = score
        item["components"] = comp
        item["shared_concepts"] = g["shared_concepts"]
        top_signal = max(comp, key=comp.get) if score > 0 else None
        bits = []
        if g["shared_concepts"]:
            bits.append("via " + ", ".join(g["shared_concepts"][:3]))
        if g["similar"] > 0:
            bits.append(f"SIMILAR_TO={g['similar']:.2f}")
        if g["shared_franchise"]:
            bits.append("same franchise")
        item["why"] = (f"[{top_signal}] " if top_signal else "") + "; ".join(bits)
        out.append(item)
    out.sort(key=lambda x: x["rerank_score"], reverse=True)
    return out


# ───────────────────────── flow helpers ─────────────────────────

def _query_concepts(session, cand_ids, top_n=15, min_frac=0.25):
    head = cand_ids[:top_n]
    rows = session.run(
        "UNWIND $ids AS cid MATCH (c:Entity {entity_id:cid})-[:HAS_CONCEPT]->(k:Concept) "
        "RETURN k.key AS key, count(*) AS n ORDER BY n DESC", ids=head)
    keep, thresh = [], max(2, int(len(head) * min_frac))
    for r in rows:
        if r["n"] >= thresh:
            keep.append(r["key"])
    return keep


def query_rerank(text, vertical=None, first_pass_n=50, weights=None):
    cands = Q.fulltext_search(text, vertical=vertical, limit=first_pass_n)
    if not cands:
        return cands, [], []
    with _driver().session(database=NEO4J_DATABASE) as s:
        qconcepts = _query_concepts(s, [c["entity_id"] for c in cands])
    reranked = rerank(cands, seed=None, query_concepts=qconcepts,
                      query_keywords=text.split(), weights=weights)
    return cands, reranked, qconcepts


def seed_rerank(seed_id, first_pass_n=60, same_vertical=True, weights=None):
    with _driver().session(database=NEO4J_DATABASE) as s:
        # seed's primary (most specific = rarest) concept, to form a focused-but-broad candidate pool
        top_concept = s.run(
            "MATCH (seed:Entity {entity_id:$id})-[:HAS_CONCEPT]->(k:Concept)<-[:HAS_CONCEPT]-(o:Entity) "
            "RETURN k.key AS key, count(o) AS df ORDER BY df ASC LIMIT 1", id=seed_id).single()
        if not top_concept:
            return [], [], None
        ck = top_concept["key"]
        vfilter = "AND c.vertical = seed.vertical " if same_vertical else ""
        cands = [r.data() for r in s.run(
            "MATCH (seed:Entity {entity_id:$id})-[:HAS_CONCEPT]->(:Concept {key:$ck})<-[:HAS_CONCEPT]-(c:Entity) "
            f"WHERE c <> seed {vfilter}"
            "RETURN DISTINCT c.entity_id AS entity_id, c.name AS name, c.vertical AS vertical, "
            "round(c.influence,4) AS score "
            "ORDER BY score DESC LIMIT $n", id=seed_id, ck=ck, n=first_pass_n)]
    reranked = rerank(cands, seed=seed_id, weights=weights)
    return cands, reranked, ck


# ───────────────────────── evaluation harness ─────────────────────────

def _name(eid_map, c):
    return f"[{c['vertical']}] {c['name']}"


def _before_after(before, after, n=10):
    before_ids = [c["entity_id"] for c in before]
    rows = []
    for i in range(n):
        b = before[i] if i < len(before) else None
        a = after[i] if i < len(after) else None
        a_move = ""
        if a:
            old = before_ids.index(a["entity_id"]) if a["entity_id"] in before_ids else None
            a_move = f"(was #{old+1})" if old is not None and old != i else ("(new)" if old is None else "(=)")
        rows.append({
            "rank": i + 1,
            "before": f"{_name(None,b)}" if b else "",
            "after": (f"{_name(None,a)}  score={a['rerank_score']} {a_move}  {a.get('why','')}") if a else "",
        })
    return rows


def _eval_case(kind, label, before, after, extra=None):
    print(f"\n{'='*78}\n{kind}: {label}" + (f"   [{extra}]" if extra else ""))
    print(f"{'BEFORE (first pass)':<42} | AFTER (reranked)")
    bids = [c["entity_id"] for c in before]
    for i in range(min(10, max(len(before), len(after)))):
        b = before[i] if i < len(before) else None
        a = after[i] if i < len(after) else None
        bstr = (f"{i+1:>2}. {_name(None,b)}")[:41] if b else ""
        if a:
            old = bids.index(a["entity_id"]) if a["entity_id"] in bids else None
            mv = f"(#{old+1}→{i+1})" if old is not None and old != i else ("(NEW)" if old is None else "(=)")
            astr = f"{i+1:>2}. {_name(None,a)} {a['rerank_score']} {mv}"
        else:
            astr = ""
        print(f"{bstr:<42} | {astr}")
    # which signal drove the top-5 after
    sig_tally = {}
    for a in after[:5]:
        top = max(a["components"], key=a["components"].get) if a.get("components") else None
        if top:
            sig_tally[top] = sig_tally.get(top, 0) + 1
    if sig_tally:
        print(f"   dominant signal in top-5 after: {sig_tally}")
    return {"kind": kind, "label": label, "extra": extra,
            "before_top10": [{"name": c["name"], "vertical": c["vertical"]} for c in before[:10]],
            "after_top10": [{"name": a["name"], "vertical": a["vertical"],
                             "rerank_score": a["rerank_score"], "components": a["components"],
                             "why": a.get("why", "")} for a in after[:10]],
            "dominant_signal_top5": sig_tally}


def main():
    report = {"default_weights": DEFAULT_WEIGHTS, "cases": []}

    # ── Flow 1: query reranks (text first pass) ──
    for text, vert in [("post-apocalyptic survival", None),
                       ("psychological horror", "movie"),
                       ("space exploration aliens", None)]:
        before, after, qc = query_rerank(text, vertical=vert)
        report["cases"].append(_eval_case("QUERY-RERANK", f'"{text}"' + (f" [{vert}]" if vert else ""),
                                          before, after, extra=f"query concepts={qc}"))

    # ── Flow 2: seed reranks ("more like this") ──
    for nm, vert in [("7 Days to Die", "game"), ("Dead Island 2", "game"),
                     ("The Whistler", "movie")]:
        sid = Q.resolve(nm, vert)
        if not sid:
            print(f"(seed '{nm}' not found)"); continue
        before, after, ck = seed_rerank(sid)
        report["cases"].append(_eval_case("SEED-RERANK", f"{nm} [{vert}]",
                                          before, after, extra=f"candidate pool concept='{ck}'"))

    # ── Failure case: influence-heavy weights over-boost popular-but-off-topic titles ──
    sid = Q.resolve("7 Days to Die", "game")
    before, after_default, ck = seed_rerank(sid)
    _, after_infl, _ = seed_rerank(sid, weights={"overlap": 0.3, "similar": 0.3, "proximity": 0.2,
                                                  "community": 0.2, "influence": 2.0})
    case = _eval_case("FAILURE-CASE (influence weight 2.0)", "7 Days to Die [game] — influence-heavy",
                      after_default, after_infl, extra="default-rerank (left) vs influence-heavy (right)")
    report["cases"].append(case)

    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"\nReport -> {OUT.relative_to(_ROOT)}")
    if _DRIVER is not None:
        _DRIVER.close()


if __name__ == "__main__":
    main()
