# Reranker v2 Test Report

Full chain: NLU → Retrieval → Negative Filter → Reranker

---

## Q1: "Games like Elden Ring Nightreign"
*entity_single, no negatives*

### NLU Output
- mode: `entity_single`
- positive_entities: `['Elden Ring', 'Nightreign']`
- negative_entities: `[]`
- additional_keywords: `[]`
- description_derived_keywords: `[]`
- target_verticals: `['game']`
- query_type: `within_vertical`

### Entity Resolution

**Positive:**
- Elden Ring Nightreign (game) [prefix]
- Elden Ring Nightreign (game) [contains]

### Retrieval — 33 candidates (top 15)

| # | Name | Vertical | Combined | Vector | BM25 | Sources |
|---|------|----------|----------|--------|------|---------|
| 1 | Elden Ring Nightreign | game | 1.1000 | 1.0000 | 1.0000 | 1 |
| 2 | Nioh 3 | game | 0.2611 | 0.1849 | 0.1056 | 1 |
| 3 | Jötunnslayer: Hordes of Hel | game | 0.1819 | 0.0774 | 0.0923 | 1 |
| 4 | Darkest Days | game | 0.1722 | 0.0875 | 0.0364 | 1 |
| 5 | Dragonkin: The Banished | game | 0.1525 | 0.0750 | 0.0000 | 1 |
| 6 | EverSiege: Untold Ages | game | 0.1479 | 0.0517 | 0.0390 | 1 |
| 7 | Code Vein II | game | 0.1299 | 0.1856 | 0.0000 | 1 |
| 8 | 33 Immortals | game | 0.1286 | 0.0244 | 0.0386 | 1 |
| 9 | Monster Hunter Wilds | game | 0.0846 | 0.1209 | 0.0000 | 1 |
| 10 | Let It Die: Inferno | game | 0.0752 | 0.1074 | 0.0000 | 1 |
| 11 | Rotwood | game | 0.0723 | 0.1033 | 0.0000 | 1 |
| 12 | Sworn | game | 0.0710 | 0.1014 | 0.0000 | 1 |
| 13 | Towerborne | game | 0.0676 | 0.0966 | 0.0000 | 1 |
| 14 | Out of Time | game | 0.0477 | 0.0682 | 0.0000 | 1 |
| 15 | Tales of Berseria Remastered: Deluxe Edition | game | 0.0473 | 0.0000 | 0.1577 | 1 |

### Negative Filter (33 → 33 candidates)

*No negative filtering applied.*

### Reranker Adjustments

- **Self-excluded:** Elden Ring Nightreign

### Final Results — Top 10 (10 results)

| Rank | Name | Vertical | Final | Combined | Neg Penalty | Adjustments | Keywords |
|------|------|----------|-------|----------|-------------|-------------|----------|
| 1 | Nioh 3 | game | 0.2611 | 0.2611 | 0.0000 |  | action, challenging, cooperative, open world |
| 2 | Jötunnslayer: Hordes of Hel | game | 0.1819 | 0.1819 | 0.0000 |  | action, cooperative, dark fantasy, roguelike |
| 3 | Darkest Days | game | 0.1722 | 0.1722 | 0.0000 |  | action, cooperative, open world, role-playing |
| 4 | Dragonkin: The Banished | game | 0.1525 | 0.1525 | 0.0000 |  | action, cooperative, dark fantasy, role-playing |
| 5 | EverSiege: Untold Ages | game | 0.1479 | 0.1479 | 0.0000 |  | cooperative, fantasy, procedural, role-playing |
| 6 | Code Vein II | game | 0.1299 | 0.1299 | 0.0000 |  | dark fantasy, role-playing, survival |
| 7 | 33 Immortals | game | 0.1286 | 0.1286 | 0.0000 |  | action, cooperative, fantasy, roguelike |
| 8 | Monster Hunter Wilds | game | 0.0846 | 0.0846 | 0.0000 |  | action, fantasy, open world, role-playing |
| 9 | Let It Die: Inferno | game | 0.0752 | 0.0752 | 0.0000 |  | action, cooperative, survival |
| 10 | Rotwood | game | 0.0723 | 0.0723 | 0.0000 |  | action, roguelike, role-playing |

### Latency
NLU 470ms + Retrieval 58ms + Filter 0ms + Rerank 4ms = **532ms**

---

## Q2: "Love Elden Ring and Dark Souls, but hate Star Wars, recommend movies"
*entity_multi + negative*

### NLU Output
- mode: `entity_multi`
- positive_entities: `['Elden Ring', 'Dark Souls']`
- negative_entities: `['Star Wars']`
- additional_keywords: `[]`
- description_derived_keywords: `[]`
- target_verticals: `['movie']`
- query_type: `cross_vertical`

### Entity Resolution

**Positive:**
- Elden Ring Nightreign (game) [prefix]

**Negative (resolved):**
- Star Wars: Galactic Racer (game) [prefix]

### Retrieval — 24 candidates (top 15)

| # | Name | Vertical | Combined | Vector | BM25 | Sources |
|---|------|----------|----------|--------|------|---------|
| 1 | In the Lost Lands | movie | 1.1812 | 1.0000 | 0.9374 | 1 |
| 2 | The Rats: A Witcher Tale | movie | 0.7711 | 0.4970 | 0.7440 | 1 |
| 3 | Tales from Black Manor | movie | 0.7629 | 0.4852 | 0.7440 | 1 |
| 4 | The Witcher: Sirens of the Deep | movie | 0.6284 | 0.1835 | 1.0000 | 1 |
| 5 | Predator: Badlands | movie | 0.4687 | 0.6696 | 0.0000 | 1 |
| 6 | Until Dawn | movie | 0.4390 | 0.6271 | 0.0000 | 1 |
| 7 | The Old Guard 2 | movie | 0.4265 | 0.6093 | 0.0000 | 1 |
| 8 | A Minecraft Movie | movie | 0.2849 | 0.4070 | 0.0000 | 1 |
| 9 | Worldbreaker | movie | 0.2571 | 0.0816 | 0.0000 | 1 |
| 10 | Peter Pan's Neverland Nightmare | movie | 0.2073 | 0.2961 | 0.0000 | 1 |
| 11 | Predator: Wastelands | movie | 0.2013 | 0.0019 | 0.0000 | 1 |
| 12 | The Jurassic Games: Extinction | movie | 0.1658 | 0.0000 | 0.5525 | 1 |
| 13 | The Land That Time Forgot | movie | 0.1658 | 0.0000 | 0.5525 | 1 |
| 14 | Sinners | movie | 0.1653 | 0.2362 | 0.0000 | 1 |
| 15 | Psycho Killer | movie | 0.1042 | 0.0000 | 0.3472 | 1 |

### Negative Filter (24 → 18 candidates)

| Entity | Action | Reason | Score Change |
|--------|--------|--------|-------------|
| Darkness of Man | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| G20 | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Diablo | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Guns Up | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| She Rides Shotgun | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Fight or Flight | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |

### Reranker Adjustments


### Final Results — Top 10 (10 results)

| Rank | Name | Vertical | Final | Combined | Neg Penalty | Adjustments | Keywords |
|------|------|----------|-------|----------|-------------|-------------|----------|
| 1 | In the Lost Lands | movie | 1.1812 | 1.1812 | 0.0000 |  | action, dark fantasy, fantasy |
| 2 | The Rats: A Witcher Tale | movie | 0.7711 | 0.7711 | 0.0000 |  | dark fantasy, fantasy |
| 3 | Tales from Black Manor | movie | 0.7629 | 0.7629 | 0.0000 |  | dark fantasy, fantasy |
| 4 | The Witcher: Sirens of the Deep | movie | 0.6284 | 0.6284 | 0.0000 |  | action, dark fantasy, fantasy |
| 5 | Predator: Badlands | movie | 0.4687 | 0.4687 | 0.0000 |  | action, survival |
| 6 | Until Dawn | movie | 0.4390 | 0.4390 | 0.0000 |  | survival |
| 7 | The Old Guard 2 | movie | 0.4265 | 0.4265 | 0.0000 |  | action, fantasy |
| 8 | A Minecraft Movie | movie | 0.2849 | 0.2849 | 0.0000 |  | fantasy |
| 9 | Worldbreaker | movie | 0.2571 | 0.2571 | 0.0000 |  | action, survival |
| 10 | Peter Pan's Neverland Nightmare | movie | 0.2073 | 0.2073 | 0.0000 |  | fantasy |

### Latency
NLU 436ms + Retrieval 80ms + Filter 30ms + Rerank 0ms = **546ms**

---

## Q3: "Horror content, not comedy, across all categories"
*theme + negative keyword*

### NLU Output
- mode: `theme_based`
- positive_entities: `[]`
- negative_entities: `['comedy']`
- additional_keywords: `['horror']`
- description_derived_keywords: `[]`
- target_verticals: `['game', 'movie', 'tv']`
- query_type: `cross_vertical`

### Entity Resolution


**Negative (keyword-only, unresolved):** ['comedy']

### Retrieval — 40 candidates (top 15)

| # | Name | Vertical | Combined | Vector | BM25 | Sources |
|---|------|----------|----------|--------|------|---------|
| 1 | The Jester 2 | movie | 0.7000 | 1.0000 | 0.0000 | 1 |
| 2 | Wizard of Oz: Dead Walk | movie | 0.6009 | 0.8585 | 0.0000 | 1 |
| 3 | Outbreak: Shades of Horror | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 4 | Garten of Banban 8: Anti Devil | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 5 | BrokenLore: Low | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 6 | Memoreum | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 7 | Kletka | game | 0.2200 | 0.0000 | 1.0000 | 1 |
| 8 | Reanimal | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 9 | Ayasa: Shadows of Silence | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 10 | Cronos: The New Dawn | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 11 | Garten of Banban 0 | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 12 | Project Songbird | game | 0.3000 | 0.0000 | 1.0000 | 1 |
| 13 | Storebound | game | 0.2200 | 0.0000 | 1.0000 | 1 |
| 14 | Die'ced: Reloaded | movie | 0.2787 | 0.3981 | 0.0000 | 1 |
| 15 | The Dreadful | movie | 0.1983 | 0.2833 | 0.0000 | 1 |

### Negative Filter (40 → 28 candidates)

| Entity | Action | Reason | Score Change |
|--------|--------|--------|-------------|
| Kletka | PENALIZED | neg_kw_text('comedy' in composed_text), penalty=0.08 | 0.3000 → 0.2200 (-0.0800) |
| Storebound | PENALIZED | neg_kw_text('comedy' in composed_text), penalty=0.08 | 0.3000 → 0.2200 (-0.0800) |
| The Monkey | REMOVED | score below floor (0.0813 - 0.1500 = -0.0687) | 0.0813 → removed |
| Mega Blood Moon: The Freelancer | REMOVED | score below floor (0.0285 - 0.1500 = -0.1215) | 0.0285 → removed |
| Control Freak | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Order 13 | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Slender Threads | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| The House in the Hollow | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Thief's Shelter | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Bulb Boy 2: Jar of Despair | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Labyrinth of the Demon King | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Mina the Hollower | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Hell is Us | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |
| Dark Atlas: Infernum | REMOVED | score below floor (0.0000 - 0.0000 = 0.0000) | 0.0000 → removed |

### Reranker Adjustments

- **Keyword boosted:** The Jester 2 (+0.05), Wizard of Oz: Dead Walk (+0.05), Outbreak: Shades of Horror (+0.05), Garten of Banban 8: Anti Devil (+0.05), BrokenLore: Low (+0.05), Memoreum (+0.05), Reanimal (+0.05), Ayasa: Shadows of Silence (+0.05)

### Final Results — GAME (10 results)

| Rank | Name | Final | Combined | Neg Penalty | Adjustments | Keywords |
|------|------|-------|----------|-------------|-------------|----------|
| 1 | Outbreak: Shades of Horror | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 2 | Garten of Banban 8: Anti Devil | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 3 | BrokenLore: Low | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 4 | Memoreum | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 5 | Reanimal | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 6 | Ayasa: Shadows of Silence | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 7 | Cronos: The New Dawn | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 8 | Garten of Banban 0 | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 9 | Project Songbird | 0.3500 | 0.3000 | 0.0000 | keyword_boost=0.05 |  |
| 10 | Kletka | 0.2700 | 0.2200 | 0.0800 | keyword_boost=0.05 |  |

### Final Results — MOVIE (10 results)

| Rank | Name | Final | Combined | Neg Penalty | Adjustments | Keywords |
|------|------|-------|----------|-------------|-------------|----------|
| 1 | The Jester 2 | 0.7500 | 0.7000 | 0.0000 | keyword_boost=0.05 |  |
| 2 | Wizard of Oz: Dead Walk | 0.6509 | 0.6009 | 0.0000 | keyword_boost=0.05 |  |
| 3 | Die'ced: Reloaded | 0.3287 | 0.2787 | 0.0000 | keyword_boost=0.05 |  |
| 4 | The Dreadful | 0.2483 | 0.1983 | 0.0000 | keyword_boost=0.05 |  |
| 5 | Bambi: The Reckoning | 0.2392 | 0.1892 | 0.0000 | keyword_boost=0.05 |  |
| 6 | Wormtown | 0.2078 | 0.1578 | 0.0000 | keyword_boost=0.05 |  |
| 7 | Hybrid Hazards: Revelation | 0.1759 | 0.1259 | 0.0000 | keyword_boost=0.05 |  |
| 8 | Darbie's Scream House | 0.1686 | 0.1186 | 0.0000 | keyword_boost=0.05 |  |
| 9 | Wolf Man | 0.1270 | 0.0770 | 0.0000 | keyword_boost=0.05 |  |
| 10 | Peter Pan's Neverland Nightmare | 0.1086 | 0.0586 | 0.0000 | keyword_boost=0.05 |  |

### Latency
NLU 415ms + Retrieval 497ms + Filter 32ms + Rerank 0ms = **944ms**

