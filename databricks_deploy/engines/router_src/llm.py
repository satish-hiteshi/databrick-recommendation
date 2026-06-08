"""Single seam for the router's LLM chat-completion call.

`llm_complete(system, user) -> str` dispatches to the configured provider
(`config.LLM_PROVIDER` = databricks | groq). Swapping providers is a config flag; nothing
downstream (schema / prompt / parser / eval) changes.

Databricks Foundation Model endpoint is OpenAI-compatible (confirmed live, see PROGRESS):
  POST {messages,temperature,max_tokens,response_format} with the PAT as `Authorization: Bearer`,
  → response {id,object,created,model,choices:[{message:{content}}],usage}.
The PAT is a SECRET read from config (router/.env). If absent, this fails with a clear message.
"""

import json
import time
from typing import Optional

import httpx

import config


class LLMError(RuntimeError):
    pass


# ── response text extraction (defensive across endpoint shapes) ────────
def _extract_text(j) -> str:
    if isinstance(j, str):
        return j
    if isinstance(j, dict):
        ch = j.get("choices")                                  # OpenAI / Databricks chat shape
        if ch:
            msg = ch[0].get("message") or {}
            if msg.get("content") is not None:
                return msg["content"]
            if ch[0].get("text") is not None:
                return ch[0]["text"]
        for k in ("predictions", "outputs", "output"):         # native MLflow shapes
            v = j.get(k)
            if isinstance(v, list) and v:
                first = v[0]
                if isinstance(first, str):
                    return first
                if isinstance(first, dict):
                    for kk in ("candidates", "content", "text", "generated_text"):
                        if kk in first:
                            val = first[kk]
                            return val if isinstance(val, str) else json.dumps(val)
                return json.dumps(first)
            if isinstance(v, str):
                return v
        if isinstance(j.get("messages"), list) and j["messages"]:
            last = j["messages"][-1]
            if isinstance(last, dict) and last.get("content") is not None:
                return last["content"]
    raise LLMError(f"could not find assistant text; response keys="
                   f"{list(j.keys()) if isinstance(j, dict) else type(j).__name__}")


# ── Databricks Foundation Model endpoint ───────────────────────────────
def _databricks(system: str, user: str, json_mode: bool, temperature: float, max_tokens: int) -> str:
    if not config.DATABRICKS_TOKEN:
        raise LLMError("DATABRICKS_TOKEN is not set — add it to router/.env "
                       "(DATABRICKS_TOKEN=dapi…) and retry. Refusing to proceed without it.")
    headers = {"Authorization": f"Bearer {config.DATABRICKS_TOKEN}", "Content-Type": "application/json"}
    # NOTE (07a finding): this endpoint REJECTS response_format:json_object with HTTP 400 ("messages must
    # contain the word 'json'") on our prompts, so it was always dropped-and-retried — a wasted ~1.1s
    # round-trip on every call. We do NOT send response_format; the system prompt already demands JSON,
    # and the caller's defensive parse (fence-strip + outermost {...}) handles the clean text output.
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
                last = f"HTTP {r.status_code}: {r.text[:150]}"
                time.sleep(1.0)
                continue
            raise LLMError(f"Databricks HTTP {r.status_code}: {r.text[:200]}")
        except httpx.HTTPError as e:
            last = f"{type(e).__name__}: {e}"
            time.sleep(1.0)
    raise LLMError(f"Databricks call failed after retry: {last}")


# ── Groq (fallback) ────────────────────────────────────────────────────
_groq_client = None


def _groq(system: str, user: str, json_mode: bool, temperature: float, max_tokens: int) -> str:
    global _groq_client
    from groq import Groq
    if _groq_client is None:
        if not config.GROQ_API_KEY:
            raise LLMError("GROQ_API_KEY is not set (LLM_PROVIDER=groq).")
        _groq_client = Groq(api_key=config.GROQ_API_KEY)
    kwargs = dict(model=config.GROQ_MODEL, temperature=temperature, max_tokens=max_tokens,
                  messages=[{"role": "system", "content": system}, {"role": "user", "content": user}])
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    resp = _groq_client.chat.completions.create(**kwargs)
    return resp.choices[0].message.content


# ── the seam ───────────────────────────────────────────────────────────
def llm_complete(system: str, user: str, json_mode: bool = True,
                 temperature: float = 0.0, max_tokens: Optional[int] = None) -> str:
    """Provider-agnostic chat completion → assistant text. Provider = config.LLM_PROVIDER."""
    max_tokens = max_tokens or config.LLM_MAX_TOKENS
    p = config.LLM_PROVIDER
    if p == "databricks":
        return _databricks(system, user, json_mode, temperature, max_tokens)
    if p == "groq":
        return _groq(system, user, json_mode, temperature, max_tokens)
    raise LLMError(f"unknown LLM_PROVIDER={p!r} (expected 'databricks' or 'groq')")


if __name__ == "__main__":
    print(f"provider={config.LLM_PROVIDER}")
    print(llm_complete("You reply with one token.", "Reply with exactly: LLM_SEAM_OK", json_mode=False))
