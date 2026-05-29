# Complex Query Test Results

## Q1: "What games feel like Hollow Knight: Silksong?"

**NLU:** mode=`entity_single`, pos=`['Hollow Knight: Silksong']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['game']` | type=`within_vertical`

**Resolved+:** Hollow Knight: Silksong (game) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Ender Magnolia: Bloom in the Mist | game | 0.3437 | 0.2861 | 0.1449 | Yes | adventure, atmospheric, hand-drawn, indie, metroidvania |
| 2 | Inayah: Life after Gods | game | 0.2775 | 0.2007 | 0.1233 | Yes | action platformer, indie, metroidvania, platform, side-scrolling |
| 3 | Sophie: Starlight Whispers | game | 0.2679 | 0.1901 | 0.1163 | Yes | adventure, exploration, fantasy, indie, metroidvania |
| 4 | Possessor(s) | game | 0.2341 | 0.1511 | 0.0944 | Yes | adventure, hand-drawn, indie, metroidvania, platform |
| 5 | Plus Ultra: Legado | game | 0.2195 | 0.1192 | 0.1201 | Yes | action platformer, adventure, exploration, indie, metroidvania |
| 6 | Somber Echoes | game | 0.1892 | 0.2702 | 0.0000 |  | adventure, indie, metroidvania, platform, side-scrolling |
| 7 | Blade Chimera | game | 0.1817 | 0.0955 | 0.0495 | Yes | exploration, indie, metroidvania, platform, side-scrolling |
| 8 | SteamDolls: Order of Chaos | game | 0.1366 | 0.0047 | 0.1109 | Yes | adventure, atmospheric, exploration, indie, metroidvania |
| 9 | Spirit of the North 2 | game | 0.1352 | 0.1931 | 0.0000 |  | adventure, atmospheric, exploration, indie, platform |
| 10 | Shadow Labyrinth | game | 0.1312 | 0.0000 | 0.1039 | Yes | adventure, atmospheric, exploration, metroidvania, platform |

*Latency: 713ms*

---

## Q2: "Find me movies that have a similar vibe to Predator: Badlands"

**NLU:** mode=`entity_single`, pos=`['Predator: Badlands']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['movie']` | type=`within_vertical`

**Resolved+:** Predator: Badlands (movie) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Predator: Wastelands | movie | 0.5479 | 0.5709 | 0.1609 | Yes | action, franchise, predator, science fiction, survival |
| 2 | Jurassic World Rebirth | movie | 0.2416 | 0.1717 | 0.0714 | Yes | action, adventure, franchise, science fiction, survival |
| 3 | War Machine | movie | 0.2314 | 0.1877 | 0.0000 | Yes | action, science fiction, survival |
| 4 | Worldbreaker | movie | 0.2091 | 0.1558 | 0.0000 | Yes | action, science fiction, survival |
| 5 | Primitive War | movie | 0.2025 | 0.1465 | 0.0000 | Yes | action, science fiction, survival |
| 6 | Star Wars: The Mandalorian and Grogu | movie | 0.1567 | 0.0663 | 0.0343 | Yes | action, adventure, franchise, science fiction |
| 7 | The Land That Time Forgot | movie | 0.1474 | 0.0646 | 0.0073 | Yes | action, adventure, science fiction, survival |
| 8 | Apex | movie | 0.1362 | 0.1946 | 0.0000 |  | action, survival |
| 9 | Avatar: Fire and Ash | movie | 0.1295 | 0.0355 | 0.0155 | Yes | adventure, franchise, science fiction |
| 10 | Thunderbolts* | movie | 0.0798 | 0.1140 | 0.0000 |  | action, adventure, science fiction |

*Latency: 508ms*

---

## Q3: "TV shows like Alien: Earth"

**NLU:** mode=`entity_single`, pos=`['Alien: Earth']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['tv']` | type=`within_vertical`

**Resolved+:** Alien: Earth (tv) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Marvel Zombies | tv | 0.2100 | 0.1388 | 0.0428 | Yes | horror, science fiction, survival |
| 2 | Star City | tv | 0.2041 | 0.1354 | 0.0309 | Yes | drama, science fiction, thriller |
| 3 | Nine Bodies in a Mexican Morgue | tv | 0.2014 | 0.1424 | 0.0056 | Yes | survival, thriller |
| 4 | The Beauty | tv | 0.1875 | 0.0600 | 0.1518 | Yes | body horror, drama, horror, science fiction, thriller |
| 5 | Something Very Bad Is Going to Happen | tv | 0.1804 | 0.0647 | 0.1170 | Yes | claustrophobic, drama, horror, science fiction |
| 6 | The Institute | tv | 0.1707 | 0.0849 | 0.0376 | Yes | horror, science fiction, thriller |
| 7 | Pluribus | tv | 0.1674 | 0.0830 | 0.0309 | Yes | drama, science fiction, thriller |
| 8 | Unchosen | tv | 0.1445 | 0.0272 | 0.0849 | Yes | claustrophobic, drama, thriller |
| 9 | Murderbot | tv | 0.1433 | 0.0478 | 0.0327 | Yes | drama, science fiction, survival |
| 10 | The Last Frontier | tv | 0.1397 | 0.0567 | 0.0000 | Yes | drama, survival |

*Latency: 453ms*

---

## Q4: "I love the game Vampire: The Masquerade - Bloodlines 2, what movies should I watch?"

**NLU:** mode=`entity_single`, pos=`['Vampire: The Masquerade - Bloodlines 2']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['movie']` | type=`cross_vertical`

**Resolved+:** Vampire: The Masquerade - Bloodlines 2 (game) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Tales from Black Manor | movie | 1.0279 | 1.0000 | 0.7597 | Yes | dark fantasy, gothic, horror |
| 2 | Vampires of the Velvet Lounge | movie | 0.5912 | 0.2853 | 0.9715 | Yes | horror, supernatural, vampires |
| 3 | In the Lost Lands | movie | 0.4561 | 0.6516 | 0.0000 |  | dark fantasy |
| 4 | Until Dawn | movie | 0.4232 | 0.3791 | 0.1927 | Yes | horror, mystery, supernatural |
| 5 | Return to Silent Hill | movie | 0.4087 | 0.0125 | 1.0000 | Yes | gothic, horror, mystery, supernatural |
| 6 | The Rats: A Witcher Tale | movie | 0.3624 | 0.5178 | 0.0000 |  | adventure, dark fantasy |
| 7 | Peaky Blinders: The Immortal Man | movie | 0.2059 | 0.2942 | 0.0000 |  |  |
| 8 | Sherlock Holmes Mare of the Night | movie | 0.2038 | 0.1275 | 0.0484 | Yes | gothic, mystery |
| 9 | Witchboard | movie | 0.1907 | 0.0000 | 0.6356 |  | gothic, horror, supernatural |
| 10 | Bone Hill | movie | 0.1907 | 0.0000 | 0.6356 |  | gothic, horror, supernatural |

*Latency: 420ms*

---

## Q5: "I really enjoyed the TV show Devil May Cry, what games would I like?"

**NLU:** mode=`None`, pos=`[]`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `[]` | type=`None`


**ERROR:** NLU failed after 3 attempts: Error code: 400 - {'error': {'message': 'tool call validation failed: parameters for tool analyze_query did not match schema: errors: [`/query_mode`: value must be one of "entity_single", "entity_multi", "theme_based", "descriptive", "mixed"]', 'type': 'invalid_request_error', 'code': 'tool_use_failed', 'failed_generation': '<function=analyze_query>{"query_mode": "cross_vertical", "query_type": "cross_vertical", "positive_entities": ["Devil May Cry"], "negative_entities": [], "additional_keywords": [], "description_derived_keywords": [], "target_verticals": ["game"]} </function>'}}

## Q6: "Based on the movie Avatar: Fire and Ash, recommend me TV shows and games"

**NLU:** mode=`entity_single`, pos=`['Avatar: Fire and Ash']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['tv', 'game']` | type=`cross_vertical`

**Resolved+:** Avatar: Fire and Ash (movie) [exact]

### TV (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Mighty Nein | 0.7000 | 1.0000 | 0.0000 |  | fantasy, science fiction |
| 2 | Gabriel and the Guardians | 0.6958 | 0.9940 | 0.0000 |  | adventure, fantasy, science fiction |
| 3 | Eyes of Wakanda | 0.6083 | 0.8691 | 0.0000 |  | adventure, science fiction |
| 4 | Fire and Water: Making the Avatar Films | 0.5040 | 0.1486 | 1.0000 | Yes | avatar, james cameron |
| 5 | Armorsaurs | 0.3418 | 0.4882 | 0.0000 |  | adventure, science fiction |
| 6 | The Black Dagger Brotherhood | 0.3014 | 0.4305 | 0.0000 |  | fantasy |
| 7 | The Dinosaurs | 0.2766 | 0.3952 | 0.0000 |  |  |
| 8 | Chief of War | 0.2702 | 0.3861 | 0.0000 |  |  |
| 9 | Iyanu | 0.2226 | 0.3180 | 0.0000 |  | adventure, fantasy |
| 10 | Wolf King | 0.1781 | 0.2544 | 0.0000 |  | adventure, fantasy, science fiction |

### GAME (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Crimson Desert | 0.6266 | 0.6322 | 0.2800 | Yes | adventure, epic, fantasy |
| 2 | Echoes of the End | 0.4101 | 0.5858 | 0.0000 |  | adventure, fantasy |
| 3 | Aphelion | 0.1858 | 0.2655 | 0.0000 |  | adventure, science fiction |
| 4 | Hyrule Warriors: Age of Imprisonment | 0.0840 | 0.0000 | 0.2800 |  | adventure, epic, fantasy |
| 5 | The Adventures of Elliot: The Millennium Tales | 0.0840 | 0.0000 | 0.2800 |  | adventure, epic, fantasy |
| 6 | Dreams of Another | 0.0721 | 0.0000 | 0.2403 |  | adventure, world-building |
| 7 | Myrk: Echoes of the Forgotten | 0.0687 | 0.0000 | 0.2290 |  | epic, fantasy |
| 8 | GreedFall: The Dying World | 0.0586 | 0.0837 | 0.0000 |  | adventure, fantasy, science fiction |
| 9 | Bearly Escape | 0.0502 | 0.0000 | 0.1675 |  | adventure, ecological |
| 10 | Bee Simulator: The Hive | 0.0502 | 0.0000 | 0.1675 |  | adventure, ecological |

*Latency: 509ms*

---

## Q7: "I love both Code Vein II and Monster Hunter Wilds, find me similar games"

**NLU:** mode=`entity_multi`, pos=`['Code Vein II', 'Monster Hunter Wilds']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['game']` | type=`within_vertical`

**Resolved+:** Code Vein II (game) [exact], Monster Hunter Wilds (game) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Monster Hunter Stories 3: Twisted Reflection | game | 0.8144 | 0.4374 | 0.1471 | Yes | action, adventure, capcom, fantasy, monster hunter |
| 2 | Beast of Reincarnation | game | 0.4697 | 0.2427 | 0.0088 | Yes | action rpg, adventure, post-apocalyptic, role-playing |
| 3 | AI Limit | game | 0.3772 | 0.0926 | 0.1254 | Yes | action, action rpg, adventure, combat, dark fantasy |
| 4 | Mongil: Star Dive | game | 0.3663 | 0.0988 | 0.0474 | Yes | action rpg, adventure, fantasy, role-playing, third person |
| 5 | The Blood of Dawnwalker | game | 0.3438 | 0.1099 | 0.0007 | Yes | action rpg, adventure, dark fantasy, open world, role-playing |
| 6 | Elden Ring Nightreign | game | 0.3317 | 0.1804 | 0.0000 |  | action, dark fantasy, fantasy, open world, role-playing |
| 7 | Duet Night Abyss | game | 0.3211 | 0.0499 | 0.0496 | Yes | action, adventure, co-op, fantasy, multiplayer |
| 8 | Tails of Iron II: Whiskers of Winter | game | 0.3062 | 0.0668 | 0.0063 | Yes | action rpg, adventure, dark fantasy, role-playing |
| 9 | Wuchang: Fallen Feathers | game | 0.2970 | 0.0593 | 0.0007 | Yes | action, action rpg, adventure, dark fantasy, open world |
| 10 | Crimson Desert | game | 0.2838 | 0.1286 | 0.0000 |  | adventure, combat, dark fantasy, fantasy, open world |

*Latency: 559ms*

---

## Q8: "Movies like both Predator: Badlands and The Old Guard 2"

**NLU:** mode=`entity_multi`, pos=`['Predator: Badlands', 'The Old Guard 2']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['movie']` | type=`within_vertical`

**Resolved+:** Predator: Badlands (movie) [exact], The Old Guard 2 (movie) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Predator: Wastelands | movie | 0.9899 | 0.5651 | 0.1533 | Yes | action, franchise, predator, science fiction, survival |
| 2 | Red Sonja | movie | 0.4934 | 0.2685 | 0.0084 | Yes | action, adventure, combat, fantasy |
| 3 | Avatar: Fire and Ash | movie | 0.4304 | 0.0697 | 0.0066 | Yes | adventure, fantasy, franchise, science fiction |
| 4 | Jurassic World Rebirth | movie | 0.4153 | 0.1606 | 0.0630 | Yes | action, adventure, franchise, science fiction, survival |
| 5 | Lost Horizon | movie | 0.3240 | 0.1721 | 0.0000 |  | action, adventure, combat |
| 6 | Suky | movie | 0.3156 | 0.0753 | 0.0101 | Yes | action, survival, visceral |
| 7 | Star Wars: The Mandalorian and Grogu | movie | 0.3017 | 0.0537 | 0.0256 | Yes | action, adventure, franchise, science fiction |
| 8 | Thunderbolts* | movie | 0.2593 | 0.1021 | 0.0000 |  | action, adventure, science fiction |
| 9 | Apex | movie | 0.1698 | 0.1837 | 0.0000 |  | action, survival |
| 10 | War Machine | movie | 0.1634 | 0.1768 | 0.0000 |  | action, combat, science fiction, survival |

*Latency: 523ms*

---

## Q9: "I enjoy Resident Evil Requiem and Silent Hill f as games, recommend me movies and TV shows"

**NLU:** mode=`entity_multi`, pos=`['Resident Evil Requiem', 'Silent Hill']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['movie', 'tv']` | type=`cross_vertical`

**Resolved+:** Resident Evil Requiem (game) [exact], Silent Hill f (game) [prefix]

### MOVIE (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Return to Silent Hill | 0.8500 | 1.0000 | 0.0000 |  | horror |
| 2 | Until Dawn | 0.7822 | 0.9031 | 0.0000 |  | horror, psychological |
| 3 | Silent Zone | 0.6836 | 0.2678 | 0.4870 | Yes | horror, survival horror |
| 4 | George A. Romero's Resident Evil | 0.6106 | 0.3087 | 0.6481 | Yes | resident evil |
| 5 | Evil Dead Burn | 0.6014 | 0.1505 | 1.0000 | Yes | franchise, horror, survival horror |
| 6 | The Strangers: Chapter 3 | 0.4511 | 0.2417 | 0.1072 | Yes | franchise, horror |
| 7 | Final Destination Bloodlines | 0.4500 | 0.0000 | 1.0000 |  | franchise, horror, survival horror |
| 8 | American Psychopath | 0.4254 | 0.1026 | 0.5846 | Yes | horror, psychological, suspense |
| 9 | Passenger | 0.4178 | 0.0000 | 0.8928 |  | horror, psychological, survival horror |
| 10 | Scream 7 | 0.3919 | 0.2027 | 0.1072 | Yes | franchise, horror |

### TV (4 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Marvel Zombies | 0.6061 | 0.1516 | 1.0000 | Yes | action, adventure, horror, zombies |
| 2 | Hell Motel | 0.1754 | 0.0000 | 0.5846 |  | horror, suspense |
| 3 | IT: Welcome to Derry | 0.1666 | 0.0000 | 0.5555 |  | 1960s, horror |
| 4 | Alien: Earth | 0.0000 | 0.0000 | 0.0000 |  | horror |

*Latency: 550ms*

---

## Q10: "Based on Marvel Zombies TV show and Alien: Earth TV show, what games should I play?"

**NLU:** mode=`entity_multi`, pos=`['Marvel Zombies TV show', 'Alien: Earth TV show']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['game']` | type=`cross_vertical`


**ERROR:** No entities resolved from: ['Marvel Zombies TV show', 'Alien: Earth TV show']

## Q11: "I like the movie In the Lost Lands and the game Crimson Desert, find me TV shows"

**NLU:** mode=`entity_multi`, pos=`['In the Lost Lands', 'Crimson Desert']`, neg=`[]`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['tv']` | type=`cross_vertical`

**Resolved+:** In the Lost Lands (movie) [exact], Crimson Desert (game) [exact]

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | American Primeval | tv | 1.3500 | 1.0000 | 1.0000 | Yes | action, frontier, western |
| 2 | Devil May Cry | tv | 1.1290 | 0.6843 | 1.0000 | Yes | action, combat, dark fantasy, fantasy |
| 3 | A Knight of the Seven Kingdoms | tv | 1.0500 | 1.0000 | 0.0000 | Yes | action, adventure, fantasy |
| 4 | The Abandons | tv | 0.9660 | 0.4514 | 1.0000 | Yes | action, frontier, western |
| 5 | The Black Dagger Brotherhood | tv | 0.8344 | 0.4931 | 0.4849 | Yes | action, dark fantasy, fantasy |
| 6 | Marshals | tv | 0.7820 | 0.4029 | 1.0000 | Yes | action, adventure, frontier, western |
| 7 | The Mighty Nein | tv | 0.7388 | 0.8411 | 0.0000 |  | action, fantasy |
| 8 | Star Wars: Tales of the Underworld | tv | 0.6462 | 0.3409 | 0.6917 | Yes | action, adventure, fantasy, moral ambiguity |
| 9 | Gabriel and the Guardians | tv | 0.5551 | 0.5073 | 0.0000 | Yes | action, adventure, fantasy |
| 10 | Spartacus: House of Ashur | tv | 0.4695 | 0.3125 | 0.1690 | Yes | action, combat |

*Latency: 598ms*

---

## Q12: "I want survival horror with psychological elements across all categories"

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`
**Keywords:** `['survival horror', 'psychological']` + derived `[]`
**Verticals:** `['game', 'movie', 'tv']` | type=`cross_vertical`


### GAME (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Dark Atlas: Infernum | 0.8422 | 0.4888 | 1.0000 | Yes |  |
| 2 | Saint of Chains | 0.7600 | 1.0000 | 0.0000 |  |  |
| 3 | Post Trauma | 0.7222 | 0.7746 | 0.0000 | Yes |  |
| 4 | Greek Tragedy | 0.5554 | 0.5792 | 0.0000 | Yes |  |
| 5 | Winter Survival | 0.5245 | 0.6779 | 0.0000 |  |  |
| 6 | Silent Hill f | 0.5000 | 0.0000 | 1.0000 | Yes |  |
| 7 | Memoreum | 0.4848 | 0.5783 | 0.0000 |  |  |
| 8 | Beneath | 0.4000 | 0.0000 | 1.0000 |  |  |
| 9 | Ire: A Prologue | 0.3102 | 0.4003 | 0.0000 |  |  |
| 10 | Order 13 | 0.2831 | 0.1289 | 0.0430 | Yes |  |

### MOVIE (7 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Passenger | 0.4000 | 0.0000 | 1.0000 |  |  |
| 2 | Until Dawn | 0.1330 | 0.1185 | 0.0000 |  |  |
| 3 | Evil Dead Burn | 0.0929 | 0.0000 | 0.0430 |  |  |
| 4 | Killer Whale | 0.0929 | 0.0000 | 0.0430 |  |  |
| 5 | Final Destination Bloodlines | 0.0629 | 0.0000 | 0.0430 |  |  |
| 6 | Silent Zone | 0.0629 | 0.0000 | 0.0430 |  |  |
| 7 | Bigfoot: Blood on the Farm | 0.0629 | 0.0000 | 0.0430 |  |  |

*Latency: 874ms*

---

## Q13: "Find me content about space exploration and alien civilizations"

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`
**Keywords:** `['space exploration', 'alien civilizations']` + derived `[]`
**Verticals:** `['game', 'movie', 'tv']` | type=`cross_vertical`


### GAME (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Terra Invicta | 0.8000 | 1.0000 | 0.0000 | Yes |  |
| 2 | Star Trek: Voyager - Across the Unknown | 0.4948 | 0.7068 | 0.0000 |  |  |
| 3 | Calx | 0.3507 | 0.5010 | 0.0000 |  |  |
| 4 | One Lonely Outpost | 0.2448 | 0.3497 | 0.0000 |  |  |
| 5 | Empyreal | 0.2084 | 0.2977 | 0.0000 |  |  |
| 6 | Ambrosia Sky: Act One | 0.1802 | 0.2574 | 0.0000 |  |  |
| 7 | Space for Sale | 0.1737 | 0.2482 | 0.0000 |  |  |
| 8 | The Alters | 0.1572 | 0.2245 | 0.0000 |  |  |
| 9 | Arknights: Endfield | 0.1019 | 0.1456 | 0.0000 |  |  |
| 10 | Revenge of the Savage Planet | 0.0971 | 0.1388 | 0.0000 |  |  |

### MOVIE (6 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Elio | 0.4611 | 0.6588 | 0.0000 |  |  |
| 2 | Winter of Empires | 0.1749 | 0.2499 | 0.0000 |  |  |
| 3 | War Machine | 0.1332 | 0.1903 | 0.0000 |  |  |
| 4 | Space/Time | 0.1017 | 0.1453 | 0.0000 |  |  |
| 5 | Xeno | 0.0666 | 0.0951 | 0.0000 |  |  |
| 6 | War of the Worlds | 0.0036 | 0.0052 | 0.0000 |  |  |

*Latency: 725ms*

---

## Q14: "I enjoy stories with political intrigue and power struggles"

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`
**Keywords:** `['political intrigue', 'power struggles']` + derived `[]`
**Verticals:** `['game', 'movie', 'tv']` | type=`cross_vertical`


### GAME (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Disciples: Domination | 0.7348 | 0.4216 | 0.9655 | Yes |  |
| 2 | Fall of an Empire | 0.3500 | 0.0000 | 1.0000 |  |  |
| 3 | Chains of Freedom | 0.0429 | 0.0185 | 0.0000 |  |  |
| 4 | Sacre Bleu | 0.0300 | 0.0000 | 0.0000 |  |  |
| 5 | Netherworld | 0.0000 | 0.0000 | 0.0000 |  |  |
| 6 | Hytale | 0.0000 | 0.0000 | 0.0000 |  |  |
| 7 | AI Limit | 0.0000 | 0.0000 | 0.0000 |  |  |
| 8 | Kingdom of Night | 0.0000 | 0.0000 | 0.0000 |  |  |
| 9 | Naïca | 0.0000 | 0.0000 | 0.0000 |  |  |
| 10 | Vampire: The Masquerade - Bloodlines 2 | 0.0000 | 0.0000 | 0.0000 |  |  |

### MOVIE (9 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Ella McCay | 0.6381 | 0.9115 | 0.0000 |  |  |
| 2 | Dune: Part Three | 0.6016 | 0.2313 | 0.9655 | Yes |  |
| 3 | Putin | 0.5122 | 0.7317 | 0.0000 |  |  |
| 4 | The Alto Knights | 0.4373 | 0.6247 | 0.0000 |  |  |
| 5 | Wild Horse Nine | 0.3397 | 0.0000 | 0.9655 |  |  |
| 6 | G20 | 0.3102 | 0.4003 | 0.0000 |  |  |
| 7 | Captain America: Brave New World | 0.1391 | 0.1558 | 0.0000 |  |  |
| 8 | The Brink of War | 0.1284 | 0.1835 | 0.0000 |  |  |
| 9 | True Justice: Eye For An Eye | 0.0677 | 0.0967 | 0.0000 |  |  |

### TV (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | House of David | 0.7300 | 1.0000 | 0.0000 |  |  |
| 2 | Death by Lightning | 0.6745 | 0.9635 | 0.0000 |  |  |
| 3 | MobLand | 0.5695 | 0.8136 | 0.0000 |  |  |
| 4 | Hostage | 0.5541 | 0.7916 | 0.0000 |  |  |
| 5 | Spartacus: House of Ashur | 0.4864 | 0.6520 | 0.0000 |  |  |
| 6 | The Residence | 0.3397 | 0.0000 | 0.9655 |  |  |
| 7 | Miss Governor | 0.3198 | 0.4568 | 0.0000 |  |  |
| 8 | Star Wars: Maul - Shadow Lord | 0.2793 | 0.3990 | 0.0000 |  |  |
| 9 | House of Guinness | 0.2504 | 0.3577 | 0.0000 |  |  |
| 10 | Bet | 0.1446 | 0.2066 | 0.0000 |  |  |

*Latency: 871ms*

---

## Q15: "Content that feels like exploring ancient magical ruins and forgotten civilizations"

**NLU:** mode=`theme_based`, pos=`[]`, neg=`[]`
**Keywords:** `['ancient', 'magical', 'ruins', 'civilizations']` + derived `['fantasy', 'adventure', 'exploration']`
**Verticals:** `['game', 'movie', 'tv']` | type=`cross_vertical`


### GAME (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Regions of Ruin: Runegate | 1.3000 | 1.0000 | 1.0000 | Yes |  |
| 2 | Echoes of the End | 1.0010 | 0.7751 | 0.5278 | Yes |  |
| 3 | Vessels of Decay | 0.8864 | 0.4092 | 1.0000 | Yes |  |
| 4 | The Light of Celestia | 0.7047 | 0.5648 | 0.0309 | Yes |  |
| 5 | Strings of Fate XI: Magic Dream | 0.5208 | 0.5155 | 0.0000 |  |  |
| 6 | Shrine's Legacy | 0.4924 | 0.4748 | 0.0000 |  |  |
| 7 | Under the Island | 0.4878 | 0.4112 | 0.0000 |  |  |
| 8 | Gecko Gods | 0.4490 | 0.4557 | 0.0000 |  |  |
| 9 | The Adventures of Elliot: The Millennium Tales | 0.4432 | 0.4045 | 0.0000 |  |  |
| 10 | Heart of Altai | 0.4273 | 0.4248 | 0.0000 |  |  |

### MOVIE (5 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Lego Disney Princess: Villains Unite | 0.2783 | 0.0000 | 0.4276 |  |  |
| 2 | Snow White | 0.2376 | 0.0000 | 0.3585 |  |  |
| 3 | Smurfs | 0.2376 | 0.0000 | 0.3585 |  |  |
| 4 | Freakier Friday | 0.2376 | 0.0000 | 0.3585 |  |  |
| 5 | The Carpenter's Son | 0.2232 | 0.0000 | 0.4107 |  |  |

### TV (3 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Iyanu | 0.2791 | 0.1701 | 0.0000 |  |  |
| 2 | Talamasca: The Secret Order | 0.2232 | 0.0000 | 0.4107 |  |  |
| 3 | The Librarians: The Next Chapter | 0.1855 | 0.0364 | 0.0000 |  |  |

*Latency: 4894ms*

---

## Q16: "I love Elden Ring Nightreign and dark fantasy but I absolutely hate anything cute or family-friendly, recommend movies"

**NLU:** mode=`mixed`, pos=`['Elden Ring', 'Nightreign']`, neg=`['cute', 'family-friendly']`
**Keywords:** `['dark fantasy']` + derived `[]`
**Verticals:** `['movie']` | type=`cross_vertical`

**Resolved+:** Elden Ring Nightreign (game) [prefix], Elden Ring Nightreign (game) [contains]
**Resolved-:** [keyword: cute], [keyword: family-friendly]
**Neg filter:** 2 penalized, 16 removed

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | In the Lost Lands | movie | 1.5312 | 1.0000 | 0.9667 | Yes | action, dark fantasy, fantasy |
| 2 | Tales from Black Manor | movie | 1.1946 | 0.7582 | 1.0000 | Yes | dark fantasy, fantasy |
| 3 | The Rats: A Witcher Tale | movie | 1.1211 | 0.5105 | 1.0000 | Yes | dark fantasy, fantasy |
| 4 | The Witcher: Sirens of the Deep | movie | 1.0384 | 0.4794 | 1.0000 | Yes | action, dark fantasy, fantasy |
| 5 | Peter Pan's Neverland Nightmare | movie | 0.6518 | 0.6282 | 0.0000 |  | fantasy |
| 6 | Predator: Badlands | movie | 0.6187 | 0.6696 | 0.0000 |  | action, survival |
| 7 | Until Dawn | movie | 0.5890 | 0.6271 | 0.0000 |  | survival |
| 8 | The Old Guard 2 | movie | 0.5765 | 0.6093 | 0.0000 |  | action, fantasy |
| 9 | The Jurassic Games: Extinction | movie | 0.4658 | 0.0000 | 0.5525 |  | action, fantasy, survival |
| 10 | Wizard of Oz: Dead Walk | movie | 0.4544 | 0.4900 | 0.0000 | Yes | fantasy |

*Latency: 5015ms*

---

## Q17: "Games similar to Resident Evil Requiem but nothing like sports or racing games, I want pure horror"

**NLU:** mode=`entity_single`, pos=`['Resident Evil Requiem']`, neg=`['sports', 'racing games']`
**Keywords:** `['horror']` + derived `[]`
**Verticals:** `['game']` | type=`within_vertical`

**Resolved+:** Resident Evil Requiem (game) [exact]
**Resolved-:** EA Sports FC 26 (game), [keyword: racing games]
**Neg filter:** 0 penalized, 3 removed

| # | Name | Vertical | Final | Vec | BM25 | Both | Keywords |
|---|------|----------|-------|-----|------|------|----------|
| 1 | Silent Hill f: Deluxe Edition | game | 0.2776 | 0.1698 | 0.0291 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 2 | Cronos: The New Dawn | game | 0.2722 | 0.1517 | 0.0534 | Yes | action, adventure, horror, puzzle & trivia, survival horror |
| 3 | Echoes of the Living | game | 0.2572 | 0.1238 | 0.0686 | Yes | adventure, horror, survival horror, zombies |
| 4 | Tormented Souls II | game | 0.2399 | 0.1138 | 0.0340 | Yes | action, adventure, horror, puzzle & trivia, survival horror |
| 5 | World War Z VR | game | 0.2169 | 0.0918 | 0.0089 | Yes | action, adventure, horror, zombies |
| 6 | Ground Zero | game | 0.2123 | 0.0175 | 0.1667 | Yes | action, horror, resource management, survival horror, zombies |
| 7 | Silent Hill f | game | 0.1973 | 0.0551 | 0.0291 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 8 | Post Trauma | game | 0.1843 | 0.0390 | 0.0233 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 9 | Code Violet | game | 0.1679 | 0.1685 | 0.0000 |  | action, horror, survival horror |
| 10 | The Mute House | game | 0.1438 | 0.1340 | 0.0000 |  | adventure, horror |

*Latency: 3626ms*

---

## Q18: "I enjoy Silent Hill f and CyberCorp but hate slow paced content, recommend TV shows and movies"

**NLU:** mode=`mixed`, pos=`['Silent Hill f', 'CyberCorp']`, neg=`['slow paced content']`
**Keywords:** `[]` + derived `['fast paced']`
**Verticals:** `['movie', 'tv']` | type=`cross_vertical`

**Resolved+:** Silent Hill f (game) [exact], CyberCorp (game) [exact]
**Resolved-:** [keyword: slow paced content]
**Neg filter:** 0 penalized, 22 removed

### MOVIE (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Last GunFight | 0.8500 | 1.0000 | 0.0000 |  | action |
| 2 | Return to Silent Hill | 0.7000 | 1.0000 | 0.0000 |  | horror |
| 3 | The Running Man | 0.6125 | 0.6474 | 0.8622 | Yes | action, dystopian |
| 4 | F1 | 0.5600 | 1.0000 | 0.0000 |  | action |
| 5 | The Jurassic Games: Extinction | 0.5587 | 0.4083 | 0.0000 | Yes | action, adventure |
| 6 | Cheetahs Up Close with Bertie Gregory | 0.5021 | 0.8966 | 0.0000 |  |  |
| 7 | The Long Walk | 0.4567 | 0.0969 | 0.6890 | Yes | dystopian, horror, psychological |
| 8 | Until Dawn | 0.4238 | 0.6054 | 0.0000 |  | horror, psychological |
| 9 | Predator: Wastelands | 0.4037 | 0.2911 | 0.0000 | Yes | action, franchise |
| 10 | Havoc | 0.3582 | 0.5117 | 0.0000 |  | action |

### TV (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Marvel Zombies | 0.4694 | 0.0000 | 0.8981 | Yes | action, adventure, dystopian, horror |
| 2 | Running Point | 0.3891 | 0.6949 | 0.0000 |  |  |
| 3 | The Testaments | 0.2157 | 0.0000 | 0.7190 |  | dystopian |
| 4 | IT: Welcome to Derry | 0.1666 | 0.0000 | 0.5555 |  | 1960s, horror |
| 5 | The Dark Wizard | 0.1278 | 0.2282 | 0.0000 |  |  |
| 6 | Court of Gold | 0.1194 | 0.2133 | 0.0000 |  |  |
| 7 | Lazarus | 0.0947 | 0.1691 | 0.0000 |  | action |
| 8 | Armorsaurs | 0.0835 | 0.1491 | 0.0000 |  | action, adventure |
| 9 | Countdown | 0.0039 | 0.0070 | 0.0000 |  |  |
| 10 | The Bondsman | 0.0035 | 0.0051 | 0.0000 |  | action, horror |

*Latency: 4963ms*

---

## Q19: "Based on my love for Monster Hunter Wilds and Crimson Desert, but I dislike sci-fi, find me movies and TV shows"

**NLU:** mode=`entity_multi`, pos=`['Monster Hunter Wilds', 'Crimson Desert']`, neg=`['sci-fi']`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['movie', 'tv']` | type=`cross_vertical`

**Resolved+:** Monster Hunter Wilds (game) [exact], Crimson Desert (game) [exact]
**Resolved-:** [keyword: sci-fi]
**Neg filter:** 0 penalized, 7 removed

### MOVIE (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Witcher: Sirens of the Deep | 1.2226 | 0.8180 | 1.0000 | Yes | action, dark fantasy, fantasy, monster hunter |
| 2 | Lost Horizon | 1.2000 | 1.0000 | 1.0000 | Yes | action, adventure, combat, mercenary |
| 3 | In the Lost Lands | 1.0113 | 0.9219 | 0.0531 | Yes | action, dark fantasy, fantasy |
| 4 | Red Sonja | 0.9004 | 0.7262 | 0.1400 | Yes | action, adventure, combat, fantasy |
| 5 | Predator: Badlands | 0.8500 | 1.0000 | 0.0000 |  | action, adventure |
| 6 | Desert Warrior | 0.8028 | 0.8385 | 0.0530 | Yes | action, adventure, epic |
| 7 | The Rats: A Witcher Tale | 0.6893 | 0.0918 | 0.9167 | Yes | adventure, dark fantasy, fantasy, monster hunter |
| 8 | Avatar: Fire and Ash | 0.6422 | 0.4329 | 0.4641 | Yes | adventure, epic, fantasy |
| 9 | Ice Beast | 0.5917 | 0.2462 | 0.7310 | Yes | action, adventure, hunting |
| 10 | The Old Guard 2 | 0.5631 | 0.4992 | 0.0454 | Yes | action, combat, fantasy |

### TV (8 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Devil May Cry | 0.8643 | 0.3626 | 0.8685 | Yes | action, combat, dark fantasy, fantasy |
| 2 | A Knight of the Seven Kingdoms | 0.5028 | 0.7182 | 0.0000 |  | action, adventure, fantasy |
| 3 | The Mighty Nein | 0.3775 | 0.5392 | 0.0000 |  | action, fantasy |
| 4 | The Black Dagger Brotherhood | 0.3007 | 0.1033 | 0.0947 | Yes | action, dark fantasy, fantasy |
| 5 | Stranger Things: Tales from '85 | 0.1540 | 0.0000 | 0.5134 |  | action, adventure, creatures |
| 6 | Eyes of Wakanda | 0.1215 | 0.1736 | 0.0000 |  | action, adventure |
| 7 | Gabriel and the Guardians | 0.1142 | 0.1631 | 0.0000 |  | action, adventure, fantasy |
| 8 | Outlander: Blood of My Blood | 0.0284 | 0.0000 | 0.0946 |  | adventure, epic |

*Latency: 4519ms*

---

## Q20: "I am a huge fan of Hollow Knight: Silksong, Elden Ring Nightreign, and Code Vein II for games, and I loved Marvel Zombies and Devil May Cry as TV shows. I dont like comedy or family content at all. Based on all of this, recommend me the best movies, games, and TV shows across all categories that match my taste"

**NLU:** mode=`entity_multi`, pos=`['Hollow Knight: Silksong', 'Elden Ring Nightreign', 'Code Vein II', 'Marvel Zombies', 'Devil May Cry']`, neg=`['comedy', 'family']`
**Keywords:** `[]` + derived `[]`
**Verticals:** `['game', 'movie', 'tv']` | type=`cross_vertical`

**Resolved+:** Hollow Knight: Silksong (game) [exact], Elden Ring Nightreign (game) [exact], Code Vein II (game) [exact], Marvel Zombies (tv) [exact], Devil May Cry (tv) [exact]
**Resolved-:** The Family Plan 2 (movie), [keyword: comedy]
**Neg filter:** 2 penalized, 13 removed

### GAME (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | Nioh 3 | 0.5743 | 0.1405 | 0.0947 | Yes | action, adventure, challenging, combat, cooperative |
| 2 | Ender Magnolia: Bloom in the Mist | 0.5400 | 0.2672 | 0.1292 | Yes | adventure, atmospheric, dark fantasy, hand-drawn, indie |
| 3 | The Blood of Dawnwalker | 0.5088 | 0.1099 | 0.0907 | Yes | action rpg, adventure, bandai namco, dark fantasy, gothic |
| 4 | Beast of Reincarnation | 0.4697 | 0.2427 | 0.0088 | Yes | action rpg, adventure, post-apocalyptic, role-playing |
| 5 | Inayah: Life after Gods | 0.4504 | 0.1796 | 0.1072 | Yes | action platformer, indie, metroidvania, platform, side-scrolling |
| 6 | Sophie: Starlight Whispers | 0.4375 | 0.1687 | 0.1000 | Yes | adventure, exploration, fantasy, indie, metroidvania |
| 7 | Vampire: The Masquerade - Bloodlines 2 | 0.4282 | 0.1658 | 0.0712 | Yes | adventure, dark fantasy, gothic, horror, role-playing |
| 8 | Possessor(s) | 0.3917 | 0.1286 | 0.0778 | Yes | adventure, combat, hand-drawn, indie, metroidvania |
| 9 | AI Limit | 0.3772 | 0.0926 | 0.1254 | Yes | action, action rpg, adventure, combat, dark fantasy |
| 10 | Plus Ultra: Legado | 0.3718 | 0.0960 | 0.1038 | Yes | action platformer, adventure, exploration, indie, metroidvania |

### MOVIE (10 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Witcher: Sirens of the Deep | 0.3490 | 0.1509 | 0.0063 | Yes | action, animation, dark fantasy, fantasy |
| 2 | Thunderbolts* | 0.2919 | 0.0546 | 0.0723 | Yes | action, adventure, marvel, science fiction, superhero |
| 3 | Silent Zone | 0.1308 | 0.1557 | 0.0000 |  | horror, post-apocalyptic, undead |
| 4 | The Demon Detective | 0.1219 | 0.1451 | 0.0000 |  | action, horror |
| 5 | Worldbreaker | 0.0925 | 0.1101 | 0.0000 |  | action, horror, post-apocalyptic, science fiction, survival |
| 6 | Night of the Zoopocalypse | 0.0696 | 0.2614 | 0.0000 |  | adventure, animation, horror, science fiction |
| 7 | 28 Years Later | 0.0631 | 0.0751 | 0.0000 |  | horror, post-apocalyptic, science fiction, survival |
| 8 | Predator: Wastelands | 0.0495 | 0.0589 | 0.0000 |  | action, post-apocalyptic, science fiction, survival |
| 9 | 28 Years Later: The Bone Temple | 0.0442 | 0.0527 | 0.0000 |  | horror, post-apocalyptic, science fiction |
| 10 | The Old Guard 2 | 0.0343 | 0.0408 | 0.0000 |  | action, combat, fantasy |

### TV (8 results)

| # | Name | Final | Vec | BM25 | Both | Keywords |
|---|------|-------|-----|------|------|----------|
| 1 | The Black Dagger Brotherhood | 0.4956 | 0.2217 | 0.1231 | Yes | action, dark fantasy, demons, fantasy, supernatural |
| 2 | The Bondsman | 0.1558 | 0.1687 | 0.0000 |  | action, fantasy, horror, science fiction, supernatural |
| 3 | The Mighty Nein | 0.0833 | 0.0901 | 0.0000 |  | action, animation, fantasy, science fiction |
| 4 | Gabriel and the Guardians | 0.0654 | 0.0707 | 0.0000 |  | action, adventure, animation, fantasy, science fiction |
| 5 | Star Wars: Maul - Shadow Lord | 0.0230 | 0.0249 | 0.0000 |  | action, adventure, animation, science fiction |
| 6 | LEGO Marvel Avengers: Strange Tails | 0.0141 | 0.0000 | 0.0356 |  | action, adventure, animation, fantasy, marvel |
| 7 | Eyes of Wakanda | 0.0108 | 0.0116 | 0.0000 |  | action, adventure, animation, science fiction |
| 8 | Iron Man and His Awesome Friends | 0.0037 | 0.0000 | 0.0094 |  | action, adventure, animation, fantasy, science fiction |

*Latency: 4781ms*

---

