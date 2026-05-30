# Embedding Generation Report — V2

**Generated:** 2026-05-29 17:26:32

## Summary
- **Total embeddings generated:** 6,945
- **Embedding dimensions:** 1024
- **Model:** voyage-4-large
- **Time taken:** 100.1 seconds (1.7 minutes)
- **Total tokens processed:** 1,514,804
- **Estimated API cost:** $0.1818
- **Retries:** 0
- **Errors:** 0

## Validation
- NaN vectors: 0
- Zero vectors: 0

## Cache Files
- `embeddings_cache_v2.json`: 157.9 MB
- `embeddings_v2.npy`: 28.4 MB
- `embeddings_ids_v2.json`: 139.6 KB

## Sanity Check — Cosine Similarity

### Similar pairs (target: > 0.5)
| Entity A | Entity B | Category | Score | Result |
|----------|----------|----------|-------|--------|
| Total Chaos | Tormented Souls | horror games | 0.7243 | PASS |
| Alien: Romulus | Predator: Badlands | sci-fi movies | 0.6535 | PASS |
| The Deck | True Crime All The Time Unsolved | true-crime podcasts | 0.7492 | PASS |

### Dissimilar pairs (target: < 0.3)
| Entity A | Entity B | Category | Score | Result |
|----------|----------|----------|-------|--------|
| Total Chaos | The Wonderfully Weird World of Gumball | horror game vs kids TV | 0.2020 | PASS |
| Alien: Romulus | Dish | sci-fi movie vs cooking podcast | 0.1565 | PASS |
| Total Chaos | Dish | horror game vs cooking podcast | 0.1456 | PASS |
