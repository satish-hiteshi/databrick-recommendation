"""
One-command setup: PostgreSQL + Qdrant + BM25.
Run with: python -m pipeline.setup_all
"""

import os
import time

from pipeline.config import RESULTS_DIR
from pipeline.database_setup import setup_postgres
from pipeline.entity_resolver import resolve_entity
from pipeline.vector_store import setup_qdrant, vector_search, keyword_search
from pipeline.embedding_generator import load_embeddings
from pipeline.data_loader import get_entity_by_name


def validate_postgres():
    """Test entity resolution against PostgreSQL."""
    print("\n=== PostgreSQL Validation ===")
    test_cases = [
        ("Elden Ring Nightreign", "exact"),
        ("elden ring nightreign", "exact (lowercase)"),
        ("Silent Hill", "prefix"),
        ("doom", "prefix (lowercase)"),
        ("Paw Patrol", "contains"),
    ]
    results = []
    for name, expected_type in test_cases:
        r = resolve_entity(name)
        if r:
            print(f"  '{name}' -> {r['name']} [{r['match_type']}] "
                  f"emb_dim={len(r['embedding']) if r['embedding'] is not None else 0} "
                  f"kw_count={len(r['bm25_keywords'])}")
            results.append((name, r["name"], r["match_type"],
                          len(r["embedding"]) if r["embedding"] is not None else 0,
                          len(r["bm25_keywords"])))
        else:
            print(f"  '{name}' -> NOT FOUND")
            results.append((name, "NOT FOUND", "none", 0, 0))
    return results


def validate_qdrant():
    """Test vector search and keyword search against Qdrant."""
    print("\n=== Qdrant Validation ===")

    # Use Elden Ring Nightreign's embedding for a test search
    r = resolve_entity("Elden Ring Nightreign")
    if not r or r["embedding"] is None:
        print("  Cannot test: Elden Ring Nightreign not found.")
        return [], []

    # Vector search (all verticals)
    print("\n  Vector search (Elden Ring Nightreign, all verticals, top 5):")
    vec_results = vector_search(r["embedding"], top_k=5)
    for eid, name, vert, score in vec_results:
        print(f"    {score:.4f}  {name} ({vert})")

    # Vector search (movies only)
    print("\n  Vector search (Elden Ring Nightreign, movies only, top 5):")
    vec_movies = vector_search(r["embedding"], target_verticals={"movie"}, top_k=5)
    for eid, name, vert, score in vec_movies:
        print(f"    {score:.4f}  {name} ({vert})")

    # Keyword search
    print(f"\n  BM25 keyword search (keywords: {r['bm25_keywords'][:5]}..., top 5):")
    kw_results = keyword_search(r["bm25_keywords"], top_k=5)
    for eid, name, vert, score in kw_results:
        print(f"    {score:.4f}  {name} ({vert})")

    return vec_results, kw_results


def generate_report(pg_results, vec_results, kw_results, elapsed):
    """Write results/STORAGE_REPORT.md."""
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, "STORAGE_REPORT.md")

    lines = [
        "# Storage Setup Report",
        "",
        f"**Total setup time:** {elapsed:.1f} seconds",
        "",
        "## PostgreSQL",
        "",
        "### Entity Resolution Tests",
        "| Search Term | Resolved Name | Match Type | Emb Dim | Keywords |",
        "|-------------|--------------|------------|---------|----------|",
    ]
    for search, name, match_type, emb_dim, kw_count in pg_results:
        lines.append(f"| {search} | {name} | {match_type} | {emb_dim} | {kw_count} |")

    lines.extend([
        "",
        "## Qdrant",
        "",
        "### Vector Search — Elden Ring Nightreign (top 5)",
        "| Name | Vertical | Score |",
        "|------|----------|-------|",
    ])
    for eid, name, vert, score in vec_results[:5]:
        lines.append(f"| {name} | {vert} | {score:.4f} |")

    lines.extend([
        "",
        "### BM25 Keyword Search — Elden Ring Nightreign (top 5)",
        "| Name | Vertical | Score |",
        "|------|----------|-------|",
    ])
    for eid, name, vert, score in kw_results[:5]:
        lines.append(f"| {name} | {vert} | {score:.4f} |")

    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    start = time.time()

    # Step 1: PostgreSQL
    print("=" * 60)
    print("STEP 1: PostgreSQL Setup")
    print("=" * 60)
    setup_postgres()

    # Step 2: Qdrant + BM25
    print("\n" + "=" * 60)
    print("STEP 2: Qdrant + BM25 Setup")
    print("=" * 60)
    setup_qdrant()

    elapsed = time.time() - start

    # Step 3: Validate
    print("\n" + "=" * 60)
    print("STEP 3: Validation")
    print("=" * 60)
    pg_results = validate_postgres()
    vec_results, kw_results = validate_qdrant()

    # Step 4: Report
    generate_report(pg_results, vec_results, kw_results, elapsed)

    print(f"\nAll setup complete in {elapsed:.1f}s.")
