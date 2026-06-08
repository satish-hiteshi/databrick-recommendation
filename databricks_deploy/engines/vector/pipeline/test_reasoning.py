"""
Test reasoning engine across all 5 query modes.
Generates results/REASONING_TEST.md and results/REASONING_REPORT.md
"""

import json
import os
import re
from collections import Counter

from pipeline.vector_store import setup_qdrant
from pipeline.query_engine import process_query
from pipeline.config import RESULTS_DIR
from pipeline.reasoning import TEMPLATES

FORBIDDEN = ["vector", "bm25", "embedding", "semantic", "cosine", "similarity score",
             "retrieval", "ranked list", "fusion"]

QUERIES = [
    ("entity_single", "Games like Elden Ring Nightreign"),
    ("entity_multi", "I love Elden Ring and Nioh 3, recommend movies"),
    ("theme_based", "Horror content across all categories"),
    ("descriptive", "I like content with country wars and gun fighting"),
    ("max_complexity",
     "I am a huge fan of Hollow Knight: Silksong, Elden Ring Nightreign, and Code Vein II "
     "for games, and I loved Marvel Zombies and Devil May Cry as TV shows. I dont like comedy "
     "or family content at all. Based on all of this, recommend me the best movies, games, "
     "and TV shows across all categories that match my taste"),
]


def run_tests():
    print("Initializing...")
    setup_qdrant()

    all_results = []
    for mode_label, query in QUERIES:
        print(f"\n{'='*60}")
        print(f"[{mode_label}] {query[:70]}...")
        output = process_query(query)

        # Collect all results (flat + by-vertical)
        results = output.get("results", [])
        for vres in output.get("results_by_vertical", {}).values():
            results.extend(vres)

        print(f"  {len(results)} results")
        for r in results:
            short = r.get("reasoning_short", "")
            long_ = r.get("reasoning_long", "")
            print(f"  {r['rank']:>2}. {r['name']:<35} | {short}")

        all_results.append({
            "mode": mode_label,
            "query": query,
            "output": output,
            "results": results,
        })

    return all_results


def validate(all_results):
    issues = []
    template_usage = Counter()
    per_query_templates = []

    for entry in all_results:
        query_templates = set()
        for r in entry["results"]:
            short = r.get("reasoning_short", "")
            long_ = r.get("reasoning_long", "")

            # Check for forbidden terms
            for term in FORBIDDEN:
                if term in short.lower() or term in long_.lower():
                    issues.append(f"FORBIDDEN TERM '{term}' in {entry['mode']}: {r['name']} — \"{short}\"")

            # Check length
            if len(short) > 80:
                issues.append(f"SHORT TOO LONG ({len(short)} chars) in {entry['mode']}: {r['name']}")

            # Track template usage
            template_usage[short] += 1
            query_templates.add(short)

        # Check for duplicates within this query
        total = len(entry["results"])
        unique = len(query_templates)
        if unique < total:
            issues.append(f"DUPLICATE templates in {entry['mode']}: {total - unique} repeats out of {total}")

        per_query_templates.append({
            "mode": entry["mode"],
            "total": total,
            "unique": unique,
            "duplicates": total - unique,
        })

    return issues, template_usage, per_query_templates


def generate_reports(all_results, issues, template_usage, per_query_templates):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # ── REASONING_TEST.md ──
    test_path = os.path.join(RESULTS_DIR, "REASONING_TEST.md")
    L = ["# Reasoning Engine Test Results", ""]

    for entry in all_results:
        L.append(f"## [{entry['mode']}] \"{entry['query'][:70]}\"")
        L.append("")
        L.append(f"**Mode:** `{entry['output'].get('query_mode', '')}`")
        L.append("")

        if entry["output"].get("results"):
            L.append("| # | Name | Vertical | Reasoning |")
            L.append("|---|------|----------|-----------|")
            for r in entry["output"]["results"]:
                L.append(f"| {r['rank']} | {r['name']} | {r['vertical']} | {r.get('reasoning_short', '')} |")
            L.append("")

        for vert, vres in entry["output"].get("results_by_vertical", {}).items():
            L.append(f"### {vert.upper()}")
            L.append("")
            L.append("| # | Name | Reasoning |")
            L.append("|---|------|-----------|")
            for r in vres:
                L.append(f"| {r['rank']} | {r['name']} | {r.get('reasoning_short', '')} |")
            L.append("")

        L.append("**Detail (reasoning_long):**")
        L.append("")
        for r in entry["results"]:
            L.append(f"- **{r['name']}:** {r.get('reasoning_long', '')}")
        L.append("")
        L.append("---")
        L.append("")

    with open(test_path, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"\nTest results saved to {test_path}")

    # ── REASONING_REPORT.md ──
    report_path = os.path.join(RESULTS_DIR, "REASONING_REPORT.md")
    R = ["# Reasoning Engine Report", ""]

    # Template pool stats
    R.append("## Template Pool")
    R.append("")
    R.append("| Category | Count |")
    R.append("|----------|-------|")
    total_templates = 0
    for cat, tmpls in sorted(TEMPLATES.items()):
        R.append(f"| {cat} | {len(tmpls)} |")
        total_templates += len(tmpls)
    R.append(f"| **Total** | **{total_templates}** |")
    R.append("")

    # Per-query template dedup
    R.append("## Template Uniqueness per Query")
    R.append("")
    R.append("| Mode | Total Results | Unique Templates | Duplicates |")
    R.append("|------|--------------|-----------------|------------|")
    for pq in per_query_templates:
        R.append(f"| {pq['mode']} | {pq['total']} | {pq['unique']} | {pq['duplicates']} |")
    R.append("")

    # Issues
    R.append("## Validation Issues")
    R.append("")
    if issues:
        for issue in issues:
            R.append(f"- {issue}")
    else:
        R.append("No issues found.")
    R.append("")

    # Most used templates
    R.append("## Most Used Templates (across all queries)")
    R.append("")
    R.append("| Template | Uses |")
    R.append("|----------|------|")
    for tmpl, count in template_usage.most_common(10):
        R.append(f"| {tmpl[:60]}... | {count} |")
    R.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(R) + "\n")
    print(f"Report saved to {report_path}")


if __name__ == "__main__":
    results = run_tests()
    issues, usage, per_query = validate(results)
    generate_reports(results, issues, usage, per_query)

    if issues:
        print(f"\n{len(issues)} ISSUES FOUND:")
        for i in issues:
            print(f"  - {i}")
    else:
        print("\nAll validations passed.")
