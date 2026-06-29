"""Extraction: query string -> LLM (via the provider-agnostic seam) -> parse + validate ->
list of Intent objects.

Isolated (NO engine calls). The LLM call goes through `llm.llm_complete` (provider =
config.LLM_PROVIDER: databricks | groq) so the provider swap is contained. On malformed/invalid
output it retries once with a "return valid JSON only" nudge, then fails cleanly.
"""

import json
from datetime import datetime, timezone
from typing import List

from llm import llm_complete
from intent import Intent, parse_intents
from extraction_prompt import SYSTEM_PROMPT

# Current-date anchor for relative time expressions ("last 2 years", "recent", "newest"). Computed at
# CALL TIME (UTC, stdlib only) so it stays correct in the deployed Databricks notebook and never goes
# stale — NEVER hardcode a date. UTC is used so "today" agrees with the UTC-based corpus release dates.
_DATE_PREAMBLE = ('The current date is {today} (UTC). Interpret ALL relative time expressions '
                  '("last 2 years", "the last N years", "recent", "new", "newest", "latest", "lately", '
                  '"this year", "from 2024", "coming out") relative to THIS date — "new"/"newest"/"latest '
                  '<category>" is a recency request (set temporal), NOT a title.\n\n')


def _system_prompt() -> str:
    today = datetime.now(timezone.utc).date().isoformat()
    return _DATE_PREAMBLE.format(today=today) + SYSTEM_PROMPT


def _balance(t: str) -> str:
    """Repair a truncated JSON object/array by appending the missing closing braces/brackets.
    LLMs occasionally drop the final brace(s) (observed: Llama emitting `{"intents":[{...}]` with no
    closing `}`). Walks the text tracking string context so braces inside strings are ignored, then
    closes any still-open `{`/`[` in reverse order."""
    stack, in_str, esc = [], False, False
    for ch in t:
        if esc:
            esc = False
        elif in_str:
            if ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    suffix = ('"' if in_str else "") + "".join("}" if c == "{" else "]" for c in reversed(stack))
    return t + suffix


def _loads(raw: str):
    """Best-effort: strip markdown fences, json.loads; fall back to the outermost {...}; finally repair
    a truncated reply by balancing unclosed braces/brackets (LLMs sometimes drop trailing braces)."""
    t = (raw or "").strip()
    if t.startswith("```"):
        t = t.strip("`")
        if t[:4].lower() == "json":
            t = t[4:]
        t = t.strip()
    a = t.find("{")
    if a > 0:
        t = t[a:]                       # drop any prose before the JSON
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        pass
    b = t.rfind("}")
    if b > 0:
        try:
            return json.loads(t[:b + 1])
        except json.JSONDecodeError:
            pass
    return json.loads(_balance(t))      # repair truncation (missing trailing braces)


_RETRY_NUDGE = ('\n\n[Your previous reply was not valid. Return ONLY the JSON object '
                '{"intents":[...]} matching the schema exactly — all fields present, null/[]/{} '
                'when absent. No prose, no markdown.]')


def extract(query: str, retries: int = 1) -> List[Intent]:
    """Return the extracted Intent list (length 1 normally; >1 for multi-intent).
    Raises ValueError if the LLM cannot produce valid JSON after `retries` retries."""
    user = query
    last_err = None
    sys_prompt = _system_prompt()                # inject today's date (computed now, UTC)
    for attempt in range(retries + 1):
        raw = llm_complete(sys_prompt, user)
        try:
            intents = parse_intents(_loads(raw))
            for it in intents:
                it.raw_query = query        # ALWAYS the literal user input — the LLM sometimes echoes a
                                            # worked example into this field (seen on gibberish like
                                            # "....."), which would corrupt the B4 grounding check.
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
