"""
Test the NLU v2 with 10 queries and generate NLU_V2_TEST.md report.
"""

import json
import os

from pipeline.nlu import parse_query
from pipeline.config import RESULTS_DIR

TEST_CASES = [
    ("Games like Elden Ring", "entity_single"),
    ("I love Elden Ring and Dark Souls, recommend movies", "entity_multi"),
    ("Horror content across all categories", "theme_based"),
    ("I like content with country wars and gun fighting", "descriptive"),
    ("Love Elden Ring but hate Star Wars, want dark fantasy movies", "mixed"),
    ("Movies for someone who loved Resident Evil and Silent Hill games", "entity_multi"),
    ("Recommend me sci-fi", "theme_based"),
    ("I enjoy slow-burn psychological tension with unreliable narrators", "descriptive"),
    ("Games and movies similar to Marvel Zombies", "entity_single"),
    ("I liked Stranger Things and Alien Earth but didn't enjoy comedy shows, recommend games", "mixed"),
]


def run_tests():
    results = []
    for query, expected_mode in TEST_CASES:
        print(f"\n{'─'*60}")
        print(f"Query: {query}")
        print(f"Expected mode: {expected_mode}")
        try:
            parsed = parse_query(query)
            correct = parsed["query_mode"] == expected_mode
            print(f"  query_mode:       {parsed['query_mode']} {'OK' if correct else 'MISMATCH (expected: ' + expected_mode + ')'}")
            print(f"  positive_entities: {parsed['positive_entities']}")
            print(f"  negative_entities: {parsed['negative_entities']}")
            print(f"  additional_kw:    {parsed['additional_keywords']}")
            print(f"  derived_kw:       {parsed['description_derived_keywords']}")
            print(f"  target_verticals: {parsed['target_verticals']}")
            print(f"  query_type:       {parsed['query_type']}")
            results.append({
                "query": query,
                "expected_mode": expected_mode,
                "parsed": parsed,
                "mode_correct": correct,
                "status": "success",
            })
        except Exception as e:
            print(f"  ERROR: {e}")
            results.append({
                "query": query,
                "expected_mode": expected_mode,
                "parsed": {},
                "mode_correct": False,
                "status": f"error: {e}",
            })
    return results


def generate_report(results):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, "NLU_V2_TEST.md")

    correct = sum(1 for r in results if r["mode_correct"])
    total = len(results)
    errors = sum(1 for r in results if r["status"] != "success")

    lines = [
        "# NLU v2 Test Report",
        "",
        "## Summary",
        f"- **Query mode classification accuracy:** {correct}/{total} ({correct/total*100:.0f}%)",
        f"- **Errors:** {errors}",
        "",
        "## Detailed Results",
        "",
    ]

    for i, r in enumerate(results, 1):
        p = r.get("parsed", {})
        mode_label = "CORRECT" if r["mode_correct"] else "WRONG"
        if r["status"] != "success":
            mode_label = "ERROR"

        lines.extend([
            f"### Q{i}: \"{r['query']}\"",
            "",
            f"**Expected mode:** `{r['expected_mode']}` | **Got:** `{p.get('query_mode', 'N/A')}` | **{mode_label}**",
            "",
            "```json",
            json.dumps({
                "query_mode": p.get("query_mode"),
                "positive_entities": p.get("positive_entities", []),
                "negative_entities": p.get("negative_entities", []),
                "additional_keywords": p.get("additional_keywords", []),
                "description_derived_keywords": p.get("description_derived_keywords", []),
                "target_verticals": p.get("target_verticals", []),
                "query_type": p.get("query_type"),
            }, indent=2),
            "```",
            "",
            "**Assessment:**",
        ])

        # Per-query assessment
        if r["status"] != "success":
            lines.append(f"- Error: {r['status']}")
        else:
            # Check specific field quality
            notes = []
            if p.get("positive_entities"):
                notes.append(f"Positive entities extracted: {p['positive_entities']}")
            if p.get("negative_entities"):
                notes.append(f"Negative entities extracted: {p['negative_entities']}")
            if p.get("additional_keywords"):
                notes.append(f"Keywords: {p['additional_keywords']}")
            if p.get("description_derived_keywords"):
                notes.append(f"Derived keywords: {p['description_derived_keywords']}")
            notes.append(f"Verticals: {p.get('target_verticals', [])}, Type: {p.get('query_type', 'N/A')}")
            for note in notes:
                lines.append(f"- {note}")

        lines.append("")

    # Classification matrix
    lines.extend([
        "## Classification Summary",
        "",
        "| # | Query (abbreviated) | Expected | Got | Match |",
        "|---|-------------------|----------|-----|-------|",
    ])
    for i, r in enumerate(results, 1):
        p = r.get("parsed", {})
        q_short = r["query"][:50] + ("..." if len(r["query"]) > 50 else "")
        got = p.get("query_mode", "ERROR")
        match = "Yes" if r["mode_correct"] else "No"
        lines.append(f"| {i} | {q_short} | {r['expected_mode']} | {got} | {match} |")
    lines.append("")

    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport saved to {report_path}")
    return report_path


if __name__ == "__main__":
    results = run_tests()
    generate_report(results)
