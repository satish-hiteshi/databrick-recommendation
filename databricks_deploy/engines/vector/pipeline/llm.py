import json
import time

import httpx

from pipeline import config


class LLMError(RuntimeError):
    pass


def _extract_text(j) -> str:
    if isinstance(j, dict):
        ch = j.get("choices")
        if ch:
            msg = ch[0].get("message") or {}
            if msg.get("content") is not None:
                return msg["content"]
            if ch[0].get("text") is not None:
                return ch[0]["text"]
    raise LLMError(f"no assistant text in response; keys={list(j.keys()) if isinstance(j, dict) else type(j)}")


def databricks_complete(system: str, user: str, json_mode: bool = True,
                        temperature: float = 0.0, max_tokens: int = 900) -> str:
    if not config.DATABRICKS_TOKEN:
        raise LLMError("DATABRICKS_TOKEN is not set — add it to vector/.env (DATABRICKS_TOKEN=dapi…).")
    headers = {"Authorization": f"Bearer {config.DATABRICKS_TOKEN}", "Content-Type": "application/json"}
    # NOTE (07a finding): this endpoint REJECTS response_format:json_object with HTTP 400 on our prompts,
    # so it was always dropped-and-retried — a wasted ~1.1s round-trip per call. We do NOT send it; the
    # system prompt already demands strict JSON and the caller (_loads) strips fences / extracts {...}.
    body = {
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature, "max_tokens": max_tokens,
    }
    last = None
    for _ in range(2):  # one retry on transient (network / 5xx)
        try:
            r = httpx.post(config.DATABRICKS_LLM_ENDPOINT, headers=headers, json=body,
                           timeout=config.LLM_TIMEOUT_S)
            if r.status_code == 200:
                return _extract_text(r.json())
            if 500 <= r.status_code < 600:
                last = f"HTTP {r.status_code}: {r.text[:150]}"; time.sleep(1.0); continue
            raise LLMError(f"Databricks HTTP {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as e:
            last = f"{type(e).__name__}: {e}"; time.sleep(1.0)
    raise LLMError(f"Databricks call failed after retry: {last}")
