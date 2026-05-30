"""
Data loader for Feeds.ai entity data.
Loads and merges compositions + entity profiles into a unified dataset.
"""

import json
from pipeline.config import COMPOSITIONS_PATH, PROFILES_PATH


def _load_and_merge():
    """Load both JSON files and merge on entity_id."""
    with open(COMPOSITIONS_PATH) as f:
        compositions = json.load(f)

    with open(PROFILES_PATH) as f:
        profiles = json.load(f)

    # Index profiles by entity_id for fast lookup
    profile_map = {p["entity_id"]: p for p in profiles}

    entities = []
    for comp in compositions:
        eid = comp["entity_id"]
        profile = profile_map.get(eid, {})

        entity = {
            "entity_id": eid,
            "name": comp["name"],
            "vertical": comp["vertical"],
            "composed_text": comp["composed_text"],
            "bm25_keywords": comp["bm25_keywords"],
            "word_count": comp.get("word_count"),
            "description": profile.get("description"),
            "canonical_genres": profile.get("canonical_genres", []),
            "themes": profile.get("themes", []),
            "franchise": profile.get("franchise"),
            "developer": profile.get("developer"),
            "publisher": profile.get("publisher"),
            "directors": profile.get("directors", []),
            "cast": profile.get("cast", []),
            "release_date": profile.get("release_date"),
        }
        entities.append(entity)

    return entities


# Module-level cache
_entities = None


def _ensure_loaded():
    global _entities
    if _entities is None:
        _entities = _load_and_merge()
    return _entities


def get_all_entities():
    """Return all merged entities."""
    return _ensure_loaded()


def get_entity_by_name(name):
    """Find entity by exact name (case-insensitive)."""
    name_lower = name.lower()
    for e in _ensure_loaded():
        if e["name"].lower() == name_lower:
            return e
    return None


def get_entities_by_vertical(vertical):
    """Return all entities for a given vertical."""
    vertical_lower = vertical.lower()
    return [e for e in _ensure_loaded() if e["vertical"].lower() == vertical_lower]


if __name__ == "__main__":
    entities = get_all_entities()

    # Total count
    print(f"Total entities loaded: {len(entities)}")

    # Count by vertical
    from collections import Counter
    verticals = Counter(e["vertical"] for e in entities)
    print(f"\nCount by vertical:")
    for v, count in sorted(verticals.items()):
        print(f"  {v}: {count}")

    # Validate completeness
    missing_text = [e for e in entities if not e["composed_text"]]
    missing_kw = [e for e in entities if not e["bm25_keywords"]]
    print(f"\nEntities missing composed_text: {len(missing_text)}")
    print(f"Entities missing bm25_keywords: {len(missing_kw)}")

    # Sample entity
    sample = entities[0]
    print(f"\n--- Sample Entity ---")
    print(f"  entity_id:    {sample['entity_id']}")
    print(f"  name:         {sample['name']}")
    print(f"  vertical:     {sample['vertical']}")
    print(f"  description:  {sample['description'][:100]}..." if sample['description'] else "  description:  None")
    print(f"  composed_text: {sample['composed_text'][:100]}...")
    print(f"  bm25_keywords: {sample['bm25_keywords']}")
    print(f"  word_count:   {sample['word_count']}")
    print(f"  franchise:    {sample['franchise']}")
    print(f"  developer:    {sample['developer']}")
    print(f"  publisher:    {sample['publisher']}")
    print(f"  genres:       {sample['canonical_genres']}")

    if len(entities) == 1757 and len(missing_text) == 0 and len(missing_kw) == 0:
        print(f"\n✓ All 1,757 entities loaded and validated successfully.")
    else:
        print(f"\n✗ Validation issues detected.")
