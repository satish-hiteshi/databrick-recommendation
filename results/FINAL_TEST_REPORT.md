# Feeds.ai Pipeline — Final Test Report

## Section 1 — Executive Summary

- **Queries tested:** 15
- **Successful (with results):** 9/15
- **NLU failures:** 1
- **Entity resolution failures:** 5
- **Average latency:** 830 ms
- **Average results per query:** 6.0

### Key Findings

**What works well:**
- Within-vertical filtering: 100% of results are in the correct vertical (40/40)
- Hybrid retrieval merges vector semantic similarity with BM25 keyword overlap effectively
- Dual-signal bonus rewards entities found by both retrieval methods (59% of all results)
- Latency is suitable for interactive use: avg 830ms (NLU 776ms + retrieval 54ms + rerank 0ms)
- Entity resolution cascade (exact → prefix → contains) handles varied name inputs

**Areas for improvement:**
- 5 queries failed entity resolution — thematic/open queries without a specific entity name are challenging
- Cross-vertical diversity limited: only 0/2 cross-vertical queries return multiple verticals in top 10

---

## Section 2 — Detailed Results Per Query

### Within-Vertical

#### Q1: "What games are like Elden Ring Nightreign?"

**NLU:** anchor=`Elden Ring Nightreign`, intent=`similar`, verticals=`['game']`, type=`within_vertical`

**Entity:** Elden Ring Nightreign (game) [exact]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | Nioh 3 | game | 0.2611 | 0.1849 | 0.1056 | Yes | action, challenging, cooperative, open world, role-playing |
| 2 | Jötunnslayer: Hordes of Hel | game | 0.1819 | 0.0774 | 0.0923 | Yes | action, cooperative, dark fantasy, roguelike, role-playing |
| 3 | Darkest Days | game | 0.1722 | 0.0875 | 0.0364 | Yes | action, cooperative, open world, role-playing, survival |
| 4 | Dragonkin: The Banished | game | 0.1525 | 0.0750 | 0.0000 | Yes | action, cooperative, dark fantasy, role-playing |
| 5 | EverSiege: Untold Ages | game | 0.1479 | 0.0517 | 0.0390 | Yes | cooperative, fantasy, procedural, role-playing |
| 6 | Code Vein II | game | 0.1299 | 0.1856 | 0.0000 |  | dark fantasy, role-playing, survival |
| 7 | 33 Immortals | game | 0.1286 | 0.0244 | 0.0386 | Yes | action, cooperative, fantasy, roguelike, role-playing |
| 8 | Monster Hunter Wilds | game | 0.0846 | 0.1209 | 0.0000 |  | action, fantasy, open world, role-playing |
| 9 | Let It Die: Inferno | game | 0.0752 | 0.1074 | 0.0000 |  | action, cooperative, survival |
| 10 | Rotwood | game | 0.0723 | 0.1033 | 0.0000 |  | action, roguelike, role-playing |

*Latency: NLU 506ms, retrieval 50ms, rerank 2ms, total 558ms*

#### Q2: "Games similar to Resident Evil Requiem"

**NLU:** anchor=`Resident Evil Requiem`, intent=`similar`, verticals=`['game']`, type=`within_vertical`

**Entity:** Resident Evil Requiem (game) [exact]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | Silent Hill f: Deluxe Edition | game | 0.2276 | 0.1698 | 0.0291 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 2 | Cronos: The New Dawn | game | 0.2222 | 0.1517 | 0.0534 | Yes | action, adventure, horror, puzzle & trivia, survival horror |
| 3 | Echoes of the Living | game | 0.2072 | 0.1238 | 0.0686 | Yes | adventure, horror, survival horror, zombies |
| 4 | Tormented Souls II | game | 0.1899 | 0.1138 | 0.0340 | Yes | action, adventure, horror, puzzle & trivia, survival horror |
| 5 | World War Z VR | game | 0.1669 | 0.0918 | 0.0089 | Yes | action, adventure, horror, zombies |
| 6 | Ground Zero | game | 0.1623 | 0.0175 | 0.1667 | Yes | action, horror, resource management, survival horror, zombies |
| 7 | Silent Hill f | game | 0.1473 | 0.0551 | 0.0291 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 8 | Post Trauma | game | 0.1343 | 0.0390 | 0.0233 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 9 | Code Violet | game | 0.1179 | 0.1685 | 0.0000 |  | action, horror, survival horror |
| 10 | The Mute House | game | 0.0938 | 0.1340 | 0.0000 |  | adventure, horror |

*Latency: NLU 468ms, retrieval 71ms, rerank 0ms, total 539ms*

#### Q3: "Find games like Silent Hill f"

**NLU:** anchor=`Silent Hill`, intent=`similar`, verticals=`['game']`, type=`within_vertical`

**Entity:** Silent Hill f (game) [prefix]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | Silent Hill f: Deluxe Edition | game | 0.7929 | 0.7503 | 0.5590 | Yes | adventure, horror, konami, neobards entertainment, puzzle & trivia |
| 2 | Post Trauma | game | 0.2564 | 0.2148 | 0.0201 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 3 | Dollhouse: Behind the Broken Mirror | game | 0.1507 | 0.0710 | 0.0034 | Yes | adventure, horror, psychological, puzzle & trivia |
| 4 | Out of Sight | game | 0.1365 | 0.0507 | 0.0034 | Yes | adventure, horror, psychological, puzzle & trivia |
| 5 | Tormented Souls II | game | 0.1166 | 0.0176 | 0.0144 | Yes | adventure, horror, puzzle & trivia, survival horror |
| 6 | Dark Memories: Prologue | game | 0.0907 | 0.1295 | 0.0000 |  | adventure, horror |
| 7 | BrokenLore: Don't Watch | game | 0.0861 | 0.1230 | 0.0000 |  | adventure, horror, psychological |
| 8 | Inner Voice | game | 0.0794 | 0.1134 | 0.0000 |  | adventure, horror, psychological |
| 9 | BrokenLore: Low | game | 0.0643 | 0.0918 | 0.0000 |  | horror, psychological |
| 10 | Subliminal | game | 0.0323 | 0.0461 | 0.0000 |  | horror, puzzle & trivia |

*Latency: NLU 623ms, retrieval 43ms, rerank 0ms, total 666ms*

#### Q4: "Movies similar to Star Wars: The Mandalorian and Grogu"

**NLU:** anchor=`Star Wars: The Mandalorian and Grogu`, intent=`similar`, verticals=`['movie']`, type=`within_vertical`

**Entity:** Star Wars: The Mandalorian and Grogu (movie) [exact]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | Winter of Empires | movie | 0.2754 | 0.2195 | 0.0725 | Yes | adventure, science fiction, space opera |
| 2 | Predator: Badlands | movie | 0.2503 | 0.1943 | 0.0475 | Yes | action, adventure, franchise, science fiction |
| 3 | Avatar: Fire and Ash | movie | 0.2214 | 0.1606 | 0.0300 | Yes | adventure, franchise, science fiction |
| 4 | The Electric State | movie | 0.1882 | 0.0924 | 0.0782 | Yes | action, adventure, found family, science fiction |
| 5 | Elio | movie | 0.1333 | 0.1904 | 0.0000 |  | adventure, science fiction |
| 6 | Jurassic World Rebirth | movie | 0.1322 | 0.0256 | 0.0475 | Yes | action, adventure, franchise, science fiction |
| 7 | Dune: Part Three | movie | 0.1166 | 0.0033 | 0.0475 | Yes | action, adventure, franchise, science fiction |
| 8 | Predator: Wastelands | movie | 0.1152 | 0.0043 | 0.0407 | Yes | action, franchise, science fiction |
| 9 | Xeno | movie | 0.1021 | 0.1458 | 0.0000 |  | adventure, science fiction |
| 10 | The Fantastic 4: First Steps | movie | 0.0591 | 0.0845 | 0.0000 |  | action, adventure, science fiction |

*Latency: NLU 816ms, retrieval 45ms, rerank 0ms, total 861ms*

#### Q5: "TV shows like Stranger Things: Tales from 85"

**NLU:** anchor=`Stranger Things: Tales from 85`, intent=`similar`, verticals=`['tv']`, type=`within_vertical`

**Entity:** FAILED — Entity not found: 'Stranger Things: Tales from 85'

*No results returned.*

### Cross-Vertical

#### Q6: "What movies should I watch if I liked Elden Ring Nightreign?"

**NLU:** anchor=`Elden Ring Nightreign`, intent=`recommend`, verticals=`['movie']`, type=`cross_vertical`

**Entity:** Elden Ring Nightreign (game) [exact]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | In the Lost Lands | movie | 1.0812 | 1.0000 | 0.9374 | Yes | action, dark fantasy, fantasy |
| 2 | The Rats: A Witcher Tale | movie | 0.7054 | 0.5460 | 0.7440 | Yes | dark fantasy, fantasy |
| 3 | Tales from Black Manor | movie | 0.6980 | 0.5354 | 0.7440 | Yes | dark fantasy, fantasy |
| 4 | The Witcher: Sirens of the Deep | movie | 0.5842 | 0.2631 | 1.0000 | Yes | action, dark fantasy, fantasy |
| 5 | Predator: Badlands | movie | 0.4912 | 0.7018 | 0.0000 |  | action, survival |
| 6 | Until Dawn | movie | 0.4644 | 0.6635 | 0.0000 |  | survival |
| 7 | The Old Guard 2 | movie | 0.4532 | 0.6474 | 0.0000 |  | action, fantasy |
| 8 | A Minecraft Movie | movie | 0.3254 | 0.4648 | 0.0000 |  | fantasy |
| 9 | The Jurassic Games: Extinction | movie | 0.2705 | 0.0067 | 0.5525 | Yes | action, fantasy, survival |
| 10 | Peter Pan's Neverland Nightmare | movie | 0.2553 | 0.3647 | 0.0000 |  | fantasy |

*Latency: NLU 476ms, retrieval 69ms, rerank 0ms, total 546ms*

#### Q7: "Find me TV shows similar to Resident Evil"

**NLU:** anchor=`Resident Evil`, intent=`similar`, verticals=`['tv']`, type=`within_vertical`

**Entity:** Resident Evil Requiem (game) [prefix]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | Marvel Zombies | tv | 1.1000 | 1.0000 | 1.0000 | Yes | action, adventure, horror, zombies |
| 2 | Devil May Cry | tv | 0.7327 | 0.8069 | 0.2263 | Yes | action, horror |
| 3 | Alien: Earth | tv | 0.7181 | 0.8476 | 0.0827 | Yes | horror |
| 4 | Hell Motel | tv | 0.7170 | 0.5414 | 0.7934 | Yes | horror, suspense |
| 5 | The Bondsman | tv | 0.3564 | 0.2692 | 0.2263 | Yes | action, horror |
| 6 | Run Away | tv | 0.2899 | 0.0557 | 0.5028 | Yes | suspense |
| 7 | Nemesis | tv | 0.2791 | 0.3987 | 0.0000 |  | action, adventure |
| 8 | Memory of a Killer | tv | 0.2508 | 0.0000 | 0.5028 | Yes | suspense |
| 9 | Something Very Bad Is Going to Happen | tv | 0.2315 | 0.1483 | 0.0924 | Yes | horror |
| 10 | True Haunting | tv | 0.2186 | 0.1298 | 0.0924 | Yes | horror |

*Latency: NLU 693ms, retrieval 44ms, rerank 0ms, total 737ms*

#### Q8: "What games would I enjoy if I like horror movies?"

**NLU:** anchor=`horror movies`, intent=`recommend`, verticals=`['game']`, type=`cross_vertical`

**Entity:** FAILED — Entity not found: 'horror movies'

*No results returned.*

#### Q9: "Recommend movies for someone who loves fantasy RPG games"

**NLU:** anchor=`fantasy RPG games`, intent=`recommend`, verticals=`['movie']`, type=`cross_vertical`

**Entity:** FAILED — Entity not found: 'fantasy RPG games'

*No results returned.*

#### Q10: "Find TV shows for fans of action adventure games"

**NLU:** anchor=`action adventure games`, intent=`recommend`, verticals=`['tv']`, type=`cross_vertical`

**Entity:** FAILED — Entity not found: 'action adventure games'

*No results returned.*

### Open / Thematic

#### Q11: "Content similar to Marvel Zombies"

**NLU:** anchor=`Marvel Zombies`, intent=`similar`, verticals=`['game', 'movie', 'tv']`, type=`cross_vertical`

**Entity:** Marvel Zombies (tv) [exact]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | Night of the Zoopocalypse | movie | 0.1916 | 0.2737 | 0.0000 |  | adventure, animation, horror, science fiction |
| 2 | Thunderbolts* | movie | 0.1835 | 0.0704 | 0.1142 | Yes | action, adventure, marvel, science fiction, superhero |
| 3 | Outbreak: Shades of Horror | game | 0.1817 | 0.0565 | 0.1404 | Yes | action, adventure, horror, undead, zombies |
| 4 | World War Z VR | game | 0.1679 | 0.0601 | 0.0861 | Yes | action, adventure, horror, science fiction, survival |
| 5 | Devil May Cry | tv | 0.1536 | 0.2194 | 0.0000 |  | action, animation, horror |
| 6 | Silent Zone | movie | 0.1188 | 0.1698 | 0.0000 |  | horror, undead |
| 7 | Worldbreaker | movie | 0.0874 | 0.1249 | 0.0000 |  | action, horror, science fiction, survival |
| 8 | 28 Years Later | movie | 0.0633 | 0.0905 | 0.0000 |  | horror, science fiction, survival |
| 9 | Predator: Wastelands | movie | 0.0522 | 0.0746 | 0.0000 |  | action, science fiction, survival |
| 10 | 28 Years Later: The Bone Temple | movie | 0.0479 | 0.0684 | 0.0000 |  | horror, science fiction |

*Latency: NLU 2597ms, retrieval 41ms, rerank 0ms, total 2637ms*

#### Q12: "Find me something with dark fantasy themes"

**NLU:** anchor=`N/A`, intent=`N/A`, verticals=`[]`, type=`N/A`

**Entity:** FAILED — NLU failed after 3 attempts: Error code: 400 - {'error': {'message': 'tool call validation failed: parameters for tool extract_query_intent did not match schema: errors: [`/anchor_entity`: expected string, but got null]', 'type': 'invalid_request_error', 'code': 'tool_use_failed', 'failed_generation': '<function=extract_query_intent>{"anchor_entity": null, "filters": {"genre": "dark fantasy", "mood": null}, "intent": "explore", "target_verticals": ["game", "movie", "tv"], "query_type": "cross_vertical"}</function>'}}

*No results returned.*

#### Q13: "Horror content across all categories"

**NLU:** anchor=`null`, intent=`explore`, verticals=`['game', 'movie', 'tv']`, type=`cross_vertical`

**Entity:** Nullstar: Solus (game) [prefix]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | TetherGeist | game | 0.1838 | 0.1014 | 0.0429 | Yes | adventure, indie, platform, precision platformer |
| 2 | ReSetna | game | 0.1824 | 0.0938 | 0.0558 | Yes | adventure, indie, platform, ruins |
| 3 | Super Meat Boy 3D | game | 0.1730 | 0.0661 | 0.0893 | Yes | arcade, indie, platform, precision platformer |
| 4 | Star Overdrive | game | 0.1637 | 0.0766 | 0.0336 | Yes | adventure, arcade, indie, speed |
| 5 | Mio: Memories in Orbit | game | 0.1358 | 0.1940 | 0.0000 |  | adventure, arcade, indie, platform |
| 6 | Shotgun Cop Man | game | 0.1343 | 0.0107 | 0.0893 | Yes | arcade, indie, platform, precision platformer |
| 7 | Toree Saturn | game | 0.1279 | 0.1827 | 0.0000 |  | adventure, arcade, platform |
| 8 | Possessor(s) | game | 0.1276 | 0.1824 | 0.0000 |  | adventure, indie, platform |
| 9 | Transporter | game | 0.0953 | 0.1362 | 0.0000 |  | arcade, platform |
| 10 | Haste | game | 0.0916 | 0.1309 | 0.0000 |  | adventure, indie, platform |

*Latency: NLU 357ms, retrieval 71ms, rerank 0ms, total 428ms*

#### Q14: "Recommend something for someone who loves sci-fi"

**NLU:** anchor=`sci-fi`, intent=`recommend`, verticals=`['game', 'movie', 'tv']`, type=`cross_vertical`

**Entity:** FAILED — Entity not found: 'sci-fi'

*No results returned.*

#### Q15: "What should I watch or play this weekend if I like mystery and thriller?"

**NLU:** anchor=`null`, intent=`explore`, verticals=`['game', 'movie', 'tv']`, type=`cross_vertical`

**Entity:** Nullstar: Solus (game) [prefix]

| Rank | Name | Vertical | Final | Vector | BM25 | Both | Shared Keywords |
|------|------|----------|-------|--------|------|------|-----------------|
| 1 | TetherGeist | game | 0.1838 | 0.1014 | 0.0429 | Yes | adventure, indie, platform, precision platformer |
| 2 | ReSetna | game | 0.1824 | 0.0938 | 0.0558 | Yes | adventure, indie, platform, ruins |
| 3 | Super Meat Boy 3D | game | 0.1730 | 0.0661 | 0.0893 | Yes | arcade, indie, platform, precision platformer |
| 4 | Star Overdrive | game | 0.1637 | 0.0766 | 0.0336 | Yes | adventure, arcade, indie, speed |
| 5 | Mio: Memories in Orbit | game | 0.1358 | 0.1940 | 0.0000 |  | adventure, arcade, indie, platform |
| 6 | Shotgun Cop Man | game | 0.1343 | 0.0107 | 0.0893 | Yes | arcade, indie, platform, precision platformer |
| 7 | Toree Saturn | game | 0.1279 | 0.1827 | 0.0000 |  | adventure, arcade, platform |
| 8 | Possessor(s) | game | 0.1276 | 0.1824 | 0.0000 |  | adventure, indie, platform |
| 9 | Transporter | game | 0.0953 | 0.1362 | 0.0000 |  | arcade, platform |
| 10 | Haste | game | 0.0916 | 0.1309 | 0.0000 |  | adventure, indie, platform |

*Latency: NLU 451ms, retrieval 49ms, rerank 0ms, total 500ms*

---

## Section 3 — Quality Analysis

### 3.1 Within-Vertical Accuracy

**Overall: 100% (40/40 results in correct vertical)**

| Query | Target Verticals | Correct | Total | Accuracy |
|-------|-----------------|---------|-------|----------|
| Q1 | ['game'] | 10 | 10 | 100.0% |
| Q2 | ['game'] | 10 | 10 | 100.0% |
| Q3 | ['game'] | 10 | 10 | 100.0% |
| Q4 | ['movie'] | 10 | 10 | 100.0% |

### 3.2 Cross-Vertical Diversity

**Queries with 2+ verticals in top 10: 0/2**

| Query | Verticals Found | Distribution |
|-------|----------------|-------------|
| Q6 | 1 | {'movie': 10} |
| Q7 | 1 | {'tv': 10} |

### 3.3 Thematic / Open Query Assessment

| Query | Anchor Resolved | Vertical Mix | Top 3 Results |
|-------|----------------|-------------|---------------|
| Q11 | Marvel Zombies | {'movie': 7, 'game': 2, 'tv': 1} | Night of the Zoopocalypse (movie); Thunderbolts* (movie); Outbreak: Shades of Horror (game) |
| Q12 | — | — | no results |
| Q13 | Nullstar: Solus | {'game': 10} | TetherGeist (game); ReSetna (game); Super Meat Boy 3D (game) |
| Q14 | — | — | no results |
| Q15 | Nullstar: Solus | {'game': 10} | TetherGeist (game); ReSetna (game); Super Meat Boy 3D (game) |

### 3.4 NLU Accuracy

| Query | Anchor Extracted | Intent | Verticals | Type |
|-------|-----------------|--------|-----------|------|
| Q1 | Elden Ring Nightreign | similar | ['game'] | within_vertical |
| Q2 | Resident Evil Requiem | similar | ['game'] | within_vertical |
| Q3 | Silent Hill | similar | ['game'] | within_vertical |
| Q4 | Star Wars: The Mandalorian and Grogu | similar | ['movie'] | within_vertical |
| Q5 | Stranger Things: Tales from 85 | similar | ['tv'] | within_vertical |
| Q6 | Elden Ring Nightreign | recommend | ['movie'] | cross_vertical |
| Q7 | Resident Evil | similar | ['tv'] | within_vertical |
| Q8 | horror movies | recommend | ['game'] | cross_vertical |
| Q9 | fantasy RPG games | recommend | ['movie'] | cross_vertical |
| Q10 | action adventure games | recommend | ['tv'] | cross_vertical |
| Q11 | Marvel Zombies | similar | ['game', 'movie', 'tv'] | cross_vertical |
| Q12 | N/A | N/A | [] | N/A |
| Q13 | null | explore | ['game', 'movie', 'tv'] | cross_vertical |
| Q14 | sci-fi | recommend | ['game', 'movie', 'tv'] | cross_vertical |
| Q15 | null | explore | ['game', 'movie', 'tv'] | cross_vertical |

### 3.5 Entity Resolution

| Query | NLU Extracted | Resolved To | Match Type | Status |
|-------|-------------- |-------------|------------|--------|
| Q1 | Elden Ring Nightreign | Elden Ring Nightreign | exact | Success |
| Q2 | Resident Evil Requiem | Resident Evil Requiem | exact | Success |
| Q3 | Silent Hill | Silent Hill f | prefix | Success |
| Q4 | Star Wars: The Mandalorian and Grogu | Star Wars: The Mandalorian and Grogu | exact | Success |
| Q5 | Stranger Things: Tales from 85 | — | — | FAILED |
| Q6 | Elden Ring Nightreign | Elden Ring Nightreign | exact | Success |
| Q7 | Resident Evil | Resident Evil Requiem | prefix | Success |
| Q8 | horror movies | — | — | FAILED |
| Q9 | fantasy RPG games | — | — | FAILED |
| Q10 | action adventure games | — | — | FAILED |
| Q11 | Marvel Zombies | Marvel Zombies | exact | Success |
| Q12 |  | — | — | FAILED |
| Q13 | null | Nullstar: Solus | prefix | Success |
| Q14 | sci-fi | — | — | FAILED |
| Q15 | null | Nullstar: Solus | prefix | Success |

**Resolution success rate: 9/15 (60%)**

---

## Section 4 — Score Analysis

### 4.1 Score Distributions

| Metric | Min | Max | Avg | Median |
|--------|-----|-----|-----|--------|
| Final Score | 0.0323 | 1.1000 | 0.2309 | 0.1637 |
| Vector Score | 0.0000 | 1.0000 | 0.1973 | 0.1249 |
| BM25 Score | 0.0000 | 1.0000 | 0.1128 | 0.0291 |

### 4.2 Signal Contribution

- **Vector-dominant results** (vector_score > bm25_score): 69/90
- **BM25-dominant results** (bm25_score > vector_score): 20/90
- Vector similarity is the primary ranking signal (weighted 0.7), with BM25 providing keyword-based refinement (0.3)

### 4.3 Dual-Signal Bonus Impact

- **Results in both vector AND BM25 sets:** 53/90 (59%)
- These results receive a +0.1 bonus, rewarding entities that are both semantically and lexically similar
- Dual-signal results are strongly correlated with higher final rankings

---

## Section 5 — Latency Analysis

### 5.1 Per-Stage Breakdown (averages)

| Stage | Avg (ms) | % of Total |
|-------|----------|------------|
| NLU (Groq API) | 776 | 93% |
| Retrieval (resolve + search + merge) | 54 | 6% |
| Reranking | 0 | 0% |
| **Total** | **830** | **100%** |

### 5.2 Per-Query Latency

| Query | NLU (ms) | Retrieval (ms) | Rerank (ms) | Total (ms) |
|-------|----------|---------------|-------------|------------|
| Q1 | 506 | 50 | 2 | 558 |
| Q2 | 468 | 71 | 0 | 539 |
| Q3 | 623 | 43 | 0 | 666 |
| Q4 | 816 | 45 | 0 | 861 |
| Q5 | 737 | 14 | 0 | 0 |
| Q6 | 476 | 69 | 0 | 546 |
| Q7 | 693 | 44 | 0 | 737 |
| Q8 | 440 | 14 | 0 | 0 |
| Q9 | 416 | 14 | 0 | 0 |
| Q10 | 340 | 15 | 0 | 0 |
| Q11 | 2597 | 41 | 0 | 2637 |
| Q12 | 0 | 0 | 0 | 0 |
| Q13 | 357 | 71 | 0 | 428 |
| Q14 | 647 | 14 | 0 | 0 |
| Q15 | 451 | 49 | 0 | 500 |

### 5.3 Bottleneck Identification

- **NLU is the bottleneck**, averaging 776ms (93% of total)
- Retrieval (PostgreSQL entity resolution + Qdrant vector search + BM25 scoring + merge) is fast at 54ms
- Reranking is negligible at 0ms
- Range: fastest query 428ms, slowest 2637ms

---

## Section 6 — Recommendations

### 6.1 Quality Improvements

- **Thematic queries:** Queries without a specific anchor entity (Q8, Q9, Q10, Q12-Q15) rely on the LLM to invent an anchor name. Consider adding a secondary path: when NLU detects no specific entity, use the query embedding directly for vector search rather than resolving an entity.
- **BM25 weight tuning:** BM25 scores are generally lower than vector scores. Consider adjusting the 0.7/0.3 weight split or enriching BM25 keywords with genre synonyms and thematic tags.
- **Franchise boost:** The franchise field is sparsely populated in the current dataset. Enriching franchise metadata would make the +0.15 boost more impactful.
- **Cross-vertical diversity:** The diversity enforcement only activates when the top 10 is single-vertical. Consider a softer approach: guarantee minimum representation per requested vertical (e.g., at least 2 per vertical).

### 6.2 Databricks Migration Path

- **Embedding storage:** Replace local PostgreSQL with Delta Lake tables on Databricks; store embeddings as array columns.
- **Vector search:** Replace in-memory Qdrant with Databricks Vector Search (backed by FAISS/DiskANN) for persistent, scalable ANN.
- **LLM:** Replace Groq API with Databricks Model Serving (llama-3.3-70b or Foundation Model API) for function calling.
- **Orchestration:** Wrap the pipeline as a Databricks job or serve via MLflow model serving endpoint.
- **BM25:** Can remain in-process or move to a Spark-based keyword scoring UDF for large-scale corpora.

### 6.3 Production Scale Considerations

- **Qdrant persistence:** Switch from in-memory to on-disk or Qdrant Cloud for durability.
- **Caching:** Cache NLU parse results and entity resolutions for repeated/similar queries to reduce LLM API calls.
- **Batch embedding:** Pre-compute query embeddings for popular/trending searches.
- **Rate limiting:** Groq free tier has rate limits; production would need a dedicated plan or self-hosted LLM.
- **Monitoring:** Add latency histograms, NLU parse quality logging, and result click-through tracking.
- **Entity catalog growth:** Current dataset is 1,757 entities. At 10k+ entities, ensure Qdrant indexing and BM25 scoring remain performant (both should scale well to 100k+).

