# Feeds.ai API Test Report

## Server Info
- **URL:** http://localhost:8000
- **Docs:** http://localhost:8000/docs
- **Startup time:** 1.4s (Qdrant + BM25 initialization)

## Endpoint Tests

### Test 1: POST /api/query
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Games like Elden Ring Nightreign"}'
```
**Result:** SUCCESS
- Status: `success`
- Mode: `entity_single`
- Resolved: Elden Ring Nightreign (game) [prefix]
- Results: 10 games (Nioh 3, Jotunnslayer, Darkest Days, ...)
- Latency: 515ms
- Saved to history as ID 1

### Test 2: GET /api/history
```bash
curl http://localhost:8000/api/history
```
**Result:** SUCCESS
- Returns 1 entry with: id, query_text, parsed_intent, result_count=10, latency_ms, created_at

### Test 3: GET /api/history/1
```bash
curl http://localhost:8000/api/history/1
```
**Result:** SUCCESS
- Returns full query details including complete results JSON

### Test 4: GET /api/entities (filtered + paginated)
```bash
curl "http://localhost:8000/api/entities?vertical=game&page=1&page_size=5"
```
**Result:** SUCCESS
- Returns 5 game entities with full metadata
- total_count: 956, total_pages: 192

### Test 5: GET /api/entities (search)
```bash
curl "http://localhost:8000/api/entities?search=elden&page_size=3"
```
**Result:** SUCCESS
- Returns 1 match: Elden Ring Nightreign with full metadata + composed_text

### Test 6: GET /api/entities/{entity_id}
```bash
curl http://localhost:8000/api/entities/Game:385645
```
**Result:** SUCCESS
- Returns Elden Ring Nightreign with: entity_id, name, vertical, description, composed_text, bm25_keywords (13 keywords), franchise, developer, publisher, canonical_genres, themes, keywords

### Test 7: GET /api/stats
```bash
curl http://localhost:8000/api/stats
```
**Result:** SUCCESS
```json
{
  "total_entities": 1757,
  "entities_by_vertical": {"game": 956, "movie": 547, "tv": 254},
  "total_queries": 1,
  "avg_latency_ms": 515.5
}
```

### Test 8: POST /api/query (multi-vertical theme)
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Horror content across all categories"}'
```
**Result:** SUCCESS
- Mode: `theme_based`
- Returns `results_by_vertical` with separate game and movie top 10 lists
- Latency: ~1100ms (includes Voyage API call for theme embedding)

### Test 9: POST /api/query (mixed + negatives)
```bash
curl -X POST http://localhost:8000/api/query \
  -H "Content-Type: application/json" \
  -d '{"query": "Love Elden Ring but hate Star Wars, want dark fantasy movies"}'
```
**Result:** SUCCESS
- Mode: `mixed`
- Resolved+: Elden Ring Nightreign
- Resolved-: Star Wars: Galactic Racer
- Negative filter: 21 entries processed
- Top results: In the Lost Lands, Tales from Black Manor, The Rats: A Witcher Tale (all dark fantasy movies)
- Latency: 1001ms

## Summary

| Endpoint | Method | Status | Notes |
|----------|--------|--------|-------|
| /api/query | POST | PASS | All query modes work |
| /api/history | GET | PASS | Returns paginated history |
| /api/history/{id} | GET | PASS | Returns full result details |
| /api/entities | GET | PASS | Vertical filter, search, pagination all work |
| /api/entities/{id} | GET | PASS | Returns complete entity with all fields |
| /api/stats | GET | PASS | Entity counts + query stats |

**All 6 endpoints passing. Server running on port 8000.**
