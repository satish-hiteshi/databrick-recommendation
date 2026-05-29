# Retrieval v2 Test Report

## Summary

- Queries tested: 5
- Modes covered: entity_single, entity_multi, theme_based, descriptive, mixed

---

## Q1: "Games like Elden Ring Nightreign"

**Expected mode:** `entity_single` | **Got:** `entity_single`

### NLU Output
- positive_entities: `['Elden Ring', 'Nightreign']`
- negative_entities: `[]`
- additional_keywords: `[]`
- description_derived_keywords: `[]`
- target_verticals: `['game']`

### Entity Resolution (SQL)

| Entity | Vertical | Match Type |
|--------|----------|------------|
| Elden Ring Nightreign | game | prefix |
| Elden Ring Nightreign | game | contains |

### Search Source: `entity:Elden Ring Nightreign`

**Vector top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Elden Ring Nightreign | game | 1.0000 |
| Code Vein II | game | 0.7434 |
| Nioh 3 | game | 0.7432 |
| Monster Hunter Wilds | game | 0.7230 |
| Let It Die: Inferno | game | 0.7187 |

**BM25 top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Elden Ring Nightreign | game | 47.7086 |
| Tales of Berseria Remastered: Deluxe Edition | game | 14.9134 |
| Nioh 3 | game | 12.8888 |
| The Blood of Dawnwalker | game | 12.7342 |
| Jötunnslayer: Hordes of Hel | game | 12.3694 |

### Merged Results (top 10 of 33)

| Rank | Name | Vertical | Combined | Vector | BM25 | Sources | Dual |
|------|------|----------|----------|--------|------|---------|------|
| 1 | Elden Ring Nightreign | game | 1.1000 | 1.0000 | 1.0000 | 1 | Yes |
| 2 | Nioh 3 | game | 0.2611 | 0.1849 | 0.1056 | 1 | Yes |
| 3 | Jötunnslayer: Hordes of Hel | game | 0.1819 | 0.0774 | 0.0923 | 1 | Yes |
| 4 | Darkest Days | game | 0.1722 | 0.0875 | 0.0364 | 1 | Yes |
| 5 | Dragonkin: The Banished | game | 0.1525 | 0.0750 | 0.0000 | 1 | Yes |
| 6 | EverSiege: Untold Ages | game | 0.1479 | 0.0517 | 0.0390 | 1 | Yes |
| 7 | Code Vein II | game | 0.1299 | 0.1856 | 0.0000 | 1 |  |
| 8 | 33 Immortals | game | 0.1286 | 0.0244 | 0.0386 | 1 | Yes |
| 9 | Monster Hunter Wilds | game | 0.0846 | 0.1209 | 0.0000 | 1 |  |
| 10 | Let It Die: Inferno | game | 0.0752 | 0.1074 | 0.0000 | 1 |  |

*Timing: NLU 590ms, retrieval 86ms*

---

## Q2: "I love Elden Ring and Nioh 3, recommend movies"

**Expected mode:** `entity_multi` | **Got:** `entity_multi`

### NLU Output
- positive_entities: `['Elden Ring', 'Nioh 3']`
- negative_entities: `[]`
- additional_keywords: `[]`
- description_derived_keywords: `[]`
- target_verticals: `['movie']`

### Entity Resolution (SQL)

| Entity | Vertical | Match Type |
|--------|----------|------------|
| Elden Ring Nightreign | game | prefix |
| Nioh 3 | game | exact |

### Search Source: `entity:Elden Ring Nightreign`

**Vector top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| In the Lost Lands | movie | 0.5461 |
| Predator: Badlands | movie | 0.5109 |
| Until Dawn | movie | 0.5063 |
| The Old Guard 2 | movie | 0.5044 |
| The Rats: A Witcher Tale | movie | 0.4925 |

**BM25 top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| The Witcher: Sirens of the Deep | movie | 6.3110 |
| In the Lost Lands | movie | 6.1006 |
| Tales from Black Manor | movie | 5.4507 |
| The Rats: A Witcher Tale | movie | 5.4507 |
| The Jurassic Games: Extinction | movie | 4.8073 |

### Search Source: `entity:Nioh 3`

**Vector top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Red Sonja | movie | 0.5024 |
| The Old Guard 2 | movie | 0.4942 |
| Ballerina | movie | 0.4835 |
| Diablo | movie | 0.4798 |
| The Last GunFight | movie | 0.4742 |

**BM25 top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Lost Horizon | movie | 4.6517 |
| Red Sonja | movie | 4.6517 |
| Sniper: No Nation | movie | 4.2387 |
| The Old Guard 2 | movie | 4.2387 |
| Love Hurts | movie | 4.2387 |

### Merged Results (top 10 of 40)

| Rank | Name | Vertical | Combined | Vector | BM25 | Sources | Dual |
|------|------|----------|----------|--------|------|---------|------|
| 1 | Red Sonja | movie | 1.3500 | 1.0000 | 1.0000 | 2 | Yes |
| 2 | In the Lost Lands | movie | 1.3312 | 1.0000 | 0.9374 | 2 | Yes |
| 3 | The Old Guard 2 | movie | 1.2365 | 0.8903 | 0.8777 | 2 | Yes |
| 4 | Tales from Black Manor | movie | 0.9129 | 0.4852 | 0.7440 | 2 | Yes |
| 5 | The Last GunFight | movie | 0.8999 | 0.6236 | 0.8777 | 1 | Yes |
| 6 | The Witcher: Sirens of the Deep | movie | 0.7784 | 0.1835 | 1.0000 | 2 | Yes |
| 7 | The Rats: A Witcher Tale | movie | 0.7711 | 0.4970 | 0.7440 | 1 | Yes |
| 8 | Diablo | movie | 0.7383 | 0.6976 | 0.0000 | 2 | Yes |
| 9 | Predator: Badlands | movie | 0.6187 | 0.6696 | 0.0000 | 2 |  |
| 10 | Ballerina | movie | 0.5236 | 0.7480 | 0.0000 | 1 |  |

*Timing: NLU 474ms, retrieval 127ms*

---

## Q3: "Horror content across all categories"

**Expected mode:** `theme_based` | **Got:** `theme_based`

### NLU Output
- positive_entities: `[]`
- negative_entities: `[]`
- additional_keywords: `['horror']`
- description_derived_keywords: `[]`
- target_verticals: `['game', 'movie', 'tv']`

### Entity Resolution (SQL)

*No entities resolved (theme/descriptive mode)*

### Search Source: `theme:horror`

**Vector top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| The Jester 2 | movie | 0.4754 |
| Wizard of Oz: Dead Walk | movie | 0.4642 |
| Die'ced: Reloaded | movie | 0.4354 |
| The Dreadful | movie | 0.4301 |
| Bambi: The Reckoning | movie | 0.4236 |

**BM25 top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Outbreak: Shades of Horror | game | 1.9334 |
| Garten of Banban 8: Anti Devil | game | 1.9334 |
| BrokenLore: Low | game | 1.9334 |
| Memoreum | game | 1.9334 |
| Kletka | game | 1.9334 |

### Merged Results (top 10 of 40)

| Rank | Name | Vertical | Combined | Vector | BM25 | Sources | Dual |
|------|------|----------|----------|--------|------|---------|------|
| 1 | The Jester 2 | movie | 0.7000 | 1.0000 | 0.0000 | 1 |  |
| 2 | Wizard of Oz: Dead Walk | movie | 0.5853 | 0.8361 | 0.0000 | 1 |  |
| 3 | Outbreak: Shades of Horror | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |
| 4 | Garten of Banban 8: Anti Devil | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |
| 5 | BrokenLore: Low | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |
| 6 | Memoreum | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |
| 7 | Kletka | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |
| 8 | Reanimal | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |
| 9 | Ayasa: Shadows of Silence | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |
| 10 | Cronos: The New Dawn | game | 0.3000 | 0.0000 | 1.0000 | 1 |  |

*Timing: NLU 906ms, retrieval 932ms*

---

## Q4: "I like content with country wars and gun fighting"

**Expected mode:** `descriptive` | **Got:** `descriptive`

### NLU Output
- positive_entities: `[]`
- negative_entities: `[]`
- additional_keywords: `[]`
- description_derived_keywords: `['military warfare', 'combat', 'war drama', 'tactical shooter']`
- target_verticals: `['game', 'movie', 'tv']`

### Entity Resolution (SQL)

*No entities resolved (theme/descriptive mode)*

### Search Source: `theme:military warfare combat war drama tactic`

**Vector top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Warfare | movie | 0.6010 |
| Forefront | game | 0.5483 |
| Sniper: The Last Stand | movie | 0.5416 |
| Arena Breakout: Infinite | game | 0.5278 |
| Sniper: No Nation | movie | 0.5200 |

**BM25 top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Shadows of Soldiers | game | 6.8490 |
| Metal Suits: Counter-Attack | game | 3.4992 |
| Kiborg | game | 3.4992 |
| Eternal Strands | game | 3.4992 |
| Mekkablood: Quarry Assault | game | 3.4992 |

### Merged Results (top 10 of 39)

| Rank | Name | Vertical | Combined | Vector | BM25 | Sources | Dual |
|------|------|----------|----------|--------|------|---------|------|
| 1 | Warfare | movie | 0.7000 | 1.0000 | 0.0000 | 1 |  |
| 2 | Shadows of Soldiers | game | 0.6204 | 0.3149 | 1.0000 | 1 | Yes |
| 3 | Forefront | game | 0.4144 | 0.5920 | 0.0000 | 1 |  |
| 4 | Sniper: The Last Stand | movie | 0.3777 | 0.5396 | 0.0000 | 1 |  |
| 5 | Arena Breakout: Infinite | game | 0.3032 | 0.4331 | 0.0000 | 1 |  |
| 6 | Sniper: No Nation | movie | 0.2611 | 0.3729 | 0.0000 | 1 |  |
| 7 | Valiant One | movie | 0.2540 | 0.3629 | 0.0000 | 1 |  |
| 8 | War Machine | movie | 0.2140 | 0.3058 | 0.0000 | 1 |  |
| 9 | Lost Horizon | movie | 0.1761 | 0.2516 | 0.0000 | 1 |  |
| 10 | Rainbow Six Mobile | game | 0.1614 | 0.2305 | 0.0000 | 1 |  |

*Timing: NLU 580ms, retrieval 408ms*

---

## Q5: "Love Resident Evil and Silent Hill, hate comedy, want dark intense TV shows"

**Expected mode:** `mixed` | **Got:** `entity_multi`

### NLU Output
- positive_entities: `['Resident Evil', 'Silent Hill']`
- negative_entities: `['comedy']`
- additional_keywords: `['dark', 'intense']`
- description_derived_keywords: `['horror']`
- target_verticals: `['tv']`

### Entity Resolution (SQL)

| Entity | Vertical | Match Type |
|--------|----------|------------|
| Resident Evil Requiem | game | prefix |
| Silent Hill f | game | prefix |

### Search Source: `entity:Resident Evil Requiem`

**Vector top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Marvel Zombies | tv | 0.5352 |
| Alien: Earth | tv | 0.5183 |
| Devil May Cry | tv | 0.5137 |
| Hell Motel | tv | 0.4842 |
| Nemesis | tv | 0.4684 |

**BM25 top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| Marvel Zombies | tv | 7.6962 |
| Hell Motel | tv | 6.3696 |
| Run Away | tv | 4.5029 |
| Memory of a Killer | tv | 4.5029 |
| Wayward | tv | 4.5029 |

### Search Source: `entity:Silent Hill f`

**Vector top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| IT: Welcome to Derry | tv | 0.5255 |
| True Haunting | tv | 0.5093 |
| Playing Gracie Darling | tv | 0.5021 |
| Hell Motel | tv | 0.4991 |
| The Institute | tv | 0.4921 |

**BM25 top 5:**
| Name | Vertical | Score |
|------|----------|-------|
| IT: Welcome to Derry | tv | 7.5869 |
| Million Dollar Secret | tv | 3.5256 |
| Half Man | tv | 3.2238 |
| Happy Face | tv | 3.1126 |
| The Beast in Me | tv | 3.1126 |

### Merged Results (top 10 of 39)

| Rank | Name | Vertical | Combined | Vector | BM25 | Sources | Dual |
|------|------|----------|----------|--------|------|---------|------|
| 1 | IT: Welcome to Derry | tv | 1.3500 | 1.0000 | 1.0000 | 2 | Yes |
| 2 | Marvel Zombies | tv | 1.2000 | 1.0000 | 1.0000 | 1 | Yes |
| 3 | Hell Motel | tv | 0.9425 | 0.6976 | 0.7748 | 2 | Yes |
| 4 | True Haunting | tv | 0.8202 | 0.8146 | 0.0106 | 2 | Yes |
| 5 | Devil May Cry | tv | 0.8038 | 0.7955 | 0.1566 | 1 | Yes |
| 6 | Alien: Earth | tv | 0.7870 | 0.8386 | 0.0000 | 1 | Yes |
| 7 | The Institute | tv | 0.6823 | 0.6176 | 0.0106 | 2 | Yes |
| 8 | Wayward | tv | 0.5683 | 0.4547 | 0.4580 | 2 | Yes |
| 9 | Playing Gracie Darling | tv | 0.5128 | 0.7326 | 0.0000 | 1 |  |
| 10 | Monster: The Ed Gein Story | tv | 0.5066 | 0.4282 | 0.0227 | 1 | Yes |

*Timing: NLU 497ms, retrieval 102ms*

