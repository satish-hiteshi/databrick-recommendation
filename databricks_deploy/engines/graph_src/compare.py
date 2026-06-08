"""Head-to-head: Neo4j graph engine vs the saved Qdrant baseline on the 100-query set.

Produces the per-query comparison and the archetype-level routing tallies that seed
results/routing_matrix.md. Reuses the Qdrant baseline's PARSED intent
(positive_entities / keywords / target_verticals) — already in
data/raw/100_query_test_results.json — to route each query to the right graph function,
so we compare retrieval quality, not NLU.

Relevance is judged by two engine-NEUTRAL proxies applied identically to both engines'
top-K (every result name resolves to a graph entity, since both engines share the same
6,945 entities):
  * vert_p@K     - fraction of top-K in the query's requested target_verticals
  * concept_p@K  - fraction of top-K whose unified-Concept set intersects the query's
                   relevance concepts (seed-entity concepts for "similar" queries; the
                   keyword-mapped concepts for theme queries)
plus set overlap (titles in both engines' top-K). Fuzzy/mood queries — where the concept
proxy is uninformative (paraphrase) — are flagged so the matrix can apply the known
paraphrase-gap judgment rather than the proxy.

Run:  ./.venv/bin/python src/compare.py
"""

import json
from collections import defaultdict
from pathlib import Path

from connection import get_driver, NEO4J_DATABASE
import query as Q

_ROOT = Path(__file__).resolve().parent.parent
BASELINE = _ROOT / "data" / "raw" / "100_query_test_results.json"
OUT = _ROOT / "results" / "comparison.json"
K = 10

# 12 source categories (by query number) -> (archetype, graph method, fuzzy?)
def classify(num):
    table = [
        (1, 10, "similar_same_vertical", "similar", False),
        (11, 20, "cross_vertical", "cross", False),
        (21, 28, "multi_similar_same_vertical", "similar_multi", False),
        (29, 36, "multi_cross_vertical", "cross_multi", False),
        (37, 46, "theme_single_vertical", "fulltext", False),
        (47, 56, "theme_multi_vertical", "fulltext", False),
        (57, 66, "descriptive_mood", "fulltext", True),
        (67, 76, "date_based", "fulltext", False),
        (77, 82, "entity_plus_date", "similar", False),
        (83, 90, "negative_filter", "negative", False),
        (91, 96, "mixed", "mixed", False),
        (97, 100, "franchise_keyword", "franchise", False),
    ]
    for lo, hi, arch, method, fuzzy in table:
        if lo <= num <= hi:
            return arch, method, fuzzy
    return "other", "fulltext", False


# ───────────────────────── caches ─────────────────────────

def load_caches(session):
    name2 = {}
    for r in session.run(
        "MATCH (e:Entity) RETURN e.entity_id AS id, e.name AS name, e.vertical AS v, "
        "[(e)-[:HAS_CONCEPT]->(c)|c.key] AS ck"):
        name2[r["name"].strip().lower()] = {"id": r["id"], "vertical": r["v"], "concepts": set(r["ck"])}
    concept_keys = {r["k"] for r in session.run("MATCH (c:Concept) RETURN c.key AS k")}
    return name2, concept_keys


def _qconcepts(keywords, concept_keys):
    out = set()
    for kw in keywords or []:
        k = kw.strip().lower()
        if k in concept_keys:
            out.add(k)
        for tok in k.replace("-", " ").split():
            if tok in concept_keys:
                out.add(tok)
    return out


# ───────────────────────── graph engine dispatcher ─────────────────────────

def _top(results, k=K):
    out, seen = [], set()
    for r in results:
        key = r["name"].strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append({"name": r["name"], "vertical": r["vertical"]})
        if len(out) >= k:
            break
    return out


def _merge(lists):
    best = {}
    for lst in lists:
        for r in lst:
            key = r["name"].strip().lower()
            if key not in best or r.get("score", 0) > best[key].get("score", 0):
                best[key] = r
    return sorted(best.values(), key=lambda x: x.get("score", 0), reverse=True)


def graph_answer(rec, name2, concept_keys):
    arch, method, fuzzy = classify(rec["num"])
    verts = rec.get("target_verticals") or []
    single_vert = verts[0] if len(verts) == 1 else None
    pos = rec.get("positive_entities") or []
    neg = [n.lower() for n in (rec.get("negative_entities") or [])]
    kws = rec.get("keywords") or []
    seeds = [sid for sid in (Q.resolve(p) for p in pos) if sid]
    seed_concepts = set()
    for s in seeds:
        nm = next((n for n, m in name2.items() if m["id"] == s), None)
        if nm:
            seed_concepts |= name2[nm]["concepts"]

    status = "ok"
    qc = _qconcepts(kws, concept_keys)

    if method in ("similar", "similar_multi") and seeds:
        lists = []
        for s in seeds:
            r = Q.similar_by_attributes(s, vertical=single_vert)
            if isinstance(r, dict):  # no_graph_signal (e.g. podcast seed)
                status = r.get("status", "no_graph_signal")
                continue
            lists.append(r)
        res = _merge(lists) if lists else []
        if verts:
            res = [r for r in res if r["vertical"] in verts] or res
        return _top(res), method, (status if not res else "ok" if res else status), arch, fuzzy, seed_concepts, qc

    if method in ("cross", "cross_multi") and seeds:
        lists = []
        for s in seeds:
            s_vert = name2.get(next((n for n, m in name2.items() if m["id"] == s), ""), {}).get("vertical")
            targets = [v for v in verts if v != s_vert] or [v for v in ["movie", "tv", "game"] if v != s_vert]
            for tv in targets:
                r = Q.cross_vertical(s, tv)
                if isinstance(r, dict):
                    status = r.get("status", "no_graph_signal")
                    continue
                lists.append(r)
        res = _merge(lists)
        return _top(res), method, ("ok" if res else status), arch, fuzzy, seed_concepts, qc

    if method == "negative":
        # positive intent via concept (if any) else broad-by-influence, EXCLUDING the negatives
        pos_concepts = [c for c in qc]
        if pos_concepts:
            res = Q.cypher_structured({"vertical": single_vert, "concept": pos_concepts}, limit=40)
        elif single_vert:
            res = Q.top_by_influence({"vertical": single_vert}, limit=40)
        else:
            res = Q.fulltext_search(rec["query"], vertical=single_vert, limit=40)
        # exclude results whose concepts/name hit a negative term
        filtered = []
        for r in res:
            cs = name2.get(r["name"].strip().lower(), {}).get("concepts", set())
            if any(n in cs or n in r["name"].lower() for n in neg):
                continue
            filtered.append(r)
        return _top(filtered), method, "ok", arch, fuzzy, seed_concepts, qc

    if method == "franchise":
        # try franchise filter (e.g. "Final Fantasy games"); fall back to full-text
        fr = None
        for token in ["Final Fantasy", "Warhammer", "Star Wars", "Mario", "Zelda", "Pokemon"]:
            if token.lower() in rec["query"].lower():
                fr = token
                break
        if fr:
            res = Q.cypher_structured({"vertical": single_vert, "franchise": fr}, limit=K)
            if res:
                return _top(res), "franchise", "ok", arch, fuzzy, seed_concepts, qc
        res = Q.fulltext_search(" ".join(kws) or rec["query"], vertical=single_vert)
        return _top(res), "fulltext", "ok", arch, fuzzy, seed_concepts, qc

    if method == "mixed":
        if seeds:
            lists = [Q.similar_by_attributes(s, vertical=single_vert) for s in seeds]
            lists = [l for l in lists if not isinstance(l, dict)]
            res = _merge(lists)
            res = [r for r in res if not any(n in name2.get(r["name"].strip().lower(), {}).get("concepts", set()) for n in neg)]
            if verts:
                res = [r for r in res if r["vertical"] in verts] or res
            return _top(res), "similar+filter", ("ok" if res else "no_graph_signal"), arch, fuzzy, seed_concepts, qc
        res = Q.fulltext_search(" ".join(kws) or rec["query"], vertical=single_vert)
        return _top(res), "fulltext", "ok", arch, fuzzy, seed_concepts, qc

    # default: full-text keyword path (theme / descriptive / date)
    text = " ".join(kws) if kws else rec["query"]
    res = Q.fulltext_search(text, vertical=single_vert)
    return _top(res), "fulltext", "ok", arch, fuzzy, seed_concepts, qc


# ───────────────────────── metrics + judgment ─────────────────────────

def _vert_p(results, verts):
    if not verts or len(verts) == 4 or not results:
        return None
    return round(sum(1 for r in results if r["vertical"] in verts) / len(results), 3)


def _concept_p(results, rel_concepts, name2):
    if not rel_concepts or not results:
        return None
    hit = 0
    for r in results:
        cs = name2.get(r["name"].strip().lower(), {}).get("concepts", set())
        if cs & rel_concepts:
            hit += 1
    return round(hit / len(results), 3)


def _overlap(a, b):
    sa = {x["name"].strip().lower() for x in a}
    sb = {x["name"].strip().lower() for x in b}
    return len(sa & sb)


def judge(arch, fuzzy, status, gm, vm):
    if status != "ok":
        return "vector", f"graph has no play ({status})"
    def blend(m):
        vals = [x for x in (m["vert_p"], m["concept_p"]) if x is not None]
        return sum(vals) / len(vals) if vals else None
    gb, vb = blend(gm), blend(vm)
    if fuzzy:
        return "vector", "fuzzy/mood — BM25 misses paraphrase/synonymy (concept proxy uninformative)"
    if gb is None or vb is None:
        return "tie", "no comparable proxy"
    if gb > vb + 0.08:
        return "graph", f"higher blended precision (g={gb:.2f} v={vb:.2f})"
    if vb > gb + 0.08:
        return "vector", f"higher blended precision (g={gb:.2f} v={vb:.2f})"
    return "tie", f"comparable (g={gb:.2f} v={vb:.2f})"


# ───────────────────────── main ─────────────────────────

def main():
    baseline = json.loads(BASELINE.read_text())
    driver = get_driver()
    with driver.session(database=NEO4J_DATABASE) as s:
        name2, concept_keys = load_caches(s)

    per_query = []
    for rec in baseline:
        arch, method0, fuzzy = classify(rec["num"])
        v_results = _top([{"name": r["name"], "vertical": r["vertical"]}
                          for r in (rec.get("results") or [])])
        if not v_results and rec.get("results_by_vertical"):
            flat = []
            for vlist in rec["results_by_vertical"].values():
                flat += [{"name": r["name"], "vertical": r["vertical"]} for r in vlist]
            v_results = _top(flat)
        if rec["status"] != "success":
            # the 4 no_results — informative own category
            g_results, method, gstatus, arch, fuzzy, sc, qc = graph_answer(rec, name2, concept_keys)
            per_query.append({"num": rec["num"], "query": rec["query"], "archetype": arch,
                              "graph_method": method, "baseline_status": "no_results",
                              "graph": g_results, "vector": [], "graph_status": gstatus,
                              "winner": "graph" if g_results else "tie",
                              "reason": "vector baseline returned no_results", "vert_p_graph": None,
                              "vert_p_vector": None, "concept_p_graph": None, "concept_p_vector": None,
                              "overlap": 0})
            continue
        g_results, method, gstatus, arch, fuzzy, seed_concepts, qc = graph_answer(rec, name2, concept_keys)
        verts = rec.get("target_verticals") or []
        rel = seed_concepts if seed_concepts else qc
        gm = {"vert_p": _vert_p(g_results, verts), "concept_p": _concept_p(g_results, rel, name2)}
        vm = {"vert_p": _vert_p(v_results, verts), "concept_p": _concept_p(v_results, rel, name2)}
        winner, reason = judge(arch, fuzzy, gstatus, gm, vm)
        per_query.append({
            "num": rec["num"], "query": rec["query"], "archetype": arch, "graph_method": method,
            "baseline_status": "success", "graph_status": gstatus,
            "graph": g_results, "vector": v_results,
            "vert_p_graph": gm["vert_p"], "vert_p_vector": vm["vert_p"],
            "concept_p_graph": gm["concept_p"], "concept_p_vector": vm["concept_p"],
            "overlap": _overlap(g_results, v_results), "winner": winner, "reason": reason})

    # aggregate by archetype
    agg = defaultdict(lambda: {"graph": 0, "vector": 0, "tie": 0, "n": 0,
                               "overlap_sum": 0, "overlap_n": 0})
    for q in per_query:
        a = agg[q["archetype"]]
        a["n"] += 1
        a[q["winner"]] += 1
        if q["baseline_status"] == "success":
            a["overlap_sum"] += q["overlap"]
            a["overlap_n"] += 1
    aggregate = {k: {**v, "avg_overlap": round(v["overlap_sum"] / v["overlap_n"], 2) if v["overlap_n"] else None}
                 for k, v in agg.items()}
    totals = {"graph": sum(1 for q in per_query if q["winner"] == "graph"),
              "vector": sum(1 for q in per_query if q["winner"] == "vector"),
              "tie": sum(1 for q in per_query if q["winner"] == "tie"), "n": len(per_query)}

    OUT.write_text(json.dumps({"totals": totals, "by_archetype": aggregate, "per_query": per_query},
                              indent=2, ensure_ascii=False))

    # console summary
    print(f"Compared {len(per_query)} queries.  Totals: {totals}")
    print(f"\n{'archetype':<28} {'n':>3} {'graph':>5} {'vec':>4} {'tie':>4} {'avgOverlap':>10}")
    order = ["similar_same_vertical", "cross_vertical", "multi_similar_same_vertical",
             "multi_cross_vertical", "theme_single_vertical", "theme_multi_vertical",
             "descriptive_mood", "date_based", "entity_plus_date", "negative_filter",
             "mixed", "franchise_keyword"]
    for a in order:
        if a in aggregate:
            v = aggregate[a]
            print(f"{a:<28} {v['n']:>3} {v['graph']:>5} {v['vector']:>4} {v['tie']:>4} {str(v['avg_overlap']):>10}")
    print(f"\nReport -> {OUT.relative_to(_ROOT)}")
    driver.close()


if __name__ == "__main__":
    main()
