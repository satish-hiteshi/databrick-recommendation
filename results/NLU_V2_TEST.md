# NLU v2 Test Report

## Summary
- **Query mode classification accuracy:** 8/10 (80%)
- **Errors:** 0

## Detailed Results

### Q1: "Games like Elden Ring"

**Expected mode:** `entity_single` | **Got:** `entity_single` | **CORRECT**

```json
{
  "query_mode": "entity_single",
  "positive_entities": [
    "Elden Ring"
  ],
  "negative_entities": [],
  "additional_keywords": [],
  "description_derived_keywords": [],
  "target_verticals": [
    "game"
  ],
  "query_type": "within_vertical"
}
```

**Assessment:**
- Positive entities extracted: ['Elden Ring']
- Verticals: ['game'], Type: within_vertical

### Q2: "I love Elden Ring and Dark Souls, recommend movies"

**Expected mode:** `entity_multi` | **Got:** `entity_multi` | **CORRECT**

```json
{
  "query_mode": "entity_multi",
  "positive_entities": [
    "Elden Ring",
    "Dark Souls"
  ],
  "negative_entities": [],
  "additional_keywords": [],
  "description_derived_keywords": [],
  "target_verticals": [
    "movie"
  ],
  "query_type": "cross_vertical"
}
```

**Assessment:**
- Positive entities extracted: ['Elden Ring', 'Dark Souls']
- Verticals: ['movie'], Type: cross_vertical

### Q3: "Horror content across all categories"

**Expected mode:** `theme_based` | **Got:** `theme_based` | **CORRECT**

```json
{
  "query_mode": "theme_based",
  "positive_entities": [],
  "negative_entities": [],
  "additional_keywords": [
    "horror"
  ],
  "description_derived_keywords": [],
  "target_verticals": [
    "game",
    "movie",
    "tv"
  ],
  "query_type": "cross_vertical"
}
```

**Assessment:**
- Keywords: ['horror']
- Verticals: ['game', 'movie', 'tv'], Type: cross_vertical

### Q4: "I like content with country wars and gun fighting"

**Expected mode:** `descriptive` | **Got:** `descriptive` | **CORRECT**

```json
{
  "query_mode": "descriptive",
  "positive_entities": [],
  "negative_entities": [],
  "additional_keywords": [],
  "description_derived_keywords": [
    "military warfare",
    "combat",
    "war drama",
    "tactical shooter"
  ],
  "target_verticals": [
    "game",
    "movie",
    "tv"
  ],
  "query_type": "cross_vertical"
}
```

**Assessment:**
- Derived keywords: ['military warfare', 'combat', 'war drama', 'tactical shooter']
- Verticals: ['game', 'movie', 'tv'], Type: cross_vertical

### Q5: "Love Elden Ring but hate Star Wars, want dark fantasy movies"

**Expected mode:** `mixed` | **Got:** `mixed` | **CORRECT**

```json
{
  "query_mode": "mixed",
  "positive_entities": [
    "Elden Ring"
  ],
  "negative_entities": [
    "Star Wars"
  ],
  "additional_keywords": [
    "dark fantasy"
  ],
  "description_derived_keywords": [],
  "target_verticals": [
    "movie"
  ],
  "query_type": "cross_vertical"
}
```

**Assessment:**
- Positive entities extracted: ['Elden Ring']
- Negative entities extracted: ['Star Wars']
- Keywords: ['dark fantasy']
- Verticals: ['movie'], Type: cross_vertical

### Q6: "Movies for someone who loved Resident Evil and Silent Hill games"

**Expected mode:** `entity_multi` | **Got:** `entity_multi` | **CORRECT**

```json
{
  "query_mode": "entity_multi",
  "positive_entities": [
    "Resident Evil",
    "Silent Hill"
  ],
  "negative_entities": [],
  "additional_keywords": [
    "horror",
    "survival"
  ],
  "description_derived_keywords": [
    "zombie",
    "apocalyptic",
    "thriller"
  ],
  "target_verticals": [
    "movie"
  ],
  "query_type": "cross_vertical"
}
```

**Assessment:**
- Positive entities extracted: ['Resident Evil', 'Silent Hill']
- Keywords: ['horror', 'survival']
- Derived keywords: ['zombie', 'apocalyptic', 'thriller']
- Verticals: ['movie'], Type: cross_vertical

### Q7: "Recommend me sci-fi"

**Expected mode:** `theme_based` | **Got:** `theme_based` | **CORRECT**

```json
{
  "query_mode": "theme_based",
  "positive_entities": [],
  "negative_entities": [],
  "additional_keywords": [
    "sci-fi"
  ],
  "description_derived_keywords": [],
  "target_verticals": [
    "game",
    "movie",
    "tv"
  ],
  "query_type": "within_vertical"
}
```

**Assessment:**
- Keywords: ['sci-fi']
- Verticals: ['game', 'movie', 'tv'], Type: within_vertical

### Q8: "I enjoy slow-burn psychological tension with unreliable narrators"

**Expected mode:** `descriptive` | **Got:** `theme_based` | **WRONG**

```json
{
  "query_mode": "theme_based",
  "positive_entities": [],
  "negative_entities": [],
  "additional_keywords": [
    "slow-burn",
    "psychological",
    "tension",
    "unreliable narrators"
  ],
  "description_derived_keywords": [
    "psychological thriller",
    "mind game",
    "suspense"
  ],
  "target_verticals": [
    "game",
    "movie",
    "tv"
  ],
  "query_type": "within_vertical"
}
```

**Assessment:**
- Keywords: ['slow-burn', 'psychological', 'tension', 'unreliable narrators']
- Derived keywords: ['psychological thriller', 'mind game', 'suspense']
- Verticals: ['game', 'movie', 'tv'], Type: within_vertical

### Q9: "Games and movies similar to Marvel Zombies"

**Expected mode:** `entity_single` | **Got:** `entity_single` | **CORRECT**

```json
{
  "query_mode": "entity_single",
  "positive_entities": [
    "Marvel Zombies"
  ],
  "negative_entities": [],
  "additional_keywords": [],
  "description_derived_keywords": [],
  "target_verticals": [
    "game",
    "movie"
  ],
  "query_type": "cross_vertical"
}
```

**Assessment:**
- Positive entities extracted: ['Marvel Zombies']
- Verticals: ['game', 'movie'], Type: cross_vertical

### Q10: "I liked Stranger Things and Alien Earth but didn't enjoy comedy shows, recommend games"

**Expected mode:** `mixed` | **Got:** `entity_multi` | **WRONG**

```json
{
  "query_mode": "entity_multi",
  "positive_entities": [
    "Stranger Things",
    "Alien Earth"
  ],
  "negative_entities": [
    "comedy shows"
  ],
  "additional_keywords": [],
  "description_derived_keywords": [],
  "target_verticals": [
    "game"
  ],
  "query_type": "cross_vertical"
}
```

**Assessment:**
- Positive entities extracted: ['Stranger Things', 'Alien Earth']
- Negative entities extracted: ['comedy shows']
- Verticals: ['game'], Type: cross_vertical

## Classification Summary

| # | Query (abbreviated) | Expected | Got | Match |
|---|-------------------|----------|-----|-------|
| 1 | Games like Elden Ring | entity_single | entity_single | Yes |
| 2 | I love Elden Ring and Dark Souls, recommend movies | entity_multi | entity_multi | Yes |
| 3 | Horror content across all categories | theme_based | theme_based | Yes |
| 4 | I like content with country wars and gun fighting | descriptive | descriptive | Yes |
| 5 | Love Elden Ring but hate Star Wars, want dark fant... | mixed | mixed | Yes |
| 6 | Movies for someone who loved Resident Evil and Sil... | entity_multi | entity_multi | Yes |
| 7 | Recommend me sci-fi | theme_based | theme_based | Yes |
| 8 | I enjoy slow-burn psychological tension with unrel... | descriptive | theme_based | No |
| 9 | Games and movies similar to Marvel Zombies | entity_single | entity_single | Yes |
| 10 | I liked Stranger Things and Alien Earth but didn't... | mixed | entity_multi | No |

