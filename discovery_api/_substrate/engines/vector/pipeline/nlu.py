import copy
import json
import os
import threading
import time

from pipeline.llm import databricks_complete

# ── deterministic-result cache (perf) ────────────────────────────────────────
# parse_query() calls the LLM at temperature 0, so its parsed signals are a pure function of the query.
# Memoizing by normalized query is BEHAVIOR-PRESERVING — a hit returns exactly what a fresh NLU call
# would, without the ~1.0-1.4s round-trip (this is the SECOND LLM hop on router-driven vector routes).
# Deep copies on store/return so callers can mutate freely. Disable with NLU_CACHE_TTL_S=0.
_NLU_CACHE_TTL_S = float(os.getenv("NLU_CACHE_TTL_S", "300"))
_NLU_CACHE_MAX = int(os.getenv("NLU_CACHE_MAX", "512"))
_nlu_cache: dict = {}
_nlu_cache_lock = threading.Lock()


def _nlu_norm(q: str) -> str:
    return " ".join((q or "").strip().lower().split())

SYSTEM_PROMPT = (
    "You are a query parser for an entertainment discovery system covering games, movies, "
    "TV shows, and podcasts. Analyze the user's query and extract all relevant signals. "
    "If they name a SPECIFIC, REAL title they already know (e.g. 'Elden Ring', 'The Last of Us', "
    "'Stardew Valley'), include it in positive_entities. "
    "CRITICAL: a genre, theme, mood, gameplay feature, audience, or generic noun-phrase is NOT a "
    "named entity. Phrases like 'horror games', 'co-op', 'couch co-op', 'open world rpg', "
    "'scary games', 'split-screen', 'multiplayer', 'something relaxing', 'party games' describe a "
    "TYPE of content, not a specific title — they must NEVER go in positive_entities. Put such genre/"
    "theme/feature/mood terms in additional_keywords (if explicit terms) or "
    "description_derived_keywords (if vague), and choose query_mode theme_based or descriptive. "
    "The test is proper-noun vs common-noun: a SPECIFIC TITLE is the proper name of one particular "
    "work (usually capitalised — 'Elden Ring', 'Resident Evil', 'Silent Hill', 'Stranger Things') "
    "and ALWAYS goes in positive_entities, EVEN when embedded in a longer descriptive sentence "
    "(e.g. 'movies for someone who loved Resident Evil and Silent Hill games' → "
    "positive_entities ['Resident Evil','Silent Hill']; 'I love Elden Ring and Dark Souls, recommend "
    "movies' → positive_entities ['Elden Ring','Dark Souls']). A common-noun genre/feature phrase "
    "('horror games', 'co-op', 'rpg') is NOT a title and must never go in positive_entities. Only the "
    "ambiguity between a generic category and nothing collapses to theme_based/descriptive — a real "
    "named title is NEVER dropped. "
    "If they mention dislikes, include those in negative_entities. "
    "If they use genre/theme terms, include those in additional_keywords. "
    "If they describe what they want vaguely, translate their description into standard "
    "entertainment terminology in description_derived_keywords. "
    "Always determine which verticals they want results from. "
    "Choose the query_mode that best describes the query type. "
    "If the user mentions any time-related terms (this week, this year, 2025, 2026, recent, new, "
    "upcoming, coming out, last month, old, classic, retro, 90s, 2000s, next week, this month, "
    "released, from, etc.), interpret them relative to today's date (2026-05-29) and populate "
    "date_filter_start and date_filter_end as YYYY-MM-DD strings. "
    "If no temporal terms are mentioned, both date fields must be null.\n\n"
    "Return ONLY a strict JSON object (no prose, no markdown) with EXACTLY these fields:\n"
    '{\n'
    '  "query_mode": one of ["entity_single","entity_multi","theme_based","descriptive","mixed"] '
    "— entity_single: the query names EXACTLY ONE specific real title "
    "(e.g. 'games like Elden Ring'); entity_multi: TWO OR MORE specific real titles the user "
    "names/likes (if positive_entities has 2+ items the mode MUST be entity_multi or mixed, NEVER "
    "entity_single); "
    "theme_based: genre/theme/feature terms with NO specific named title (e.g. 'horror games', "
    "'co-op games', 'open world rpg', 'sci-fi'); descriptive: vague natural-language wants with no "
    "named title (e.g. 'something relaxing for a rainy night', 'a co-op game to play with my "
    "girlfriend'); mixed: a specific named title combined with extra themes or dislikes. "
    "If the query names no specific real title, you MUST choose theme_based or descriptive (never an "
    "entity_* mode), and positive_entities MUST be [].\n"
    '  "positive_entities": [exact names of SPECIFIC REAL titles the user likes / wants similar to], '
    "[] if none. NEVER put a genre/theme/feature/mood/descriptor phrase here "
    "('horror games', 'co-op', 'rpg', 'relaxing', 'couch co-op') — those are keywords, not entities.\n"
    '  "negative_entities": [entities the user dislikes/avoids — "don\'t like","not like","hate",'
    '"except","but not"], [] if none.\n'
    '  "additional_keywords": [explicit genre/theme/mood terms the user actually used, e.g. "horror",'
    '"dark fantasy","challenging","sci-fi"], [] if none.\n'
    '  "description_derived_keywords": [standard entertainment terms translated from a vague '
    'description], [] if the user used standard terms.\n'
    '  "target_verticals": subset of ["game","movie","tv","podcast"] — "movies"/"films"=["movie"], '
    '"shows"/"TV shows"/"series"=["tv"], "games"=["game"], "podcasts"=["podcast"]; if "content"/'
    '"something"/unspecified return all four.\n'
    '  "query_type": "within_vertical" (same type as their reference) or "cross_vertical" '
    "(different types, or all types).\n"
    '  "date_filter_start": "YYYY-MM-DD" or null (e.g. "2026"/"this year"=2026-01-01, "2025"/'
    '"last year"=2025-01-01, "recent"/"new"=2025-11-29, "upcoming"/"coming out"=2026-05-29).\n'
    '  "date_filter_end": "YYYY-MM-DD" or null (e.g. "2026"/"this year"=2026-12-31, "2025"/'
    '"last year"=2025-12-31, "recent"/"new"=2026-05-29, "upcoming"=2026-12-31).\n'
    '}'
)


def _safe_list(val):
    if val is None:
        return []
    if isinstance(val, list):
        return [x for x in val if x is not None]
    return []


def _loads(raw: str):
    t = (raw or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        a, b = t.find("{"), t.rfind("}")
        if a >= 0 and b > a:
            return json.loads(t[a:b + 1])
        raise


def parse_query(user_query: str, max_retries: int = 2) -> dict:
    ckey = _nlu_norm(user_query)
    if _NLU_CACHE_TTL_S > 0 and ckey:
        with _nlu_cache_lock:
            ent = _nlu_cache.get(ckey)
            if ent is not None and (time.time() - ent[0]) < _NLU_CACHE_TTL_S:
                return copy.deepcopy(ent[1])
    for attempt in range(max_retries + 1):
        try:
            raw = databricks_complete(SYSTEM_PROMPT, user_query, json_mode=True, temperature=0)
            args = _loads(raw)
            result = {
                "query_mode": args.get("query_mode", "descriptive"),
                "positive_entities": _safe_list(args.get("positive_entities")),
                "negative_entities": _safe_list(args.get("negative_entities")),
                "additional_keywords": _safe_list(args.get("additional_keywords")),
                "description_derived_keywords": _safe_list(args.get("description_derived_keywords")),
                "target_verticals": _safe_list(args.get("target_verticals")) or ["game", "movie", "tv", "podcast"],
                "query_type": args.get("query_type", "cross_vertical"),
                "date_filter_start": args.get("date_filter_start") or None,
                "date_filter_end": args.get("date_filter_end") or None,
                "raw_response": args,
            }
            if _NLU_CACHE_TTL_S > 0 and ckey:
                with _nlu_cache_lock:
                    if len(_nlu_cache) >= _NLU_CACHE_MAX and ckey not in _nlu_cache:
                        _nlu_cache.pop(min(_nlu_cache, key=lambda k: _nlu_cache[k][0]), None)
                    _nlu_cache[ckey] = (time.time(), copy.deepcopy(result))
            return result
        except Exception as e:
            if attempt < max_retries:
                print(f"NLU attempt {attempt + 1} failed: {e}. Retrying in 2s...")
                time.sleep(2)
            else:
                raise RuntimeError(f"NLU failed after {max_retries + 1} attempts: {e}")


if __name__ == "__main__":
    test_queries = [
        "Games like Elden Ring",
        "I love Elden Ring and Dark Souls, recommend movies",
        "Horror content across all categories",
        "Love Elden Ring but hate Star Wars, want dark fantasy movies",
        "Recommend me sci-fi",
        "TV shows from the last 2 years",
    ]
    for q in test_queries:
        print(f"\nQuery: {q}")
        r = parse_query(q)
        print(f"  query_mode:        {r['query_mode']}")
        print(f"  positive_entities: {r['positive_entities']}")
        print(f"  negative_entities: {r['negative_entities']}")
        print(f"  additional_kw:     {r['additional_keywords']}")
        print(f"  target_verticals:  {r['target_verticals']}")
        print(f"  dates:             {r['date_filter_start']} .. {r['date_filter_end']}")
