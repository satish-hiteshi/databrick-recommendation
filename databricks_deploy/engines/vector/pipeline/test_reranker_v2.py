"""
Test the full chain: NLU → Retrieval → Negative Filter → Reranker (v2).
Generates results/RERANKER_V2_TEST.md.
"""

import json
import os
import time

from pipeline.vector_store import setup_qdrant
from pipeline.nlu import parse_query
from pipeline.retrieval import retrieve
from pipeline.negative_filter import apply_negative_filter
from pipeline.reranker import rerank
from pipeline.config import RESULTS_DIR

TEST_QUERIES = [
    ("Games like Elden Ring Nightreign", "entity_single, no negatives"),
    ("Love Elden Ring and Dark Souls, but hate Star Wars, recommend movies", "entity_multi + negative"),
    ("Horror content, not comedy, across all categories", "theme + negative keyword"),
]


def run_tests():
    print("Initializing Qdrant + BM25 index...")
    setup_qdrant()

    results = []
    for query, desc in TEST_QUERIES:
        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print(f"Description: {desc}")
        print(f"{'='*70}")

        # NLU
        t0 = time.time()
        nlu = parse_query(query)
        nlu_ms = (time.time() - t0) * 1000
        print(f"\nNLU ({nlu_ms:.0f}ms):")
        print(f"  mode={nlu['query_mode']}, pos={nlu['positive_entities']}, "
              f"neg={nlu['negative_entities']}")
        print(f"  add_kw={nlu['additional_keywords']}, desc_kw={nlu['description_derived_keywords']}")
        print(f"  verticals={nlu['target_verticals']}, type={nlu['query_type']}")

        # Retrieval
        t0 = time.time()
        ret = retrieve(nlu)
        retrieval_ms = (time.time() - t0) * 1000
        cands = ret["candidates"]
        print(f"\nRetrieval ({retrieval_ms:.0f}ms): {len(cands)} candidates")
        print(f"  Resolved positive: {[e['name'] for e in ret['resolved_positive']]}")
        print(f"  Resolved negative: {[e['name'] for e in ret['resolved_negative']]}")
        if ret.get("unresolved_neg_keywords"):
            print(f"  Unresolved neg keywords: {ret['unresolved_neg_keywords']}")
        print(f"\n  Top 15 (pre-filter):")
        for i, c in enumerate(cands[:15], 1):
            print(f"    {i:>2}. {c['name']:<40} {c['vertical']:<6} "
                  f"combined={c['combined_score']:.4f} vec={c['vector_score']:.4f} "
                  f"bm25={c['bm25_score']:.4f} srcs={c['appeared_in_searches']}")

        # Negative filter
        t0 = time.time()
        filtered, neg_log = apply_negative_filter(
            cands, ret["resolved_negative"], ret.get("unresolved_neg_keywords", [])
        )
        filter_ms = (time.time() - t0) * 1000
        print(f"\nNegative Filter ({filter_ms:.0f}ms):")
        if neg_log:
            for entry in neg_log:
                print(f"  {entry['action']}: {entry['name']} — {entry['reason']}")
                if entry["action"] == "PENALIZED":
                    print(f"    score: {entry['original_score']:.4f} → {entry['new_score']:.4f} "
                          f"(penalty={entry['penalty']:.4f})")
        else:
            print("  No negative entities to filter (or none resolved)")
        print(f"  Candidates: {len(cands)} → {len(filtered)}")

        # Reranker
        t0 = time.time()
        reranked = rerank(filtered, ret["resolved_positive"], nlu, nlu["query_mode"])
        rerank_ms = (time.time() - t0) * 1000
        rdebug = reranked["debug"]
        print(f"\nReranker ({rerank_ms:.0f}ms):")
        if rdebug.get("self_excluded"):
            print(f"  Self-excluded: {rdebug['self_excluded']}")
        if rdebug.get("franchise_boosted"):
            print(f"  Franchise boosted: {rdebug['franchise_boosted']}")
        if rdebug.get("keyword_boosted"):
            for name, boost in rdebug["keyword_boosted"][:5]:
                print(f"  Keyword boosted: {name} +{boost}")
        if rdebug.get("franchise_capped"):
            for name, f in rdebug["franchise_capped"]:
                print(f"  Franchise capped: {name} ({f})")

        # Print final results
        if reranked.get("split_by_vertical"):
            print(f"\n  Final Results (per-vertical):")
            for vert, vresults in reranked["results"].items():
                print(f"\n  [{vert.upper()}] ({len(vresults)} results):")
                _print_results(vresults)
        else:
            print(f"\n  Final Results (top 10):")
            _print_results(reranked["results"])

        total_ms = nlu_ms + retrieval_ms + filter_ms + rerank_ms
        print(f"\n  Total: {total_ms:.0f}ms (NLU={nlu_ms:.0f} + retrieval={retrieval_ms:.0f} "
              f"+ filter={filter_ms:.0f} + rerank={rerank_ms:.0f})")

        results.append({
            "query": query,
            "description": desc,
            "nlu": nlu,
            "retrieval_count": len(cands),
            "retrieval_top15": [_cand_dict(c) for c in cands[:15]],
            "neg_log": neg_log,
            "filter_count": len(filtered),
            "reranked": reranked,
            "resolved_pos": [{"name": e["name"], "vertical": e["vertical"], "match_type": e["match_type"]}
                             for e in ret["resolved_positive"]],
            "resolved_neg": [{"name": e["name"], "vertical": e["vertical"], "match_type": e["match_type"]}
                             for e in ret["resolved_negative"]],
            "unresolved_neg_kw": ret.get("unresolved_neg_keywords", []),
            "timings": {
                "nlu_ms": round(nlu_ms, 1),
                "retrieval_ms": round(retrieval_ms, 1),
                "filter_ms": round(filter_ms, 1),
                "rerank_ms": round(rerank_ms, 1),
                "total_ms": round(nlu_ms + retrieval_ms + filter_ms + rerank_ms, 1),
            },
        })

    return results


def _print_results(results):
    for i, c in enumerate(results[:10], 1):
        kw_str = ", ".join(c.get("shared_keywords", [])[:4])
        adj = c.get("adjustments", {})
        adj_str = " ".join(f"{k}={v}" for k, v in adj.items()) if adj else ""
        print(f"    {i:>2}. {c['name']:<40} {c['vertical']:<6} "
              f"final={c['final_score']:.4f} combined={c['combined_score']:.4f} "
              f"neg_pen={c.get('negative_penalty', 0):.4f} {adj_str}")
        if kw_str:
            print(f"        kw: {kw_str}")


def _cand_dict(c):
    return {
        "name": c["name"],
        "vertical": c["vertical"],
        "combined_score": round(c["combined_score"], 4),
        "vector_score": round(c["vector_score"], 4),
        "bm25_score": round(c["bm25_score"], 4),
        "appeared_in_searches": c["appeared_in_searches"],
    }


def generate_report(results):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, "RERANKER_V2_TEST.md")

    lines = [
        "# Reranker v2 Test Report",
        "",
        "Full chain: NLU → Retrieval → Negative Filter → Reranker",
        "",
    ]

    for idx, r in enumerate(results, 1):
        nlu = r["nlu"]
        t = r["timings"]

        lines.extend([
            "---",
            "",
            f"## Q{idx}: \"{r['query']}\"",
            f"*{r['description']}*",
            "",
            "### NLU Output",
            f"- mode: `{nlu['query_mode']}`",
            f"- positive_entities: `{nlu['positive_entities']}`",
            f"- negative_entities: `{nlu['negative_entities']}`",
            f"- additional_keywords: `{nlu['additional_keywords']}`",
            f"- description_derived_keywords: `{nlu['description_derived_keywords']}`",
            f"- target_verticals: `{nlu['target_verticals']}`",
            f"- query_type: `{nlu['query_type']}`",
            "",
            "### Entity Resolution",
            "",
        ])

        if r["resolved_pos"]:
            lines.append("**Positive:**")
            for e in r["resolved_pos"]:
                lines.append(f"- {e['name']} ({e['vertical']}) [{e['match_type']}]")
        if r["resolved_neg"]:
            lines.append("\n**Negative (resolved):**")
            for e in r["resolved_neg"]:
                lines.append(f"- {e['name']} ({e['vertical']}) [{e['match_type']}]")
        if r.get("unresolved_neg_kw"):
            lines.append(f"\n**Negative (keyword-only, unresolved):** {r['unresolved_neg_kw']}")
        lines.append("")

        # Retrieval top 15
        lines.extend([
            f"### Retrieval — {r['retrieval_count']} candidates (top 15)",
            "",
            "| # | Name | Vertical | Combined | Vector | BM25 | Sources |",
            "|---|------|----------|----------|--------|------|---------|",
        ])
        for i, c in enumerate(r["retrieval_top15"], 1):
            lines.append(f"| {i} | {c['name']} | {c['vertical']} | "
                         f"{c['combined_score']:.4f} | {c['vector_score']:.4f} | "
                         f"{c['bm25_score']:.4f} | {c['appeared_in_searches']} |")
        lines.append("")

        # Negative filter
        lines.extend([
            f"### Negative Filter ({r['retrieval_count']} → {r['filter_count']} candidates)",
            "",
        ])
        if r["neg_log"]:
            lines.append("| Entity | Action | Reason | Score Change |")
            lines.append("|--------|--------|--------|-------------|")
            for entry in r["neg_log"]:
                if entry["action"] == "REMOVED":
                    change = f"{entry['original_score']:.4f} → removed"
                else:
                    change = f"{entry['original_score']:.4f} → {entry['new_score']:.4f} (-{entry['penalty']:.4f})"
                lines.append(f"| {entry['name']} | {entry['action']} | {entry['reason'][:60]} | {change} |")
        else:
            lines.append("*No negative filtering applied.*")
        lines.append("")

        # Reranked results
        reranked = r["reranked"]
        rdebug = reranked["debug"]

        lines.append("### Reranker Adjustments")
        lines.append("")
        if rdebug.get("self_excluded"):
            lines.append(f"- **Self-excluded:** {', '.join(rdebug['self_excluded'])}")
        if rdebug.get("franchise_boosted"):
            lines.append(f"- **Franchise boosted:** {', '.join(rdebug['franchise_boosted'])}")
        if rdebug.get("keyword_boosted"):
            kw_strs = [f"{n} (+{b})" for n, b in rdebug["keyword_boosted"][:8]]
            lines.append(f"- **Keyword boosted:** {', '.join(kw_strs)}")
        if rdebug.get("franchise_capped"):
            lines.append(f"- **Franchise capped:** {', '.join(n for n, f in rdebug['franchise_capped'])}")
        lines.append("")

        # Final results
        if reranked.get("split_by_vertical"):
            for vert, vresults in reranked["results"].items():
                lines.extend([
                    f"### Final Results — {vert.upper()} ({len(vresults)} results)",
                    "",
                    "| Rank | Name | Final | Combined | Neg Penalty | Adjustments | Keywords |",
                    "|------|------|-------|----------|-------------|-------------|----------|",
                ])
                for i, c in enumerate(vresults[:10], 1):
                    adj = " ".join(f"{k}={v}" for k, v in c.get("adjustments", {}).items())
                    kws = ", ".join(c.get("shared_keywords", [])[:4])
                    lines.append(
                        f"| {i} | {c['name']} | {c['final_score']:.4f} | "
                        f"{c['combined_score']:.4f} | {c.get('negative_penalty', 0):.4f} | "
                        f"{adj} | {kws} |"
                    )
                lines.append("")
        else:
            final = reranked["results"]
            lines.extend([
                f"### Final Results — Top 10 ({len(final)} results)",
                "",
                "| Rank | Name | Vertical | Final | Combined | Neg Penalty | Adjustments | Keywords |",
                "|------|------|----------|-------|----------|-------------|-------------|----------|",
            ])
            for i, c in enumerate(final[:10], 1):
                adj = " ".join(f"{k}={v}" for k, v in c.get("adjustments", {}).items())
                kws = ", ".join(c.get("shared_keywords", [])[:4])
                lines.append(
                    f"| {i} | {c['name']} | {c['vertical']} | {c['final_score']:.4f} | "
                    f"{c['combined_score']:.4f} | {c.get('negative_penalty', 0):.4f} | "
                    f"{adj} | {kws} |"
                )
            lines.append("")

        lines.extend([
            f"### Latency",
            f"NLU {t['nlu_ms']:.0f}ms + Retrieval {t['retrieval_ms']:.0f}ms + "
            f"Filter {t['filter_ms']:.0f}ms + Rerank {t['rerank_ms']:.0f}ms = "
            f"**{t['total_ms']:.0f}ms**",
            "",
        ])

    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    results = run_tests()
    generate_report(results)
