"""Vendored identity module — the composite-key convention used across the graph, corpus, and APIs.

Reconstructed for serving from the (uncommitted) shared/identity.py surface the search/E1 upgrade imports:
entity_id = "{Vertical}:{media_source_guid}" with prefixes Game / Movie / TV / Podcast (TV all-caps), and
the per-source profile_key family (igdb_property_game, watchmode_property_movie, watchmode_property_tv,
podchaser_property_podcast). (profile_key, media_source_guid) is the composite key; entity_id is its
serving-side encoding.
"""
from dataclasses import dataclass
from typing import Optional

_PREFIX = {"game": "Game", "movie": "Movie", "tv": "TV", "podcast": "Podcast"}
_VERT_BY_PREFIX = {v.lower(): k for k, v in _PREFIX.items()}
_PROFILE_BY_VERT = {"game": "igdb_property_game", "movie": "watchmode_property_movie",
                    "tv": "watchmode_property_tv", "podcast": "podchaser_property_podcast"}
_VERT_BY_PROFILE = {v: k for k, v in _PROFILE_BY_VERT.items()}


@dataclass(frozen=True)
class ParsedEntityId:
    entity_id: str
    vertical: str
    media_source_guid: str


def make_entity_id(vertical: str, media_source_guid) -> Optional[str]:
    v = (vertical or "").strip().lower()
    if v not in _PREFIX or media_source_guid in (None, ""):
        return None
    return f"{_PREFIX[v]}:{media_source_guid}"


def parse_entity_id(entity_id: str) -> Optional[ParsedEntityId]:
    s = (entity_id or "").strip()
    if ":" not in s:
        return None
    pfx, guid = s.split(":", 1)
    v = _VERT_BY_PREFIX.get(pfx.strip().lower())
    if v is None or not guid:
        return None
    return ParsedEntityId(entity_id=f"{_PREFIX[v]}:{guid}", vertical=v, media_source_guid=guid)


def vertical_for_profile_key(profile_key: str) -> Optional[str]:
    return _VERT_BY_PROFILE.get((profile_key or "").strip().lower())


def profile_key_for_vertical(vertical: str) -> Optional[str]:
    return _PROFILE_BY_VERT.get((vertical or "").strip().lower())


def composite_of(entity_id: str) -> dict:
    p = parse_entity_id(entity_id)
    if p is None:
        return {"profile_key": None, "media_source_guid": None}
    return {"profile_key": _PROFILE_BY_VERT.get(p.vertical), "media_source_guid": p.media_source_guid}


def candidate_entity_ids(media_source_guid) -> list:
    if media_source_guid in (None, ""):
        return []
    return [f"{pfx}:{media_source_guid}" for pfx in _PREFIX.values()]


def coerce_to_entity_id(key) -> Optional[str]:
    """entity_id string / {'entity_id':…} / composite {'profile_key','media_source_guid'} → canonical
    entity_id; a bare source_id is AMBIGUOUS (cross-vertical twins) → None (caller resolves candidates)."""
    if key is None:
        return None
    if isinstance(key, dict):
        if key.get("entity_id"):
            p = parse_entity_id(str(key["entity_id"]));  return p.entity_id if p else None
        v = key.get("vertical") or vertical_for_profile_key(key.get("profile_key"))
        return make_entity_id(v, key.get("media_source_guid"))
    s = str(key).strip()
    if ":" in s:
        p = parse_entity_id(s);  return p.entity_id if p else None
    if "|" in s:                                          # "profile_key|guid" composite string
        pk, _, guid = s.partition("|")
        return make_entity_id(vertical_for_profile_key(pk), guid)
    return None                                           # bare source_id: ambiguous
