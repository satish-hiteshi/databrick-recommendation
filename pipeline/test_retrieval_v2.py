"""
Test retrieval v2 with 5 queries covering all query modes.
Generates results/RETRIEVAL_V2_TEST.md.
"""

import json
import os
import time

from pipeline.vector_store import setup_qdrant
from pipeline.nlu import parse_query
from pipeline.retrieval import retrieve
from pipeline.config import RESULTS_DIR

TEST_QUERIES = [
    ("Games like Elden Ring Nightreign", "entity_single"),
    ("I love Elden Ring and Nioh 3, recommend movies", "entity_multi"),
    ("Horror content across all categories", "theme_based"),
    ("I like content with country wars and gun fighting", "descriptive"),
    ("Love Resident Evil and Silent Hill, hate comedy, want dark intense TV shows", "mixed"),
]


def run_tests():
    print("Initializing Qdrant + BM25 index...")
    setup_qdrant()

    results = []
    for query, expected_mode in TEST_QUERIES:
        print(f"\n{'='*70}")
        print(f"Query: {query}")
        print(f"Expected mode: {expected_mode}")
        print(f"{'='*70}")

        t0 = time.time()
        nlu = parse_query(query)
        nlu_ms = (time.time() - t0) * 1000

        t0 = time.time()
        ret = retrieve(nlu)
        retrieval_ms = (time.time() - t0) * 1000

        mode = nlu["query_mode"]
        print(f"\n  NLU mode: {mode} ({'OK' if mode == expected_mode else 'MISMATCH'})")
        print(f"  positive_entities: {nlu['positive_entities']}")
        print(f"  negative_entities: {nlu['negative_entities']}")
        print(f"  additional_keywords: {nlu['additional_keywords']}")
        print(f"  derived_keywords: {nlu['description_derived_keywords']}")
        print(f"  target_verticals: {nlu['target_verticals']}")

        # Show resolved entities
        print(f"\n  Resolved positive entities:")
        for e in ret["resolved_positive"]:
            print(f"    {e['name']} ({e['vertical']}) [{e['match_type']}] "
                  f"emb={'yes' if e['embedding'] is not None else 'no'}")
        if ret["resolved_negative"]:
            print(f"  Resolved negative entities:")
            for e in ret["resolved_negative"]:
                print(f"    {e['name']} ({e['vertical']}) [{e['match_type']}]")

        # Show per-source debug
        for dbg in ret["debug"]:
            if "error" in dbg:
                print(f"\n  ERROR: {dbg['error']}")
                continue
            print(f"\n  Source: {dbg['source']}")
            print(f"    Vector top 5:")
            for n, v, s in dbg.get("vec_top5", []):
                print(f"      {s}  {n} ({v})")
            print(f"    BM25 top 5:")
            for n, v, s in dbg.get("bm25_top5", []):
                print(f"      {s}  {n} ({v})")

        # Show merged top 10
        cands = ret["candidates"][:10]
        print(f"\n  Merged top 10 (of {len(ret['candidates'])} candidates):")
        print(f"  {'Rank':<5} {'Name':<40} {'Vert':<6} {'Combined':<9} {'Vec':<7} {'BM25':<7} {'Srcs':<5} {'Dual'}")
        print(f"  {'-'*5} {'-'*40} {'-'*6} {'-'*9} {'-'*7} {'-'*7} {'-'*5} {'-'*4}")
        for i, c in enumerate(cands, 1):
            dual = "*" if c["in_vector"] and c["in_bm25"] else ""
            print(f"  {i:<5} {c['name']:<40} {c['vertical']:<6} "
                  f"{c['combined_score']:<9.4f} {c['vector_score']:<7.4f} "
                  f"{c['bm25_score']:<7.4f} {c['appeared_in_searches']:<5} {dual}")

        print(f"\n  Timing: NLU={nlu_ms:.0f}ms, retrieval={retrieval_ms:.0f}ms")

        results.append({
            "query": query,
            "expected_mode": expected_mode,
            "nlu": nlu,
            "retrieval": {
                "query_mode": ret["query_mode"],
                "candidate_count": len(ret["candidates"]),
                "top10": [
                    {
                        "name": c["name"],
                        "vertical": c["vertical"],
                        "combined_score": round(c["combined_score"], 4),
                        "vector_score": round(c["vector_score"], 4),
                        "bm25_score": round(c["bm25_score"], 4),
                        "appeared_in_searches": c["appeared_in_searches"],
                        "dual_signal": c["in_vector"] and c["in_bm25"],
                    }
                    for c in cands
                ],
                "resolved_pos": [
                    {"name": e["name"], "vertical": e["vertical"], "match_type": e["match_type"]}
                    for e in ret["resolved_positive"]
                ],
                "resolved_neg": [
                    {"name": e["name"], "vertical": e["vertical"], "match_type": e["match_type"]}
                    for e in ret["resolved_negative"]
                ],
                "debug": ret["debug"],
            },
            "nlu_ms": round(nlu_ms, 1),
            "retrieval_ms": round(retrieval_ms, 1),
        })

    return results


def generate_report(results):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, "RETRIEVAL_V2_TEST.md")

    lines = [
        "# Retrieval v2 Test Report",
        "",
        "## Summary",
        "",
        f"- Queries tested: {len(results)}",
        f"- Modes covered: {', '.join(r['expected_mode'] for r in results)}",
        "",
    ]

    for i, r in enumerate(results, 1):
        nlu = r["nlu"]
        ret = r["retrieval"]

        lines.extend([
            "---",
            "",
            f"## Q{i}: \"{r['query']}\"",
            "",
            f"**Expected mode:** `{r['expected_mode']}` | **Got:** `{nlu['query_mode']}`",
            "",
            "### NLU Output",
            f"- positive_entities: `{nlu['positive_entities']}`",
            f"- negative_entities: `{nlu['negative_entities']}`",
            f"- additional_keywords: `{nlu['additional_keywords']}`",
            f"- description_derived_keywords: `{nlu['description_derived_keywords']}`",
            f"- target_verticals: `{nlu['target_verticals']}`",
            "",
            "### Entity Resolution (SQL)",
            "",
        ])

        if ret["resolved_pos"]:
            lines.append("| Entity | Vertical | Match Type |")
            lines.append("|--------|----------|------------|")
            for e in ret["resolved_pos"]:
                lines.append(f"| {e['name']} | {e['vertical']} | {e['match_type']} |")
        else:
            lines.append("*No entities resolved (theme/descriptive mode)*")

        if ret["resolved_neg"]:
            lines.extend(["", "**Negative entities (for filtering):**"])
            for e in ret["resolved_neg"]:
                lines.append(f"- {e['name']} ({e['vertical']}) [{e['match_type']}]")

        lines.append("")

        # Per-source debug
        for dbg in ret["debug"]:
            if "error" in dbg:
                lines.append(f"**Error:** {dbg['error']}")
                continue
            lines.extend([
                f"### Search Source: `{dbg['source']}`",
                "",
                "**Vector top 5:**",
                "| Name | Vertical | Score |",
                "|------|----------|-------|",
            ])
            for n, v, s in dbg.get("vec_top5", []):
                lines.append(f"| {n} | {v} | {s} |")
            lines.extend([
                "",
                "**BM25 top 5:**",
                "| Name | Vertical | Score |",
                "|------|----------|-------|",
            ])
            for n, v, s in dbg.get("bm25_top5", []):
                lines.append(f"| {n} | {v} | {s} |")
            lines.append("")

        # Merged results
        lines.extend([
            f"### Merged Results (top 10 of {ret['candidate_count']})",
            "",
            "| Rank | Name | Vertical | Combined | Vector | BM25 | Sources | Dual |",
            "|------|------|----------|----------|--------|------|---------|------|",
        ])
        for j, c in enumerate(ret["top10"], 1):
            dual = "Yes" if c["dual_signal"] else ""
            lines.append(
                f"| {j} | {c['name']} | {c['vertical']} | "
                f"{c['combined_score']:.4f} | {c['vector_score']:.4f} | "
                f"{c['bm25_score']:.4f} | {c['appeared_in_searches']} | {dual} |"
            )

        lines.extend([
            "",
            f"*Timing: NLU {r['nlu_ms']:.0f}ms, retrieval {r['retrieval_ms']:.0f}ms*",
            "",
        ])

    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    results = run_tests()
    generate_report(results)
