#!/usr/bin/env python3
"""Extract 1,000 extra movies + 1,000 extra TV shows from Watchmode_Title source data.

Avoids overlap with existing entity_profiles_movies_tv.json names.
Enriches with genres (via edges + genre_mappings) and cast/creators (via persons CSV).
"""

import csv
import json
import sys
import os
from collections import defaultdict, Counter
from datetime import datetime

csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.abspath(__file__))

MOVIE_TYPES = {"movie", "tv_movie", "short_film"}
TV_TYPES = {"tv_series", "tv_miniseries"}


def parse_props(row):
    try:
        return json.loads(row["properties"])
    except Exception:
        return {}


# ═══════════════════════════════════════════════════════════════════
# STAGE 1: Build exclusion set from existing profiles
# ═══════════════════════════════════════════════════════════════════
print("STAGE 1: Loading existing profiles for exclusion...")

existing_path = os.path.join(BASE, "entity_profiles_movies_tv.json")
with open(existing_path, "r") as f:
    existing_profiles = json.load(f)

existing_movie_names = set()
existing_tv_names = set()
for p in existing_profiles:
    name_lower = p["name"].strip().lower()
    if p["vertical"] == "movie":
        existing_movie_names.add(name_lower)
    elif p["vertical"] == "tv":
        existing_tv_names.add(name_lower)

print(f"  Existing movies: {len(existing_movie_names)}, TV: {len(existing_tv_names)}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 2: Load genre mappings (Watchmode)
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 2: Loading Watchmode genre mappings...")

wm_genre_map = defaultdict(set)
with open(os.path.join(BASE, "genre_mappings.csv"), "r") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        src = row["media_source_name"]
        if "Watchmode" in src:
            wm_genre_map[row["source_name"]].add(row["feeds_name"])

wm_genre_map = {k: sorted(v) for k, v in wm_genre_map.items()}
print(f"  Loaded {len(wm_genre_map)} Watchmode genre mappings")


# ═══════════════════════════════════════════════════════════════════
# STAGE 3: Load Watchmode_Genre property nodes
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 3: Loading Watchmode_Genre property nodes...")

genre_nodes = {}  # id → genre name
with open(os.path.join(BASE, "property_nodes_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        if row["node_type"] == "Watchmode_Genre":
            props = parse_props(row)
            genre_nodes[row["id"]] = props.get("name", "")

print(f"  Loaded {len(genre_nodes)} Watchmode_Genre nodes")


# ═══════════════════════════════════════════════════════════════════
# STAGE 4: Load WatchmodeTitleHasGenre edges
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 4: Loading WatchmodeTitleHasGenre edges...")

title_genres = defaultdict(list)
edge_count = 0
with open(os.path.join(BASE, "edges_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        if row["relationship"] == "WatchmodeTitleHasGenre":
            title_genres[row["src"]].append(row["dst"])
            edge_count += 1

print(f"  Loaded {edge_count:,} genre edges for {len(title_genres):,} titles")


# ═══════════════════════════════════════════════════════════════════
# STAGE 5: Load persons index
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 5: Loading watchmode persons...")

persons_index = defaultdict(lambda: defaultdict(list))
with open(os.path.join(BASE, "watchmode_persons_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        title_lower = row["title_name"].strip().lower()
        persons_index[title_lower][row["job_type"]].append(row["person_name"])

print(f"  Loaded persons for {len(persons_index):,} unique titles")


# ═══════════════════════════════════════════════════════════════════
# STAGE 6: Scan Watchmode_Title entries — collect movies and TV
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 6: Scanning Watchmode_Title entries...")

candidate_movies = []
candidate_tv = []
total_wm_movies = 0
total_wm_tv = 0
excluded_movies = 0
excluded_tv = 0
no_desc_movies = 0
no_desc_tv = 0

with open(os.path.join(BASE, "source_entities_watchmode_podcast_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        if row["node_type"] != "Watchmode_Title":
            continue
        props = parse_props(row)
        mt = props.get("media_type", "")
        name = (props.get("name", "") or "").strip()
        desc = (props.get("description", "") or "").strip()
        name_lower = name.lower()

        if mt in MOVIE_TYPES:
            total_wm_movies += 1
            if len(desc) <= 20:
                no_desc_movies += 1
                continue
            if name_lower in existing_movie_names:
                excluded_movies += 1
                continue
            # Parse relevance_percentile
            rp = props.get("relevance_percentile")
            try:
                rp = float(rp) if rp is not None else 0.0
            except (ValueError, TypeError):
                rp = 0.0
            candidate_movies.append({
                "id": row["id"],
                "name": name,
                "props": props,
                "relevance_percentile": rp,
            })

        elif mt in TV_TYPES:
            total_wm_tv += 1
            if len(desc) <= 20:
                no_desc_tv += 1
                continue
            if name_lower in existing_tv_names:
                excluded_tv += 1
                continue
            rp = props.get("relevance_percentile")
            try:
                rp = float(rp) if rp is not None else 0.0
            except (ValueError, TypeError):
                rp = 0.0
            candidate_tv.append({
                "id": row["id"],
                "name": name,
                "props": props,
                "relevance_percentile": rp,
            })

print(f"  Watchmode movies: {total_wm_movies:,} total")
print(f"    No desc (<=20 chars): {no_desc_movies:,}")
print(f"    Excluded (name overlap): {excluded_movies:,}")
print(f"    Candidates: {len(candidate_movies):,}")
print(f"  Watchmode TV: {total_wm_tv:,} total")
print(f"    No desc (<=20 chars): {no_desc_tv:,}")
print(f"    Excluded (name overlap): {excluded_tv:,}")
print(f"    Candidates: {len(candidate_tv):,}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 7: Select top 1,000 by relevance_percentile
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 7: Selecting top 1,000 movies and 1,000 TV shows...")

candidate_movies.sort(key=lambda x: x["relevance_percentile"], reverse=True)
candidate_tv.sort(key=lambda x: x["relevance_percentile"], reverse=True)

selected_movies = candidate_movies[:1000]
selected_tv = candidate_tv[:1000]

movie_rp_min = selected_movies[-1]["relevance_percentile"] if selected_movies else None
movie_rp_max = selected_movies[0]["relevance_percentile"] if selected_movies else None
tv_rp_min = selected_tv[-1]["relevance_percentile"] if selected_tv else None
tv_rp_max = selected_tv[0]["relevance_percentile"] if selected_tv else None

print(f"  Selected movies: {len(selected_movies)}, "
      f"relevance_percentile range: {movie_rp_min} – {movie_rp_max}")
print(f"  Selected TV: {len(selected_tv)}, "
      f"relevance_percentile range: {tv_rp_min} – {tv_rp_max}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 8: Helper functions
# ═══════════════════════════════════════════════════════════════════

def get_genres_for_title(watchmode_id):
    """Get canonical Feeds genres for a Watchmode_Title via edges."""
    genre_ids = title_genres.get(watchmode_id, [])
    source_genres = []
    for gid in genre_ids:
        gname = genre_nodes.get(gid, "")
        if gname:
            source_genres.append(gname)

    canonical = set()
    for sg in source_genres:
        if sg in wm_genre_map:
            canonical.update(wm_genre_map[sg])
        else:
            canonical.add(sg)
    return sorted(canonical)


def get_persons(title_name):
    """Get cast and creators by title name."""
    name_lower = title_name.strip().lower()
    persons = persons_index.get(name_lower, {})
    actors = persons.get("Actor", [])[:5]
    creators = persons.get("Creator", [])[:3]
    return actors, creators


def build_profile(entry, vertical):
    """Build a profile dict from a selected entry."""
    p = entry["props"]
    wm_id = entry["id"]
    name = entry["name"]

    # Genres
    genres = get_genres_for_title(wm_id)

    # Cast / directors
    actors, creators = get_persons(name)

    # Fields from properties
    release_date = p.get("release_date")
    release_year = p.get("release_year")
    runtime = p.get("runtime_minutes")
    rp = p.get("relevance_percentile")
    lang = p.get("original_language", "")
    desc = (p.get("description", "") or "").strip()

    # Type coercion
    try:
        release_year = int(release_year) if release_year else None
    except (ValueError, TypeError):
        release_year = None
    try:
        runtime = int(float(runtime)) if runtime else None
    except (ValueError, TypeError):
        runtime = None
    if runtime == 0:
        runtime = None
    try:
        rp = float(rp) if rp is not None else None
    except (ValueError, TypeError):
        rp = None

    return {
        "entity_id": wm_id,
        "name": name,
        "vertical": vertical,
        "description": desc,
        "canonical_genres": genres,
        "themes": [],
        "keywords": [],
        "franchise": None,
        "developer": None,
        "publisher": None,
        "directors": creators,
        "cast": actors,
        "release_date": release_date if release_date else None,
        "release_year": release_year,
        "runtime_minutes": runtime,
        "language": lang if lang else None,
        "relevance_percentile": rp,
        "source_match": "direct",
        "match_quality": "direct",
    }


# ═══════════════════════════════════════════════════════════════════
# STAGE 9: Build profiles
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 9: Building profiles...")

movie_profiles = []
for entry in selected_movies:
    movie_profiles.append(build_profile(entry, "movie"))

tv_profiles = []
for entry in selected_tv:
    tv_profiles.append(build_profile(entry, "tv"))

print(f"  Built {len(movie_profiles)} movie profiles")
print(f"  Built {len(tv_profiles)} TV profiles")


# ═══════════════════════════════════════════════════════════════════
# STAGE 10: Coverage stats
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 10: Computing coverage stats...")


def coverage_stats(profiles, label):
    n = len(profiles)
    genre_has = sum(1 for p in profiles if p["canonical_genres"])
    cast_has = sum(1 for p in profiles if p["cast"])
    director_has = sum(1 for p in profiles if p["directors"])
    release_has = sum(1 for p in profiles if p["release_date"])
    year_has = sum(1 for p in profiles if p["release_year"])
    runtime_has = sum(1 for p in profiles if p["runtime_minutes"])
    lang_has = sum(1 for p in profiles if p["language"])
    rp_values = [p["relevance_percentile"] for p in profiles
                 if p["relevance_percentile"] is not None]

    print(f"  {label} ({n}):")
    print(f"    Genre: {genre_has} ({100*genre_has/n:.1f}%)")
    print(f"    Cast: {cast_has} ({100*cast_has/n:.1f}%)")
    print(f"    Directors/Creators: {director_has} ({100*director_has/n:.1f}%)")
    print(f"    Release date: {release_has} ({100*release_has/n:.1f}%)")
    print(f"    Runtime: {runtime_has} ({100*runtime_has/n:.1f}%)")

    return {
        "count": n,
        "genre": genre_has,
        "cast": cast_has,
        "directors": director_has,
        "release_date": release_has,
        "release_year": year_has,
        "runtime": runtime_has,
        "language": lang_has,
        "rp_min": min(rp_values) if rp_values else None,
        "rp_max": max(rp_values) if rp_values else None,
        "rp_avg": sum(rp_values) / len(rp_values) if rp_values else None,
    }


movie_stats = coverage_stats(movie_profiles, "Movies")
tv_stats = coverage_stats(tv_profiles, "TV Shows")


# ═══════════════════════════════════════════════════════════════════
# STAGE 11: Overlap verification
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 11: Verifying zero overlap with existing profiles...")

movie_overlap = [p["name"] for p in movie_profiles
                 if p["name"].lower() in existing_movie_names]
tv_overlap = [p["name"] for p in tv_profiles
              if p["name"].lower() in existing_tv_names]

print(f"  Movie name overlaps: {len(movie_overlap)}")
print(f"  TV name overlaps: {len(tv_overlap)}")
if movie_overlap:
    print(f"  WARNING — movie overlaps: {movie_overlap[:10]}")
if tv_overlap:
    print(f"  WARNING — TV overlaps: {tv_overlap[:10]}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 12: Save output files
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 12: Saving output files...")

out_movies = os.path.join(BASE, "entity_profiles_movies_extra.json")
with open(out_movies, "w") as f:
    json.dump(movie_profiles, f, indent=2, ensure_ascii=False)
print(f"  Saved {len(movie_profiles)} extra movie profiles to {out_movies}")

out_tv = os.path.join(BASE, "entity_profiles_tv_extra.json")
with open(out_tv, "w") as f:
    json.dump(tv_profiles, f, indent=2, ensure_ascii=False)
print(f"  Saved {len(tv_profiles)} extra TV profiles to {out_tv}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 13: Generate report
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 13: Generating EXTRA_MOVIES_TV_REPORT.md...")

lines = []
lines.append("# Feeds.ai V2 — Extra Movies & TV Shows Extraction Report")
lines.append("")
lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f"**Source:** source_entities_watchmode_podcast_v2.csv (Watchmode_Title)")
lines.append(f"**Outputs:** entity_profiles_movies_extra.json (1,000 movies), "
             f"entity_profiles_tv_extra.json (1,000 TV shows)")
lines.append("")
lines.append("---")
lines.append("")

# 1. Source pool
lines.append("## 1. Source Pool")
lines.append("")
lines.append("| Metric | Movies | TV Shows |")
lines.append("|--------|--------|----------|")
lines.append(f"| Total Watchmode entries | {total_wm_movies:,} | {total_wm_tv:,} |")
lines.append(f"| Dropped: no description (<=20 chars) | {no_desc_movies:,} | {no_desc_tv:,} |")
lines.append(f"| Excluded: name overlap with existing | {excluded_movies:,} | {excluded_tv:,} |")
lines.append(f"| Remaining candidates | {len(candidate_movies):,} | {len(candidate_tv):,} |")
lines.append(f"| **Selected (top by relevance_percentile)** | **{len(selected_movies):,}** | **{len(selected_tv):,}** |")
lines.append("")

# 2. Selection criteria
lines.append("## 2. Selection Criteria")
lines.append("")
lines.append("- **Movies:** media_type = 'movie' (also includes tv_movie, short_film)")
lines.append("- **TV Shows:** media_type IN ('tv_series', 'tv_miniseries')")
lines.append("- Must have description > 20 characters")
lines.append("- Name (case-insensitive) must NOT match any existing profile")
lines.append("- Selected top 1,000 by relevance_percentile (highest first)")
lines.append("")

lines.append("### Relevance Percentile Ranges")
lines.append("")
lines.append("| Vertical | Min | Max | Avg |")
lines.append("|----------|-----|-----|-----|")
lines.append(f"| Movies | {movie_stats['rp_min']:.1f} | {movie_stats['rp_max']:.1f} | {movie_stats['rp_avg']:.1f} |")
lines.append(f"| TV Shows | {tv_stats['rp_min']:.1f} | {tv_stats['rp_max']:.1f} | {tv_stats['rp_avg']:.1f} |")
lines.append("")

# 3. Overlap check
lines.append("## 3. Overlap Verification")
lines.append("")
lines.append(f"- Movie name overlaps with existing: **{len(movie_overlap)}**")
lines.append(f"- TV name overlaps with existing: **{len(tv_overlap)}**")
if not movie_overlap and not tv_overlap:
    lines.append("- **CONFIRMED: Zero overlap with existing entity_profiles_movies_tv.json**")
lines.append("")

# 4. Coverage
lines.append("## 4. Metadata Coverage")
lines.append("")
n_m = movie_stats["count"]
n_t = tv_stats["count"]
lines.append("| Field | Movies | % | TV Shows | % |")
lines.append("|-------|--------|---|----------|---|")
lines.append(f"| Genre (>=1) | {movie_stats['genre']:,} | {100*movie_stats['genre']/n_m:.1f}% | {tv_stats['genre']:,} | {100*tv_stats['genre']/n_t:.1f}% |")
lines.append(f"| Cast (>=1 actor) | {movie_stats['cast']:,} | {100*movie_stats['cast']/n_m:.1f}% | {tv_stats['cast']:,} | {100*tv_stats['cast']/n_t:.1f}% |")
lines.append(f"| Directors/Creators | {movie_stats['directors']:,} | {100*movie_stats['directors']/n_m:.1f}% | {tv_stats['directors']:,} | {100*tv_stats['directors']/n_t:.1f}% |")
lines.append(f"| Release date | {movie_stats['release_date']:,} | {100*movie_stats['release_date']/n_m:.1f}% | {tv_stats['release_date']:,} | {100*tv_stats['release_date']/n_t:.1f}% |")
lines.append(f"| Release year | {movie_stats['release_year']:,} | {100*movie_stats['release_year']/n_m:.1f}% | {tv_stats['release_year']:,} | {100*tv_stats['release_year']/n_t:.1f}% |")
lines.append(f"| Runtime | {movie_stats['runtime']:,} | {100*movie_stats['runtime']/n_m:.1f}% | {tv_stats['runtime']:,} | {100*tv_stats['runtime']/n_t:.1f}% |")
lines.append(f"| Language | {movie_stats['language']:,} | {100*movie_stats['language']/n_m:.1f}% | {tv_stats['language']:,} | {100*tv_stats['language']/n_t:.1f}% |")
lines.append("")

# 5. Genre distribution
lines.append("## 5. Genre Distribution")
lines.append("")

for label, profiles in [("Movies", movie_profiles), ("TV Shows", tv_profiles)]:
    genre_dist = Counter()
    for p in profiles:
        for g in p["canonical_genres"]:
            genre_dist[g] += 1
    n = len(profiles)
    lines.append(f"### {label}")
    lines.append("")
    lines.append("| Genre | Count | % |")
    lines.append("|-------|-------|---|")
    for g, c in genre_dist.most_common():
        lines.append(f"| {g} | {c:,} | {100*c/n:.1f}% |")
    lines.append("")

# 6. Top 10 movies
lines.append("## 6. Top 10 Movies by Relevance Percentile (sanity check)")
lines.append("")
lines.append("| Rank | Name | Rel% | Genres | Year | Language |")
lines.append("|------|------|------|--------|------|----------|")
for i, p in enumerate(movie_profiles[:10], 1):
    genres_str = ", ".join(p["canonical_genres"]) if p["canonical_genres"] else "N/A"
    yr = p["release_year"] if p["release_year"] else "N/A"
    lang = p["language"] if p["language"] else "N/A"
    rp = p["relevance_percentile"]
    rp_str = f"{rp:.1f}" if rp is not None else "N/A"
    lines.append(f"| {i} | {p['name']} | {rp_str} | {genres_str} | {yr} | {lang} |")
lines.append("")

# 7. Top 10 TV
lines.append("## 7. Top 10 TV Shows by Relevance Percentile (sanity check)")
lines.append("")
lines.append("| Rank | Name | Rel% | Genres | Year | Language |")
lines.append("|------|------|------|--------|------|----------|")
for i, p in enumerate(tv_profiles[:10], 1):
    genres_str = ", ".join(p["canonical_genres"]) if p["canonical_genres"] else "N/A"
    yr = p["release_year"] if p["release_year"] else "N/A"
    lang = p["language"] if p["language"] else "N/A"
    rp = p["relevance_percentile"]
    rp_str = f"{rp:.1f}" if rp is not None else "N/A"
    lines.append(f"| {i} | {p['name']} | {rp_str} | {genres_str} | {yr} | {lang} |")
lines.append("")

# 8. Total summary
lines.append("## 8. Total New Entities")
lines.append("")
lines.append(f"| Vertical | Count |")
lines.append(f"|----------|-------|")
lines.append(f"| Extra movies | {len(movie_profiles):,} |")
lines.append(f"| Extra TV shows | {len(tv_profiles):,} |")
lines.append(f"| **Total new** | **{len(movie_profiles) + len(tv_profiles):,}** |")
lines.append("")
lines.append("### Combined with existing profiles")
lines.append("")
lines.append(f"| Vertical | Existing | Extra | Total |")
lines.append(f"|----------|----------|-------|-------|")
lines.append(f"| Movies | {len(existing_movie_names):,} | {len(movie_profiles):,} | {len(existing_movie_names) + len(movie_profiles):,} |")
lines.append(f"| TV Shows | {len(existing_tv_names):,} | {len(tv_profiles):,} | {len(existing_tv_names) + len(tv_profiles):,} |")
lines.append(f"| **Total** | **{len(existing_movie_names) + len(existing_tv_names):,}** | **{len(movie_profiles) + len(tv_profiles):,}** | **{len(existing_movie_names) + len(existing_tv_names) + len(movie_profiles) + len(tv_profiles):,}** |")
lines.append("")

report_path = os.path.join(BASE, "EXTRA_MOVIES_TV_REPORT.md")
with open(report_path, "w") as f:
    f.write("\n".join(lines))
print(f"  Saved report to {report_path}")


# ═══════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════
print(f"\n{'=' * 60}")
print(f"DONE — {len(movie_profiles) + len(tv_profiles):,} extra profiles extracted")
print(f"  Extra movies: {len(movie_profiles):,}")
print(f"  Extra TV:     {len(tv_profiles):,}")
print(f"  Overlap:      {len(movie_overlap) + len(tv_overlap)} (should be 0)")
print(f"{'=' * 60}")
