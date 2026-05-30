#!/usr/bin/env python3
"""Entity profile extraction for Feeds.ai V2 — Movies, TV, Podcasts."""

import csv
import json
import sys
import os
from collections import defaultdict, Counter
from datetime import datetime

csv.field_size_limit(sys.maxsize)
BASE = os.path.dirname(os.path.abspath(__file__))

# ─── Tracking for report ───
report = {}

# ═══════════════════════════════════════════════════════════════════
# STAGE 1: Genre mappings
# ═══════════════════════════════════════════════════════════════════
print("STAGE 1: Loading genre mappings...")

# Watchmode source_name → list of feeds_name
wm_genre_map = defaultdict(set)
with open(os.path.join(BASE, "genre_mappings.csv"), "r") as f:
    reader = csv.DictReader(f, delimiter=";")
    for row in reader:
        src = row["media_source_name"]
        if "Watchmode" in src:
            wm_genre_map[row["source_name"]].add(row["feeds_name"])

# Convert sets to sorted lists
wm_genre_map = {k: sorted(v) for k, v in wm_genre_map.items()}
print(f"  Watchmode genre mappings loaded: {len(wm_genre_map)} source genres")
for g, feeds in sorted(wm_genre_map.items()):
    print(f"    {g} → {feeds}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 2: Load and deduplicate canonical entities
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 2: Loading and deduplicating canonical entities...")

import re

def parse_props(row):
    try:
        return json.loads(row["properties"])
    except:
        return {}

def is_random_hash(name):
    if not name or len(name) >= 15 or " " in name:
        return False
    if not re.match(r"^[a-z0-9]+$", name):
        return False
    has_letter = any(c.isalpha() for c in name)
    has_digit = any(c.isdigit() for c in name)
    return has_letter and has_digit and len(name) >= 8

test_prefixes = ["FollowCalendar_", "FollowingPlaylist_", "PropertyFollow_",
                 "UserPropertyVerify_", "MediaFilter_"]
test_exact_names = {"Custom Property Title", "Delete Test Property",
                    "Property After Edit", "Property for Campaign Edit",
                    "Property for Moment Edit"}

def is_test(row):
    props = parse_props(row)
    name = props.get("name", "") or ""
    desc = props.get("description", "") or ""
    for prefix in test_prefixes:
        if name.startswith(prefix):
            return True
    if name in test_exact_names:
        return True
    if is_random_hash(name) and not desc.strip():
        return True
    if "Property for media type filter test" in desc:
        return True
    return False

# Load all canonical entities, exclude test data
all_canonical = []
with open(os.path.join(BASE, "canonical_entities_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        if row["node_type"] in ("Movie", "TV", "Podcast") and not is_test(row):
            all_canonical.append(row)

raw_counts = Counter(r["node_type"] for r in all_canonical)
print(f"  Loaded (after test removal): {dict(raw_counts)}")

# Deduplicate: for each (name, node_type), keep the row with latest created_at
grouped = defaultdict(list)
for row in all_canonical:
    props = parse_props(row)
    name = (props.get("name", "") or "").strip()
    grouped[(name, row["node_type"])].append(row)

deduped = []
removed_counts = Counter()
for (name, ntype), rows in grouped.items():
    if len(rows) == 1:
        deduped.append(rows[0])
    else:
        # Sort by created_at (from properties JSON), keep latest
        def get_created(r):
            p = parse_props(r)
            ca = p.get("created_at", "") or ""
            try:
                return datetime.fromisoformat(ca.replace("Z", "+00:00"))
            except:
                return datetime.min
        rows.sort(key=get_created)
        deduped.append(rows[-1])  # keep latest
        removed_counts[ntype] += len(rows) - 1

clean_counts = Counter(r["node_type"] for r in deduped)
print(f"  Deduplication — removed per vertical: {dict(removed_counts)}")
print(f"  Clean counts: {dict(clean_counts)}")
report["dedup_removed"] = dict(removed_counts)
report["clean_counts"] = dict(clean_counts)

# Split by vertical
movies = [r for r in deduped if r["node_type"] == "Movie"]
tvshows = [r for r in deduped if r["node_type"] == "TV"]
podcasts = [r for r in deduped if r["node_type"] == "Podcast"]
print(f"  Movies: {len(movies)}, TV: {len(tvshows)}, Podcasts: {len(podcasts)}")


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
# STAGE 4: Load relevant edges
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 4: Loading edges (WatchmodeTitleHasGenre)...")

# Build: watchmode_title_id → [genre_node_ids]
title_genres = defaultdict(list)  # Watchmode_Title:XXX → [Watchmode_Genre:YYY, ...]
edge_count = 0
with open(os.path.join(BASE, "edges_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        if row["relationship"] == "WatchmodeTitleHasGenre":
            title_genres[row["src"]].append(row["dst"])
            edge_count += 1

print(f"  Loaded {edge_count} WatchmodeTitleHasGenre edges for {len(title_genres)} titles")


# ═══════════════════════════════════════════════════════════════════
# STAGE 5: Load source entities
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 5: Loading source entities...")

# Watchmode_Title: build name index
# name_lower → list of (id, props_dict)
wm_name_index = defaultdict(list)
wm_count = 0

# Podchaser_Podcast: build title index
# title_lower → list of (id, props_dict)
pc_title_index = defaultdict(list)
pc_count = 0

with open(os.path.join(BASE, "source_entities_watchmode_podcast_v2.csv"), "r") as f:
    reader = csv.DictReader(f)
    for row in reader:
        if row["node_type"] == "Watchmode_Title":
            props = parse_props(row)
            name = (props.get("name", "") or "").strip()
            if name:
                entry = {
                    "id": row["id"],
                    "name": name,
                    "media_type": props.get("media_type", ""),
                    "description": props.get("description", ""),
                    "release_date": props.get("release_date"),
                    "release_year": props.get("release_year"),
                    "runtime_minutes": props.get("runtime_minutes"),
                    "relevance_percentile": props.get("relevance_percentile"),
                    "original_language": props.get("original_language", ""),
                }
                wm_name_index[name.lower()].append(entry)
            wm_count += 1
        elif row["node_type"] == "Podchaser_Podcast":
            props = parse_props(row)
            title = (props.get("title", "") or "").strip()
            if title:
                entry = {
                    "id": row["id"],
                    "title": title,
                    "description": props.get("description", ""),
                    "language": props.get("language", ""),
                    "number_of_episodes": props.get("number_of_episodes"),
                    "avg_episode_length": props.get("avg_episode_length"),
                    "power_score": props.get("power_score"),
                    "start_date": props.get("start_date"),
                    "latest_episode_date": props.get("latest_episode_date"),
                    "status": props.get("status", ""),
                }
                pc_title_index[title.lower()].append(entry)
            pc_count += 1

print(f"  Watchmode_Title: {wm_count} loaded, {len(wm_name_index)} unique names indexed")
print(f"  Podchaser_Podcast: {pc_count} loaded, {len(pc_title_index)} unique titles indexed")


# ═══════════════════════════════════════════════════════════════════
# STAGE 6: Load watchmode persons
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 6: Loading watchmode persons...")

# title_name_lower → {"Actor": [names], "Creator": [names]}
persons_index = defaultdict(lambda: defaultdict(list))
with open(os.path.join(BASE, "watchmode_persons_v2.csv"), "r") as f:
    for row in csv.DictReader(f):
        title_lower = row["title_name"].strip().lower()
        persons_index[title_lower][row["job_type"]].append(row["person_name"])

print(f"  Loaded persons for {len(persons_index)} unique titles")


# ═══════════════════════════════════════════════════════════════════
# STAGE 7: Match and extract Movies / TV
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 7: Extracting Movie/TV profiles...")

# Media type preferences per vertical
MOVIE_TYPES = {"movie", "tv_movie", "short_film"}
TV_TYPES = {"tv_series", "tv_miniseries", "tv_special"}

def match_watchmode(canonical_name, vertical):
    """Match a canonical entity name to a Watchmode_Title entry.
    Returns (matched_entry, match_quality) or (None, None).
    """
    name_lower = canonical_name.lower().strip()
    preferred_types = MOVIE_TYPES if vertical == "movie" else TV_TYPES

    # 1. Exact match
    if name_lower in wm_name_index:
        candidates = wm_name_index[name_lower]
        # Prefer matching media_type
        preferred = [c for c in candidates if c["media_type"] in preferred_types]
        if preferred:
            return preferred[0], "exact"
        return candidates[0], "exact"

    # 2. Contains match: canonical name contained in source name
    contains_matches = []
    for src_name_lower, entries in wm_name_index.items():
        if name_lower in src_name_lower and len(name_lower) >= 3:
            contains_matches.extend([(e, len(src_name_lower)) for e in entries])

    if contains_matches:
        # Prefer matching media_type, then shortest name (closest to exact)
        preferred = [(e, l) for e, l in contains_matches if e["media_type"] in preferred_types]
        if preferred:
            preferred.sort(key=lambda x: x[1])
            return preferred[0][0], "contains"
        contains_matches.sort(key=lambda x: x[1])
        return contains_matches[0][0], "contains"

    return None, None


def get_genres_for_title(watchmode_id):
    """Get canonical Feeds genres for a Watchmode_Title via edges."""
    genre_ids = title_genres.get(watchmode_id, [])
    source_genres = []
    for gid in genre_ids:
        gname = genre_nodes.get(gid, "")
        if gname:
            source_genres.append(gname)

    # Translate to canonical Feeds genres
    canonical = set()
    for sg in source_genres:
        if sg in wm_genre_map:
            canonical.update(wm_genre_map[sg])
        else:
            canonical.add(sg)  # keep as-is if no mapping

    return sorted(canonical)


def get_persons_for_title(canonical_name):
    """Get cast and creators by title name."""
    name_lower = canonical_name.lower().strip()
    persons = persons_index.get(name_lower, {})
    actors = persons.get("Actor", [])[:5]
    creators = persons.get("Creator", [])[:3]
    return actors, creators


# Process movies and TV
movie_tv_profiles = []
match_stats = {"Movie": Counter(), "TV": Counter()}
genre_coverage = {"Movie": 0, "TV": 0}
release_date_coverage = {"Movie": 0, "TV": 0}
cast_coverage = {"Movie": 0, "TV": 0}
unmatched = {"Movie": [], "TV": []}

for entities, vertical_name in [(movies, "Movie"), (tvshows, "TV")]:
    for row in entities:
        props = parse_props(row)
        name = (props.get("name", "") or "").strip()
        desc = (props.get("description", "") or "").strip()
        vertical_lower = vertical_name.lower()

        # Match to Watchmode
        matched, quality = match_watchmode(name, vertical_lower)

        if matched:
            match_stats[vertical_name][quality] += 1
            wm_id = matched["id"]
            genres = get_genres_for_title(wm_id)
            actors, creators = get_persons_for_title(name)

            release_date = matched.get("release_date")
            release_year = matched.get("release_year")
            runtime = matched.get("runtime_minutes")
            rel_perc = matched.get("relevance_percentile")
            lang = matched.get("original_language", "")

            # Type coercion
            try:
                release_year = int(release_year) if release_year else None
            except:
                release_year = None
            try:
                runtime = int(float(runtime)) if runtime else None
            except:
                runtime = None
            try:
                rel_perc = float(rel_perc) if rel_perc else None
            except:
                rel_perc = None

            if genres:
                genre_coverage[vertical_name] += 1
            if release_date:
                release_date_coverage[vertical_name] += 1
            if actors:
                cast_coverage[vertical_name] += 1

            profile = {
                "entity_id": row["id"],
                "name": name,
                "vertical": vertical_lower,
                "description": desc,
                "canonical_genres": genres,
                "themes": [],
                "keywords": [],
                "franchise": None,
                "developer": None,
                "publisher": None,
                "directors": [],
                "cast": actors,
                "release_date": release_date if release_date else None,
                "release_year": release_year,
                "runtime_minutes": runtime,
                "language": lang if lang else None,
                "relevance_percentile": rel_perc,
                "source_match": wm_id,
                "match_quality": quality,
            }
        else:
            match_stats[vertical_name]["unmatched"] += 1
            unmatched[vertical_name].append(name)

            profile = {
                "entity_id": row["id"],
                "name": name,
                "vertical": vertical_lower,
                "description": desc,
                "canonical_genres": [],
                "themes": [],
                "keywords": [],
                "franchise": None,
                "developer": None,
                "publisher": None,
                "directors": [],
                "cast": [],
                "release_date": None,
                "release_year": None,
                "runtime_minutes": None,
                "language": None,
                "relevance_percentile": None,
                "source_match": None,
                "match_quality": "none",
            }

        movie_tv_profiles.append(profile)

print(f"  Movie match stats: {dict(match_stats['Movie'])}")
print(f"  TV match stats: {dict(match_stats['TV'])}")
print(f"  Total Movie/TV profiles: {len(movie_tv_profiles)}")
report["match_stats"] = {k: dict(v) for k, v in match_stats.items()}
report["genre_coverage"] = genre_coverage
report["release_date_coverage"] = release_date_coverage
report["cast_coverage"] = cast_coverage
report["unmatched"] = unmatched


# ═══════════════════════════════════════════════════════════════════
# STAGE 8: Extract Podcast profiles
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 8: Extracting Podcast profiles...")

def match_podchaser(canonical_name):
    """Match canonical podcast name to Podchaser_Podcast title."""
    name_lower = canonical_name.lower().strip()

    # 1. Exact match
    if name_lower in pc_title_index:
        return pc_title_index[name_lower][0], "exact"

    # 2. Contains match
    contains_matches = []
    for title_lower, entries in pc_title_index.items():
        if name_lower in title_lower and len(name_lower) >= 3:
            contains_matches.extend([(e, len(title_lower)) for e in entries])

    if contains_matches:
        contains_matches.sort(key=lambda x: x[1])
        return contains_matches[0][0], "contains"

    return None, None


podcast_profiles_all = []
pod_match_stats = Counter()
pod_desc_coverage = 0
pod_unmatched = []

for row in podcasts:
    props = parse_props(row)
    name = (props.get("name", "") or "").strip()
    desc = (props.get("description", "") or "").strip()

    matched, quality = match_podchaser(name)

    if matched:
        pod_match_stats[quality] += 1
        pc_id = matched["id"]

        # Extract fields
        ep_count = matched.get("number_of_episodes")
        avg_ep_len = matched.get("avg_episode_length")
        power = matched.get("power_score")
        status = matched.get("status", "")
        latest_ep = matched.get("latest_episode_date")
        lang = matched.get("language", "")

        # If canonical has no description but Podchaser does, use Podchaser's
        pc_desc = (matched.get("description", "") or "").strip()
        if not desc and pc_desc:
            desc = pc_desc

        # Type coercion
        try:
            ep_count = int(ep_count) if ep_count else None
        except:
            ep_count = None
        try:
            avg_ep_len = round(float(avg_ep_len) / 60) if avg_ep_len else None
        except:
            avg_ep_len = None
        try:
            power = float(power) if power else None
        except:
            power = None

        if desc:
            pod_desc_coverage += 1

        profile = {
            "entity_id": row["id"],
            "name": name,
            "vertical": "podcast",
            "description": desc,
            "canonical_genres": [],
            "themes": [],
            "keywords": [],
            "franchise": None,
            "developer": None,
            "publisher": None,
            "directors": [],
            "cast": [],
            "episode_count": ep_count,
            "avg_episode_length_mins": avg_ep_len,
            "power_score": power,
            "podcast_status": status if status else None,
            "latest_episode_date": latest_ep if latest_ep else None,
            "language": lang if lang else None,
            "source_match": pc_id,
            "match_quality": quality,
        }
    else:
        pod_match_stats["unmatched"] += 1
        pod_unmatched.append(name)

        if desc:
            pod_desc_coverage += 1

        profile = {
            "entity_id": row["id"],
            "name": name,
            "vertical": "podcast",
            "description": desc,
            "canonical_genres": [],
            "themes": [],
            "keywords": [],
            "franchise": None,
            "developer": None,
            "publisher": None,
            "directors": [],
            "cast": [],
            "episode_count": None,
            "avg_episode_length_mins": None,
            "power_score": None,
            "podcast_status": None,
            "latest_episode_date": None,
            "language": None,
            "source_match": None,
            "match_quality": "none",
        }

    podcast_profiles_all.append(profile)

print(f"  Podcast match stats: {dict(pod_match_stats)}")
print(f"  Total podcast profiles before filtering: {len(podcast_profiles_all)}")

# Filter: drop podcasts with no description
podcast_with_desc = [p for p in podcast_profiles_all if (p["description"] or "").strip()]
dropped_no_desc = len(podcast_profiles_all) - len(podcast_with_desc)
print(f"  Dropped {dropped_no_desc} podcasts with no description")

# Sort by power_score descending, use episode_count as fallback
def podcast_sort_key(p):
    ps = p.get("power_score")
    ep = p.get("episode_count")
    # power_score primary (higher first), episode_count fallback
    if ps is not None:
        return (1, ps)  # has power_score
    elif ep is not None:
        return (0, ep / 100000.0)  # fallback: scaled episode count
    else:
        return (0, 0)

podcast_with_desc.sort(key=podcast_sort_key, reverse=True)

# Keep top 2,000
podcast_profiles = podcast_with_desc[:2000]
cutoff_score = podcast_profiles[-1].get("power_score") if podcast_profiles else None
print(f"  Top 2,000 podcasts selected. Cutoff power_score: {cutoff_score}")

# Power score stats for the 2000
ps_values = [p["power_score"] for p in podcast_profiles if p["power_score"] is not None]
ps_values_sorted = sorted(ps_values)
report["podcast"] = {
    "match_stats": dict(pod_match_stats),
    "total_before_filter": len(podcast_profiles_all),
    "dropped_no_desc": dropped_no_desc,
    "with_desc": len(podcast_with_desc),
    "final_count": len(podcast_profiles),
    "desc_coverage": pod_desc_coverage,
    "unmatched": pod_unmatched,
    "power_score_stats": {
        "count": len(ps_values),
        "min": min(ps_values_sorted) if ps_values_sorted else None,
        "max": max(ps_values_sorted) if ps_values_sorted else None,
        "median": ps_values_sorted[len(ps_values_sorted)//2] if ps_values_sorted else None,
        "cutoff_2000": cutoff_score,
    },
    "top_5": [(p["name"], p["power_score"]) for p in podcast_profiles[:5]],
    "bottom_5": [(p["name"], p["power_score"]) for p in podcast_profiles[-5:]],
}


# ═══════════════════════════════════════════════════════════════════
# STAGE 9: Save output files
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 9: Saving output files...")

out_mt = os.path.join(BASE, "entity_profiles_movies_tv.json")
with open(out_mt, "w") as f:
    json.dump(movie_tv_profiles, f, indent=2, ensure_ascii=False)
print(f"  Saved {len(movie_tv_profiles)} Movie/TV profiles to {out_mt}")

out_pod = os.path.join(BASE, "entity_profiles_podcasts.json")
with open(out_pod, "w") as f:
    json.dump(podcast_profiles, f, indent=2, ensure_ascii=False)
print(f"  Saved {len(podcast_profiles)} Podcast profiles to {out_pod}")


# ═══════════════════════════════════════════════════════════════════
# STAGE 10: Generate extraction report
# ═══════════════════════════════════════════════════════════════════
print("\nSTAGE 10: Generating extraction report...")

total_ready = len(movie_tv_profiles) + len(podcast_profiles)

# Build report markdown
lines = []
lines.append("# Feeds.ai V2 Entity Profile Extraction Report")
lines.append("")
lines.append(f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M')}")
lines.append(f"**Verticals processed:** Movie, TV, Podcast (Games deferred)")
lines.append("")
lines.append("---")
lines.append("")

# Deduplication
lines.append("## 1. Deduplication Results")
lines.append("")
lines.append("For each (name, node_type) pair with duplicates, kept ONLY the row with the latest `created_at` timestamp.")
lines.append("")
lines.append("| Vertical | Before dedup | Duplicates removed | After dedup |")
lines.append("|----------|--------------|--------------------|-------------|")
for v in ["Movie", "TV", "Podcast"]:
    before = raw_counts.get(v, 0)
    removed = removed_counts.get(v, 0)
    after = clean_counts.get(v, 0)
    lines.append(f"| {v} | {before:,} | {removed:,} | {after:,} |")
total_before = sum(raw_counts.get(v, 0) for v in ["Movie", "TV", "Podcast"])
total_removed = sum(removed_counts.get(v, 0) for v in ["Movie", "TV", "Podcast"])
total_after = sum(clean_counts.get(v, 0) for v in ["Movie", "TV", "Podcast"])
lines.append(f"| **TOTAL** | **{total_before:,}** | **{total_removed:,}** | **{total_after:,}** |")
lines.append("")

# Clean unique entity counts
lines.append("## 2. Clean Unique Entity Counts")
lines.append("")
lines.append(f"- **Movie:** {len(movies):,}")
lines.append(f"- **TV:** {len(tvshows):,}")
lines.append(f"- **Podcast:** {len(podcasts):,}")
lines.append(f"- **Total:** {len(movies) + len(tvshows) + len(podcasts):,}")
lines.append("")

# Source match rates
lines.append("## 3. Source Match Rates")
lines.append("")
lines.append("### Movies")
ms = match_stats["Movie"]
m_total = sum(ms.values())
lines.append(f"- Exact match: {ms.get('exact', 0):,} ({100*ms.get('exact',0)/m_total:.1f}%)")
lines.append(f"- Contains match: {ms.get('contains', 0):,} ({100*ms.get('contains',0)/m_total:.1f}%)")
lines.append(f"- Unmatched: {ms.get('unmatched', 0):,} ({100*ms.get('unmatched',0)/m_total:.1f}%)")
lines.append("")
lines.append("### TV")
ts = match_stats["TV"]
t_total = sum(ts.values())
lines.append(f"- Exact match: {ts.get('exact', 0):,} ({100*ts.get('exact',0)/t_total:.1f}%)")
lines.append(f"- Contains match: {ts.get('contains', 0):,} ({100*ts.get('contains',0)/t_total:.1f}%)")
lines.append(f"- Unmatched: {ts.get('unmatched', 0):,} ({100*ts.get('unmatched',0)/t_total:.1f}%)")
lines.append("")
lines.append("### Podcasts")
ps_stats = pod_match_stats
p_total = sum(ps_stats.values())
lines.append(f"- Exact match: {ps_stats.get('exact', 0):,} ({100*ps_stats.get('exact',0)/p_total:.1f}%)")
lines.append(f"- Contains match: {ps_stats.get('contains', 0):,} ({100*ps_stats.get('contains',0)/p_total:.1f}%)")
lines.append(f"- Unmatched: {ps_stats.get('unmatched', 0):,} ({100*ps_stats.get('unmatched',0)/p_total:.1f}%)")
lines.append("")

# Genre coverage
lines.append("## 4. Genre Coverage (Movies/TV)")
lines.append("")
lines.append(f"- **Movie:** {genre_coverage['Movie']:,}/{len(movies):,} ({100*genre_coverage['Movie']/len(movies):.1f}%) have at least one genre")
lines.append(f"- **TV:** {genre_coverage['TV']:,}/{len(tvshows):,} ({100*genre_coverage['TV']/len(tvshows):.1f}%) have at least one genre")
lines.append("")

# Release date coverage
lines.append("## 5. Release Date Coverage (Movies/TV)")
lines.append("")
lines.append(f"- **Movie:** {release_date_coverage['Movie']:,}/{len(movies):,} ({100*release_date_coverage['Movie']/len(movies):.1f}%)")
lines.append(f"- **TV:** {release_date_coverage['TV']:,}/{len(tvshows):,} ({100*release_date_coverage['TV']/len(tvshows):.1f}%)")
lines.append("")

# Cast coverage
lines.append("## 6. Cast Coverage (Movies/TV)")
lines.append("")
lines.append(f"- **Movie:** {cast_coverage['Movie']:,}/{len(movies):,} ({100*cast_coverage['Movie']/len(movies):.1f}%) have at least one cast member")
lines.append(f"- **TV:** {cast_coverage['TV']:,}/{len(tvshows):,} ({100*cast_coverage['TV']/len(tvshows):.1f}%) have at least one cast member")
lines.append("")

# Podcast description coverage
lines.append("## 7. Podcast Description Coverage")
lines.append("")
lines.append(f"- With description: {pod_desc_coverage:,}/{len(podcasts):,} ({100*pod_desc_coverage/len(podcasts):.1f}%)")
lines.append(f"- Dropped (no description): {dropped_no_desc:,}")
lines.append("")

# Power score distribution
ps_info = report["podcast"]["power_score_stats"]
lines.append("## 8. Podcast Power Score Distribution (Top 2,000)")
lines.append("")
lines.append(f"- Count with power_score: {ps_info['count']:,}")
lines.append(f"- Min: {ps_info['min']}")
lines.append(f"- Max: {ps_info['max']}")
lines.append(f"- Median: {ps_info['median']}")
lines.append(f"- Cutoff at 2,000th podcast: {ps_info['cutoff_2000']}")
lines.append("")

# Top/bottom 5 podcasts
lines.append("### Top 5 podcasts by power_score")
lines.append("")
lines.append("| Rank | Name | Power Score |")
lines.append("|------|------|-------------|")
for i, (name, ps) in enumerate(report["podcast"]["top_5"], 1):
    lines.append(f"| {i} | {name} | {ps} |")
lines.append("")

lines.append("### Bottom 5 podcasts that made the cut")
lines.append("")
lines.append("| Rank | Name | Power Score |")
lines.append("|------|------|-------------|")
for i, (name, ps) in enumerate(report["podcast"]["bottom_5"], 1996):
    lines.append(f"| {i} | {name} | {ps} |")
lines.append("")

# Total entities ready
lines.append("## 9. Total Entities Ready for Composition")
lines.append("")
lines.append(f"- **Movies:** {len(movies):,}")
lines.append(f"- **TV:** {len(tvshows):,}")
lines.append(f"- **Podcasts:** {len(podcast_profiles):,} (top 2,000 by power_score)")
lines.append(f"- **TOTAL:** {total_ready:,}")
lines.append("")

# Unmatched entities
lines.append("## 10. Unmatched Entities")
lines.append("")
lines.append("Entities that could not be matched to any source entity by name.")
lines.append("")

for v in ["Movie", "TV"]:
    ulist = unmatched[v]
    lines.append(f"### {v} — {len(ulist)} unmatched")
    lines.append("")
    if ulist:
        for name in sorted(ulist):
            lines.append(f"- {name}")
    else:
        lines.append("*(none)*")
    lines.append("")

lines.append(f"### Podcast — {len(pod_unmatched)} unmatched")
lines.append("")
if pod_unmatched:
    # Show all if manageable, otherwise top 50
    display = sorted(pod_unmatched)
    if len(display) > 100:
        lines.append(f"*Showing first 100 of {len(display)} unmatched:*")
        lines.append("")
        display = display[:100]
    for name in display:
        lines.append(f"- {name}")
else:
    lines.append("*(none)*")
lines.append("")

# Write report
report_path = os.path.join(BASE, "EXTRACTION_REPORT_V2.md")
with open(report_path, "w") as f:
    f.write("\n".join(lines))
print(f"  Saved extraction report to {report_path}")

print(f"\n{'='*60}")
print(f"DONE — {total_ready:,} entity profiles ready for composition")
print(f"  Movies: {len(movies):,}")
print(f"  TV: {len(tvshows):,}")
print(f"  Podcasts: {len(podcast_profiles):,}")
print(f"{'='*60}")
