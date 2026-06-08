"""
Comprehensive Phase 2 test suite — 20 queries across all modes.
Generates results/FINAL_TEST_REPORT_V2.md and results/test_results_v2.json.
"""

import json
import os
import time
from collections import Counter

from pipeline.vector_store import setup_qdrant
from pipeline.query_engine import process_query, print_results
from pipeline.config import RESULTS_DIR

# ── Test queries ──────────────────────────────────────────────────────

ENTITY_SINGLE = [
    ("Q1", "What games are like Elden Ring Nightreign?", "entity_single"),
    ("Q2", "Movies similar to Star Wars: The Mandalorian and Grogu", "entity_single"),
    ("Q3", "TV shows like Stranger Things: Tales from 85", "entity_single"),
]

ENTITY_MULTI = [
    ("Q4", "I love Elden Ring and Nioh 3, recommend me movies", "entity_multi"),
    ("Q5", "Games similar to both Resident Evil Requiem and Silent Hill f", "entity_multi"),
    ("Q6", "I enjoy Marvel Zombies and Alien Earth, find me games", "entity_multi"),
]

THEME_BASED = [
    ("Q7", "Horror content across all categories", "theme_based"),
    ("Q8", "Recommend me sci-fi adventure content", "theme_based"),
    ("Q9", "Find me dark fantasy games", "theme_based"),
]

DESCRIPTIVE = [
    ("Q10", "I like content with country wars and gun fighting and military operations", "descriptive"),
    ("Q11", "Something with slow-burn psychological tension and unreliable narrators", "descriptive"),
    ("Q12", "I want cozy wholesome content about building and creating things", "descriptive"),
]

MIXED_NEGATIVE = [
    ("Q13", "Love Elden Ring but hate Star Wars, want dark fantasy movies", "mixed"),
    ("Q14", "I like Resident Evil and horror games but dislike comedy, recommend TV shows", "mixed"),
    ("Q15", "Recommend games based on Marvel Zombies and Devil May Cry but nothing like kids shows", "mixed"),
    ("Q16", "I enjoyed Silent Hill f and psychological horror but I dont like action-heavy content, find movies", "mixed"),
]

MULTI_VERTICAL = [
    ("Q17", "Content similar to Elden Ring Nightreign across all categories", "entity_single"),
    ("Q18", "Recommend me games movies and TV shows based on my love for horror and survival themes", "theme_based"),
    ("Q19", "I love Dark Souls and Stranger Things, recommend everything", "entity_multi"),
    ("Q20", "Find me dark intense content across games movies and TV", "theme_based"),
]

ALL_CATEGORIES = [
    ("Entity Single", ENTITY_SINGLE),
    ("Entity Multi", ENTITY_MULTI),
    ("Theme Based", THEME_BASED),
    ("Descriptive", DESCRIPTIVE),
    ("Mixed + Negatives", MIXED_NEGATIVE),
    ("Multi-Vertical", MULTI_VERTICAL),
]

ALL_QUERIES = []
for _, qs in ALL_CATEGORIES:
    ALL_QUERIES.extend(qs)


# ── Run ───────────────────────────────────────────────────────────────

def run_all():
    print("Initializing Qdrant + BM25 index...")
    setup_qdrant()

    results = {}
    for qid, query, expected_mode in ALL_QUERIES:
        print(f"\n{'─'*60}")
        print(f"{qid}: {query}")
        try:
            output = process_query(query)
            print_results(output)
            output["expected_mode"] = expected_mode
        except Exception as e:
            print(f"  ERROR: {e}")
            output = {
                "query": query,
                "status": "error",
                "error": str(e),
                "parsed_intent": {},
                "results": [],
                "results_by_vertical": {},
                "timings": {},
                "expected_mode": expected_mode,
            }
        results[qid] = output

    return results


# ── Analysis ──────────────────────────────────────────────────────────

def analyze(results):
    a = {}

    # Success per mode
    mode_stats = {}
    for qid, r in results.items():
        mode = r.get("expected_mode", "unknown")
        has_results = bool(r.get("results")) or bool(r.get("results_by_vertical"))
        if mode not in mode_stats:
            mode_stats[mode] = {"total": 0, "success": 0, "fail_ids": []}
        mode_stats[mode]["total"] += 1
        if has_results and r.get("status") == "success":
            mode_stats[mode]["success"] += 1
        else:
            mode_stats[mode]["fail_ids"].append(qid)
    a["mode_stats"] = mode_stats

    # Gather all results into flat list for score analysis
    all_results_flat = []
    for r in results.values():
        for res in r.get("results", []):
            all_results_flat.append(res)
        for vert_results in r.get("results_by_vertical", {}).values():
            for res in vert_results:
                all_results_flat.append(res)

    # Score distributions
    if all_results_flat:
        finals = [x["final_score"] for x in all_results_flat]
        vecs = [x["vector_score"] for x in all_results_flat]
        bm25s = [x["bm25_score"] for x in all_results_flat]

        def stats(arr):
            s = sorted(arr)
            return {
                "min": round(s[0], 4), "max": round(s[-1], 4),
                "avg": round(sum(s) / len(s), 4),
                "median": round(s[len(s) // 2], 4),
            }

        a["scores"] = {
            "final": stats(finals), "vector": stats(vecs), "bm25": stats(bm25s),
            "total_results": len(all_results_flat),
            "dual_signal": sum(1 for x in all_results_flat if x.get("in_both_sets")),
            "vec_dominant": sum(1 for x in all_results_flat if x["vector_score"] > x["bm25_score"]),
            "bm25_dominant": sum(1 for x in all_results_flat if x["bm25_score"] > x["vector_score"]),
        }
    else:
        a["scores"] = {}

    # Latency
    successful = [r for r in results.values() if r.get("timings", {}).get("total_ms")]
    if successful:
        a["latency"] = {
            "avg_total": round(sum(r["timings"]["total_ms"] for r in successful) / len(successful), 1),
            "avg_nlu": round(sum(r["timings"].get("nlu_ms", 0) for r in successful) / len(successful), 1),
            "avg_retrieval": round(sum(r["timings"].get("retrieval_ms", 0) for r in successful) / len(successful), 1),
            "avg_filter": round(sum(r["timings"].get("filter_ms", 0) for r in successful) / len(successful), 1),
            "avg_rerank": round(sum(r["timings"].get("rerank_ms", 0) for r in successful) / len(successful), 1),
        }
    else:
        a["latency"] = {}

    # Negative filter effectiveness
    neg_queries = [r for r in results.values() if r.get("neg_filter_log")]
    a["neg_filter"] = {
        "queries_with_neg": len(neg_queries),
        "total_penalized": sum(
            sum(1 for e in r["neg_filter_log"] if e["action"] == "PENALIZED") for r in neg_queries
        ),
        "total_removed": sum(
            sum(1 for e in r["neg_filter_log"] if e["action"] == "REMOVED") for r in neg_queries
        ),
    }

    # Keyword boost
    kw_boosted = 0
    for r in results.values():
        rd = r.get("reranker_debug", {})
        kw_boosted += len(rd.get("keyword_boosted", []))
    a["keyword_boost_count"] = kw_boosted

    # Within-vertical accuracy (for single-vertical queries)
    wv_correct = 0
    wv_total = 0
    for r in results.values():
        verts = r.get("parsed_intent", {}).get("target_verticals", [])
        if len(verts) == 1:
            target = verts[0]
            for res in r.get("results", []):
                wv_total += 1
                if res["vertical"] == target:
                    wv_correct += 1
    a["within_vertical"] = {"correct": wv_correct, "total": wv_total,
                            "accuracy": round(wv_correct / wv_total * 100, 1) if wv_total else 0}

    # Cross-vertical diversity (for multi-vertical queries)
    mv_details = []
    for qid, r in results.items():
        verts = r.get("parsed_intent", {}).get("target_verticals", [])
        if len(verts) > 1 and r.get("results_by_vertical"):
            mv_details.append({
                "qid": qid,
                "verticals_returned": list(r["results_by_vertical"].keys()),
                "counts": {v: len(rs) for v, rs in r["results_by_vertical"].items()},
            })
    a["multi_vertical"] = mv_details

    return a


# ── Report ────────────────────────────────────────────────────────────

def generate_report(results, analysis):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    path = os.path.join(RESULTS_DIR, "FINAL_TEST_REPORT_V2.md")

    L = []

    # ── Section 1: Executive Summary ──
    total_q = len(results)
    success_q = sum(1 for r in results.values()
                    if r.get("status") == "success" and (r.get("results") or r.get("results_by_vertical")))
    lat = analysis.get("latency", {})

    L.append("# Feeds.ai Pipeline v2 — Final Test Report")
    L.append("")
    L.append("## Section 1 — Executive Summary")
    L.append("")
    L.append(f"- **Total queries:** {total_q}")
    L.append(f"- **Successful (with results):** {success_q}/{total_q} ({success_q/total_q*100:.0f}%)")
    L.append(f"- **Average latency:** {lat.get('avg_total', 0):.0f} ms")
    L.append("")
    L.append("### Success Rate by Query Mode")
    L.append("")
    L.append("| Mode | Success | Total | Rate | Failed |")
    L.append("|------|---------|-------|------|--------|")
    for mode, ms in sorted(analysis["mode_stats"].items()):
        rate = ms["success"] / ms["total"] * 100 if ms["total"] else 0
        fails = ", ".join(ms["fail_ids"]) if ms["fail_ids"] else "—"
        L.append(f"| {mode} | {ms['success']} | {ms['total']} | {rate:.0f}% | {fails} |")
    L.append("")

    # ── Section 2: Detailed Results ──
    L.append("---")
    L.append("")
    L.append("## Section 2 — Detailed Results")
    L.append("")

    for cat_name, cat_queries in ALL_CATEGORIES:
        L.append(f"### {cat_name}")
        L.append("")
        for qid, query, expected in cat_queries:
            r = results[qid]
            nlu = r.get("parsed_intent", {})
            t = r.get("timings", {})

            L.append(f"#### {qid}: \"{query}\"")
            L.append("")
            L.append(f"**NLU:** mode=`{nlu.get('query_mode', 'N/A')}` (expected `{expected}`), "
                      f"pos=`{nlu.get('positive_entities', [])}`, neg=`{nlu.get('negative_entities', [])}`")
            L.append(f"**Keywords:** add=`{nlu.get('additional_keywords', [])}`, "
                      f"derived=`{nlu.get('description_derived_keywords', [])}`")
            L.append(f"**Verticals:** `{nlu.get('target_verticals', [])}`, type=`{nlu.get('query_type', 'N/A')}`")
            L.append("")

            if r.get("anchor_entities_resolved"):
                L.append(f"**Resolved:** {', '.join(r['anchor_entities_resolved'])}")
            if r.get("negative_entities_resolved"):
                L.append(f"**Negatives:** {', '.join(r['negative_entities_resolved'])}")
            L.append("")

            if r.get("status") != "success":
                L.append(f"**Error:** {r.get('error', 'unknown')}")
                L.append("")
                continue

            # Neg filter
            neg_log = r.get("neg_filter_log", [])
            if neg_log:
                penalized = [e for e in neg_log if e["action"] == "PENALIZED"]
                removed = [e for e in neg_log if e["action"] == "REMOVED"]
                L.append(f"**Neg filter:** {len(penalized)} penalized, {len(removed)} removed "
                          f"({r.get('retrieval_candidate_count', '?')} → {r.get('post_filter_count', '?')})")
                L.append("")

            # Results tables
            if r.get("results_by_vertical"):
                for vert, vres in r["results_by_vertical"].items():
                    L.append(f"**{vert.upper()}** ({len(vres)} results):")
                    L.append("")
                    L.append("| # | Name | Final | Vec | BM25 | Both | Keywords |")
                    L.append("|---|------|-------|-----|------|------|----------|")
                    for res in vres[:10]:
                        both = "Yes" if res.get("in_both_sets") else ""
                        kws = ", ".join(res.get("shared_keywords", [])[:4])
                        L.append(f"| {res['rank']} | {res['name']} | {res['final_score']:.4f} | "
                                  f"{res['vector_score']:.4f} | {res['bm25_score']:.4f} | {both} | {kws} |")
                    L.append("")
            elif r.get("results"):
                L.append("| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |")
                L.append("|---|------|----------|-------|-----|------|------|----------|")
                for res in r["results"][:10]:
                    both = "Yes" if res.get("in_both_sets") else ""
                    kws = ", ".join(res.get("shared_keywords", [])[:4])
                    L.append(f"| {res['rank']} | {res['name']} | {res['vertical']} | "
                              f"{res['final_score']:.4f} | {res['vector_score']:.4f} | "
                              f"{res['bm25_score']:.4f} | {both} | {kws} |")
                L.append("")
            else:
                L.append("*No results.*")
                L.append("")

            L.append(f"*Latency: {t.get('total_ms', 0):.0f}ms "
                      f"(NLU {t.get('nlu_ms', 0):.0f} + retrieval {t.get('retrieval_ms', 0):.0f} "
                      f"+ filter {t.get('filter_ms', 0):.0f} + rerank {t.get('rerank_ms', 0):.0f})*")
            L.append("")

    # ── Section 3: Quality Analysis ──
    L.append("---")
    L.append("")
    L.append("## Section 3 — Quality Analysis")
    L.append("")

    wv = analysis["within_vertical"]
    L.append(f"### 3.1 Within-Vertical Accuracy")
    L.append(f"**{wv['accuracy']:.0f}%** ({wv['correct']}/{wv['total']} results in correct vertical)")
    L.append("")

    L.append("### 3.2 Cross-Vertical Diversity")
    L.append("")
    if analysis["multi_vertical"]:
        L.append("| Query | Verticals Returned | Counts |")
        L.append("|-------|--------------------|--------|")
        for d in analysis["multi_vertical"]:
            L.append(f"| {d['qid']} | {d['verticals_returned']} | {d['counts']} |")
    else:
        L.append("*No multi-vertical results to analyze.*")
    L.append("")

    nf = analysis["neg_filter"]
    L.append("### 3.3 Negative Filtering Effectiveness")
    L.append(f"- Queries with negative filter active: {nf['queries_with_neg']}")
    L.append(f"- Total candidates penalized: {nf['total_penalized']}")
    L.append(f"- Total candidates removed: {nf['total_removed']}")
    L.append("")

    L.append("### 3.4 Keyword Boosting Impact")
    L.append(f"- Total candidates keyword-boosted across all queries: {analysis['keyword_boost_count']}")
    L.append("")

    L.append("### 3.5 Multi-Entity Overlap Scoring")
    L.append("")
    overlap_queries = [r for r in results.values()
                       if r.get("parsed_intent", {}).get("query_mode") in ("entity_multi", "mixed")
                       and r.get("status") == "success"]
    if overlap_queries:
        for r in overlap_queries:
            multi_src = [res for res_list in ([r.get("results", [])] +
                         list(r.get("results_by_vertical", {}).values()))
                         for res in res_list if res.get("appeared_in_searches", 1) > 1]
            if multi_src:
                L.append(f"- **\"{r['query'][:50]}...\"**: {len(multi_src)} results appeared in multiple entity searches")
    else:
        L.append("*No multi-entity queries succeeded.*")
    L.append("")

    # ── Section 4: Score Analysis ──
    L.append("---")
    L.append("")
    L.append("## Section 4 — Score Analysis")
    L.append("")
    sc = analysis.get("scores", {})
    if sc:
        L.append("| Metric | Min | Max | Avg | Median |")
        L.append("|--------|-----|-----|-----|--------|")
        for label, key in [("Final Score", "final"), ("Vector Score", "vector"), ("BM25 Score", "bm25")]:
            d = sc[key]
            L.append(f"| {label} | {d['min']:.4f} | {d['max']:.4f} | {d['avg']:.4f} | {d['median']:.4f} |")
        L.append("")
        L.append(f"- **Total results:** {sc['total_results']}")
        L.append(f"- **Dual-signal:** {sc['dual_signal']} ({sc['dual_signal']/sc['total_results']*100:.0f}%)")
        L.append(f"- **Vector-dominant:** {sc['vec_dominant']}, **BM25-dominant:** {sc['bm25_dominant']}")
    L.append("")

    # ── Section 5: Latency ──
    L.append("---")
    L.append("")
    L.append("## Section 5 — Latency Breakdown")
    L.append("")
    if lat:
        total_avg = lat["avg_total"] or 1
        L.append("| Stage | Avg (ms) | % of Total |")
        L.append("|-------|----------|------------|")
        for label, key in [("NLU", "avg_nlu"), ("Retrieval", "avg_retrieval"),
                           ("Neg Filter", "avg_filter"), ("Reranker", "avg_rerank")]:
            val = lat[key]
            L.append(f"| {label} | {val:.0f} | {val/total_avg*100:.0f}% |")
        L.append(f"| **Total** | **{total_avg:.0f}** | **100%** |")
    L.append("")

    L.append("### Per-Query Latency")
    L.append("")
    L.append("| Query | NLU | Retrieval | Filter | Rerank | Total |")
    L.append("|-------|-----|-----------|--------|--------|-------|")
    for qid, _, _ in ALL_QUERIES:
        t = results[qid].get("timings", {})
        L.append(f"| {qid} | {t.get('nlu_ms',0):.0f} | {t.get('retrieval_ms',0):.0f} | "
                  f"{t.get('filter_ms',0):.0f} | {t.get('rerank_ms',0):.0f} | {t.get('total_ms',0):.0f} |")
    L.append("")

    # ── Section 6: Comparison vs Phase 1 ──
    L.append("---")
    L.append("")
    L.append("## Section 6 — Comparison vs Phase 1")
    L.append("")
    L.append("Phase 1 only supported `entity_single` mode. Queries without a named entity failed completely.")
    L.append("")
    L.append("| Capability | Phase 1 | Phase 2 |")
    L.append("|-----------|---------|---------|")
    L.append("| Entity-single queries | Yes | Yes |")
    L.append("| Multi-entity queries | No | Yes (overlap scoring) |")
    L.append("| Theme/genre queries | No (failed) | Yes (query embedding) |")
    L.append("| Descriptive queries | No (failed) | Yes (LLM keyword derivation + embedding) |")
    L.append("| Negative filtering | No | Yes (embedding sim + keyword + franchise) |")
    L.append("| Keyword boosting | No | Yes (+0.05 keyword, +0.03 text) |")
    L.append("| Per-vertical splitting | No | Yes (top 10 per vertical) |")
    L.append("| Franchise diversity | No | Yes (max 3 per franchise) |")
    L.append("| Unresolved neg keywords | No | Yes (keyword-only penalty) |")
    L.append("")

    # Previously-failing queries
    L.append("### Previously-Failing Query Types Now Working")
    L.append("")
    phase1_fails = ["theme_based", "descriptive", "mixed"]
    now_working = []
    still_failing = []
    for qid, r in results.items():
        mode = r.get("expected_mode", "")
        if mode in phase1_fails:
            if r.get("status") == "success" and (r.get("results") or r.get("results_by_vertical")):
                now_working.append(f"{qid} ({mode})")
            else:
                still_failing.append(f"{qid} ({mode}): {r.get('error', 'unknown')}")

    if now_working:
        L.append(f"**Now succeeding:** {', '.join(now_working)}")
    if still_failing:
        L.append(f"\n**Still failing:** {', '.join(still_failing)}")
    L.append("")

    # ── Section 7: Remaining Gaps ──
    L.append("---")
    L.append("")
    L.append("## Section 7 — Remaining Gaps and Recommendations")
    L.append("")

    # Dynamic gap analysis based on failures
    failed = [(qid, r) for qid, r in results.items()
              if r.get("status") != "success" or not (r.get("results") or r.get("results_by_vertical"))]

    if failed:
        L.append("### Queries That Failed")
        L.append("")
        for qid, r in failed:
            L.append(f"- **{qid}**: \"{r['query'][:60]}\" — {r.get('error', 'no results')}")
        L.append("")

    L.append("### Recommendations")
    L.append("")
    L.append("1. **Entity catalog expansion:** Entities not in the 1,757-item DB (e.g., Dark Souls, Stranger Things) "
             "fail resolution. Expanding the catalog or adding fuzzy matching with Levenshtein distance would help.")
    L.append("2. **NLU mode boundary refinement:** The LLM sometimes classifies mixed queries as entity_multi "
             "(when negatives are present). Fine-tuning the system prompt or adding few-shot examples could improve this.")
    L.append("3. **Theme query embedding quality:** For broad themes like 'horror', the single-keyword embedding "
             "may not capture nuance well. Consider expanding theme queries with related terms before embedding.")
    L.append("4. **Negative filter tuning:** The 0.6 cosine similarity threshold for embedding-based penalties "
             "could be tuned per use case. Comedy penalties may need different thresholds than franchise penalties.")
    L.append("5. **Production considerations:** Replace in-memory Qdrant with persistent storage, add NLU caching, "
             "and implement query-level result caching for repeated searches.")
    L.append("")

    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"\nReport saved to {path}")


# ── Main ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    start = time.time()
    results = run_all()
    elapsed = time.time() - start

    # Save raw JSON
    json_path = os.path.join(RESULTS_DIR, "test_results_v2.json")
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # Serialize — strip non-JSON-serializable fields
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if hasattr(obj, "tolist"):
            return obj.tolist()
        return obj

    with open(json_path, "w") as f:
        json.dump(_clean(results), f, indent=2, default=str)
    print(f"\nRaw results saved to {json_path}")

    analysis = analyze(results)
    generate_report(results, analysis)

    print(f"\nTotal suite runtime: {elapsed:.1f}s")
