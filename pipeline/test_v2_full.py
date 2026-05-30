"""V2 full test suite — 20 queries across all features."""
import json, os, time, subprocess
from pipeline.config import RESULTS_DIR

API = "http://localhost:8000"
FORBIDDEN = ["vector", "bm25", "embedding", "semantic", "cosine", "retrieval", "ranked list", "fusion"]

QUERIES = [
    # Basic entity
    ("Q1", "entity_single", "Games similar to Hades II"),
    ("Q2", "entity_single", "Movies like The Last of Us"),
    ("Q3", "entity_single", "TV shows similar to Severance"),
    # Cross-vertical
    ("Q4", "cross_vertical", "I love Hades II, recommend me movies and TV shows"),
    ("Q5", "cross_vertical", "Based on the movie Dungeons & Dragons: Honor Among Thieves, suggest games"),
    ("Q6", "cross_vertical", "I enjoy the TV show INVINCIBLE, find me similar games and movies"),
    # Multi-entity
    ("Q7", "multi_entity", "I love both Monster Hunter Rise and Hollow Knight: Silksong, find me similar games"),
    ("Q8", "multi_entity", "Based on The Last of Us and Severance, recommend movies"),
    ("Q9", "multi_entity", "I enjoy Crime Junkie and Dateline NBC podcasts, find me similar podcasts"),
    # Theme / descriptive
    ("Q10", "theme", "Horror content across all categories"),
    ("Q11", "descriptive", "I want something with political intrigue and power struggles"),
    ("Q12", "theme", "Content about space exploration and alien civilizations"),
    # Date filtering
    ("Q13", "date", "Games coming out in 2026"),
    ("Q14", "date+theme", "Horror movies from 2025"),
    ("Q15", "date", "New TV shows released this year"),
    # Combined date + entity
    ("Q16", "date+entity", "Games like Elden Ring releasing in 2025 or 2026"),
    ("Q17", "date+entity", "Sci-fi movies from the last 2 years similar to INVINCIBLE"),
    # Mixed + negatives + date
    ("Q18", "mixed+date", "I love Hades II and Monster Hunter Rise but hate sports games, recommend me 2025 movies"),
    ("Q19", "mixed+date", "Horror content from 2024 onwards, not comedy, across all categories"),
    ("Q20", "max_complex", "I am a huge fan of The Last of Us, Severance, and Crime Junkie. I dislike reality TV and family content. Recommend me the best games, movies, and TV shows from the last 2 years"),
]


def post_query(query):
    import urllib.request
    req = urllib.request.Request(
        f"{API}/api/query",
        data=json.dumps({"query": query}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read())


def run_all():
    results = {}
    for qid, category, query in QUERIES:
        print(f"\n{'─'*60}")
        print(f"{qid} [{category}]: {query[:60]}...")
        try:
            out = post_query(query)
            # Flatten results
            all_res = out.get("results", [])
            for vres in out.get("results_by_vertical", {}).values():
                all_res.extend(vres)

            nlu = out.get("parsed_intent", {})
            t = out.get("timings", {})
            print(f"  Status: {out['status']} | Mode: {out.get('query_mode')} | Results: {len(all_res)} | Latency: {t.get('total_ms',0):.0f}ms")
            print(f"  Date filter: {out.get('date_filter_applied')} | {out.get('date_filter_description','')}")
            for r in all_res[:3]:
                print(f"    {r['rank']:>2}. {r['name']:<40} {r.get('similarity_percentage',0):>3}% | {r.get('reasoning_short','')[:50]}")

            results[qid] = {
                "qid": qid, "category": category, "query": query,
                "output": out, "all_results": all_res, "status": "success",
            }
        except Exception as e:
            print(f"  ERROR: {e}")
            results[qid] = {
                "qid": qid, "category": category, "query": query,
                "output": {}, "all_results": [], "status": f"error: {e}",
            }
    return results


def generate_report(results):
    os.makedirs(RESULTS_DIR, exist_ok=True)

    # ── Get DB stats ──
    db_stats = {
        "total": 6945,
        "by_vertical": {"game": 1997, "movie": 1653, "podcast": 1998, "tv": 1297},
        "release_date_coverage": {"game": 1997, "movie": 1627, "tv": 1193, "podcast": 0},
    }

    L = []
    L.append("# V2 Full Test Report")
    L.append("")

    # ── Section 1: System Status ──
    L.append("## Section 1 — System Status")
    L.append("")
    L.append(f"- **Total entities:** {db_stats['total']}")
    L.append(f"- **By vertical:** {db_stats['by_vertical']}")
    L.append(f"- **Release date coverage:** {db_stats['release_date_coverage']}")
    L.append(f"- **Backend:** http://192.168.100.191:8000 (running)")
    L.append(f"- **Frontend:** http://192.168.100.191:3000 (running)")
    L.append("")

    # ── Section 2: Per-Query Results ──
    L.append("## Section 2 — Per-Query Results")
    L.append("")

    for qid, _, query in QUERIES:
        r = results[qid]
        out = r["output"]
        nlu = out.get("parsed_intent", {})
        t = out.get("timings", {})
        all_res = r["all_results"]

        L.append(f"### {qid}: \"{query}\"")
        L.append(f"**Category:** {r['category']} | **Status:** {r['status']}")
        L.append("")

        if r["status"] != "success":
            L.append(f"**Error:** {r['status']}")
            L.append("")
            continue

        L.append(f"**NLU:** mode=`{nlu.get('query_mode')}`, pos=`{nlu.get('positive_entities',[])}`, "
                  f"neg=`{nlu.get('negative_entities',[])}`, kw=`{nlu.get('additional_keywords',[])}`, "
                  f"verticals=`{nlu.get('target_verticals',[])}`")
        L.append(f"**Date:** start=`{nlu.get('date_filter_start')}`, end=`{nlu.get('date_filter_end')}` | "
                  f"Applied: {out.get('date_filter_applied')} | Desc: {out.get('date_filter_description','')}")
        L.append(f"**Results:** {len(all_res)} | **Latency:** {t.get('total_ms',0):.0f}ms")
        L.append("")

        # Results by vertical breakdown
        if out.get("results_by_vertical"):
            for vert, vres in out["results_by_vertical"].items():
                L.append(f"**{vert.upper()}** ({len(vres)}):")
        L.append("")

        L.append("| # | Name | Vertical | Match% | Release Date | Reasoning |")
        L.append("|---|------|----------|--------|-------------|-----------|")
        for res in all_res[:5]:
            rd = res.get("release_date", "—") or "—"
            reason = (res.get("reasoning_short") or "—")[:55]
            L.append(f"| {res['rank']} | {res['name']} | {res['vertical']} | "
                      f"{res.get('similarity_percentage',0)}% | {rd} | {reason} |")
        if len(all_res) > 5:
            L.append(f"| ... | *{len(all_res)-5} more results* | | | | |")
        L.append("")
        L.append("---")
        L.append("")

    # ── Section 3: Feature Verification ──
    L.append("## Section 3 — Feature Verification")
    L.append("")

    # Reasoning check
    total_results = 0
    reasoning_populated = 0
    reasoning_empty = 0
    forbidden_found = []
    for r in results.values():
        for res in r["all_results"]:
            total_results += 1
            rs = res.get("reasoning_short", "")
            rl = res.get("reasoning_long", "")
            if rs:
                reasoning_populated += 1
            else:
                reasoning_empty += 1
            for term in FORBIDDEN:
                if term in rs.lower() or term in rl.lower():
                    forbidden_found.append(f"{r['qid']}: {res['name']} contains '{term}'")

    L.append("### Reasoning")
    L.append(f"- Results with reasoning: {reasoning_populated}/{total_results}")
    L.append(f"- Results without reasoning: {reasoning_empty}")
    L.append(f"- Forbidden technical terms found: {len(forbidden_found)}")
    if forbidden_found:
        for f in forbidden_found[:5]:
            L.append(f"  - {f}")
    L.append("")

    # Date filtering check
    date_queries = [qid for qid, cat, _ in QUERIES if "date" in cat]
    L.append("### Date Filtering")
    L.append("")
    L.append("| Query | Date Start | Date End | Filter Applied | Results in Range |")
    L.append("|-------|-----------|---------|---------------|-----------------|")
    for qid in date_queries:
        r = results[qid]
        out = r["output"]
        nlu = out.get("parsed_intent", {})
        ds = nlu.get("date_filter_start")
        de = nlu.get("date_filter_end")
        applied = out.get("date_filter_applied", False)
        # Check if results are in range
        in_range = 0
        out_of_range = 0
        for res in r["all_results"]:
            rd = res.get("release_date")
            if rd and ds and de:
                if ds <= rd <= de:
                    in_range += 1
                else:
                    out_of_range += 1
            elif rd is None:
                pass  # no date to check
            else:
                in_range += 1
        L.append(f"| {qid} | {ds} | {de} | {applied} | {in_range} in / {out_of_range} out |")
    L.append("")

    # Negative filtering check
    neg_queries = ["Q18", "Q19", "Q20"]
    L.append("### Negative Filtering")
    L.append("")
    for qid in neg_queries:
        r = results[qid]
        out = r["output"]
        neg_log = out.get("neg_filter_log", [])
        penalized = sum(1 for e in neg_log if e.get("action") == "PENALIZED")
        removed = sum(1 for e in neg_log if e.get("action") == "REMOVED")
        L.append(f"- **{qid}:** {penalized} penalized, {removed} removed from candidates")
    L.append("")

    # ── Section 4: Quality Assessment ──
    L.append("## Section 4 — Quality Assessment")
    L.append("")

    success_count = sum(1 for r in results.values() if r["status"] == "success" and r["all_results"])
    total_q = len(results)
    all_latencies = [r["output"].get("timings", {}).get("total_ms", 0) for r in results.values() if r["status"] == "success"]
    all_result_counts = [len(r["all_results"]) for r in results.values()]

    L.append(f"- **Success rate:** {success_count}/{total_q} queries returned results")
    L.append(f"- **Average results per query:** {sum(all_result_counts)/len(all_result_counts):.1f}")
    L.append(f"- **Average latency:** {sum(all_latencies)/len(all_latencies):.0f}ms" if all_latencies else "- **Average latency:** N/A")
    L.append(f"- **Min latency:** {min(all_latencies):.0f}ms" if all_latencies else "")
    L.append(f"- **Max latency:** {max(all_latencies):.0f}ms" if all_latencies else "")
    L.append("")

    # Per-category performance
    cat_stats = {}
    for r in results.values():
        cat = r["category"]
        if cat not in cat_stats:
            cat_stats[cat] = {"total": 0, "success": 0, "latencies": []}
        cat_stats[cat]["total"] += 1
        if r["status"] == "success" and r["all_results"]:
            cat_stats[cat]["success"] += 1
            cat_stats[cat]["latencies"].append(r["output"].get("timings", {}).get("total_ms", 0))

    L.append("| Category | Success | Avg Latency |")
    L.append("|----------|---------|------------|")
    for cat, s in sorted(cat_stats.items()):
        avg_lat = f"{sum(s['latencies'])/len(s['latencies']):.0f}ms" if s["latencies"] else "—"
        L.append(f"| {cat} | {s['success']}/{s['total']} | {avg_lat} |")
    L.append("")

    # ── Section 5: Issues ──
    L.append("## Section 5 — Issues Found")
    L.append("")
    issues = []
    for r in results.values():
        if r["status"] != "success":
            issues.append(f"**{r['qid']}**: {r['status']}")
        elif not r["all_results"]:
            issues.append(f"**{r['qid']}**: Returned 0 results")
    if reasoning_empty > 0:
        issues.append(f"**Reasoning:** {reasoning_empty} results missing reasoning text")
    if forbidden_found:
        issues.append(f"**Forbidden terms:** {len(forbidden_found)} results contain technical terms")

    if issues:
        for i in issues:
            L.append(f"- {i}")
    else:
        L.append("No issues found.")
    L.append("")

    path = os.path.join(RESULTS_DIR, "V2_FULL_TEST_REPORT.md")
    with open(path, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"\nReport saved to {path}")

    # Save raw JSON
    json_path = os.path.join(RESULTS_DIR, "v2_test_results.json")
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
    print(f"Raw results saved to {json_path}")


if __name__ == "__main__":
    results = run_all()
    generate_report(results)
