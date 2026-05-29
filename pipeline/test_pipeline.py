"""
Test the full query pipeline with 3 queries and generate PIPELINE_REPORT.md.
"""

import json
import os
import time

from pipeline.vector_store import setup_qdrant
from pipeline.query_engine import process_query, print_results
from pipeline.config import RESULTS_DIR


TEST_QUERIES = [
    "What games are like Elden Ring Nightreign?",
    "Movies similar to Star Wars: The Mandalorian and Grogu",
    "Find me TV shows similar to Resident Evil",
]


def run_tests():
    """Run all test queries and return results."""
    print("Initializing Qdrant + BM25 index...")
    setup_qdrant()

    all_results = []
    for query in TEST_QUERIES:
        output = process_query(query)
        print_results(output)
        all_results.append(output)

    return all_results


def generate_report(all_results):
    """Generate results/PIPELINE_REPORT.md."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, "PIPELINE_REPORT.md")

    lines = [
        "# Pipeline Test Report",
        "",
        "## Architecture",
        "",
        "| Module | Role |",
        "|--------|------|",
        "| `nlu.py` | Groq LLM function calling to parse user query into structured intent |",
        "| `retrieval.py` | Entity resolution + dual retrieval (vector + BM25) + hybrid merge |",
        "| `reranker.py` | Franchise boost, self-exclusion, diversity enforcement |",
        "| `query_engine.py` | Orchestrator: NLU -> Retrieval -> Rerank -> formatted output |",
        "",
    ]

    for i, output in enumerate(all_results, 1):
        p = output["parsed_intent"]
        lines.extend([
            f"---",
            f"",
            f"## Query {i}: \"{output['query']}\"",
            f"",
            f"### NLU Output",
            f"```json",
            json.dumps(p, indent=2),
            f"```",
            f"",
        ])

        if isinstance(output.get("anchor_entity_found"), dict):
            a = output["anchor_entity_found"]
            lines.extend([
                f"### Entity Resolution",
                f"- **Resolved:** {a['name']} ({a['vertical']}) [{a['match_type']} match]",
                f"",
            ])
        else:
            lines.extend([
                f"### Entity Resolution",
                f"- **Error:** {output.get('error', 'Not found')}",
                f"",
            ])
            continue

        d = output.get("debug", {})

        # Vector search top 5
        lines.extend([
            f"### Vector Search (top 5 before merge)",
            f"| Name | Vertical | Score |",
            f"|------|----------|-------|",
        ])
        for name, vert, score in d.get("vec_top5", []):
            lines.append(f"| {name} | {vert} | {score} |")

        lines.append("")

        # BM25 top 5
        lines.extend([
            f"### BM25 Search (top 5 before merge)",
            f"| Name | Vertical | Score |",
            f"|------|----------|-------|",
        ])
        for name, vert, score in d.get("bm25_top5", []):
            lines.append(f"| {name} | {vert} | {score} |")

        lines.append("")

        # Final results
        lines.extend([
            f"### Final Ranked Results (top 10)",
            f"| Rank | Name | Vertical | Final | Vector | BM25 | Both Sets | Shared Keywords |",
            f"|------|------|----------|-------|--------|------|-----------|-----------------|",
        ])
        for r in output["results"]:
            both = "Yes" if r["in_both_sets"] else ""
            kws = ", ".join(r["shared_keywords"][:5]) if r["shared_keywords"] else ""
            lines.append(
                f"| {r['rank']} | {r['name']} | {r['vertical']} | "
                f"{r['final_score']:.4f} | {r['vector_score']:.4f} | {r['bm25_score']:.4f} | "
                f"{both} | {kws} |"
            )

        lines.append("")

        # Timings
        t = output["timings"]
        lines.extend([
            f"### Latency",
            f"| Stage | Time |",
            f"|-------|------|",
            f"| NLU | {t['nlu_ms']:.0f} ms |",
            f"| Retrieval (resolve + vector + BM25 + merge) | {t['retrieval_ms']:.0f} ms |",
            f"| Reranking | {t['rerank_ms']:.0f} ms |",
            f"| **Total** | **{t['total_ms']:.0f} ms** |",
            f"",
            f"### Stats",
            f"- Vector results: {d.get('vec_results_count', 0)}",
            f"- BM25 results: {d.get('bm25_results_count', 0)}",
            f"- Merged candidates: {d.get('merged_count', 0)}",
            f"- Dual-signal candidates: {d.get('dual_signal_count', 0)}",
            f"",
        ])

    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    results = run_tests()
    generate_report(results)
