# Feeds.ai Pipeline v2 — Final Test Report

## Section 1 — Executive Summary

- **Total queries:** 20
- **Successful (with results):** 19/20 (95%)
- **Average latency:** 1588 ms

### Success Rate by Query Mode

| Mode | Success | Total | Rate | Failed |
|------|---------|-------|------|--------|
| descriptive | 3 | 3 | 100% | — |
| entity_multi | 4 | 4 | 100% | — |
| entity_single | 3 | 4 | 75% | Q3 |
| mixed | 4 | 4 | 100% | — |
| theme_based | 5 | 5 | 100% | — |

---

## Section 2 — Detailed Results

### Entity Single

#### Q1: "What games are like Elden Ring Nightreign?"

**NLU:** mode=`entity_single` (expected `entity_single`), pos=`['Elden Ring', 'Nightreign']`, neg=`[]`
**Keywords:** add=`[]`, derived=`[]`
**Verticals:** `['game']`, type=`within_vertical`

**Resolved:** Elden Ring Nightreign (game) [prefix], Elden Ring Nightreign (game) [contains]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Nioh 3 | game | 0.2611 | 0.1849 | 0.1056 | Yes | action, challenging, cooperative, open world |
| 2 | Jötunnslayer: Hordes of Hel | game | 0.1819 | 0.0774 | 0.0923 | Yes | action, cooperative, dark fantasy, roguelike |
| 3 | Darkest Days | game | 0.1722 | 0.0875 | 0.0364 | Yes | action, cooperative, open world, role-playing |
| 4 | Dragonkin: The Banished | game | 0.1525 | 0.0750 | 0.0000 | Yes | action, cooperative, dark fantasy, role-playing |
| 5 | EverSiege: Untold Ages | game | 0.1479 | 0.0517 | 0.0390 | Yes | cooperative, fantasy, procedural, role-playing |
| 6 | Code Vein II | game | 0.1299 | 0.1856 | 0.0000 |  | dark fantasy, role-playing, survival |
| 7 | 33 Immortals | game | 0.1286 | 0.0244 | 0.0386 | Yes | action, cooperative, fantasy, roguelike |
| 8 | Monster Hunter Wilds | game | 0.0846 | 0.1209 | 0.0000 |  | action, fantasy, open world, role-playing |
| 9 | Let It Die: Inferno | game | 0.0752 | 0.1074 | 0.0000 |  | action, cooperative, survival |
| 10 | Rotwood | game | 0.0723 | 0.1033 | 0.0000 |  | action, roguelike, role-playing |

*Latency: 488ms (NLU 424 + retrieval 60 + filter 0 + rerank 4)*

#### Q2: "Movies similar to Star Wars: The Mandalorian and Grogu"

**NLU:** mode=`entity_multi` (expected `entity_single`), pos=`['Star Wars: The Mandalorian', 'Grogu']`, neg=`[]`
**Keywords:** add=`['space', 'sci-fi']`, derived=`[]`
**Verticals:** `['movie']`, type=`within_vertical`

**Resolved:** Star Wars: The Mandalorian and Grogu (movie) [prefix], Star Wars: The Mandalorian and Grogu (movie) [contains]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Winter of Empires | movie | 0.6620 | 0.2122 | 0.0655 | Yes | adventure, science fiction, space opera |
| 2 | Predator: Badlands | movie | 0.5957 | 0.1869 | 0.0404 | Yes | action, adventure, franchise, science fiction |
| 3 | Avatar: Fire and Ash | movie | 0.5572 | 0.1528 | 0.0227 | Yes | adventure, franchise, science fiction |
| 4 | The Electric State | movie | 0.5128 | 0.0840 | 0.0713 | Yes | action, adventure, found family, science fiction |
| 5 | Jurassic World Rebirth | movie | 0.4383 | 0.0165 | 0.0404 | Yes | action, adventure, franchise, science fiction |
| 6 | Elio | movie | 0.3890 | 0.1829 | 0.0000 |  | adventure, science fiction |
| 7 | Xeno | movie | 0.2924 | 0.1378 | 0.0000 |  | adventure, science fiction |
| 8 | The Fantastic 4: First Steps | movie | 0.2352 | 0.0760 | 0.0000 |  | action, adventure, science fiction |
| 9 | Greenland 2: Migration | movie | 0.2008 | 0.0387 | 0.0000 |  | adventure, science fiction |
| 10 | Moana | movie | 0.1821 | 0.0185 | 0.0000 |  | adventure |

*Latency: 589ms (NLU 504 + retrieval 85 + filter 0 + rerank 0)*

#### Q3: "TV shows like Stranger Things: Tales from 85"

**NLU:** mode=`entity_single` (expected `entity_single`), pos=`['Stranger Things: Tales from 85']`, neg=`[]`
**Keywords:** add=`[]`, derived=`[]`
**Verticals:** `['tv']`, type=`within_vertical`


**Error:** No entity resolved from: ['Stranger Things: Tales from 85']

### Entity Multi

#### Q4: "I love Elden Ring and Nioh 3, recommend me movies"

**NLU:** mode=`entity_multi` (expected `entity_multi`), pos=`['Elden Ring', 'Nioh 3']`, neg=`[]`
**Keywords:** add=`[]`, derived=`[]`
**Verticals:** `['movie']`, type=`cross_vertical`

**Resolved:** Elden Ring Nightreign (game) [prefix], Nioh 3 (game) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Red Sonja | movie | 1.3500 | 1.0000 | 1.0000 | Yes | action, adventure, combat, fantasy |
| 2 | In the Lost Lands | movie | 1.3312 | 1.0000 | 0.9374 | Yes | action, dark fantasy, fantasy |
| 3 | The Old Guard 2 | movie | 1.2365 | 0.8903 | 0.8777 | Yes | action, combat, fantasy |
| 4 | Tales from Black Manor | movie | 0.9129 | 0.4852 | 0.7440 | Yes | dark fantasy, fantasy |
| 5 | The Last GunFight | movie | 0.8999 | 0.6236 | 0.8777 | Yes | action, combat |
| 6 | The Witcher: Sirens of the Deep | movie | 0.7784 | 0.1835 | 1.0000 | Yes | action, dark fantasy, fantasy |
| 7 | The Rats: A Witcher Tale | movie | 0.7711 | 0.4970 | 0.7440 | Yes | adventure, dark fantasy, fantasy |
| 8 | Diablo | movie | 0.7383 | 0.6976 | 0.0000 | Yes | action, survival |
| 9 | Predator: Badlands | movie | 0.6187 | 0.6696 | 0.0000 |  | action, adventure, survival |
| 10 | Ballerina | movie | 0.5236 | 0.7480 | 0.0000 |  | action |

*Latency: 604ms (NLU 519 + retrieval 85 + filter 0 + rerank 0)*

#### Q5: "Games similar to both Resident Evil Requiem and Silent Hill f"

**NLU:** mode=`entity_multi` (expected `entity_multi`), pos=`['Resident Evil Requiem', 'Silent Hill']`, neg=`[]`
**Keywords:** add=`['survival horror']`, derived=`[]`
**Verticals:** `['game']`, type=`within_vertical`

**Resolved:** Resident Evil Requiem (game) [exact], Silent Hill f (game) [prefix]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Silent Hill f: Deluxe Edition | game | 1.4800 | 0.7457 | 0.5528 | Yes | adventure, horror, konami, neobards entertainment |
| 2 | Post Trauma | game | 0.6496 | 0.2003 | 0.0064 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 3 | Cronos: The New Dawn | game | 0.5825 | 0.1173 | 0.0840 | Yes | action, adventure, horror, puzzle & trivia |
| 4 | Tormented Souls II | game | 0.5382 | 0.0778 | 0.0108 | Yes | action, adventure, horror, puzzle & trivia |
| 5 | Code Violet | game | 0.4545 | 0.1347 | 0.0184 | Yes | action, horror, survival horror, third-person |
| 6 | Echoes of the Living | game | 0.3968 | 0.0883 | 0.0462 | Yes | adventure, horror, survival horror, zombies |
| 7 | Ground Zero | game | 0.2781 | 0.0000 | 0.1467 |  | action, horror, resource management, survival horror |
| 8 | Saint of Chains | game | 0.2372 | 0.0424 | 0.0000 |  | action, adventure, horror |
| 9 | Greek Tragedy | game | 0.2267 | 0.0000 | 0.0170 |  | action, adventure, horror, puzzle & trivia |
| 10 | The Mute House | game | 0.1244 | 0.0989 | 0.0000 |  | adventure, horror, third-person |

*Latency: 561ms (NLU 479 + retrieval 81 + filter 0 + rerank 0)*

#### Q6: "I enjoy Marvel Zombies and Alien Earth, find me games"

**NLU:** mode=`entity_multi` (expected `entity_multi`), pos=`['Marvel Zombies', 'Alien Earth']`, neg=`[]`
**Keywords:** add=`[]`, derived=`[]`
**Verticals:** `['game']`, type=`within_vertical`

**Resolved:** Marvel Zombies (tv) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Outbreak: Shades of Horror | game | 1.1709 | 0.9777 | 0.9550 | Yes | action, adventure, horror, undead |
| 2 | World War Z VR | game | 1.0871 | 1.0000 | 0.6237 | Yes | action, adventure, horror, science fiction |
| 3 | Dead Static Drive | game | 0.6782 | 0.4984 | 0.4310 | Yes | action, adventure, apocalypse, horror |
| 4 | Ground Zero | game | 0.6305 | 0.5644 | 0.1182 | Yes | action, horror, survival, zombies |
| 5 | Echoes of the Living | game | 0.5125 | 0.7322 | 0.0000 |  | adventure, horror, zombies |
| 6 | AI Limit | game | 0.4407 | 0.6296 | 0.0000 |  | action, adventure, dystopian |
| 7 | Darkest Days | game | 0.4327 | 0.6182 | 0.0000 |  | action, adventure, survival |
| 8 | Marvel's Wolverine | game | 0.3910 | 0.2403 | 0.0758 | Yes | action, adventure, marvel, science fiction |
| 9 | Zombie Army VR | game | 0.3774 | 0.0545 | 0.4642 | Yes | action, adventure, horror, survival |
| 10 | Antarctica 88: Remaster | game | 0.3650 | 0.5215 | 0.0000 |  | action, adventure, horror, survival |

*Latency: 570ms (NLU 448 + retrieval 122 + filter 0 + rerank 0)*

### Theme Based

#### Q7: "Horror content across all categories"

**NLU:** mode=`theme_based` (expected `theme_based`), pos=`[]`, neg=`[]`
**Keywords:** add=`['horror']`, derived=`[]`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`


**GAME** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Outbreak: Shades of Horror | 0.3500 | 0.0000 | 1.0000 |  |  |
| 2 | Garten of Banban 8: Anti Devil | 0.3500 | 0.0000 | 1.0000 |  |  |
| 3 | BrokenLore: Low | 0.3500 | 0.0000 | 1.0000 |  |  |
| 4 | Memoreum | 0.3500 | 0.0000 | 1.0000 |  |  |
| 5 | Kletka | 0.3500 | 0.0000 | 1.0000 |  |  |
| 6 | Reanimal | 0.3500 | 0.0000 | 1.0000 |  |  |
| 7 | Ayasa: Shadows of Silence | 0.3500 | 0.0000 | 1.0000 |  |  |
| 8 | Cronos: The New Dawn | 0.3500 | 0.0000 | 1.0000 |  |  |
| 9 | Garten of Banban 0 | 0.3500 | 0.0000 | 1.0000 |  |  |
| 10 | Project Songbird | 0.3500 | 0.0000 | 1.0000 |  |  |

**MOVIE** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Jester 2 | 0.7500 | 1.0000 | 0.0000 |  |  |
| 2 | Wizard of Oz: Dead Walk | 0.6504 | 0.8577 | 0.0000 |  |  |
| 3 | Die'ced: Reloaded | 0.3394 | 0.4134 | 0.0000 |  |  |
| 4 | The Dreadful | 0.2588 | 0.2983 | 0.0000 |  |  |
| 5 | Bambi: The Reckoning | 0.2364 | 0.2664 | 0.0000 |  |  |
| 6 | Wormtown | 0.2147 | 0.2353 | 0.0000 |  |  |
| 7 | Darbie's Scream House | 0.1884 | 0.1977 | 0.0000 |  |  |
| 8 | Hybrid Hazards: Revelation | 0.1564 | 0.1520 | 0.0000 |  |  |
| 9 | Wolf Man | 0.1101 | 0.0859 | 0.0000 |  |  |
| 10 | The Monkey | 0.1005 | 0.0721 | 0.0000 |  |  |

*Latency: 913ms (NLU 435 + retrieval 478 + filter 0 + rerank 0)*

#### Q8: "Recommend me sci-fi adventure content"

**NLU:** mode=`theme_based` (expected `theme_based`), pos=`[]`, neg=`[]`
**Keywords:** add=`['sci-fi', 'adventure']`, derived=`[]`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`


**GAME** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Space Adventure Cobra: The Awakening | 0.8394 | 0.4849 | 1.0000 | Yes |  |
| 2 | Citizen Sleeper 2: Starward Vector | 0.7500 | 1.0000 | 0.0000 |  |  |
| 3 | Mio: Memories in Orbit | 0.6664 | 0.8805 | 0.0000 |  |  |
| 4 | Pragmata | 0.6635 | 0.8765 | 0.0000 |  |  |
| 5 | Empyreal | 0.5712 | 0.1018 | 1.0000 | Yes |  |
| 6 | Shrapnel | 0.4000 | 0.0000 | 1.0000 |  |  |
| 7 | Revenge of the Savage Planet | 0.4000 | 0.0000 | 1.0000 |  |  |
| 8 | Of Lies and Rain | 0.4000 | 0.0000 | 1.0000 |  |  |
| 9 | MindsEye | 0.4000 | 0.0000 | 1.0000 |  |  |
| 10 | The Expanse: Osiris Reborn | 0.3141 | 0.3773 | 0.0000 |  |  |

**MOVIE** (3 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Winter of Empires | 0.5361 | 0.6944 | 0.0000 |  |  |
| 2 | Elio | 0.3774 | 0.4677 | 0.0000 |  |  |
| 3 | Space/Time | 0.1358 | 0.1940 | 0.0000 |  |  |

*Latency: 865ms (NLU 496 + retrieval 369 + filter 0 + rerank 0)*

#### Q9: "Find me dark fantasy games"

**NLU:** mode=`theme_based` (expected `theme_based`), pos=`[]`, neg=`[]`
**Keywords:** add=`['dark fantasy']`, derived=`[]`
**Verticals:** `['game']`, type=`within_vertical`


| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | The Blood of Dawnwalker | game | 0.7500 | 1.0000 | 0.0000 |  |  |
| 2 | Netherworld Covenant | game | 0.7283 | 0.3975 | 1.0000 | Yes |  |
| 3 | Lost in Random: The Eternal Die | game | 0.6850 | 0.3357 | 1.0000 | Yes |  |
| 4 | Under Heaven or Hell | game | 0.6764 | 0.8949 | 0.0000 |  |  |
| 5 | Mandragora: Whispers of the Witch Tree | game | 0.5956 | 0.6365 | 0.0000 | Yes |  |
| 6 | Tainted Grail: The Fall of Avalon | game | 0.5882 | 0.6260 | 0.0000 | Yes |  |
| 7 | Kristala | game | 0.5858 | 0.6226 | 0.0000 | Yes |  |
| 8 | Styx: Blades of Greed | game | 0.5486 | 0.1408 | 1.0000 | Yes |  |
| 9 | Chaos Zero Nightmare | game | 0.4639 | 0.5913 | 0.0000 |  |  |
| 10 | Mörk Borg Heresy Supreme | game | 0.4456 | 0.5651 | 0.0000 |  |  |

*Latency: 845ms (NLU 456 + retrieval 389 + filter 0 + rerank 0)*

### Descriptive

#### Q10: "I like content with country wars and gun fighting and military operations"

**NLU:** mode=`descriptive` (expected `descriptive`), pos=`[]`, neg=`[]`
**Keywords:** add=`[]`, derived=`['military warfare', 'combat', 'war drama', 'tactical shooter']`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`


**GAME** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Shadows of Soldiers | 0.7598 | 0.3569 | 1.0000 | Yes |  |
| 2 | Forefront | 0.4907 | 0.6153 | 0.0000 |  |  |
| 3 | Arena Breakout: Infinite | 0.3855 | 0.4650 | 0.0000 |  |  |
| 4 | Rainbow Six Mobile | 0.2362 | 0.2517 | 0.0000 |  |  |
| 5 | Shrapnel | 0.2149 | 0.2641 | 0.0000 |  |  |
| 6 | Sniper Warrior Elite | 0.1848 | 0.2212 | 0.0000 |  |  |
| 7 | Dustwind: Resistance | 0.1566 | 0.2237 | 0.0000 |  |  |
| 8 | Gallipoli | 0.1251 | 0.1358 | 0.0000 |  |  |
| 9 | Battlefield 6: Phantom Edition | 0.1247 | 0.1352 | 0.0000 |  |  |
| 10 | Battlefield REDSEC | 0.0986 | 0.0979 | 0.0000 |  |  |

**MOVIE** (7 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Warfare | 0.7300 | 1.0000 | 0.0000 |  |  |
| 2 | Sniper: The Last Stand | 0.3889 | 0.5556 | 0.0000 |  |  |
| 3 | Sniper: No Nation | 0.3218 | 0.3883 | 0.0000 |  |  |
| 4 | War Machine | 0.2770 | 0.3243 | 0.0000 |  |  |
| 5 | Valiant One | 0.2599 | 0.3713 | 0.0000 |  |  |
| 6 | Lost Horizon | 0.2227 | 0.2468 | 0.0000 |  |  |
| 7 | One Mile: Chapter Two | 0.0715 | 0.0594 | 0.0000 |  |  |

*Latency: 799ms (NLU 426 + retrieval 372 + filter 0 + rerank 0)*

#### Q11: "Something with slow-burn psychological tension and unreliable narrators"

**NLU:** mode=`theme_based` (expected `descriptive`), pos=`[]`, neg=`[]`
**Keywords:** add=`['slow-burn', 'psychological', 'tension', 'unreliable narrators']`, derived=`['psychological thriller', 'mind game', 'suspense']`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`


**GAME** (7 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Slender Threads | 1.0472 | 0.6389 | 1.0000 | Yes |  |
| 2 | Who's at the Door? | 0.4767 | 0.5239 | 0.0000 |  |  |
| 3 | Thief's Shelter | 0.2954 | 0.3505 | 0.0000 |  |  |
| 4 | Suspense: Madman's Dreams | 0.2337 | 0.2481 | 0.0000 |  |  |
| 5 | Centum | 0.2224 | 0.2462 | 0.0000 |  |  |
| 6 | Post Trauma | 0.1715 | 0.1164 | 0.0000 |  |  |
| 7 | True Fear: Forsaken Souls Part 3 | 0.1136 | 0.0000 | 0.1120 |  |  |

**MOVIE** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Past Life | 0.8787 | 0.7868 | 0.3265 | Yes |  |
| 2 | American Psychopath | 0.8626 | 0.7638 | 0.3265 | Yes |  |
| 3 | The Actor | 0.5888 | 0.7269 | 0.0000 |  |  |
| 4 | The Highest Stakes | 0.3587 | 0.0000 | 0.7624 |  |  |
| 5 | Refuge | 0.2403 | 0.1433 | 0.0000 |  |  |
| 6 | The Man in My Basement | 0.2367 | 0.1810 | 0.0000 |  |  |
| 7 | The Home | 0.2226 | 0.0000 | 0.4087 |  |  |
| 8 | Unauthorized Love | 0.2224 | 0.1463 | 0.0000 |  |  |
| 9 | Newborn | 0.2157 | 0.0000 | 0.3856 |  |  |
| 10 | Girl in the Attic | 0.1980 | 0.0000 | 0.3265 |  |  |

**TV** (6 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Beast in Me | 1.0757 | 1.0000 | 0.3856 | Yes |  |
| 2 | Half Man | 0.4695 | 0.1504 | 0.4474 | Yes |  |
| 3 | Memory of a Killer | 0.2280 | 0.0000 | 0.3265 |  |  |
| 4 | We Were Liars | 0.1949 | 0.1641 | 0.0000 |  |  |
| 5 | 56 Days | 0.1790 | 0.0986 | 0.0000 |  |  |
| 6 | Unchosen | 0.1201 | 0.0859 | 0.0000 |  |  |

*Latency: 908ms (NLU 527 + retrieval 378 + filter 0 + rerank 3)*

#### Q12: "I want cozy wholesome content about building and creating things"

**NLU:** mode=`theme_based` (expected `descriptive`), pos=`[]`, neg=`[]`
**Keywords:** add=`['cozy', 'wholesome', 'building', 'creating']`, derived=`['creative building', 'construction', 'crafting']`
**Verticals:** `['game', 'movie', 'tv']`, type=`within_vertical`


**GAME** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | House Builder 2 | 0.8100 | 1.0000 | 0.0000 |  |  |
| 2 | Architect Life: A House Design Simulator | 0.6418 | 0.3229 | 0.7191 | Yes |  |
| 3 | Outbound | 0.4938 | 0.3317 | 0.2052 | Yes |  |
| 4 | Aerthlings | 0.4800 | 0.0000 | 1.0000 |  |  |
| 5 | Winter Burrow | 0.4579 | 0.3255 | 0.0000 | Yes |  |
| 6 | Little Witch in the Woods | 0.4253 | 0.0000 | 0.9178 |  |  |
| 7 | Camper Van: Make it Home | 0.4184 | 0.4835 | 0.0000 |  |  |
| 8 | Cozy Caravan | 0.3715 | 0.1797 | 0.0524 | Yes |  |
| 9 | Preserve | 0.3236 | 0.0852 | 0.2131 | Yes |  |
| 10 | Pocket Nook | 0.3228 | 0.3897 | 0.0000 |  |  |

*Latency: 916ms (NLU 562 + retrieval 354 + filter 0 + rerank 0)*

### Mixed + Negatives

#### Q13: "Love Elden Ring but hate Star Wars, want dark fantasy movies"

**NLU:** mode=`mixed` (expected `mixed`), pos=`['Elden Ring']`, neg=`['Star Wars']`
**Keywords:** add=`['dark fantasy']`, derived=`[]`
**Verticals:** `['movie']`, type=`cross_vertical`

**Resolved:** Elden Ring Nightreign (game) [prefix]
**Negatives:** Star Wars: Galactic Racer (game)

**Neg filter:** 0 penalized, 21 removed (53 → 32)

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | In the Lost Lands | movie | 1.3812 | 1.0000 | 0.9667 | Yes | action, dark fantasy, fantasy |
| 2 | Tales from Black Manor | movie | 1.0390 | 0.7482 | 1.0000 | Yes | dark fantasy, fantasy |
| 3 | The Rats: A Witcher Tale | movie | 0.9711 | 0.5084 | 1.0000 | Yes | dark fantasy, fantasy |
| 4 | The Witcher: Sirens of the Deep | movie | 0.8874 | 0.4775 | 1.0000 | Yes | action, dark fantasy, fantasy |
| 5 | Peter Pan's Neverland Nightmare | movie | 0.4962 | 0.6182 | 0.0000 |  | fantasy |
| 6 | Predator: Badlands | movie | 0.4687 | 0.6696 | 0.0000 |  | action, survival |
| 7 | Wizard of Oz: Dead Walk | movie | 0.4492 | 0.4808 | 0.0000 | Yes | fantasy |
| 8 | Until Dawn | movie | 0.4390 | 0.6271 | 0.0000 |  | survival |
| 9 | The Old Guard 2 | movie | 0.4265 | 0.6093 | 0.0000 |  | action, fantasy |
| 10 | The Jurassic Games: Extinction | movie | 0.3158 | 0.0000 | 0.5525 |  | action, fantasy, survival |

*Latency: 486ms (NLU 365 + retrieval 81 + filter 40 + rerank 0)*

#### Q14: "I like Resident Evil and horror games but dislike comedy, recommend TV shows"

**NLU:** mode=`mixed` (expected `mixed`), pos=`['Resident Evil']`, neg=`['comedy']`
**Keywords:** add=`['horror']`, derived=`[]`
**Verticals:** `['tv']`, type=`cross_vertical`

**Resolved:** Resident Evil Requiem (game) [prefix]
**Negatives:** [keyword: comedy]

**Neg filter:** 2 penalized, 10 removed (40 → 30)

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Marvel Zombies | tv | 1.4000 | 1.0000 | 1.0000 | Yes | action, adventure, horror, zombies |
| 2 | IT: Welcome to Derry | tv | 1.1720 | 1.0000 | 0.9667 | Yes | horror |
| 3 | Hell Motel | tv | 1.1493 | 0.9452 | 1.0000 | Yes | horror, suspense |
| 4 | Devil May Cry | tv | 1.0797 | 0.8208 | 1.0000 | Yes | action, horror |
| 5 | Alien: Earth | tv | 1.0013 | 0.8386 | 0.9667 | Yes | horror |
| 6 | The Institute | tv | 0.9912 | 0.6629 | 1.0000 | Yes | horror |
| 7 | The Beauty | tv | 0.9901 | 0.6609 | 1.0000 | Yes | horror |
| 8 | Something Very Bad Is Going to Happen | tv | 0.9421 | 0.5752 | 1.0000 | Yes | horror |
| 9 | True Haunting | tv | 0.9169 | 0.5301 | 1.0000 | Yes | horror |
| 10 | The Bondsman | tv | 0.8001 | 0.5895 | 1.0000 | Yes | action, horror |

*Latency: 503ms (NLU 380 + retrieval 88 + filter 35 + rerank 0)*

#### Q15: "Recommend games based on Marvel Zombies and Devil May Cry but nothing like kids shows"

**NLU:** mode=`entity_multi` (expected `mixed`), pos=`['Marvel Zombies', 'Devil May Cry']`, neg=`['kids shows']`
**Keywords:** add=`[]`, derived=`['mature', 'action']`
**Verticals:** `['game']`, type=`within_vertical`

**Resolved:** Marvel Zombies (tv) [exact], Devil May Cry (tv) [exact]
**Negatives:** [keyword: kids shows]

**Neg filter:** 0 penalized, 4 removed (46 → 42)

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Outbreak: Shades of Horror | game | 1.2209 | 0.9777 | 0.9550 | Yes | action, adventure, horror, undead |
| 2 | World War Z VR | game | 1.1371 | 1.0000 | 0.6237 | Yes | action, adventure, horror, science fiction |
| 3 | Lethal Honor: Order of the Apocalypse | game | 0.9716 | 0.7881 | 0.4431 | Yes | action, adventure, brutal, dark fantasy |
| 4 | Under Heaven or Hell | game | 0.9049 | 0.5784 | 1.0000 | Yes | adventure, dark fantasy, fantasy, gothic |
| 5 | Code Vein II | game | 0.8800 | 1.0000 | 0.0000 |  | combat, dark fantasy, survival |
| 6 | The Red Bell’s Lament | game | 0.8019 | 0.7268 | 0.3105 | Yes | adventure, dark fantasy, gothic, supernatural |
| 7 | Doom: The Dark Ages | game | 0.7782 | 0.6756 | 0.1844 | Yes | action, dark fantasy, demons, science fiction |
| 8 | Dead Static Drive | game | 0.7282 | 0.4984 | 0.4310 | Yes | action, adventure, apocalypse, horror |
| 9 | Ground Zero | game | 0.6805 | 0.5644 | 0.1182 | Yes | action, horror, survival, zombies |
| 10 | Hell is Us | game | 0.5947 | 0.8068 | 0.0000 |  | adventure, fantasy, horror, science fiction |

*Latency: 570ms (NLU 438 + retrieval 95 + filter 36 + rerank 0)*

#### Q16: "I enjoyed Silent Hill f and psychological horror but I dont like action-heavy content, find movies"

**NLU:** mode=`mixed` (expected `mixed`), pos=`['Silent Hill f']`, neg=`['action-heavy content']`
**Keywords:** add=`['psychological horror']`, derived=`[]`
**Verticals:** `['movie']`, type=`cross_vertical`

**Resolved:** Silent Hill f (game) [exact]
**Negatives:** [keyword: action-heavy content]

**Neg filter:** 0 penalized, 19 removed (56 → 37)

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Return to Silent Hill | movie | 1.0000 | 1.0000 | 0.9667 | Yes | horror |
| 2 | American Psychopath | movie | 0.7100 | 1.0000 | 0.0000 |  | horror, psychological |
| 3 | Bight | movie | 0.6961 | 0.4037 | 1.0000 | Yes | horror |
| 4 | Dark Frequency | movie | 0.6060 | 0.8142 | 0.0000 |  | horror, psychological |
| 5 | Sherlock Holmes Mare of the Night | movie | 0.5798 | 0.1960 | 1.0000 | Yes |  |
| 6 | Until Dawn | movie | 0.5738 | 0.6054 | 0.0000 |  | horror, psychological |
| 7 | Bone Hill | movie | 0.5677 | 0.7460 | 0.0000 |  | horror |
| 8 | Passenger | movie | 0.5178 | 0.0000 | 0.8928 | Yes | horror, psychological, survival horror |
| 9 | Hypochondriac | movie | 0.4777 | 0.7995 | 0.0000 |  | horror, psychological |
| 10 | The Home | movie | 0.4695 | 0.1708 | 0.0000 | Yes | horror, psychological |

*Latency: 2912ms (NLU 2459 + retrieval 411 + filter 41 + rerank 0)*

### Multi-Vertical

#### Q17: "Content similar to Elden Ring Nightreign across all categories"

**NLU:** mode=`entity_single` (expected `entity_single`), pos=`['Elden Ring', 'Nightreign']`, neg=`[]`
**Keywords:** add=`[]`, derived=`[]`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`

**Resolved:** Elden Ring Nightreign (game) [prefix], Elden Ring Nightreign (game) [contains]

**GAME** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Nioh 3 | 0.2611 | 0.1849 | 0.1056 | Yes | action, challenging, cooperative, open world |
| 2 | Jötunnslayer: Hordes of Hel | 0.1819 | 0.0774 | 0.0923 | Yes | action, cooperative, dark fantasy, roguelike |
| 3 | Darkest Days | 0.1722 | 0.0875 | 0.0364 | Yes | action, cooperative, open world, role-playing |
| 4 | Dragonkin: The Banished | 0.1525 | 0.0750 | 0.0000 | Yes | action, cooperative, dark fantasy, role-playing |
| 5 | EverSiege: Untold Ages | 0.1479 | 0.0517 | 0.0390 | Yes | cooperative, fantasy, procedural, role-playing |
| 6 | Code Vein II | 0.1299 | 0.1856 | 0.0000 |  | dark fantasy, role-playing, survival |
| 7 | 33 Immortals | 0.1286 | 0.0244 | 0.0386 | Yes | action, cooperative, fantasy, roguelike |
| 8 | Monster Hunter Wilds | 0.0846 | 0.1209 | 0.0000 |  | action, fantasy, open world, role-playing |
| 9 | Let It Die: Inferno | 0.0752 | 0.1074 | 0.0000 |  | action, cooperative, survival |
| 10 | Rotwood | 0.0723 | 0.1033 | 0.0000 |  | action, roguelike, role-playing |

*Latency: 4540ms (NLU 4442 + retrieval 98 + filter 0 + rerank 0)*

#### Q18: "Recommend me games movies and TV shows based on my love for horror and survival themes"

**NLU:** mode=`theme_based` (expected `theme_based`), pos=`[]`, neg=`[]`
**Keywords:** add=`['horror', 'survival']`, derived=`[]`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`


**GAME** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | I Hate this Place | 0.8008 | 0.8583 | 0.0000 | Yes |  |
| 2 | Ground Zero | 0.8000 | 1.0000 | 0.0000 |  |  |
| 3 | Storebound | 0.6097 | 0.1568 | 1.0000 | Yes |  |
| 4 | Memoreum | 0.5011 | 0.0016 | 1.0000 | Yes |  |
| 5 | Halloween | 0.4025 | 0.2893 | 0.0000 | Yes |  |
| 6 | Garten of Banban 8: Anti Devil | 0.4000 | 0.0000 | 1.0000 |  |  |
| 7 | Kletka | 0.4000 | 0.0000 | 1.0000 |  |  |
| 8 | Echoes of the Living | 0.3366 | 0.3665 | 0.0000 |  |  |
| 9 | Dead Static Drive | 0.3217 | 0.3168 | 0.0000 |  |  |
| 10 | Outbreak: Shades of Horror | 0.2556 | 0.2508 | 0.0000 |  |  |

*Latency: 5041ms (NLU 4633 + retrieval 408 + filter 0 + rerank 0)*

#### Q19: "I love Dark Souls and Stranger Things, recommend everything"

**NLU:** mode=`entity_multi` (expected `entity_multi`), pos=`['Dark Souls', 'Stranger Things']`, neg=`[]`
**Keywords:** add=`[]`, derived=`[]`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`

**Resolved:** Stranger Things: Fireplace (movie) [prefix]

**GAME** (4 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Slender Threads | 0.0134 | 0.0000 | 0.0373 |  | atmospheric, eerie |
| 2 | Dark Memories: Prologue | 0.0134 | 0.0000 | 0.0373 |  | atmospheric, eerie |
| 3 | Sonokuni | 0.0088 | 0.0000 | 0.0245 |  | atmospheric, science fiction, supernatural |
| 4 | Projected Dreams | 0.0083 | 0.0000 | 0.0230 |  | cozy, nostalgia |

**MOVIE** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | World of Westeros Ambient Video | 0.3678 | 0.0895 | 0.1090 | Yes | ambient, atmospheric, cozy |
| 2 | Crazy Texas | 0.2677 | 0.0210 | 0.0159 | Yes | atmospheric, holiday |
| 3 | Backrooms | 0.1054 | 0.1141 | 0.0000 |  | science fiction |
| 4 | Lookout | 0.0540 | 0.0585 | 0.0000 |  | atmospheric, science fiction |
| 5 | My Secret Santa | 0.0484 | 0.0000 | 0.1223 |  | cozy, holiday, seasonal |
| 6 | Silent Night, Deadly Night | 0.0427 | 0.0462 | 0.0000 |  | holiday |
| 7 | One Last Adventure: The Making of Stranger Things 5 | 0.0313 | 0.0000 | 0.0791 |  | nostalgia, stranger things |
| 8 | A Paw Patrol Christmas | 0.0253 | 0.0000 | 0.0638 |  | holiday, seasonal |
| 9 | iHeartRadio Jingle Ball 2025 | 0.0253 | 0.0000 | 0.0638 |  | holiday, seasonal |
| 10 | Keeper | 0.0173 | 0.0187 | 0.0000 |  | atmospheric, supernatural |

**TV** (7 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Stranger Things: Tales from '85 | 0.4657 | 0.2698 | 0.0530 | Yes | nostalgia, science fiction, supernatural |
| 2 | Playing Gracie Darling | 0.2926 | 0.0489 | 0.0876 | Yes | atmospheric, eerie, supernatural |
| 3 | True Haunting | 0.1535 | 0.1827 | 0.0000 |  | atmospheric, supernatural |
| 4 | Something Very Bad Is Going to Happen | 0.0526 | 0.0626 | 0.0000 |  | science fiction, supernatural |
| 5 | The 'Burbs | 0.0484 | 0.0576 | 0.0000 |  |  |
| 6 | Haunted Hotel | 0.0000 | 0.0000 | 0.0000 |  | supernatural |
| 7 | Talamasca: The Secret Order | 0.0000 | 0.0000 | 0.0000 |  | science fiction, supernatural |

*Latency: 3738ms (NLU 3676 + retrieval 62 + filter 0 + rerank 0)*

#### Q20: "Find me dark intense content across games movies and TV"

**NLU:** mode=`theme_based` (expected `theme_based`), pos=`[]`, neg=`[]`
**Keywords:** add=`['dark', 'intense']`, derived=`[]`
**Verticals:** `['game', 'movie', 'tv']`, type=`cross_vertical`


**GAME** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Through the Nightmares | 0.3919 | 0.4884 | 0.0000 |  |  |
| 2 | Street Gods | 0.3800 | 0.0000 | 1.0000 |  |  |
| 3 | Oxide Room 208 | 0.3441 | 0.0000 | 0.8804 |  |  |
| 4 | Netherworld Covenant | 0.3105 | 0.4007 | 0.0000 |  |  |
| 5 | The First Berserker: Khazan | 0.2882 | 0.3403 | 0.0000 |  |  |
| 6 | DarkSwitch | 0.2553 | 0.3219 | 0.0000 |  |  |
| 7 | SteamDolls: Order of Chaos | 0.2534 | 0.3191 | 0.0000 |  |  |
| 8 | The Coma 3: Bloodlines | 0.2461 | 0.1373 | 0.0000 | Yes |  |
| 9 | Night Swarm | 0.2283 | 0.2833 | 0.0000 |  |  |
| 10 | Dark Atlas: Infernum | 0.1554 | 0.1792 | 0.0000 |  |  |

**MOVIE** (10 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Darkness of Man | 0.7300 | 1.0000 | 0.0000 |  |  |
| 2 | Sherlock Holmes Mare of the Night | 0.6020 | 0.8172 | 0.0000 |  |  |
| 3 | Hellfire | 0.3800 | 0.0000 | 1.0000 |  |  |
| 4 | In the Lost Lands | 0.3510 | 0.4586 | 0.0000 |  |  |
| 5 | Darbie's Scream House | 0.3500 | 0.0000 | 1.0000 |  |  |
| 6 | The Dreadful | 0.2240 | 0.1057 | 0.0000 | Yes |  |
| 7 | Dark Frequency | 0.2186 | 0.2694 | 0.0000 |  |  |
| 8 | Peter Pan's Neverland Nightmare | 0.2111 | 0.2587 | 0.0000 |  |  |
| 9 | Silent Night, Deadly Night | 0.0500 | 0.0000 | 0.0000 |  |  |
| 10 | Twisted | 0.0500 | 0.0000 | 0.0000 |  |  |

**TV** (4 results):

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Black Dagger Brotherhood | 0.5398 | 0.7283 | 0.0000 |  |  |
| 2 | Star Wars: Maul - Shadow Lord | 0.2378 | 0.2969 | 0.0000 |  |  |
| 3 | The Terminal List: Dark Wolf | 0.0500 | 0.0000 | 0.0000 |  |  |
| 4 | Monster: The Ed Gein Story | 0.0500 | 0.0000 | 0.0000 |  |  |

*Latency: 5097ms (NLU 4452 + retrieval 645 + filter 0 + rerank 0)*

---

## Section 3 — Quality Analysis

### 3.1 Within-Vertical Accuracy
**100%** (100/100 results in correct vertical)

### 3.2 Cross-Vertical Diversity

| Query | Verticals Returned | Counts |
|-------|--------------------|--------|
| Q7 | ['game', 'movie'] | {'game': 10, 'movie': 10} |
| Q8 | ['game', 'movie'] | {'game': 10, 'movie': 3} |
| Q10 | ['game', 'movie'] | {'game': 10, 'movie': 7} |
| Q11 | ['game', 'movie', 'tv'] | {'game': 7, 'movie': 10, 'tv': 6} |
| Q12 | ['game'] | {'game': 10} |
| Q17 | ['game'] | {'game': 10} |
| Q18 | ['game'] | {'game': 10} |
| Q19 | ['game', 'movie', 'tv'] | {'game': 4, 'movie': 10, 'tv': 7} |
| Q20 | ['game', 'movie', 'tv'] | {'game': 10, 'movie': 10, 'tv': 4} |

### 3.3 Negative Filtering Effectiveness
- Queries with negative filter active: 4
- Total candidates penalized: 2
- Total candidates removed: 54

### 3.4 Keyword Boosting Impact
- Total candidates keyword-boosted across all queries: 362

### 3.5 Multi-Entity Overlap Scoring

- **"Movies similar to Star Wars: The Mandalorian and G..."**: 10 results appeared in multiple entity searches
- **"I love Elden Ring and Nioh 3, recommend me movies..."**: 7 results appeared in multiple entity searches
- **"Games similar to both Resident Evil Requiem and Si..."**: 8 results appeared in multiple entity searches
- **"Love Elden Ring but hate Star Wars, want dark fant..."**: 6 results appeared in multiple entity searches
- **"I like Resident Evil and horror games but dislike ..."**: 10 results appeared in multiple entity searches
- **"Recommend games based on Marvel Zombies and Devil ..."**: 2 results appeared in multiple entity searches
- **"I enjoyed Silent Hill f and psychological horror b..."**: 7 results appeared in multiple entity searches

---

## Section 4 — Score Analysis

| Metric | Min | Max | Avg | Median |
|--------|-----|-----|-----|--------|
| Final Score | 0.0000 | 1.4800 | 0.4466 | 0.3800 |
| Vector Score | 0.0000 | 1.0000 | 0.3398 | 0.2237 |
| BM25 Score | 0.0000 | 1.0000 | 0.2802 | 0.0000 |

- **Total results:** 248
- **Dual-signal:** 94 (38%)
- **Vector-dominant:** 162, **BM25-dominant:** 78

---

## Section 5 — Latency Breakdown

| Stage | Avg (ms) | % of Total |
|-------|----------|------------|
| NLU | 1346 | 85% |
| Retrieval | 234 | 15% |
| Neg Filter | 8 | 0% |
| Reranker | 1 | 0% |
| **Total** | **1588** | **100%** |

### Per-Query Latency

| Query | NLU | Retrieval | Filter | Rerank | Total |
|-------|-----|-----------|--------|--------|-------|
| Q1 | 424 | 60 | 0 | 4 | 488 |
| Q2 | 504 | 85 | 0 | 0 | 589 |
| Q3 | 799 | 13 | 0 | 0 | 812 |
| Q4 | 519 | 85 | 0 | 0 | 604 |
| Q5 | 479 | 81 | 0 | 0 | 561 |
| Q6 | 448 | 122 | 0 | 0 | 570 |
| Q7 | 435 | 478 | 0 | 0 | 913 |
| Q8 | 496 | 369 | 0 | 0 | 865 |
| Q9 | 456 | 389 | 0 | 0 | 845 |
| Q10 | 426 | 372 | 0 | 0 | 799 |
| Q11 | 527 | 378 | 0 | 3 | 908 |
| Q12 | 562 | 354 | 0 | 0 | 916 |
| Q13 | 365 | 81 | 40 | 0 | 486 |
| Q14 | 380 | 88 | 35 | 0 | 503 |
| Q15 | 438 | 95 | 36 | 0 | 570 |
| Q16 | 2459 | 411 | 41 | 0 | 2912 |
| Q17 | 4442 | 98 | 0 | 0 | 4540 |
| Q18 | 4633 | 408 | 0 | 0 | 5041 |
| Q19 | 3676 | 62 | 0 | 0 | 3738 |
| Q20 | 4452 | 645 | 0 | 0 | 5097 |

---

## Section 6 — Comparison vs Phase 1

Phase 1 only supported `entity_single` mode. Queries without a named entity failed completely.

| Capability | Phase 1 | Phase 2 |
|-----------|---------|---------|
| Entity-single queries | Yes | Yes |
| Multi-entity queries | No | Yes (overlap scoring) |
| Theme/genre queries | No (failed) | Yes (query embedding) |
| Descriptive queries | No (failed) | Yes (LLM keyword derivation + embedding) |
| Negative filtering | No | Yes (embedding sim + keyword + franchise) |
| Keyword boosting | No | Yes (+0.05 keyword, +0.03 text) |
| Per-vertical splitting | No | Yes (top 10 per vertical) |
| Franchise diversity | No | Yes (max 3 per franchise) |
| Unresolved neg keywords | No | Yes (keyword-only penalty) |

### Previously-Failing Query Types Now Working

**Now succeeding:** Q7 (theme_based), Q8 (theme_based), Q9 (theme_based), Q10 (descriptive), Q11 (descriptive), Q12 (descriptive), Q13 (mixed), Q14 (mixed), Q15 (mixed), Q16 (mixed), Q18 (theme_based), Q20 (theme_based)

---

## Section 7 — Remaining Gaps and Recommendations

### Queries That Failed

- **Q3**: "TV shows like Stranger Things: Tales from 85" — No entity resolved from: ['Stranger Things: Tales from 85']

### Recommendations

1. **Entity catalog expansion:** Entities not in the 1,757-item DB (e.g., Dark Souls, Stranger Things) fail resolution. Expanding the catalog or adding fuzzy matching with Levenshtein distance would help.
2. **NLU mode boundary refinement:** The LLM sometimes classifies mixed queries as entity_multi (when negatives are present). Fine-tuning the system prompt or adding few-shot examples could improve this.
3. **Theme query embedding quality:** For broad themes like 'horror', the single-keyword embedding may not capture nuance well. Consider expanding theme queries with related terms before embedding.
4. **Negative filter tuning:** The 0.6 cosine similarity threshold for embedding-based penalties could be tuned per use case. Comedy penalties may need different thresholds than franchise penalties.
5. **Production considerations:** Replace in-memory Qdrant with persistent storage, add NLU caching, and implement query-level result caching for repeated searches.

