import json
from typing import List

from llm import llm_complete
from intent import Intent, parse_intents
from extraction_prompt import SYSTEM_PROMPT


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
    user = query
    last_err = None
    for attempt in range(retries + 1):
        raw = llm_complete(SYSTEM_PROMPT, user)
        try:
            intents = parse_intents(_loads(raw))
            for it in intents:
                if not it.raw_query:
                    it.raw_query = query
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
