"""
Complex test suite + ground truth evaluation for Feeds.ai pipeline.
Runs 20 queries, then evaluates result quality against metadata-based ground truth.
Generates:
  - results/COMPLEX_TEST_RESULTS.md
  - results/QUALITY_EVALUATION.md
  - results/quality_evaluation_data.json
"""

import json
import os
import time
from collections import Counter

from pipeline.vector_store import setup_qdrant
from pipeline.query_engine import process_query, print_results
from pipeline.config import RESULTS_DIR, PROFILES_PATH, COMPOSITIONS_PATH

# ── 20 Test Queries ──────────────────────────────────────────────────

QUERIES = [
    # Single entity — within vertical
    ("Q1", "What games feel like Hollow Knight: Silksong?"),
    ("Q2", "Find me movies that have a similar vibe to Predator: Badlands"),
    ("Q3", "TV shows like Alien: Earth"),
    # Single entity — cross vertical
    ("Q4", "I love the game Vampire: The Masquerade - Bloodlines 2, what movies should I watch?"),
    ("Q5", "I really enjoyed the TV show Devil May Cry, what games would I like?"),
    ("Q6", "Based on the movie Avatar: Fire and Ash, recommend me TV shows and games"),
    # Multi entity — same vertical
    ("Q7", "I love both Code Vein II and Monster Hunter Wilds, find me similar games"),
    ("Q8", "Movies like both Predator: Badlands and The Old Guard 2"),
    # Multi entity — cross vertical
    ("Q9", "I enjoy Resident Evil Requiem and Silent Hill f as games, recommend me movies and TV shows"),
    ("Q10", "Based on Marvel Zombies TV show and Alien: Earth TV show, what games should I play?"),
    ("Q11", "I like the movie In the Lost Lands and the game Crimson Desert, find me TV shows"),
    # Theme and descriptive
    ("Q12", "I want survival horror with psychological elements across all categories"),
    ("Q13", "Find me content about space exploration and alien civilizations"),
    ("Q14", "I enjoy stories with political intrigue and power struggles"),
    ("Q15", "Content that feels like exploring ancient magical ruins and forgotten civilizations"),
    # Mixed with negatives
    ("Q16", "I love Elden Ring Nightreign and dark fantasy but I absolutely hate anything cute or family-friendly, recommend movies"),
    ("Q17", "Games similar to Resident Evil Requiem but nothing like sports or racing games, I want pure horror"),
    ("Q18", "I enjoy Silent Hill f and CyberCorp but hate slow paced content, recommend TV shows and movies"),
    ("Q19", "Based on my love for Monster Hunter Wilds and Crimson Desert, but I dislike sci-fi, find me movies and TV shows"),
    # Edge case — maximum complexity
    ("Q20", "I am a huge fan of Hollow Knight: Silksong, Elden Ring Nightreign, and Code Vein II for games, and I loved Marvel Zombies and Devil May Cry as TV shows. I dont like comedy or family content at all. Based on all of this, recommend me the best movies, games, and TV shows across all categories that match my taste"),
]

# ══════════════════════════════════════════════════════════════════════
# PART 1 — Run queries
# ══════════════════════════════════════════════════════════════════════

def run_all():
    print("Initializing Qdrant + BM25 index...")
    setup_qdrant()

    results = {}
    for qid, query in QUERIES:
        print(f"\n{'─'*60}")
        print(f"{qid}: {query[:80]}...")
        try:
            output = process_query(query)
            print_results(output)
        except Exception as e:
            print(f"  ERROR: {e}")
            output = {
                "query": query, "status": "error", "error": str(e),
                "parsed_intent": {}, "results": [], "results_by_vertical": {},
                "timings": {},
            }
        results[qid] = output

    return results


def generate_complex_results_report(results):
    """Generate results/COMPLEX_TEST_RESULTS.md"""
    path = os.path.join(RESULTS_DIR, "COMPLEX_TEST_RESULTS.md")
    L = ["# Complex Query Test Results", ""]

    for qid, query in QUERIES:
        r = results[qid]
        nlu = r.get("parsed_intent", {})
        t = r.get("timings", {})

        L.append(f"## {qid}: \"{query}\"")
        L.append("")
        L.append(f"**NLU:** mode=`{nlu.get('query_mode')}`, pos=`{nlu.get('positive_entities', [])}`, "
                  f"neg=`{nlu.get('negative_entities', [])}`")
        L.append(f"**Keywords:** `{nlu.get('additional_keywords', [])}` + derived `{nlu.get('description_derived_keywords', [])}`")
        L.append(f"**Verticals:** `{nlu.get('target_verticals', [])}` | type=`{nlu.get('query_type')}`")
        L.append("")

        if r.get("anchor_entities_resolved"):
            L.append(f"**Resolved+:** {', '.join(r['anchor_entities_resolved'])}")
        if r.get("negative_entities_resolved"):
            L.append(f"**Resolved-:** {', '.join(r['negative_entities_resolved'])}")

        neg_log = r.get("neg_filter_log", [])
        if neg_log:
            pen = sum(1 for e in neg_log if e["action"] == "PENALIZED")
            rem = sum(1 for e in neg_log if e["action"] == "REMOVED")
            L.append(f"**Neg filter:** {pen} penalized, {rem} removed")
        L.append("")

        if r.get("status") != "success":
            L.append(f"**ERROR:** {r.get('error')}")
            L.append("")
            continue

        # Results
        if r.get("results_by_vertical"):
            for vert, vres in r["results_by_vertical"].items():
                L.append(f"### {vert.upper()} ({len(vres)} results)")
                L.append("")
                L.append("| # | Name | Final | Vec | BM25 | Both | Keywords |")
                L.append("|---|------|-------|-----|------|------|----------|")
                for res in vres[:10]:
                    both = "Yes" if res.get("in_both_sets") else ""
                    kws = ", ".join(res.get("shared_keywords", [])[:5])
                    L.append(f"| {res['rank']} | {res['name']} | {res['final_score']:.4f} | "
                              f"{res['vector_score']:.4f} | {res['bm25_score']:.4f} | {both} | {kws} |")
                L.append("")
        elif r.get("results"):
            L.append("| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |")
            L.append("|---|------|----------|-------|-----|------|------|----------|")
            for res in r["results"][:10]:
                both = "Yes" if res.get("in_both_sets") else ""
                kws = ", ".join(res.get("shared_keywords", [])[:5])
                L.append(f"| {res['rank']} | {res['name']} | {res['vertical']} | "
                          f"{res['final_score']:.4f} | {res['vector_score']:.4f} | "
                          f"{res['bm25_score']:.4f} | {both} | {kws} |")
            L.append("")

        L.append(f"*Latency: {t.get('total_ms',0):.0f}ms*")
        L.append("")
        L.append("---")
        L.append("")

    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"Results report saved to {path}")


# ══════════════════════════════════════════════════════════════════════
# PART 2 — Ground Truth Evaluation
# ══════════════════════════════════════════════════════════════════════

def load_entity_db():
    """Load full entity database with profiles + compositions merged."""
    with open(PROFILES_PATH) as f:
        profiles = json.load(f)
    with open(COMPOSITIONS_PATH) as f:
        compositions = json.load(f)

    comp_map = {c["entity_id"]: c for c in compositions}
    db = {}
    for p in profiles:
        eid = p["entity_id"]
        c = comp_map.get(eid, {})
        db[eid] = {
            "entity_id": eid,
            "name": p["name"],
            "vertical": p["vertical"],
            "canonical_genres": [g.lower() for g in (p.get("canonical_genres") or [])],
            "themes": [t.lower() for t in (p.get("themes") or [])],
            "keywords": [k.lower() for k in (p.get("keywords") or [])],
            "franchise": (p.get("franchise") or "").lower() or None,
            "developer": (p.get("developer") or "").lower() or None,
            "publisher": (p.get("publisher") or "").lower() or None,
            "bm25_keywords": [k.lower() for k in (c.get("bm25_keywords") or [])],
            "description": p.get("description", ""),
        }
    # Also build name->eid lookup
    name_map = {db[eid]["name"]: eid for eid in db}
    return db, name_map


def compute_ground_truth_score(anchor_entities, candidate, is_theme_query=False, theme_terms=None):
    """
    Compute metadata-based ground truth relevance score.
    For entity queries: compare candidate metadata against anchor entity metadata.
    For theme queries: compare candidate metadata against theme terms.
    """
    score = 0.0

    if is_theme_query and theme_terms:
        terms_set = set(t.lower() for t in theme_terms)
        # Check genres
        for g in candidate["canonical_genres"]:
            if g in terms_set:
                score += 2
        # Check themes
        for t in candidate["themes"]:
            if t in terms_set:
                score += 3
        # Check bm25 keywords
        for k in candidate["bm25_keywords"]:
            if k in terms_set:
                score += 1
        # Check keywords
        for k in candidate["keywords"]:
            if k in terms_set:
                score += 1
        return score

    # Entity-based scoring: aggregate across all anchor entities
    for anchor in anchor_entities:
        # Shared canonical genres: +2 per shared
        shared_genres = set(anchor["canonical_genres"]) & set(candidate["canonical_genres"])
        score += len(shared_genres) * 2

        # Shared themes: +3 per shared
        shared_themes = set(anchor["themes"]) & set(candidate["themes"])
        score += len(shared_themes) * 3

        # Shared keywords: +1 per shared
        shared_kw = set(anchor["keywords"]) & set(candidate["keywords"])
        score += len(shared_kw) * 1

        # Shared bm25 keywords: +1 per shared
        shared_bm25 = set(anchor["bm25_keywords"]) & set(candidate["bm25_keywords"])
        score += len(shared_bm25) * 1

        # Shared franchise: +5
        if anchor["franchise"] and candidate["franchise"] and anchor["franchise"] == candidate["franchise"]:
            score += 5

        # Shared developer: +2
        if anchor["developer"] and candidate["developer"] and anchor["developer"] == candidate["developer"]:
            score += 2

        # Shared publisher: +2
        if anchor["publisher"] and candidate["publisher"] and anchor["publisher"] == candidate["publisher"]:
            score += 2

    return score


def get_ideal_top10(db, anchor_eids, target_verticals, exclude_eids=None,
                    is_theme=False, theme_terms=None):
    """Get the ideal top 10 by ground truth metadata scoring."""
    exclude = set(exclude_eids or [])
    anchor_entities = [db[eid] for eid in anchor_eids if eid in db]
    target_set = set(target_verticals) if target_verticals else None

    scored = []
    for eid, ent in db.items():
        if eid in exclude:
            continue
        if target_set and ent["vertical"] not in target_set:
            continue
        gt_score = compute_ground_truth_score(anchor_entities, ent,
                                               is_theme_query=is_theme,
                                               theme_terms=theme_terms)
        if gt_score > 0:
            scored.append((eid, ent["name"], ent["vertical"], gt_score))

    scored.sort(key=lambda x: x[3], reverse=True)
    return scored[:10]


def evaluate_query(qid, result, db, name_map):
    """Evaluate a single query's results against ground truth."""
    nlu = result.get("parsed_intent", {})
    mode = nlu.get("query_mode", "")
    pos_names = nlu.get("positive_entities", [])
    target_verts = nlu.get("target_verticals", ["game", "movie", "tv"])
    add_kw = nlu.get("additional_keywords", [])
    desc_kw = nlu.get("description_derived_keywords", [])

    # Resolve anchor entity IDs
    anchor_eids = []
    for name in pos_names:
        # Try exact match first, then prefix
        if name in name_map:
            anchor_eids.append(name_map[name])
        else:
            for ename, eid in name_map.items():
                if ename.lower().startswith(name.lower()):
                    anchor_eids.append(eid)
                    break

    # Also check resolved entities from the pipeline output
    if not anchor_eids and result.get("anchor_entities_resolved"):
        for res_str in result["anchor_entities_resolved"]:
            # Parse "Name (vertical) [match_type]"
            ename = res_str.split(" (")[0]
            if ename in name_map:
                anchor_eids.append(name_map[ename])

    anchor_eids = list(set(anchor_eids))

    # Determine if theme query
    is_theme = mode in ("theme_based", "descriptive") or (not anchor_eids)
    theme_terms = add_kw + desc_kw

    # Get ideal results
    ideal = get_ideal_top10(db, anchor_eids, target_verts,
                            exclude_eids=anchor_eids,
                            is_theme=is_theme, theme_terms=theme_terms)

    # Get pipeline results (flatten multi-vertical)
    pipeline_results = []
    if result.get("results"):
        pipeline_results = result["results"][:10]
    elif result.get("results_by_vertical"):
        for vert, vres in result["results_by_vertical"].items():
            pipeline_results.extend(vres[:10])

    # Extract pipeline entity names for comparison
    pipeline_names = set(r["name"] for r in pipeline_results)
    ideal_names = set(name for _, name, _, _ in ideal)

    # Precision@10 and Recall@10
    overlap = pipeline_names & ideal_names
    precision = len(overlap) / len(pipeline_names) if pipeline_names else 0
    recall = len(overlap) / len(ideal_names) if ideal_names else 0

    # Verdict
    overlap_count = len(overlap)
    if overlap_count >= 7:
        verdict = "EXCELLENT"
    elif overlap_count >= 5:
        verdict = "GOOD"
    elif overlap_count >= 3:
        verdict = "FAIR"
    else:
        verdict = "POOR"

    # If no ideal results exist (theme query with no metadata matches), adjust
    if not ideal:
        verdict = "N/A (no metadata-based ideal)"

    # False negatives (in ideal but not pipeline)
    false_negatives = []
    for eid, name, vert, gt_score in ideal:
        if name not in pipeline_names:
            false_negatives.append({"name": name, "vertical": vert, "gt_score": gt_score})

    # False positives (in pipeline but not ideal)
    false_positives = []
    for r in pipeline_results:
        if r["name"] not in ideal_names:
            # Check its actual GT score
            eid_candidates = [eid for eid, ent in db.items() if ent["name"] == r["name"]]
            gt = 0
            if eid_candidates:
                gt = compute_ground_truth_score(
                    [db[a] for a in anchor_eids if a in db],
                    db[eid_candidates[0]],
                    is_theme_query=is_theme, theme_terms=theme_terms
                )
            false_positives.append({
                "name": r["name"], "vertical": r["vertical"],
                "pipeline_score": r["final_score"], "gt_score": gt,
            })

    return {
        "qid": qid,
        "query": result["query"],
        "mode": mode,
        "anchor_count": len(anchor_eids),
        "is_theme": is_theme,
        "ideal_top10": [{"name": n, "vertical": v, "gt_score": s} for _, n, v, s in ideal],
        "pipeline_top10": [{"name": r["name"], "vertical": r["vertical"],
                            "pipeline_score": r["final_score"]} for r in pipeline_results[:10]],
        "overlap_names": sorted(overlap),
        "overlap_count": overlap_count,
        "precision_at_10": round(precision, 3),
        "recall_at_10": round(recall, 3),
        "verdict": verdict,
        "false_negatives": false_negatives,
        "false_positives": false_positives,
    }


def run_evaluation(results):
    """Run ground truth evaluation for all queries."""
    db, name_map = load_entity_db()
    evaluations = {}

    for qid, query in QUERIES:
        r = results.get(qid, {})
        if r.get("status") == "error" or (not r.get("results") and not r.get("results_by_vertical")):
            evaluations[qid] = {
                "qid": qid, "query": query, "verdict": "FAILED",
                "error": r.get("error", "no results"),
                "overlap_count": 0, "precision_at_10": 0, "recall_at_10": 0,
                "ideal_top10": [], "pipeline_top10": [],
                "false_negatives": [], "false_positives": [],
                "overlap_names": [], "mode": r.get("parsed_intent", {}).get("query_mode", ""),
            }
            continue

        ev = evaluate_query(qid, r, db, name_map)
        evaluations[qid] = ev

    return evaluations, db, name_map


def generate_quality_report(evaluations, db, name_map):
    """Generate results/QUALITY_EVALUATION.md"""
    path = os.path.join(RESULTS_DIR, "QUALITY_EVALUATION.md")
    L = ["# Ground Truth Quality Evaluation", ""]

    # ── Section 1: Per-query evaluation ──
    L.append("## Section 1 — Per-Query Evaluation")
    L.append("")

    verdicts = Counter()
    all_precisions = []
    all_recalls = []

    for qid, _ in QUERIES:
        ev = evaluations[qid]
        verdicts[ev["verdict"]] += 1

        if ev["verdict"] == "FAILED":
            L.append(f"### {qid}: \"{ev.get('query', '')[:70]}\"")
            L.append(f"**FAILED**: {ev.get('error', 'unknown')}")
            L.append("")
            continue

        all_precisions.append(ev["precision_at_10"])
        all_recalls.append(ev["recall_at_10"])

        L.append(f"### {qid}: \"{ev['query'][:70]}\"")
        L.append(f"**Mode:** `{ev['mode']}` | **Verdict: {ev['verdict']}** | "
                  f"Overlap: {ev['overlap_count']}/10 | "
                  f"P@10={ev['precision_at_10']:.1%} | R@10={ev['recall_at_10']:.1%}")
        L.append("")

        # Side-by-side comparison
        L.append("| # | Pipeline Result | P.Score | Ideal Result | GT Score | Match |")
        L.append("|---|--------------- |---------|------------- |----------|-------|")
        for i in range(max(len(ev["pipeline_top10"]), len(ev["ideal_top10"]))):
            p_name = ev["pipeline_top10"][i]["name"] if i < len(ev["pipeline_top10"]) else "—"
            p_score = f"{ev['pipeline_top10'][i]['pipeline_score']:.4f}" if i < len(ev["pipeline_top10"]) else "—"
            i_name = ev["ideal_top10"][i]["name"] if i < len(ev["ideal_top10"]) else "—"
            i_score = f"{ev['ideal_top10'][i]['gt_score']:.0f}" if i < len(ev["ideal_top10"]) else "—"
            match = "Yes" if p_name in ev["overlap_names"] else ""
            L.append(f"| {i+1} | {p_name} | {p_score} | {i_name} | {i_score} | {match} |")
        L.append("")

        if ev["false_negatives"]:
            L.append(f"**Missed (in ideal, not in pipeline):** "
                      + ", ".join(f"{fn['name']} (gt={fn['gt_score']:.0f})" for fn in ev["false_negatives"][:5]))
        if ev["false_positives"]:
            fp_low = [fp for fp in ev["false_positives"] if fp["gt_score"] == 0]
            if fp_low:
                L.append(f"**No metadata overlap:** "
                          + ", ".join(f"{fp['name']}" for fp in fp_low[:5]))
        L.append("")

    # ── Section 2: Aggregate scores ──
    L.append("---")
    L.append("")
    L.append("## Section 2 — Aggregate Scores")
    L.append("")
    L.append("### Verdict Distribution")
    L.append("")
    L.append("| Verdict | Count |")
    L.append("|---------|-------|")
    for v in ["EXCELLENT", "GOOD", "FAIR", "POOR", "N/A (no metadata-based ideal)", "FAILED"]:
        if verdicts[v]:
            L.append(f"| {v} | {verdicts[v]} |")
    L.append("")

    if all_precisions:
        avg_p = sum(all_precisions) / len(all_precisions)
        avg_r = sum(all_recalls) / len(all_recalls)
        L.append(f"- **Average Precision@10:** {avg_p:.1%}")
        L.append(f"- **Average Recall@10:** {avg_r:.1%}")
        L.append(f"- **Queries evaluated:** {len(all_precisions)} (excluding failures)")
    L.append("")

    # ── Section 3: Systematic analysis ──
    L.append("---")
    L.append("")
    L.append("## Section 3 — Systematic Analysis")
    L.append("")

    # Frequently missed entities (appear in ideal but not pipeline across multiple queries)
    missed_counts = Counter()
    for ev in evaluations.values():
        for fn in ev.get("false_negatives", []):
            missed_counts[fn["name"]] += 1

    if missed_counts:
        L.append("### Frequently Missed Entities (in ideal but not pipeline)")
        L.append("")
        L.append("| Entity | Times Missed | Likely Cause |")
        L.append("|--------|-------------|-------------|")
        for name, count in missed_counts.most_common(15):
            cause = "Low embedding similarity despite metadata overlap"
            L.append(f"| {name} | {count} | {cause} |")
        L.append("")

    # Frequently recommended without metadata support
    over_ranked = Counter()
    for ev in evaluations.values():
        for fp in ev.get("false_positives", []):
            if fp["gt_score"] == 0:
                over_ranked[fp["name"]] += 1

    if over_ranked:
        L.append("### Frequently Over-Ranked (no metadata overlap)")
        L.append("")
        L.append("| Entity | Times Over-Ranked | Likely Cause |")
        L.append("|--------|------------------|-------------|")
        for name, count in over_ranked.most_common(10):
            cause = "High embedding similarity from composition text, but metadata doesn't overlap"
            L.append(f"| {name} | {count} | {cause} |")
        L.append("")

    # Genre/theme performance
    L.append("### Performance by Query Type")
    L.append("")
    type_stats = {}
    for ev in evaluations.values():
        mode = ev.get("mode", "unknown")
        if ev["verdict"] == "FAILED":
            continue
        if mode not in type_stats:
            type_stats[mode] = {"precisions": [], "recalls": [], "verdicts": []}
        type_stats[mode]["precisions"].append(ev["precision_at_10"])
        type_stats[mode]["recalls"].append(ev["recall_at_10"])
        type_stats[mode]["verdicts"].append(ev["verdict"])

    L.append("| Mode | Queries | Avg P@10 | Avg R@10 | Verdicts |")
    L.append("|------|---------|----------|----------|----------|")
    for mode, stats in sorted(type_stats.items()):
        n = len(stats["precisions"])
        avg_p = sum(stats["precisions"]) / n if n else 0
        avg_r = sum(stats["recalls"]) / n if n else 0
        v_dist = dict(Counter(stats["verdicts"]))
        L.append(f"| {mode} | {n} | {avg_p:.1%} | {avg_r:.1%} | {v_dist} |")
    L.append("")

    # ── Section 4: False Negative Analysis ──
    L.append("---")
    L.append("")
    L.append("## Section 4 — False Negative Analysis")
    L.append("")
    L.append("These entities had high metadata overlap with query anchors but were not returned by the pipeline.")
    L.append("")

    # Detailed analysis of top missed entities
    all_fn = []
    for qid, _ in QUERIES:
        ev = evaluations[qid]
        for fn in ev.get("false_negatives", []):
            all_fn.append({"qid": qid, **fn})

    if all_fn:
        L.append("| Query | Missed Entity | Vertical | GT Score | Likely Reason |")
        L.append("|-------|-------------- |----------|----------|---------------|")
        seen = set()
        for fn in sorted(all_fn, key=lambda x: x["gt_score"], reverse=True)[:25]:
            key = (fn["qid"], fn["name"])
            if key in seen:
                continue
            seen.add(key)
            reason = "Embedding captures experiential essence rather than metadata attributes"
            if fn["gt_score"] <= 4:
                reason = "Low metadata score — borderline relevance"
            L.append(f"| {fn['qid']} | {fn['name']} | {fn['vertical']} | "
                      f"{fn['gt_score']:.0f} | {reason} |")
        L.append("")

    L.append("### Why Pipeline Misses High-Metadata Entities")
    L.append("")
    L.append("The pipeline uses **experiential embeddings** (based on 180-word compositions describing how "
             "content *feels*) rather than metadata matching. This creates a deliberate tradeoff:")
    L.append("")
    L.append("- **Embedding advantage:** Captures subjective similarity — two entities can feel alike despite "
             "having different genres/themes in metadata (e.g., a horror game and a thriller movie)")
    L.append("- **Metadata advantage:** Captures objective overlap — shared genres, developers, and franchises "
             "are strong signals that metadata catches but embeddings may miss")
    L.append("- **BM25 bridge:** The keyword search partially bridges this gap by matching genre terms directly")
    L.append("")

    # ── Section 5: Recommendations ──
    L.append("---")
    L.append("")
    L.append("## Section 5 — Recommendations for Improvement")
    L.append("")

    L.append("### 5.1 Scoring Weight Adjustments")
    L.append("- The current 0.7 vector / 0.3 BM25 split favors experiential similarity over metadata matching")
    L.append("- Consider testing 0.6/0.4 or 0.5/0.5 to give BM25 keywords more influence, especially for "
             "within-vertical queries where genre matching matters more")
    L.append("")

    L.append("### 5.2 Metadata-Augmented Retrieval")
    L.append("- Add a third retrieval signal: direct metadata overlap scoring (genre + theme + franchise)")
    L.append("- Weight: 0.5 vector + 0.25 BM25 + 0.25 metadata")
    L.append("- This would capture entities that the ground truth identifies as relevant but embeddings miss")
    L.append("")

    L.append("### 5.3 Composition Improvements")
    L.append("- Entities whose compositions don't reflect their genre metadata well will have low embedding "
             "similarity despite high metadata overlap")
    L.append("- Consider appending genre/theme tags to compositions before embedding, or generating a "
             "secondary 'genre-focused' embedding per entity")
    L.append("")

    L.append("### 5.4 Franchise and Developer Boosting")
    L.append("- Only 119/1,757 entities have franchise data — enriching this would improve franchise-based boosting")
    L.append("- Developer/publisher matches are a strong signal for game recommendations but are currently unused in scoring")
    L.append("")

    L.append("### 5.5 Hybrid Ideal Metric")
    L.append("- The ground truth metric here is purely metadata-based, which penalizes the pipeline for making "
             "subjectively good recommendations that don't share metadata tags")
    L.append("- A better evaluation would combine metadata overlap + human relevance judgments")
    L.append("")

    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"Quality evaluation saved to {path}")


# ══════════════════════════════════════════════════════════════════════
# Main
# ══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    os.makedirs(RESULTS_DIR, exist_ok=True)
    start = time.time()

    # Part 1: Run queries
    results = run_all()

    # Part 1: Generate results report
    generate_complex_results_report(results)

    # Part 2: Ground truth evaluation
    evaluations, db, name_map = run_evaluation(results)

    # Part 2: Generate quality report
    generate_quality_report(evaluations, db, name_map)

    # Save raw data
    def _clean(obj):
        if isinstance(obj, dict):
            return {k: _clean(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [_clean(v) for v in obj]
        if hasattr(obj, "tolist"):
            return obj.tolist()
        return obj

    json_path = os.path.join(RESULTS_DIR, "quality_evaluation_data.json")
    with open(json_path, "w") as f:
        json.dump(_clean(evaluations), f, indent=2, default=str)
    print(f"Raw evaluation data saved to {json_path}")

    elapsed = time.time() - start
    print(f"\nTotal runtime: {elapsed:.1f}s")
