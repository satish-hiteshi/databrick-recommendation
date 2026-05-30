# Feeds.ai V2 — Extra Movies & TV Shows Extraction Report

**Generated:** 2026-05-29 13:46
**Source:** source_entities_watchmode_podcast_v2.csv (Watchmode_Title)
**Outputs:** entity_profiles_movies_extra.json (1,000 movies), entity_profiles_tv_extra.json (1,000 TV shows)

---

## 1. Source Pool

| Metric | Movies | TV Shows |
|--------|--------|----------|
| Total Watchmode entries | 192,513 | 45,854 |
| Dropped: no description (<=20 chars) | 28,064 | 13,837 |
| Excluded: name overlap with existing | 940 | 310 |
| Remaining candidates | 163,509 | 31,707 |
| **Selected (top by relevance_percentile)** | **1,000** | **1,000** |

## 2. Selection Criteria

- **Movies:** media_type = 'movie' (also includes tv_movie, short_film)
- **TV Shows:** media_type IN ('tv_series', 'tv_miniseries')
- Must have description > 20 characters
- Name (case-insensitive) must NOT match any existing profile
- Selected top 1,000 by relevance_percentile (highest first)

### Relevance Percentile Ranges

| Vertical | Min | Max | Avg |
|----------|-----|-----|-----|
| Movies | 99.0 | 100.0 | 99.9 |
| TV Shows | 98.0 | 100.0 | 99.4 |

## 3. Overlap Verification

- Movie name overlaps with existing: **0**
- TV name overlaps with existing: **0**
- **CONFIRMED: Zero overlap with existing entity_profiles_movies_tv.json**

## 4. Metadata Coverage

| Field | Movies | % | TV Shows | % |
|-------|--------|---|----------|---|
| Genre (>=1) | 1,000 | 100.0% | 1,000 | 100.0% |
| Cast (>=1 actor) | 257 | 25.7% | 191 | 19.1% |
| Directors/Creators | 4 | 0.4% | 9 | 0.9% |
| Release date | 1,000 | 100.0% | 1,000 | 100.0% |
| Release year | 1,000 | 100.0% | 1,000 | 100.0% |
| Runtime | 976 | 97.6% | 438 | 43.8% |
| Language | 1,000 | 100.0% | 1,000 | 100.0% |

## 5. Genre Distribution

### Movies

| Genre | Count | % |
|-------|-------|---|
| Drama | 439 | 43.9% |
| Comedy | 283 | 28.3% |
| Thriller | 235 | 23.5% |
| Action | 224 | 22.4% |
| Horror | 156 | 15.6% |
| Adventure | 151 | 15.1% |
| Crime | 127 | 12.7% |
| Science Fiction | 125 | 12.5% |
| Romance | 121 | 12.1% |
| Fantasy | 119 | 11.9% |
| Mystery | 102 | 10.2% |
| Animation | 92 | 9.2% |
| History | 80 | 8.0% |
| Family | 72 | 7.2% |
| Documentary | 61 | 6.1% |
| Music | 54 | 5.4% |
| War | 36 | 3.6% |
| Western | 8 | 0.8% |
| TV Movie | 8 | 0.8% |

### TV Shows

| Genre | Count | % |
|-------|-------|---|
| Drama | 747 | 74.7% |
| Comedy | 317 | 31.7% |
| Crime | 312 | 31.2% |
| Mystery | 257 | 25.7% |
| Action | 231 | 23.1% |
| Science Fiction | 190 | 19.0% |
| Thriller | 180 | 18.0% |
| Fantasy | 174 | 17.4% |
| Animation | 136 | 13.6% |
| Adventure | 136 | 13.6% |
| Romance | 114 | 11.4% |
| Documentary | 67 | 6.7% |
| Horror | 53 | 5.3% |
| History | 49 | 4.9% |
| Supernatural | 45 | 4.5% |
| War | 31 | 3.1% |
| Family | 26 | 2.6% |
| Sports | 26 | 2.6% |
| Reality / Unscripted | 19 | 1.9% |
| Music | 16 | 1.6% |
| Kids | 10 | 1.0% |
| Western | 9 | 0.9% |
| Soap | 1 | 0.1% |

## 6. Top 10 Movies by Relevance Percentile (sanity check)

| Rank | Name | Rel% | Genres | Year | Language |
|------|------|------|--------|------|----------|
| 1 | Billie Eilish - Hit Me Hard and Soft: The Tour (Live in 3D) | 100.0 | Documentary, Music | 2026 | en |
| 2 | Dungeons & Dragons: Honor Among Thieves | 100.0 | Adventure, Comedy, Fantasy | 2023 | en |
| 3 | The Bus: A French Football Mutiny | 100.0 | Documentary | 2026 | fr |
| 4 | Fantastic Beasts: The Secrets of Dumbledore | 100.0 | Adventure, Fantasy | 2022 | en |
| 5 | Fast X | 100.0 | Action, Crime, Thriller | 2023 | en |
| 6 | F9 | 100.0 | Action, Adventure, Crime | 2021 | en |
| 7 | In the Heights | 100.0 | Drama, Romance | 2021 | en |
| 8 | Jurassic World: Dominion | 100.0 | Adventure, Science Fiction, Thriller | 2022 | en |
| 9 | Minions: The Rise of Gru | 100.0 | Animation, Comedy, Crime, Family, Science Fiction | 2022 | en |
| 10 | Red Notice | 100.0 | Action, Comedy, Crime | 2021 | en |

## 7. Top 10 TV Shows by Relevance Percentile (sanity check)

| Rank | Name | Rel% | Genres | Year | Language |
|------|------|------|--------|------|----------|
| 1 | The Stand | 100.0 | Drama, Fantasy, Horror, Science Fiction, Supernatural | 2020 | en |
| 2 | INVINCIBLE | 100.0 | Action, Animation, Drama, Science Fiction | 2021 | en |
| 3 | Shadow and Bone | 100.0 | Action, Adventure, Drama, Fantasy | 2021 | en |
| 4 | Obi-Wan Kenobi | 100.0 | Action, Adventure, Science Fiction | 2022 | en |
| 5 | The Last of Us | 100.0 | Action, Drama, Horror | 2023 | en |
| 6 | Tokyo Vice | 100.0 | Crime, Drama | 2022 | en |
| 7 | The Sandman | 100.0 | Action, Adventure, Drama, Fantasy | 2022 | en |
| 8 | Severance | 100.0 | Drama, Mystery, Science Fiction | 2022 | en |
| 9 | Platonic | 100.0 | Comedy | 2023 | en |
| 10 | Jeen-yuhs: A Kanye Trilogy | 100.0 | Documentary, Music | 2022 | en |

## 8. Total New Entities

| Vertical | Count |
|----------|-------|
| Extra movies | 1,000 |
| Extra TV shows | 1,000 |
| **Total new** | **2,000** |

### Combined with existing profiles

| Vertical | Existing | Extra | Total |
|----------|----------|-------|-------|
| Movies | 656 | 1,000 | 1,656 |
| TV Shows | 297 | 1,000 | 1,297 |
| **Total** | **953** | **2,000** | **2,953** |
