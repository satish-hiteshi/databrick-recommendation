# Embedding Generation Report

## Summary
- **Total embeddings generated:** 1,757
- **Embedding dimensions:** 1024
- **Model:** voyage-4-large
- **Time taken:** 30.1 seconds
- **Total tokens processed:** 405,272
- **Estimated API cost:** $0.0486
- **Retries:** 0
- **Errors:** 0

## Validation
- NaN vectors: 0
- Zero vectors: 0

## Cache Files
- `data/embeddings_cache.json`: 39.9 MB
- `data/embeddings.npy`: 7.2 MB
- `data/embeddings_ids.json`: ID ordering index

## Sanity Check — Cosine Similarity

### Similar pairs (target: > 0.7)
| Entity A | Entity B | Score | Result |
|----------|----------|-------|--------|
| Elden Ring Nightreign | Vampire: The Masquerade - Bloodlines 2 | 0.6072 | LOW |
| Silent Hill f | Return to Silent Hill | 0.6955 | LOW |
| Doom: The Dark Ages | Resident Evil Requiem | 0.5363 | LOW |

### Dissimilar pairs (target: < 0.5)
| Entity A | Entity B | Score | Result |
|----------|----------|-------|--------|
| Doom: The Dark Ages | A Paw Patrol Christmas | 0.1837 | PASS |
| Silent Hill f | Mario Tennis Fever | 0.2966 | PASS |
| Resident Evil Requiem | The First Snow of Fraggle Rock | 0.1983 | PASS |
