import copy
import json
import os
import threading
import time
from typing import List

from llm import llm_complete
from intent import Intent, parse_intents
from extraction_prompt import SYSTEM_PROMPT

# ── deterministic-result cache (perf) ────────────────────────────────────────
# extract() calls the LLM at temperature 0, so the parsed intents are a pure function of the query.
# Memoizing by normalized query is therefore BEHAVIOR-PRESERVING — a cache hit returns exactly what a
# fresh LLM call would, only without the ~1.6-2.1s round-trip. Deep copies on store/return so callers
# that mutate the returned intents never corrupt the cached entry. Disable with EXTRACT_CACHE_TTL_S=0.
_CACHE_TTL_S = float(os.getenv("EXTRACT_CACHE_TTL_S", "300"))
_CACHE_MAX = int(os.getenv("EXTRACT_CACHE_MAX", "512"))
_cache: dict = {}
_cache_lock = threading.Lock()


def _norm_query(q: str) -> str:
    return " ".join((q or "").strip().lower().split())


def _cache_get(key: str):
    if _CACHE_TTL_S <= 0 or not key:
        return None
    with _cache_lock:
        ent = _cache.get(key)
        if ent is not None and (time.time() - ent[0]) < _CACHE_TTL_S:
            return [copy.deepcopy(it) for it in ent[1]]
    return None


def _cache_put(key: str, intents) -> None:
    if _CACHE_TTL_S <= 0 or not key:
        return
    with _cache_lock:
        if len(_cache) >= _CACHE_MAX and key not in _cache:
            _cache.pop(min(_cache, key=lambda k: _cache[k][0]), None)   # evict oldest
        _cache[key] = (time.time(), [copy.deepcopy(it) for it in intents])


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


_RETRY_NUDGE = ('\n\n[Your previous reply was not valid. Return ONLY the JSON object '
                '{"intents":[...]} matching the schema exactly — all fields present, null/[]/{} '
                'when absent. No prose, no markdown.]')


def extract(query: str, retries: int = 1) -> List[Intent]:
    ckey = _norm_query(query)
    cached = _cache_get(ckey)
    if cached is not None:
        return cached
    user = query
    last_err = None
    for attempt in range(retries + 1):
        raw = llm_complete(SYSTEM_PROMPT, user)
        try:
            intents = parse_intents(_loads(raw))
            for it in intents:
                if not it.raw_query:
                    it.raw_query = query
            _cache_put(ckey, intents)
            return intents
        except Exception as e:  # parse or validation failure
            last_err = e
            user = query + _RETRY_NUDGE
    raise ValueError(f"extraction failed after {retries + 1} attempts: {last_err}")


if __name__ == "__main__":
    import sys
    q = " ".join(sys.argv[1:]) or "Horror games by a developer that also makes RPGs, atmospheric"
    for it in extract(q):
        print(json.dumps(it.model_dump(), indent=2, ensure_ascii=False))
