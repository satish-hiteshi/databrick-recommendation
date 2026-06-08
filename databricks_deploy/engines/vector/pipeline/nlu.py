"""
Natural Language Understanding v2 for Feeds.ai pipeline.
Supports 5 query modes: entity_single, entity_multi, theme_based, descriptive, mixed.

LLM = Databricks Foundation Model (Meta Llama 3.3 70B) via pipeline.llm.databricks_complete — NO Groq.
Uses JSON mode (response_format=json_object) with the schema spelled out in the prompt (the Databricks
serving endpoint is used in JSON mode, not OpenAI tool-calling). Output shape is unchanged from before.

NOTE: in the unified-router architecture this standalone NLU is superseded by the router's single
shared brain (ROUTER_PLAN §8); it remains only for the legacy standalone vector-search surface.
"""

import json
import time

from pipeline.llm import databricks_complete

SYSTEM_PROMPT = (
    "You are a query parser for an entertainment discovery system covering games, movies, "
    "TV shows, and podcasts. Analyze the user's query and extract all relevant signals. "
    "If they name specific entities, include them in positive_entities. "
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
    "— entity_single: exactly one named entity; entity_multi: 2+ named entities the user likes; "
    "theme_based: genres/themes without named entities; descriptive: vague natural-language wants; "
    "mixed: named entities combined with themes or dislikes.\n"
    '  "positive_entities": [exact names of entities the user likes / wants similar to], [] if none.\n'
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
    """Convert null/None to empty list."""
    if val is None:
        return []
    if isinstance(val, list):
        return [x for x in val if x is not None]
    return []


def _loads(raw: str):
    """Strip markdown fences, json.loads; fall back to the outermost {...}."""
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
    """
    Parse a user query into structured intent using the Databricks Llama endpoint (JSON mode).
    Returns dict with all v2 fields (shape unchanged from the previous Groq implementation).
    """
    for attempt in range(max_retries + 1):
        try:
            raw = databricks_complete(SYSTEM_PROMPT, user_query, json_mode=True, temperature=0)
            args = _loads(raw)
            return {
                "query_mode": args.get("query_mode", "entity_single"),
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
