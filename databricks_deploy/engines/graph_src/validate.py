"""Validate the loaded Feeds.ai graph and print a report.

Reports node counts by label, relationship counts by type, entity counts by
vertical, rich sample entities, the most common genres/themes, a cross-vertical
shared-attribute check (verticals attached to Genre 'Horror'), and a full-text
query against the entityText index. Also writes results/load_validation.json.

Run:  ./.venv/bin/python src/validate.py
"""

import json
from pathlib import Path

from connection import get_driver, NEO4J_DATABASE

_ROOT = Path(__file__).resolve().parent.parent
OUT = _ROOT / "results" / "load_validation.json"

NODE_LABELS = ["Entity", "Genre", "Theme", "Keyword", "Franchise", "Developer", "Publisher"]
REL_TYPES = ["HAS_GENRE", "HAS_THEME", "HAS_KEYWORD", "IN_FRANCHISE", "DEVELOPED_BY", "PUBLISHED_BY"]

SAMPLE_CYPHER = """
MATCH (e:Entity {vertical: $v})
WITH e, size([(e)-[:HAS_GENRE]->(:Genre) | 1])
       + size([(e)-[:HAS_THEME]->(:Theme) | 1])
       + size([(e)-[:HAS_KEYWORD]->(:Keyword) | 1]) AS deg
ORDER BY deg DESC LIMIT 1
RETURN e.entity_id AS entity_id, e.name AS name, e.vertical AS vertical,
       e.word_count AS word_count, size(e.bm25_keywords) AS bm25_kw_count,
       [(e)-[:HAS_GENRE]->(g)   | g.name] AS genres,
       [(e)-[:HAS_THEME]->(t)   | t.name] AS themes,
       [(e)-[:HAS_KEYWORD]->(k) | k.name][..6] AS keywords_sample,
       [(e)-[:IN_FRANCHISE]->(f) | f.name][0] AS franchise,
       [(e)-[:DEVELOPED_BY]->(d) | d.name][0] AS developer,
       [(e)-[:PUBLISHED_BY]->(p) | p.name][0] AS publisher
"""


def main():
    driver = get_driver()
    report = {}
    try:
        with driver.session(database=NEO4J_DATABASE) as s:
            # 1. Node counts by label
            node_counts = {
                lbl: s.run(f"MATCH (n:{lbl}) RETURN count(n) AS c").single()["c"]
                for lbl in NODE_LABELS
            }
            # 2. Relationship counts by type
            rel_counts = {
                rt: s.run(f"MATCH ()-[r:{rt}]->() RETURN count(r) AS c").single()["c"]
                for rt in REL_TYPES
            }
            # 3. Entity counts by vertical
            vert_counts = {
                r["vertical"]: r["c"] for r in s.run(
                    "MATCH (e:Entity) RETURN e.vertical AS vertical, count(*) AS c "
                    "ORDER BY c DESC"
                )
            }
            # 4. Sample entities (richest per vertical)
            samples = [s.run(SAMPLE_CYPHER, v=v).single().data()
                       for v in ["game", "movie", "tv", "podcast"]]
            # 5. Most common genres / themes
            top_genres = [r.data() for r in s.run(
                "MATCH (g:Genre)<-[:HAS_GENRE]-(:Entity) "
                "RETURN g.name AS name, count(*) AS c ORDER BY c DESC LIMIT 10")]
            top_themes = [r.data() for r in s.run(
                "MATCH (t:Theme)<-[:HAS_THEME]-(:Entity) "
                "RETURN t.name AS name, count(*) AS c ORDER BY c DESC LIMIT 10")]
            # 6. Cross-vertical shared-node check: Horror
            horror = s.run(
                "MATCH (g:Genre {name:'Horror'})<-[:HAS_GENRE]-(e:Entity) "
                "RETURN count(e) AS entities, count(DISTINCT e.vertical) AS verticals, "
                "collect(DISTINCT e.vertical) AS which").single().data()
            horror_by_vert = {r["v"]: r["c"] for r in s.run(
                "MATCH (g:Genre {name:'Horror'})<-[:HAS_GENRE]-(e:Entity) "
                "RETURN e.vertical AS v, count(*) AS c ORDER BY c DESC")}
            horror["by_vertical"] = horror_by_vert
            # 7. Full-text query
            ft = [r.data() for r in s.run(
                "CALL db.index.fulltext.queryNodes('entityText', 'survival') "
                "YIELD node, score "
                "RETURN node.name AS name, node.vertical AS vertical, "
                "round(score, 4) AS score ORDER BY score DESC LIMIT 5")]
    finally:
        driver.close()

    report = {
        "node_counts": node_counts,
        "relationship_counts": rel_counts,
        "entity_by_vertical": vert_counts,
        "sample_entities": samples,
        "top_genres": top_genres,
        "top_themes": top_themes,
        "cross_vertical_horror": horror,
        "fulltext_survival_top5": ft,
    }
    OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # ---- console report ----
    print("=== NODE COUNTS BY LABEL ===")
    for k, v in node_counts.items():
        print(f"  {k:10}: {v:,}")
    print(f"  TOTAL nodes: {sum(node_counts.values()):,}")
    print("\n=== RELATIONSHIP COUNTS BY TYPE ===")
    for k, v in rel_counts.items():
        print(f"  {k:13}: {v:,}")
    print(f"  TOTAL rels: {sum(rel_counts.values()):,}")
    print("\n=== ENTITY COUNTS BY VERTICAL ===")
    for k, v in vert_counts.items():
        print(f"  {k:8}: {v:,}")
    print("\n=== SAMPLE ENTITIES (richest per vertical) ===")
    for sm in samples:
        print(f"  [{sm['vertical']}] {sm['name']} ({sm['entity_id']})  "
              f"wc={sm['word_count']} bm25={sm['bm25_kw_count']}")
        print(f"      genres={sm['genres']}")
        print(f"      themes={sm['themes']}")
        print(f"      keywords[:6]={sm['keywords_sample']}")
        print(f"      franchise={sm['franchise']} | developer={sm['developer']} "
              f"| publisher={sm['publisher']}")
    print("\n=== TOP GENRES ===")
    for g in top_genres:
        print(f"  {g['name']:24} {g['c']:,}")
    print("\n=== TOP THEMES ===")
    for t in top_themes:
        print(f"  {t['name']:24} {t['c']:,}")
    print("\n=== CROSS-VERTICAL CHECK: Genre 'Horror' ===")
    print(f"  entities={horror['entities']}, distinct verticals={horror['verticals']} "
          f"{horror['which']}")
    print(f"  by vertical: {horror['by_vertical']}")
    print("\n=== FULL-TEXT: queryNodes('entityText','survival') top 5 ===")
    for r in ft:
        print(f"  {r['score']:>8}  [{r['vertical']}] {r['name']}")
    print(f"\nReport written -> {OUT.relative_to(_ROOT)}")


if __name__ == "__main__":
    main()
