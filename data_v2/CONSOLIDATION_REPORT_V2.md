# Consolidation Report — V2 Compositions

**Generated:** 2026-05-29 17:23:27

## Batch File Inventory

| File | Count |
|------|-------|
| batch_movies_w1_000_219.json | 220 |
| batch_movies_w2_220_439.json | 220 |
| batch_movies_w3_440_end.json | 217 |
| batch_tv_w4_all.json | 297 |
| batch_podcasts_w5_000_499.json | 500 |
| batch_podcasts_w6_500_999.json | 500 |
| batch_podcasts_w7_1000_1499.json | 500 |
| batch_podcasts_w8_1500_1999.json | 500 |
| batch_games_w_g1_000_499.json | 500 |
| batch_games_w_g2_500_999.json | 500 |
| batch_games_w_g3_1000_1499.json | 500 |
| batch_games_w_g4_1500_1999.json | 500 |
| batch_movies_extra_w_em_000_999.json | 1,000 |
| batch_tv_extra_w_et_000_999.json | 1,000 |
| **Total raw** | **6,954** |

## Deduplication — By Entity ID

Duplicate entity_ids found: **0**


## Deduplication — By Name + Vertical

Duplicate name+vertical pairs found: **9**

| Name | Vertical | Kept ID | Removed ID |
|------|----------|---------|------------|
| LEGO Disney Princess: Villains Unite | movie | Movie:386018 | Movie:972 |
| Infamous | podcast | Podcast:13870 | Podcast:14338 |
| We The People | podcast | Podcast:12088 | Podcast:18771 |
| Prince of Persia: The Lost Crown | game | IGDB_Game:252476 | IGDB_Game:341533 |
| Tower of Fantasy | game | IGDB_Game:174590 | IGDB_Game:256153 |
| Alan Wake II: Deluxe Edition | game | IGDB_Game:311975 | IGDB_Game:250806 |
| Black Box | movie | Watchmode_Title:1596771 | Watchmode_Title:1614172 |
| Speak No Evil | movie | Watchmode_Title:1635856 | Watchmode_Title:1857829 |
| Good Boy | movie | Watchmode_Title:1877467 | Watchmode_Title:1938968 |

## Validation Issues

Issues found: **28**

- Podcast:6190 (ChinesePod - Intermediate): composed_text only 129 words (min 140)
- Podcast:9261 (A Cast of Kings - A Knight of the Seven Kingdoms Podcast): composed_text only 117 words (min 140)
- Podcast:21207 (Packernet Podcast: Daily Green Bay Packers Podcast): composed_text only 128 words (min 140)
- Podcast:15580 (Rogue Energy): composed_text only 126 words (min 140)
- Podcast:23031 (Tomorrowland Friendship Mix): composed_text only 137 words (min 140)
- Podcast:6581 (Modern Mentor): composed_text only 135 words (min 140)
- Podcast:11384 (Digital Foundry Direct Weekly): composed_text only 139 words (min 140)
- Podcast:13940 (Pod Save the People): composed_text only 129 words (min 140)
- Podcast:11010 (Gun Talk): composed_text only 115 words (min 140)
- Podcast:22391 (Manchester United Podcast by Stretford Paddock): composed_text only 124 words (min 140)
- Podcast:8318 (The Sports Junkies): composed_text only 134 words (min 140)
- Podcast:9893 (Feeling Good Podcast | TEAM-CBT - The New Mood Therapy): composed_text only 128 words (min 140)
- Podcast:22856 (Don't Miss This Study): composed_text only 111 words (min 140)
- Podcast:6320 (Bitch Bible): composed_text only 132 words (min 140)
- Podcast:7654 (Sensemaker): composed_text only 110 words (min 140)
- Podcast:9209 (Optimal Work Daily - Career, Productivity and Entrepreneurship): composed_text only 115 words (min 140)
- Podcast:10965 (This Is Not A Drill with Gavin Esler): composed_text only 133 words (min 140)
- Podcast:12180 (Risky Bulletin): composed_text only 119 words (min 140)
- Podcast:7995 (Down These Mean Streets (Old Time Radio Detectives)): composed_text only 138 words (min 140)
- Podcast:20084 (Scheananigans with Scheana Shay): composed_text only 122 words (min 140)
- Podcast:22284 (Kuhner's Corner): composed_text only 117 words (min 140)
- Podcast:17548 (Where Politics Meets History): composed_text only 137 words (min 140)
- Podcast:18030 (My So-Called Midlife with Reshma Saujani): composed_text only 139 words (min 140)
- Podcast:19301 (Hoax!): composed_text only 139 words (min 140)
- Podcast:4603 (The Climate Question): composed_text only 137 words (min 140)
- Podcast:9265 (Scrum V): composed_text only 114 words (min 140)
- Podcast:20991 (Forgotten Australia): composed_text only 130 words (min 140)
- Podcast:15776 (The Jim Rome Podcast): composed_text only 124 words (min 140)

## Final Statistics

**Total entities after dedup:** 6,945

| Vertical | Count | Word Count (min/avg/max) | Keywords (min/avg/max) |
|----------|-------|--------------------------|------------------------|
| game | 1,997 | 150 / 179 / 200 | 12 / 14 / 15 |
| movie | 1,653 | 150 / 179 / 220 | 11 / 13 / 15 |
| podcast | 1,998 | 110 / 182 / 259 | 12 / 13 / 15 |
| tv | 1,297 | 142 / 177 / 204 | 12 / 14 / 15 |
| **Total** | **6,945** | | |
