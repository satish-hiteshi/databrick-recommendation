# V2 Database Setup Report

**Generated:** 2026-05-29 17:28:15

## PostgreSQL
- **Total rows:** 6,945
- **Table:** entities (with release_date column)
- **Indexes:** name_lower, vertical, franchise, release_date
- **Function:** find_entity() with exact/prefix/contains cascade

### Entity Resolution Tests
| Query | Found | Vertical | Match Type |
|-------|-------|----------|------------|
| Elden Ring | Elden Ring | game | exact |
| The Dark Knight | NOT FOUND | — | — |
| Breaking Bad | NOT FOUND | — | — |
| Serial | Serialously with Annie Elise | podcast | prefix |
| Hades | Hades II | game | prefix |

### Release Date Coverage
| Vertical | Total | With Date | Coverage |
|----------|-------|-----------|----------|
| game | 1,997 | 1,997 | 100% |
| movie | 1,653 | 1,627 | 98% |
| podcast | 1,998 | 0 | 0% |
| tv | 1,297 | 1,193 | 92% |

## Qdrant
- **Collection:** feedsai_entities
- **Vector count:** 6,945
- **Dimensions:** 1024
- **Distance metric:** Cosine

## BM25
- **Index size:** 6,945 entities

## Summary
All three stores rebuilt with V2 dataset (6,945 entities).
