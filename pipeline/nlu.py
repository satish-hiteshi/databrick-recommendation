"""
Natural Language Understanding v2 for Feeds.ai pipeline.
Supports 5 query modes: entity_single, entity_multi, theme_based, descriptive, mixed.
Uses Groq API (Llama 3.3 70B) with function calling.
"""

import json
import time

from groq import Groq

from pipeline.config import GROQ_API_KEY, GROQ_MODEL

SYSTEM_PROMPT = (
    "You are a query parser for an entertainment discovery system covering games, movies, "
    "and TV shows. Analyze the user's query and extract all relevant signals. "
    "If they name specific entities, include them in positive_entities. "
    "If they mention dislikes, include those in negative_entities. "
    "If they use genre/theme terms, include those in additional_keywords. "
    "If they describe what they want vaguely, translate their description into standard "
    "entertainment terminology in description_derived_keywords. "
    "Always determine which verticals they want results from. "
    "Choose the query_mode that best describes the query type."
)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "analyze_query",
            "description": "Analyze a user's entertainment discovery query and extract structured signals",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_mode": {
                        "type": "string",
                        "enum": ["entity_single", "entity_multi", "theme_based", "descriptive", "mixed"],
                        "description": (
                            "entity_single: user names exactly one entity. "
                            "entity_multi: user names 2+ entities they like. "
                            "theme_based: user describes genres/themes without naming entities. "
                            "descriptive: user describes what they want in natural language. "
                            "mixed: user combines named entities with theme descriptions or includes dislikes."
                        ),
                    },
                    "positive_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Entertainment entities the user likes or wants similar content to. "
                            "Extract exact names as the user wrote them. Empty array if no specific entities mentioned."
                        ),
                    },
                    "negative_entities": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Entities the user explicitly dislikes or wants to avoid. "
                            "Look for phrases like 'I dont like', 'not like', 'hate', 'except', 'but not'. "
                            "Empty array if none."
                        ),
                    },
                    "additional_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Explicit genre, theme, or mood terms from the query. "
                            "Examples: 'horror', 'dark fantasy', 'challenging', 'sci-fi', 'comedy'. "
                            "Only include terms the user actually used."
                        ),
                    },
                    "description_derived_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "When the user describes what they want vaguely (e.g., 'content with country wars "
                            "and gun fighting'), translate their description into standard entertainment terms "
                            "(e.g., 'military warfare', 'combat', 'war drama', 'tactical shooter'). "
                            "Empty if user used standard terms."
                        ),
                    },
                    "target_verticals": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["game", "movie", "tv"]},
                        "description": (
                            "Which verticals to search. 'movies' or 'films' = ['movie']. "
                            "'shows' or 'TV shows' or 'series' = ['tv']. 'games' = ['game']. "
                            "If user says 'content' or 'something' or doesn't specify, "
                            "return all three: ['game', 'movie', 'tv']."
                        ),
                    },
                    "query_type": {
                        "type": "string",
                        "enum": ["within_vertical", "cross_vertical"],
                        "description": (
                            "within_vertical if user wants same type as their reference "
                            "(games like a game). cross_vertical if they want different types "
                            "(movies based on a game they like) or all types."
                        ),
                    },
                },
                "required": [
                    "query_mode",
                    "positive_entities",
                    "negative_entities",
                    "additional_keywords",
                    "description_derived_keywords",
                    "target_verticals",
                    "query_type",
                ],
            },
        },
    }
]


def _safe_list(val):
    """Convert null/None to empty list."""
    if val is None:
        return []
    if isinstance(val, list):
        return [x for x in val if x is not None]
    return []


def parse_query(user_query: str, max_retries: int = 2) -> dict:
    """
    Parse a user query into structured intent using Groq LLM function calling.
    Returns dict with all v2 fields.
    """
    client = Groq(api_key=GROQ_API_KEY)

    for attempt in range(max_retries + 1):
        try:
            response = client.chat.completions.create(
                model=GROQ_MODEL,
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_query},
                ],
                tools=TOOLS,
                tool_choice={"type": "function", "function": {"name": "analyze_query"}},
                temperature=0,
            )

            tool_call = response.choices[0].message.tool_calls[0]
            args = json.loads(tool_call.function.arguments)

            return {
                "query_mode": args.get("query_mode", "entity_single"),
                "positive_entities": _safe_list(args.get("positive_entities")),
                "negative_entities": _safe_list(args.get("negative_entities")),
                "additional_keywords": _safe_list(args.get("additional_keywords")),
                "description_derived_keywords": _safe_list(args.get("description_derived_keywords")),
                "target_verticals": _safe_list(args.get("target_verticals")) or ["game", "movie", "tv"],
                "query_type": args.get("query_type", "cross_vertical"),
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
        "I like content with country wars and gun fighting",
        "Love Elden Ring but hate Star Wars, want dark fantasy movies",
        "Movies for someone who loved Resident Evil and Silent Hill games",
        "Recommend me sci-fi",
        "I enjoy slow-burn psychological tension with unreliable narrators",
        "Games and movies similar to Marvel Zombies",
        "I liked Stranger Things and Alien Earth but didn't enjoy comedy shows, recommend games",
    ]
    for q in test_queries:
        print(f"\nQuery: {q}")
        r = parse_query(q)
        print(f"  query_mode:       {r['query_mode']}")
        print(f"  positive_entities: {r['positive_entities']}")
        print(f"  negative_entities: {r['negative_entities']}")
        print(f"  additional_kw:    {r['additional_keywords']}")
        print(f"  derived_kw:       {r['description_derived_keywords']}")
        print(f"  target_verticals: {r['target_verticals']}")
        print(f"  query_type:       {r['query_type']}")
