# Feeds.ai V2 — IGDB Games Extraction Report

**Generated:** 2026-05-29 11:45
**Source:** source_entities_igdb_v2.csv
**Output:** entity_profiles_games_source.json (2,000 games)

---

## 1. Source Data Overview

| Metric | Count |
|--------|-------|
| Total IGDB_Game rows | 28,618 |
| Have 'description' field | 28,618 |
| Non-empty descriptions (>10 chars) | 25,298 |
| Have critic_rating | 2,732 |
| Have user_rating | 2,011 |
| Have BOTH ratings | 1,263 |
| Have EITHER rating | 3,480 |

## 2. Selection Criteria & Cutoffs

From the pool of games with non-empty descriptions (>10 characters), 2,000 were selected using this priority:

1. **Tier 1** — Games with BOTH critic_rating AND user_rating (most notable)
2. **Tier 2** — Games with EITHER rating
3. **Tier 3** — Games with neither rating, sorted by description length (longer = richer)

| Tier | Count |
|------|-------|
| Tier 1 (both ratings) | 1,263 |
| Tier 2 (either rating) | 737 |
| Tier 3 (desc length only) | 0 |
| **Total selected** | **2,000** |

Eligible pool: 25,298 games with non-empty descriptions
Cutoff game: desc_len=296, has_both_ratings=False, has_any_rating=True

## 3. Metadata Coverage (of 2,000 selected)

| Field | Count | % |
|-------|-------|---|
| Genre (>=1 canonical genre) | 1,997 | 99.8% |
| Theme (>=1 theme) | 1,909 | 95.5% |
| Keyword (>=1 keyword) | 1,563 | 78.2% |
| Franchise | 592 | 29.6% |
| Developer | 1,960 | 98.0% |
| Publisher | 1,966 | 98.3% |
| Release date | 2,000 | 100.0% |
| Critic rating | 1,753 | 87.7% |
| User rating | 1,510 | 75.5% |

## 4. Rating Statistics (selected games)

**Critic Rating:** min=0.00, max=100.00, avg=77.26, count=1,753

**User Rating:** min=14.07, max=99.73, avg=73.23, count=1,510

## 5. Top 10 Games by Critic Rating (sanity check)

| Rank | Name | Critic Rating | User Rating | Genres |
|------|------|---------------|-------------|--------|
| 1 | Final Fantasy VII Remake: Episode Intermission | 100.00 | 77.16 | Adventure, Role-Playing |
| 2 | The Legend of Zelda: Tears of the Kingdom - Nintendo Switch 2 Edition | 100.00 | 99.73 | Adventure, Puzzle & Trivia |
| 3 | Turbo Overkill | 100.00 | 70.68 | Action, Indie |
| 4 | Mario Kart 8 Deluxe: Booster Course Pass | 100.00 | 84.73 | Simulation |
| 5 | Bionic Bay | 100.00 | 70.03 | Adventure, Indie, Platform, Puzzle & Trivia |
| 6 | Cassette Beasts | 100.00 | 61.03 | Adventure, Indie, Role-Playing, Strategy |
| 7 | RoadCraft | 100.00 | 83.55 | Adventure, Simulation |
| 8 | Fatal Fury: City of the Wolves - Special Edition | 100.00 | N/A | Action |
| 9 | Vampire Survivors: Emergency Meeting | 100.00 | N/A | Hack and slash/Beat 'em up, Indie |
| 10 | Ghost Town | 100.00 | N/A | Adventure, Puzzle & Trivia |

## 6. Bottom 10 Games by Description Length (may need LLM enrichment)

| Rank | Name | Desc Length | Has Genres | Has Themes |
|------|------|-------------|------------|------------|
| 1 | MLB The Show 23 | 29 | Yes | Yes |
| 2 | Made in Abyss: Binary Star Falling into Darkness | 57 | Yes | Yes |
| 3 | V-Racer Hoverbike | 63 | Yes | Yes |
| 4 | Football Manager 26 | 70 | Yes | No |
| 5 | Freshly Frosted | 81 | Yes | No |
| 6 | Call of Duty: Warzone | 82 | Yes | Yes |
| 7 | Road 96: Mile 0 | 88 | Yes | Yes |
| 8 | Solo Leveling: Arise | 91 | Yes | Yes |
| 9 | Dragon Quest Treasures | 92 | Yes | Yes |
| 10 | Red Dead Redemption | 93 | Yes | Yes |

## 7. Canonical Genre Distribution

| Genre | Count | % of 2,000 |
|-------|-------|------------|
| Adventure | 1,313 | 65.7% |
| Indie | 826 | 41.3% |
| Role-Playing | 696 | 34.8% |
| Simulation | 477 | 23.9% |
| Action | 474 | 23.7% |
| Strategy | 401 | 20.1% |
| Puzzle & Trivia | 393 | 19.6% |
| Platform | 354 | 17.7% |
| Arcade | 280 | 14.0% |
| Hack and slash/Beat 'em up | 158 | 7.9% |
| Sports | 130 | 6.5% |
| Point-and-click | 71 | 3.5% |
| Visual Novel | 60 | 3.0% |
| Music | 45 | 2.2% |
| MOBA | 6 | 0.3% |
| Casual / Arcade | 4 | 0.2% |

## 8. Theme Distribution (top 20)

| Theme | Count | % of 2,000 |
|-------|-------|------------|
| Action | 1,385 | 69.2% |
| Fantasy | 609 | 30.4% |
| Science fiction | 391 | 19.6% |
| Horror | 229 | 11.4% |
| Open world | 204 | 10.2% |
| Mystery | 182 | 9.1% |
| Comedy | 181 | 9.1% |
| Survival | 176 | 8.8% |
| Kids | 134 | 6.7% |
| Sandbox | 124 | 6.2% |
| Drama | 97 | 4.8% |
| Historical | 95 | 4.8% |
| Stealth | 73 | 3.6% |
| Party | 73 | 3.6% |
| Warfare | 71 | 3.5% |
| Thriller | 60 | 3.0% |
| Business | 45 | 2.2% |
| Non-fiction | 43 | 2.1% |
| Romance | 38 | 1.9% |
| Educational | 14 | 0.7% |

## 9. Game Mode Distribution

| Mode | Count |
|------|-------|
| Single player | 1,910 |
| Multiplayer | 738 |
| Co-operative | 553 |
| Split screen | 93 |
| Massively Multiplayer Online (MMO) | 41 |
| Battle Royale | 20 |

## 10. Player Perspective Distribution

| Perspective | Count |
|-------------|-------|
| Third person | 798 |
| Bird view / Isometric | 452 |
| Side view | 421 |
| First person | 401 |
| Virtual Reality | 82 |
| Text | 68 |
| Auditory | 6 |
