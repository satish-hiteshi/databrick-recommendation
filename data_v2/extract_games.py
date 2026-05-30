#!/usr/bin/env python3
"""Entity profile extraction for Feeds.ai V2 — IGDB Games (2,000 selected)."""

import csv
import json
import sys
import os
from collections import defaultdict, Counter
from datetime import datetime

csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.abspath(__file__))


def parse_props(row):
    try:
        return json.loads(row["properties"])
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════
# TASK 1: VERIFY IGDB_GAME DESCRIPTIONS
# ═══════════════════════════════════════════════════════════════════
print("=" * 60)
print("TASK 1: VERIFY IGDB_GAME DESCRIPTIONS")
print("=" * 60)

print("\nLoading source_entities_igdb_v2.csv...")
all_games = []
with open(os.path.join(BASE, "source_entities_igdb_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        if row["node_type"] == "IGDB_Game":
            props = parse_props(row)
            all_games.append({"id": row["id"], "props": props})

total_rows = len(all_games)
print(f"  Total IGDB_Game rows: {total_rows}")

# Analyze descriptions
has_desc_field = 0
has_nonempty_desc = 0  # > 10 chars
has_critic = 0
has_user = 0
has_both_ratings = 0
has_either_rating = 0
sample_with_desc = []

for g in all_games:
    p = g["props"]
    desc = p.get("description", "")
    cr = p.get("critic_rating")
    ur = p.get("user_rating")

    if "description" in p:
        has_desc_field += 1
    if desc and len(desc.strip()) > 10:
        has_nonempty_desc += 1
        if len(sample_with_desc) < 3:
            sample_with_desc.append(p)
    if cr is not None:
        has_critic += 1
    if ur is not None:
        has_user += 1
    if cr is not None and ur is not None:
        has_both_ratings += 1
    if cr is not None or ur is not None:
        has_either_rating += 1

print(f"\n--- TASK 1 RESULTS ---")
print(f"  Total rows:                   {total_rows:,}")
print(f"  Have 'description' field:     {has_desc_field:,}")
print(f"  Non-empty descriptions (>10): {has_nonempty_desc:,}")
print(f"  Have critic_rating:           {has_critic:,}")
print(f"  Have user_rating:             {has_user:,}")
print(f"  Have BOTH ratings:            {has_both_ratings:,}")
print(f"  Have EITHER rating:           {has_either_rating:,}")

print(f"\n--- 3 SAMPLE PROPERTIES JSONs WITH DESCRIPTIONS ---")
for i, sp in enumerate(sample_with_desc, 1):
    print(f"\n  Sample {i}: {sp.get('name', 'N/A')}")
    print(f"  {json.dumps(sp, indent=4, ensure_ascii=False)[:1500]}")


# ═══════════════════════════════════════════════════════════════════
# TASK 2: EXTRACT 2,000 GAME PROFILES
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 60)
print("TASK 2: EXTRACT 2,000 GAME PROFILES")
print("=" * 60)

# ─── STAGE 1: Select 2,000 games ─────────────────────────────────
print("\nSTAGE 1: Selecting 2,000 games...")

# Filter to games with non-empty descriptions (>10 chars)
eligible = []
for g in all_games:
    p = g["props"]
    desc = (p.get("description", "") or "").strip()
    if len(desc) > 10:
        cr = p.get("critic_rating")
        ur = p.get("user_rating")
        has_both = cr is not None and ur is not None
        has_any = cr is not None or ur is not None
        eligible.append({
            "id": g["id"],
            "props": p,
            "has_both_ratings": has_both,
            "has_any_rating": has_any,
            "desc_len": len(desc),
        })

print(f"  Eligible games (non-empty desc >10 chars): {len(eligible):,}")

# Sort: both ratings first, then either rating, then by desc length
def selection_sort_key(g):
    return (
        2 if g["has_both_ratings"] else (1 if g["has_any_rating"] else 0),
        g["desc_len"],
    )

eligible.sort(key=selection_sort_key, reverse=True)
selected = eligible[:2000]

# Record cutoff info
tier_counts = Counter()
for g in selected:
    if g["has_both_ratings"]:
        tier_counts["both_ratings"] += 1
    elif g["has_any_rating"]:
        tier_counts["either_rating"] += 1
    else:
        tier_counts["desc_only"] += 1

print(f"  Selected 2,000 breakdown:")
print(f"    Tier 1 (both ratings):  {tier_counts['both_ratings']:,}")
print(f"    Tier 2 (either rating): {tier_counts['either_rating']:,}")
print(f"    Tier 3 (desc only):     {tier_counts['desc_only']:,}")

last_game = selected[-1]
print(f"  Cutoff: desc_len={last_game['desc_len']}, "
      f"has_both={last_game['has_both_ratings']}, has_any={last_game['has_any_rating']}")

# Build selected ID set for edge filtering
selected_ids = {g["id"] for g in selected}

# ─── STAGE 2: Load genre mappings for IGDB ───────────────────────
print("\nSTAGE 2: Loading IGDB genre mappings...")

# IGDB genre name → set of Feeds canonical genre names
# Use core_genres rows where media_source_name=IGDB
igdb_genre_map = defaultdict(set)
with open(os.path.join(BASE, "genre_mappings.csv"), "r") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        if row["media_source_name"] == "IGDB":
            igdb_genre_map[row["source_name"]].add(row["feeds_name"])

igdb_genre_map = {k: sorted(v) for k, v in igdb_genre_map.items()}
print(f"  Loaded {len(igdb_genre_map)} IGDB genre/theme → Feeds mappings:")
for g, feeds in sorted(igdb_genre_map.items()):
    print(f"    {g} -> {feeds}")

# ─── STAGE 3: Load property nodes (IGDB types only) ──────────────
print("\nSTAGE 3: Loading IGDB property nodes...")

IGDB_NODE_TYPES = {
    "IGDB_Genre", "IGDB_Theme", "IGDB_Keyword", "IGDB_Franchise",
    "IGDB_Company", "IGDB_GameMode", "IGDB_PlayerPerspective", "IGDB_ReleaseDate"
}

prop_nodes = {}  # id -> {"name": ..., "type": ..., ...extra fields}
node_type_counts = Counter()

with open(os.path.join(BASE, "property_nodes_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        ntype = row["node_type"]
        if ntype in IGDB_NODE_TYPES:
            props = parse_props(row)
            entry = {"name": props.get("name", ""), "type": ntype}

            # Extra fields for specific types
            if ntype == "IGDB_Company":
                entry["description"] = props.get("description", "")
            elif ntype == "IGDB_ReleaseDate":
                entry["release_date"] = props.get("release_date", "")

            prop_nodes[row["id"]] = entry
            node_type_counts[ntype] += 1

print(f"  Loaded property nodes:")
for ntype, count in sorted(node_type_counts.items()):
    print(f"    {ntype}: {count:,}")

# ─── STAGE 4: Load IGDB_Game edges ───────────────────────────────
print("\nSTAGE 4: Loading IGDB_Game edges...")

IGDB_RELATIONSHIPS = {
    "IGDBGameHasGenre", "IGDBGameHasTheme", "IGDBGameHasKeyword",
    "IGDBGameInFranchise", "IGDBGameHasDeveloper", "IGDBGameHasPublisher",
    "IGDBGameHasMode", "IGDBGameHasPerspective", "IGDBGameHasReleaseDate"
}

# game_id -> {relationship: [dst_ids]}
game_edges = defaultdict(lambda: defaultdict(list))
edge_counts = Counter()

with open(os.path.join(BASE, "edges_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        rel = row["relationship"]
        if rel in IGDB_RELATIONSHIPS:
            src = row["src"]
            if src in selected_ids:
                game_edges[src][rel].append(row["dst"])
                edge_counts[rel] += 1

print(f"  Loaded edges for selected games:")
for rel, count in sorted(edge_counts.items()):
    print(f"    {rel}: {count:,}")

# ─── STAGE 5: Compute global keyword frequencies ─────────────────
print("\nSTAGE 5: Computing keyword frequencies across selected games...")

keyword_freq = Counter()
for gid in selected_ids:
    kw_ids = game_edges[gid].get("IGDBGameHasKeyword", [])
    for kid in kw_ids:
        node = prop_nodes.get(kid)
        if node and node["name"]:
            keyword_freq[node["name"]] += 1

print(f"  Unique keywords across selected games: {len(keyword_freq):,}")
print(f"  Top 20 most common keywords:")
for kw, count in keyword_freq.most_common(20):
    print(f"    {kw}: {count}")

# ─── STAGE 6: Build profiles ─────────────────────────────────────
print("\nSTAGE 6: Building 2,000 game profiles...")

profiles = []

# Tracking for report
genre_has = 0
theme_has = 0
keyword_has = 0
franchise_has = 0
developer_has = 0
publisher_has = 0
release_date_has = 0
critic_ratings = []
user_ratings = []

for g in selected:
    gid = g["id"]
    p = g["props"]
    edges = game_edges[gid]

    # --- Genres: translate to canonical Feeds genres ---
    raw_genre_names = []
    for dst in edges.get("IGDBGameHasGenre", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            raw_genre_names.append(node["name"])

    canonical_genres = set()
    for gname in raw_genre_names:
        if gname in igdb_genre_map:
            canonical_genres.update(igdb_genre_map[gname])
        else:
            canonical_genres.add(gname)  # keep as-is if no mapping
    canonical_genres = sorted(canonical_genres)

    # --- Themes: raw theme names ---
    themes = []
    for dst in edges.get("IGDBGameHasTheme", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            themes.append(node["name"])
    themes = sorted(set(themes))

    # --- Keywords: top 15 by global frequency ---
    all_kws = []
    for dst in edges.get("IGDBGameHasKeyword", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            all_kws.append(node["name"])
    # Sort by global frequency (most common first), keep top 15
    all_kws = sorted(set(all_kws), key=lambda k: keyword_freq.get(k, 0), reverse=True)
    keywords = all_kws[:15]

    # --- Franchise ---
    franchise = None
    for dst in edges.get("IGDBGameInFranchise", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            franchise = node["name"]
            break  # take first

    # --- Developer ---
    developer = None
    developer_description = None
    for dst in edges.get("IGDBGameHasDeveloper", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            developer = node["name"]
            dev_desc = node.get("description", "")
            if dev_desc and len(dev_desc.strip()) > 0:
                developer_description = dev_desc.strip()
            break  # take first

    # --- Publisher ---
    publisher = None
    publisher_description = None
    for dst in edges.get("IGDBGameHasPublisher", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            publisher = node["name"]
            pub_desc = node.get("description", "")
            if pub_desc and len(pub_desc.strip()) > 0:
                publisher_description = pub_desc.strip()
            break  # take first

    # --- Modes ---
    modes = []
    for dst in edges.get("IGDBGameHasMode", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            modes.append(node["name"])
    modes = sorted(set(modes))

    # --- Perspectives ---
    perspectives = []
    for dst in edges.get("IGDBGameHasPerspective", []):
        node = prop_nodes.get(dst)
        if node and node["name"]:
            perspectives.append(node["name"])
    perspectives = sorted(set(perspectives))

    # --- Release date: earliest ---
    release_dates = []
    for dst in edges.get("IGDBGameHasReleaseDate", []):
        node = prop_nodes.get(dst)
        if node and node.get("release_date"):
            rd = node["release_date"].strip()
            if rd:
                release_dates.append(rd)

    release_date = None
    if release_dates:
        # Sort lexicographically (ISO dates sort correctly)
        release_dates.sort()
        release_date = release_dates[0]

    # --- Ratings ---
    cr = p.get("critic_rating")
    ur = p.get("user_rating")
    if cr is not None:
        try:
            cr = round(float(cr), 2)
            critic_ratings.append(cr)
        except (ValueError, TypeError):
            cr = None
    if ur is not None:
        try:
            ur = round(float(ur), 2)
            user_ratings.append(ur)
        except (ValueError, TypeError):
            ur = None

    # --- Coverage tracking ---
    if canonical_genres:
        genre_has += 1
    if themes:
        theme_has += 1
    if keywords:
        keyword_has += 1
    if franchise:
        franchise_has += 1
    if developer:
        developer_has += 1
    if publisher:
        publisher_has += 1
    if release_date:
        release_date_has += 1

    # --- Build profile ---
    profile = {
        "entity_id": gid,
        "name": p.get("name", ""),
        "vertical": "game",
        "description": (p.get("description", "") or "").strip(),
        "canonical_genres": canonical_genres,
        "themes": themes,
        "keywords": keywords,
        "franchise": franchise,
        "developer": developer,
        "publisher": publisher,
        "developer_description": developer_description,
        "publisher_description": publisher_description,
        "modes": modes,
        "perspectives": perspectives,
        "release_date": release_date,
        "critic_rating": cr,
        "user_rating": ur,
        "source_match": "direct",
        "match_quality": "direct",
    }
    profiles.append(profile)

print(f"  Built {len(profiles)} game profiles")

# ─── STAGE 7: Save profiles ──────────────────────────────────────
print("\nSTAGE 7: Saving output files...")

out_path = os.path.join(BASE, "entity_profiles_games_source.json")
with open(out_path, "w") as f:
    json.dump(profiles, f, indent=2, ensure_ascii=False)
print(f"  Saved {len(profiles)} game profiles to {out_path}")

# ─── STAGE 8: Generate GAMES_EXTRACTION_REPORT.md ────────────────
print("\nSTAGE 8: Generating extraction report...")

n = len(profiles)

# Rating stats
def rating_stats(values, label):
    if not values:
        return f"  {label}: no data"
    return (f"  {label}: count={len(values)}, "
            f"min={min(values):.2f}, max={max(values):.2f}, "
            f"avg={sum(values)/len(values):.2f}")

# Top 10 by critic rating
by_critic = sorted([p for p in profiles if p["critic_rating"] is not None],
                   key=lambda p: p["critic_rating"], reverse=True)

# Bottom 10 by description length
by_desc_len = sorted(profiles, key=lambda p: len(p["description"]))

lines = []
lines.append("# Feeds.ai V2 \u2014 IGDB Games Extraction Report")
lines.append("")
lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f"**Source:** source_entities_igdb_v2.csv")
lines.append(f"**Output:** entity_profiles_games_source.json (2,000 games)")
lines.append("")
lines.append("---")
lines.append("")

# 1. Source overview
lines.append("## 1. Source Data Overview")
lines.append("")
lines.append(f"| Metric | Count |")
lines.append(f"|--------|-------|")
lines.append(f"| Total IGDB_Game rows | {total_rows:,} |")
lines.append(f"| Have 'description' field | {has_desc_field:,} |")
lines.append(f"| Non-empty descriptions (>10 chars) | {has_nonempty_desc:,} |")
lines.append(f"| Have critic_rating | {has_critic:,} |")
lines.append(f"| Have user_rating | {has_user:,} |")
lines.append(f"| Have BOTH ratings | {has_both_ratings:,} |")
lines.append(f"| Have EITHER rating | {has_either_rating:,} |")
lines.append("")

# 2. Selection criteria
lines.append("## 2. Selection Criteria & Cutoffs")
lines.append("")
lines.append("From the pool of games with non-empty descriptions (>10 characters), "
             "2,000 were selected using this priority:")
lines.append("")
lines.append("1. **Tier 1** \u2014 Games with BOTH critic_rating AND user_rating (most notable)")
lines.append("2. **Tier 2** \u2014 Games with EITHER rating")
lines.append("3. **Tier 3** \u2014 Games with neither rating, sorted by description length (longer = richer)")
lines.append("")
lines.append(f"| Tier | Count |")
lines.append(f"|------|-------|")
lines.append(f"| Tier 1 (both ratings) | {tier_counts['both_ratings']:,} |")
lines.append(f"| Tier 2 (either rating) | {tier_counts['either_rating']:,} |")
lines.append(f"| Tier 3 (desc length only) | {tier_counts['desc_only']:,} |")
lines.append(f"| **Total selected** | **2,000** |")
lines.append("")
lines.append(f"Eligible pool: {len(eligible):,} games with non-empty descriptions")
lines.append(f"Cutoff game: desc_len={last_game['desc_len']}, "
             f"has_both_ratings={last_game['has_both_ratings']}, "
             f"has_any_rating={last_game['has_any_rating']}")
lines.append("")

# 3. Coverage stats
lines.append("## 3. Metadata Coverage (of 2,000 selected)")
lines.append("")
lines.append(f"| Field | Count | % |")
lines.append(f"|-------|-------|---|")
lines.append(f"| Genre (>=1 canonical genre) | {genre_has:,} | {100*genre_has/n:.1f}% |")
lines.append(f"| Theme (>=1 theme) | {theme_has:,} | {100*theme_has/n:.1f}% |")
lines.append(f"| Keyword (>=1 keyword) | {keyword_has:,} | {100*keyword_has/n:.1f}% |")
lines.append(f"| Franchise | {franchise_has:,} | {100*franchise_has/n:.1f}% |")
lines.append(f"| Developer | {developer_has:,} | {100*developer_has/n:.1f}% |")
lines.append(f"| Publisher | {publisher_has:,} | {100*publisher_has/n:.1f}% |")
lines.append(f"| Release date | {release_date_has:,} | {100*release_date_has/n:.1f}% |")
lines.append(f"| Critic rating | {len(critic_ratings):,} | {100*len(critic_ratings)/n:.1f}% |")
lines.append(f"| User rating | {len(user_ratings):,} | {100*len(user_ratings)/n:.1f}% |")
lines.append("")

# 4. Rating stats
lines.append("## 4. Rating Statistics (selected games)")
lines.append("")
if critic_ratings:
    lines.append(f"**Critic Rating:** min={min(critic_ratings):.2f}, "
                 f"max={max(critic_ratings):.2f}, "
                 f"avg={sum(critic_ratings)/len(critic_ratings):.2f}, "
                 f"count={len(critic_ratings):,}")
else:
    lines.append("**Critic Rating:** no data")
lines.append("")
if user_ratings:
    lines.append(f"**User Rating:** min={min(user_ratings):.2f}, "
                 f"max={max(user_ratings):.2f}, "
                 f"avg={sum(user_ratings)/len(user_ratings):.2f}, "
                 f"count={len(user_ratings):,}")
else:
    lines.append("**User Rating:** no data")
lines.append("")

# 5. Top 10 by critic rating
lines.append("## 5. Top 10 Games by Critic Rating (sanity check)")
lines.append("")
lines.append("| Rank | Name | Critic Rating | User Rating | Genres |")
lines.append("|------|------|---------------|-------------|--------|")
for i, p in enumerate(by_critic[:10], 1):
    ur_str = f"{p['user_rating']:.2f}" if p["user_rating"] is not None else "N/A"
    genres_str = ", ".join(p["canonical_genres"]) if p["canonical_genres"] else "N/A"
    lines.append(f"| {i} | {p['name']} | {p['critic_rating']:.2f} | {ur_str} | {genres_str} |")
lines.append("")

# 6. Bottom 10 by description length
lines.append("## 6. Bottom 10 Games by Description Length (may need LLM enrichment)")
lines.append("")
lines.append("| Rank | Name | Desc Length | Has Genres | Has Themes |")
lines.append("|------|------|-------------|------------|------------|")
for i, p in enumerate(by_desc_len[:10], 1):
    has_g = "Yes" if p["canonical_genres"] else "No"
    has_t = "Yes" if p["themes"] else "No"
    lines.append(f"| {i} | {p['name']} | {len(p['description'])} | {has_g} | {has_t} |")
lines.append("")

# 7. Genre distribution
lines.append("## 7. Canonical Genre Distribution")
lines.append("")
genre_dist = Counter()
for p in profiles:
    for g in p["canonical_genres"]:
        genre_dist[g] += 1
lines.append("| Genre | Count | % of 2,000 |")
lines.append("|-------|-------|------------|")
for g, c in genre_dist.most_common():
    lines.append(f"| {g} | {c:,} | {100*c/n:.1f}% |")
lines.append("")

# 8. Theme distribution
lines.append("## 8. Theme Distribution (top 20)")
lines.append("")
theme_dist = Counter()
for p in profiles:
    for t in p["themes"]:
        theme_dist[t] += 1
lines.append("| Theme | Count | % of 2,000 |")
lines.append("|-------|-------|------------|")
for t, c in theme_dist.most_common(20):
    lines.append(f"| {t} | {c:,} | {100*c/n:.1f}% |")
lines.append("")

# 9. Mode distribution
lines.append("## 9. Game Mode Distribution")
lines.append("")
mode_dist = Counter()
for p in profiles:
    for m in p["modes"]:
        mode_dist[m] += 1
lines.append("| Mode | Count |")
lines.append("|------|-------|")
for m, c in mode_dist.most_common():
    lines.append(f"| {m} | {c:,} |")
lines.append("")

# 10. Perspective distribution
lines.append("## 10. Player Perspective Distribution")
lines.append("")
persp_dist = Counter()
for p in profiles:
    for pp in p["perspectives"]:
        persp_dist[pp] += 1
lines.append("| Perspective | Count |")
lines.append("|-------------|-------|")
for pp, c in persp_dist.most_common():
    lines.append(f"| {pp} | {c:,} |")
lines.append("")

report_path = os.path.join(BASE, "GAMES_EXTRACTION_REPORT.md")
with open(report_path, "w") as f:
    f.write("\n".join(lines))
print(f"  Saved extraction report to {report_path}")

# ─── SUMMARY ─────────────────────────────────────────────────────
print(f"\n{'=' * 60}")
print(f"DONE \u2014 2,000 IGDB game profiles extracted")
print(f"  Output: entity_profiles_games_source.json")
print(f"  Report: GAMES_EXTRACTION_REPORT.md")
print(f"  Genre coverage:    {genre_has:,}/2,000 ({100*genre_has/n:.1f}%)")
print(f"  Theme coverage:    {theme_has:,}/2,000 ({100*theme_has/n:.1f}%)")
print(f"  Keyword coverage:  {keyword_has:,}/2,000 ({100*keyword_has/n:.1f}%)")
print(f"  Franchise:         {franchise_has:,}/2,000 ({100*franchise_has/n:.1f}%)")
print(f"  Developer:         {developer_has:,}/2,000 ({100*developer_has/n:.1f}%)")
print(f"  Publisher:         {publisher_has:,}/2,000 ({100*publisher_has/n:.1f}%)")
print(f"  Release date:      {release_date_has:,}/2,000 ({100*release_date_has/n:.1f}%)")
print(f"{'=' * 60}")
