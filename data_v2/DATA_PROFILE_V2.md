# Feeds.ai V2 Data Profile Report

**Generated:** 2026-05-28
**Data directory:** `/home/ishaan/Desktop/Feedsai-pipeline/data_v2/`

---

## 1. File Inventory

| File | Rows | Columns | Size |
|------|------|---------|------|
| canonical_entities_v2.csv | 22,520 | 6 | 16 MB |
| source_entities_watchmode_podcast_v2.csv | 317,768 | 5 | 352 MB |
| property_nodes_v2.csv | 645,429 | 5 | 217 MB |
| edges_v2.csv | 1,427,417 | 3 | 92 MB |
| watchmode_persons_v2.csv | 152,442 | 3 | 6 MB |
| **TOTAL** | **2,565,576** | | **683 MB** |

---

## 2. canonical_entities_v2.csv

**Columns:** `id`, `label`, `node_key`, `properties` (JSON), `node_type`, `created_at`

### 2a. Raw counts by node_type

| node_type | Count |
|-----------|-------|
| Podcast | 18,459 |
| Game | 2,145 |
| Movie | 1,160 |
| TV | 756 |
| **TOTAL** | **22,520** |

### 2b. Test / scaffold data identified

**Total test rows: 154** (all Games)

| Detection rule | Count |
|---------------|-------|
| Prefix match (`FollowCalendar_`, `FollowingPlaylist_`, `PropertyFollow_`, `UserPropertyVerify_`, `MediaFilter_`) | 121 |
| Random alphanumeric hash (lowercase+digits, 8-14 chars, no description) | 33 |
| Exact name match (`Custom Property Title`, etc.) | 0 |
| Description contains "Property for media type filter test" | 0 |

**Sample test entities:**
```
[Game] 'FollowCalendar_Property_1779372761808'
[Game] 'FollowingPlaylist_Property_1779372768124'
[Game] 'PropertyFollow_Property_1779372793528'
[Game] '80wagwb90p'  (random hash, no description)
[Game] '7usv88ncp56' (random hash, no description)
```

**Note:** The exact-name and test-description patterns matched 0 rows in this dataset. The user-specified rules may apply to future data or were already cleaned upstream.

### 2c. CLEAN counts (after removing 154 test rows)

| node_type | Clean count | Unique names | Duplicate name pairs |
|-----------|-------------|--------------|---------------------|
| Podcast | 18,459 | 18,359 | 97 |
| Game | 1,991 | 1,043 | 925 |
| Movie | 1,160 | 657 | 503 |
| TV | 756 | 297 | 273 |
| **TOTAL** | **22,366** | **20,356** | **1,798** |

**IMPORTANT — Massive duplication:** 1,798 (name, type) pairs have 2+ rows. This is especially severe in Games (925/1,043 unique names appear in duplicate rows) and Movies (503/657). Deduplication will be required before building entity profiles.

### 2d. Description coverage

| Vertical | Has description | Pct |
|----------|----------------|-----|
| Game | 1,983 / 1,991 | 99.6% |
| Movie | 1,158 / 1,160 | 99.8% |
| TV | 755 / 756 | 99.9% |
| Podcast | 18,275 / 18,459 | 99.0% |

### 2e. Properties JSON keys

All canonical entities share the same key structure:
- `name`, `description`, `source`, `created_at`, `updated_at`, `ingested_at`
- Vertical-specific ID: `game_id` (Games), `movie_id` (Movies), `tv_id` (TV), `podcast_id` (Podcasts)
- `media_source_id` (Games, TV, Podcasts) or `media_type_id` (Movies)

### 2f. Sample entities (3 per vertical)

#### Game
```json
{
    "name": "Hytale",
    "description": "Hytale combines the scope of a sandbox with the depth of a roleplaying game, immersing players in a procedurally generated world where teetering towers and deep dungeons promise rich rewards...",
    "game_id": "1", "source": "feeds", "media_source_id": 1
}
{
    "name": "AI Limit",
    "description": "In the distant future when civilization is on the verge of extinction, people follow the legend of the Elysium in the last city, Havenswell. In this post-apocalyptic wasteland sci-fi ARPG...",
    "game_id": "10", "source": "feeds", "media_source_id": 1
}
{
    "name": "Labyrinth of the Demon King",
    "description": "Venture through the Labyrinth Of The Demon King, solving puzzles and fighting fearsome monsters in an epic quest...",
    "game_id": "100", "source": "feeds", "media_source_id": 1
}
```

#### Movie
```json
{
    "name": "My Father, the BTK Killer",
    "description": "A woman recounts what it was like to grow up with a parent who seemed ordinary at home while secretly committing horrific crimes...",
    "movie_id": "1000", "source": "feeds", "media_type_id": 3
}
{
    "name": "The Patron Saint of Roadkill",
    "description": "Andy's bogus job search comes to an end when they accept a mysterious position giving funerals to roadkill.",
    "movie_id": "1009", "source": "feeds", "media_type_id": 3
}
{
    "name": "Lost Horizon",
    "description": "A former soldier, now working for hire, fights to rescue the innocent in a land torn by war...",
    "movie_id": "1033", "source": "feeds", "media_type_id": 3
}
```

#### TV
```json
{
    "name": "The Dark Wizard",
    "description": "This series follows a world-famous, controversial extreme athlete pushing the limits through climbing, base jumping, and highline walking...",
    "tv_id": "1581", "source": "feeds", "media_source_id": 3
}
{
    "name": "Seeking Persephone",
    "description": "To protect her family's future, a young woman enters a marriage of necessity with a powerful, emotionally distant nobleman...",
    "tv_id": "1584", "source": "feeds", "media_source_id": 3
}
{
    "name": "Your Friendly Neighborhood Spider-Man",
    "description": "Peter Parker is starting his journey toward heroism, but things quickly become anything but simple...",
    "tv_id": "1585", "source": "feeds", "media_source_id": 3
}
```

#### Podcast
```json
{
    "name": "Ali on the Run Show",
    "description": "Every week on the Ali on the Run Show, I talk with inspiring people who lead interesting lives on the run and beyond...",
    "podcast_id": "10001", "source": "feeds", "media_source_id": 4
}
{
    "name": "Neura Pod (All Things Neuralink)",
    "description": "Neura Pod is a series covering topics related to Neuralink, Inc. Topics such as brain-machine interfaces...",
    "podcast_id": "10002", "source": "feeds", "media_source_id": 4
}
{
    "name": "Ruslan KD Podcast",
    "description": "The Ruslan KD Podcast bridges the gap between faith and real life...",
    "podcast_id": "10003", "source": "feeds", "media_source_id": 4
}
```

---

## 3. source_entities_watchmode_podcast_v2.csv

**Columns:** `id`, `label`, `node_key`, `properties` (JSON), `node_type`

### 3a. Counts by node_type

| node_type | Count |
|-----------|-------|
| Watchmode_Title | 240,906 |
| Podchaser_Podcast | 76,862 |
| **TOTAL** | **317,768** |

### 3b. Watchmode_Title

#### All unique property keys (from 100-row sample)
```
backdrop_url, description, id, ingested_at, media_type, name,
original_language, original_title, release_date, release_year,
relevance_percentile, runtime_minutes, source, thumbnail_url,
user_rating, watchmode_title_id
```

**Key: `media_type`** — differentiates movies vs TV:

| media_type | Count |
|-----------|-------|
| movie | 150,652 |
| tv_series | 38,188 |
| short_film | 36,170 |
| tv_miniseries | 7,666 |
| tv_movie | 5,691 |
| tv_special | 2,539 |

#### Field coverage

| Field | Count | Pct |
|-------|-------|-----|
| name | 240,906 | 100% |
| release_date | 240,906 | 100% |
| relevance_percentile | 240,906 | 100% |
| original_language | 240,886 | 100% |
| release_year | 239,094 | 99.2% |
| runtime_minutes | 215,435 | 89.4% |
| description | 199,688 | 82.9% |
| user_rating | present in some | — |

**Note:** No `type` field exists — use `media_type` instead. No `imdb_id` or `tmdb_id` in this export.

#### relevance_percentile stats
- Range: 0.0 – 100.0
- Median: 48.0, Mean: 39.6
- p25: 0.0, p75: 77.0

#### Sample Watchmode_Title
```json
{
    "name": "Homemade Gatorade",
    "description": "A woman embarks on a road trip to deliver homemade Gatorade to a mysterious online buyer...",
    "media_type": "movie",
    "release_date": "2025-01-22",
    "release_year": 2025,
    "runtime_minutes": 14,
    "relevance_percentile": 46.2,
    "original_language": "en",
    "watchmode_title_id": "11000016"
}
```

### 3c. Podchaser_Podcast

#### All unique property keys (from 100-row sample)
```
avg_episode_length, days_between_episodes, description, html_description,
image_url, ingested_at, language, latest_episode_date, number_of_episodes,
podchaser_podcast_id, power_score, rating_average, rating_count,
review_count, rss_url, sanitized_description, source, start_date,
status, title, url, web_url
```

**IMPORTANT:** Podchaser uses `title` (not `name`) for the podcast name. The `name` field is always empty.

#### Field coverage

| Field | Count | Pct |
|-------|-------|-----|
| title | 76,856 | 100% |
| language | 76,862 | 100% |
| status | 76,862 | 100% |
| image_url | 76,862 | 100% |
| rss_url | 76,847 | 100% |
| number_of_episodes | 76,776 | 99.9% |
| description | 76,289 | 99.3% |
| web_url | 74,545 | 97.0% |
| power_score | 65,461 | 85.2% |

#### power_score stats
- Range: 0.0 – 99.0
- Median: 23.05, Mean: 24.3
- p25: 0.0, p75: 45.15

#### Sample Podchaser_Podcast
```json
{
    "title": "Unreasonable Health with Regan Archibald",
    "description": "My name is Regan Archibald and I want you to have Unreasonable Health...",
    "power_score": 42.5,
    "number_of_episodes": 312,
    "language": "English",
    "status": "ACTIVE",
    "start_date": "2018-06-15",
    "avg_episode_length": 28,
    "days_between_episodes": 7,
    "podchaser_podcast_id": "1000082"
}
```

---

## 4. property_nodes_v2.csv

**Columns:** `id`, `label`, `node_key`, `properties` (JSON), `node_type`

### 4a. Counts by node_type

| node_type | Count |
|-----------|-------|
| IGDB_ReleaseDate | 557,677 |
| IGDB_Company | 70,162 |
| Podchaser_Creator | 7,674 |
| IGDB_Keyword | 6,990 |
| IGDB_Franchise | 2,611 |
| IGDB_Platform | 220 |
| Watchmode_Genre | 37 |
| IGDB_Genre | 23 |
| IGDB_Theme | 22 |
| IGDB_PlayerPerspective | 7 |
| IGDB_GameMode | 6 |
| **TOTAL** | **645,429** |

**Note:** `Podchaser_Creator` nodes (7,674) have **empty properties** — no name, no metadata. They are ID-only stubs used as edge targets.

### 4b. Full taxonomy lists

#### Watchmode_Genre (37 genres — for Movies/TV)
```
Action, Action & Adventure, Adult, Adventure, Animation, Anime,
Biography, Comedy, Crime, Documentary, Drama, Family, Fantasy, Food,
Game Show, History, Horror, Kids, Music, Musical, Mystery, Nature,
News, Reality, Romance, Sci-Fi & Fantasy, Science Fiction, Soap,
Sports, Supernatural, TV Movie, Talk, Thriller, Travel, War,
War & Politics, Western
```

#### IGDB_Genre (23 genres — for Games)
```
Adventure, Arcade, Card & Board Game, Fighting,
Hack and slash/Beat 'em up, Indie, MOBA, Music, Pinball, Platform,
Point-and-click, Puzzle, Quiz/Trivia, Racing, Real Time Strategy (RTS),
Role-playing (RPG), Shooter, Simulator, Sport, Strategy, Tactical,
Turn-based strategy (TBS), Visual Novel
```

#### IGDB_Theme (22 themes — for Games)
```
4X (explore, expand, exploit, and exterminate), Action, Business,
Comedy, Drama, Educational, Erotic, Fantasy, Historical, Horror, Kids,
Mystery, Non-fiction, Open world, Party, Romance, Sandbox,
Science fiction, Stealth, Survival, Thriller, Warfare
```

#### IGDB_GameMode (6 modes)
```
Battle Royale, Co-operative, Massively Multiplayer Online (MMO),
Multiplayer, Single player, Split screen
```

#### IGDB_PlayerPerspective (7 perspectives)
```
Auditory, Bird view / Isometric, First person, Side view, Text,
Third person, Virtual Reality
```

### 4c. Sample property nodes

#### IGDB_Company
```json
{"name": "Electronic Arts", "company_id": "1", "slug": "electronic-arts",
 "description": "Electronic Arts is a leading global interactive entertainment software company..."}
{"name": "LucasArts", "company_id": "10", "slug": "lucasarts",
 "description": "With titles on consoles, PCs, and mobile devices..."}
```

#### IGDB_Franchise
```json
{"name": "Star Wars", "franchise_id": "1", "slug": "star-wars"}
{"name": "Sid Meier", "franchise_id": "10", "slug": "sid-meier"}
{"name": "Spongebob Squarepants", "franchise_id": "100", "slug": "spongebob-squarepants"}
```

#### IGDB_Keyword
```json
{"name": "modern warfare", "keyword_id": "1"}
{"name": "multitouch", "keyword_id": "100"}
{"name": "monomyth", "keyword_id": "10006"}
```

#### Watchmode_Genre
```json
{"name": "Action", "watchmode_genre_id": "1", "tmdb_genre_id": "28"}
{"name": "History", "watchmode_genre_id": "10", "tmdb_genre_id": "36"}
{"name": "Horror", "watchmode_genre_id": "11", "tmdb_genre_id": "27"}
```

#### IGDB_ReleaseDate
```json
{"release_date": "1994-03-01", "platform_id": 19, "region_id": 8, "release_date_id": "100010"}
{"release_date": "1993-04-23", "platform_id": 19, "region_id": 8, "release_date_id": "100012"}
```

---

## 5. edges_v2.csv

**Columns:** `src`, `dst`, `relationship`

### 5a. Full relationship type breakdown

| Relationship | Count | Description |
|-------------|-------|-------------|
| WatchmodeTitleSimilarTo | 452,347 | Movie/TV similarity graph |
| WatchmodeTitleHasGenre | 388,279 | Movie/TV → Watchmode_Genre |
| PodchaserPodcastHasEpisode | 241,183 | Podcast → Episode (62,949 unique podcasts) |
| IGDBGameHasReleaseDate | 78,950 | Game → release date/platform/region |
| IGDBGameHasGenre | 63,105 | Game → IGDB_Genre |
| IGDBGameHasKeyword | 41,283 | Game → IGDB_Keyword |
| IGDBGameHasMode | 33,721 | Game → IGDB_GameMode |
| IGDBGameHasTheme | 30,833 | Game → IGDB_Theme |
| PodcastMapsTo | 18,497 | Canonical Podcast → Property node |
| IGDBGameHasPublisher | 17,575 | Game → IGDB_Company (publisher) |
| IGDBGameHasDeveloper | 15,555 | Game → IGDB_Company (developer) |
| IGDBGameHasPerspective | 13,953 | Game → IGDB_PlayerPerspective |
| IGDBGameSimilarTo | 13,691 | Game similarity graph |
| WatchmodeTitleHasRole | 12,007 | Movie/TV → Watchmode_Person |
| GameMapsTo | 2,331 | Canonical Game → Property node |
| IGDBGameInFranchise | 2,116 | Game → IGDB_Franchise |
| MovieMapsTo | 1,197 | Canonical Movie → Property node |
| TVMapsTo | 794 | Canonical TV → Property node |
| **TOTAL** | **1,427,417** | |

### 5b. Canonical entity mapping edges

Only canonical entities (Game:, Movie:, TV:, Podcast:) appear as edge **sources**, and only in MapsTo relationships. All MapsTo edges point to `Property:*` destination nodes, which are **not present** in property_nodes_v2.csv — they appear to be internal knowledge graph constructs.

| Mapping edge | Count | Canonical entities mapped |
|-------------|-------|--------------------------|
| PodcastMapsTo | 18,497 | ~18,497 of 18,459 canonical podcasts |
| GameMapsTo | 2,331 | ~2,331 of 1,991 clean games |
| MovieMapsTo | 1,197 | 1,197 of 1,160 canonical movies |
| TVMapsTo | 794 | 794 of 756 canonical TV shows |

### 5c. Key observations for pipeline design

1. **IGDB edges reference ~25,137 unique IGDB_Game IDs** but only 84 overlap with canonical `game_id` values. The IGDB source data uses its own ID namespace (`IGDB_Game:XXXXX`), separate from canonical entity IDs.

2. **No direct canonical-to-source edges exist.** Canonical entities connect to `Property:` nodes via MapsTo; source entities (IGDB_Game, Watchmode_Title, Podchaser_Podcast) connect to property nodes via Has* edges. The entity resolution/matching strategy must be defined at profile-building time.

3. **WatchmodeTitleSimilarTo (452K edges)** and **IGDBGameSimilarTo (13.7K edges)** provide pre-computed similarity graphs that could supplement or validate our embedding-based similarity.

4. **WatchmodeTitleHasRole (12K edges)** links Watchmode_Title entities to Watchmode_Person nodes (not in our data files), but **watchmode_persons_v2.csv** provides the same cast/creator information by title_name, making name-based joins the practical approach for Movies/TV.

---

## 6. watchmode_persons_v2.csv

**Columns:** `person_name`, `job_type`, `title_name`

| Metric | Value |
|--------|-------|
| Total rows | 152,442 |
| Unique title_names | 33,651 |
| Unique person_names | 65,362 |

### 6a. Breakdown by job_type

| job_type | Count |
|----------|-------|
| Actor | 150,995 |
| Creator | 1,447 |

**Note:** No "Director" job_type. TV series creators are captured, but movie directors are **not present** in this file. Director data will need to come from another source or be omitted for V2.

### 6b. Sample rows

| person_name | job_type | title_name |
|-------------|----------|------------|
| Karl Spiehs | Actor | "Auf der Alm da gibt's koa Sünd" - Die Erotikfilme... |
| Ralf Wolter | Actor | "Auf der Alm da gibt's koa Sünd" - Die Erotikfilme... |
| Karl Dall | Actor | "Auf der Alm da gibt's koa Sünd" - Die Erotikfilme... |
| Zachi Noy | Actor | "Auf der Alm da gibt's koa Sünd" - Die Erotikfilme... |
| Leo Moser | Actor | "Auf der Alm da gibt's koa Sünd" - Die Erotikfilme... |

---

## 7. Genre Mapping File

**File:** `genre_mappings.csv` — **NOT FOUND** in project directory. The user specified `/home/ishaan/Desktop/Feedsai-pipeline/config_tables/dimensions/genre_mappings.csv` but the `config_tables/` directory does not exist. This file is needed to map IGDB and Watchmode source genres to canonical Feeds genres.

---

## 8. Summary & Key Issues for Entity Profile Building

### Scale comparison: V1 → V2

| Vertical | V1 entities | V2 clean entities | V2 unique names |
|----------|-------------|-------------------|-----------------|
| Game | 956 | 1,991 | 1,043 |
| Movie | 547 | 1,160 | 657 |
| TV | 254 | 756 | 297 |
| Podcast | 0 | 18,459 | 18,359 |
| **TOTAL** | **1,757** | **22,366** | **20,356** |

### Critical issues to resolve before profile extraction

1. **Deduplication (1,798 name+type pairs have 2+ rows).** Must decide: keep first? keep most recent? merge? This is the largest data quality issue.

2. **No genre_mappings.csv found.** Need this file to map IGDB genres (23) and Watchmode genres (37) to canonical Feeds genres.

3. **Canonical-to-source entity matching.** No direct mapping exists between canonical entity IDs and source entity IDs (Watchmode_Title, IGDB_Game, Podchaser_Podcast). For entity profile enrichment:
   - **Movies/TV:** Must match by name against Watchmode_Title entities
   - **Games:** Must match by name against IGDB_Game source entities (not in current files — waiting on IGDB_Game descriptions file)
   - **Podcasts:** Must match by name against Podchaser_Podcast source entities

4. **Podcasts are the dominant vertical (18,459 / 22,366 = 82.5%).** Composition LLM costs and embedding API costs will be heavily weighted toward podcasts.

5. **Podchaser_Creator nodes have empty properties (0/7,674 have data).** Creator names for podcasts are not available through property_nodes; need to check if edge-based lookup to Podchaser_Creator IDs yields anything or if creator names must come from elsewhere.

6. **No director data in watchmode_persons_v2.csv.** Only Actor (151K) and Creator (1.4K) job types. Director information for movies is missing.

7. **Games deferred.** IGDB_Game source entity file with descriptions still pending from client. Current session should process Movies, TV, and Podcasts only.

### Available enrichment paths per vertical

| Vertical | Description | Genres | Themes/Keywords | Franchise | Cast/Crew | Similarity graph |
|----------|-------------|--------|-----------------|-----------|-----------|-----------------|
| Movie | canonical (99.8%) | via Watchmode_Title edges → Watchmode_Genre | — | — | watchmode_persons (Actor only) | WatchmodeTitleSimilarTo (452K) |
| TV | canonical (99.9%) | via Watchmode_Title edges → Watchmode_Genre | — | — | watchmode_persons (Actor + Creator) | WatchmodeTitleSimilarTo (452K) |
| Podcast | canonical (99.0%) | — | — | — | Podchaser_Creator (empty props) | — |
| Game | canonical (99.6%) | via IGDB edges → IGDB_Genre | IGDB_Theme, IGDB_Keyword | IGDB_Franchise | — | IGDBGameSimilarTo (13.7K) |

### Source data richness

| Source | Total entities | With description | Key metadata |
|--------|---------------|-----------------|--------------|
| Watchmode_Title | 240,906 | 199,688 (82.9%) | media_type, release_date, runtime, relevance_percentile, original_language |
| Podchaser_Podcast | 76,862 | 76,289 (99.3%) | power_score, number_of_episodes, avg_episode_length, status, language, start_date |
