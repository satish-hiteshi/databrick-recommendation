# Pipeline Test Report

## Architecture

| Module | Role |
|--------|------|
| `nlu.py` | Groq LLM function calling to parse user query into structured intent |
| `retrieval.py` | Entity resolution + dual retrieval (vector + BM25) + hybrid merge |
| `reranker.py` | Franchise boost, self-exclusion, diversity enforcement |
| `query_engine.py` | Orchestrator: NLU -> Retrieval -> Rerank -> formatted output |

---

## Query 1: "What games are like Elden Ring Nightreign?"

### NLU Output
```json
{
  "anchor_entity": "Elden Ring Nightreign",
  "intent": "similar",
  "target_verticals": [
    "game"
  ],
  "query_type": "within_vertical",
  "filters": {
    "genre": null,
    "mood": null
  }
}
```

### Entity Resolution
- **Resolved:** Elden Ring Nightreign (game) [exact match]

### Vector Search (top 5 before merge)
| Name | Vertical | Score |
|------|----------|-------|
| Elden Ring Nightreign | game | 1.0000 |
| Code Vein II | game | 0.7434 |
| Nioh 3 | game | 0.7432 |
| Monster Hunter Wilds | game | 0.7230 |
| Let It Die: Inferno | game | 0.7187 |

### BM25 Search (top 5 before merge)
| Name | Vertical | Score |
|------|----------|-------|
| Elden Ring Nightreign | game | 47.7086 |
| Tales of Berseria Remastered: Deluxe Edition | game | 14.9134 |
| Nioh 3 | game | 12.8888 |
| The Blood of Dawnwalker | game | 12.7342 |
| Jötunnslayer: Hordes of Hel | game | 12.3694 |

### Final Ranked Results (top 10)
| Rank | Name | Vertical | Final | Vector | BM25 | Both Sets | Shared Keywords |
|------|------|----------|-------|--------|------|-----------|-----------------|
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

### Latency
| Stage | Time |
|-------|------|
| NLU | 1524 ms |
| Retrieval (resolve + vector + BM25 + merge) | 48 ms |
| Reranking | 2 ms |
| **Total** | **1575 ms** |

### Stats
- Vector results: 20
- BM25 results: 20
- Merged candidates: 33
- Dual-signal candidates: 7

---

## Query 2: "Movies similar to Star Wars: The Mandalorian and Grogu"

### NLU Output
```json
{
  "anchor_entity": "Star Wars: The Mandalorian and Grogu",
  "intent": "similar",
  "target_verticals": [
    "movie"
  ],
  "query_type": "within_vertical",
  "filters": {
    "genre": null,
    "mood": null
  }
}
```

### Entity Resolution
- **Resolved:** Star Wars: The Mandalorian and Grogu (movie) [exact match]

### Vector Search (top 5 before merge)
| Name | Vertical | Score |
|------|----------|-------|
| Star Wars: The Mandalorian and Grogu | movie | 1.0000 |
| Winter of Empires | movie | 0.6144 |
| Predator: Badlands | movie | 0.6020 |
| Elio | movie | 0.6000 |
| Avatar: Fire and Ash | movie | 0.5853 |

### BM25 Search (top 5 before merge)
| Name | Vertical | Score |
|------|----------|-------|
| Star Wars: The Mandalorian and Grogu | movie | 64.4355 |
| The Electric State | movie | 8.7526 |
| Winter of Empires | movie | 8.4063 |
| TRON: Ares | movie | 6.9004 |
| Dune: Part Three | movie | 6.9004 |

### Final Ranked Results (top 10)
| Rank | Name | Vertical | Final | Vector | BM25 | Both Sets | Shared Keywords |
|------|------|----------|-------|--------|------|-----------|-----------------|
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

### Latency
| Stage | Time |
|-------|------|
| NLU | 437 ms |
| Retrieval (resolve + vector + BM25 + merge) | 45 ms |
| Reranking | 0 ms |
| **Total** | **482 ms** |

### Stats
- Vector results: 20
- BM25 results: 20
- Merged candidates: 32
- Dual-signal candidates: 8

---

## Query 3: "Find me TV shows similar to Resident Evil"

### NLU Output
```json
{
  "anchor_entity": "Resident Evil",
  "intent": "similar",
  "target_verticals": [
    "tv"
  ],
  "query_type": "within_vertical",
  "filters": {
    "genre": null,
    "mood": null
  }
}
```

### Entity Resolution
- **Resolved:** Resident Evil Requiem (game) [prefix match]

### Vector Search (top 5 before merge)
| Name | Vertical | Score |
|------|----------|-------|
| Marvel Zombies | tv | 0.5352 |
| Alien: Earth | tv | 0.5183 |
| Devil May Cry | tv | 0.5137 |
| Hell Motel | tv | 0.4842 |
| Nemesis | tv | 0.4684 |

### BM25 Search (top 5 before merge)
| Name | Vertical | Score |
|------|----------|-------|
| Marvel Zombies | tv | 7.6962 |
| Hell Motel | tv | 6.3696 |
| Run Away | tv | 4.5029 |
| Memory of a Killer | tv | 4.5029 |
| Wayward | tv | 4.5029 |

### Final Ranked Results (top 10)
| Rank | Name | Vertical | Final | Vector | BM25 | Both Sets | Shared Keywords |
|------|------|----------|-------|--------|------|-----------|-----------------|
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

### Latency
| Stage | Time |
|-------|------|
| NLU | 475 ms |
| Retrieval (resolve + vector + BM25 + merge) | 48 ms |
| Reranking | 0 ms |
| **Total** | **523 ms** |

### Stats
- Vector results: 20
- BM25 results: 20
- Merged candidates: 30
- Dual-signal candidates: 10

