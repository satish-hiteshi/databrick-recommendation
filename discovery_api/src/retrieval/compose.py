"""Discovery v2 — STRING COMPOSER (Source 2).

Composes the vector-path query TEXT for a taste cluster. Genre intent rides INSIDE the phrase because
/api/retrieve filters only by `vertical` (verified substrate fact). Two interchangeable composers behind
ONE interface so V2-P6 can A/B them by flipping config.V2_STRING_COMPOSER:
  - deterministic_compose : template from top_genres + top_keywords (fast, free, deterministic) — DEFAULT
  - llm_compose           : reuse Endpoint 1's LLM to write a natural phrase from the SAME attributes
                            (cached + short-timeout; on failure → deterministic).
"""

from __future__ import annotations

from typing import Tuple

from .. import config
from .llm_seam import LLMComposeError, llm_complete_short

_LLM_CACHE: dict = {}   # (vertical, genres, keywords) -> phrase  (profile changes slowly; safe to cache)


def _attrs(cluster):
    gs = [g for g, _ in cluster.top_genres[:config.V2_COMPOSE_TOP_GENRES]]
    ks = [k for k, _ in cluster.top_keywords[:config.V2_COMPOSE_TOP_KEYWORDS]]
    return gs, ks


def deterministic_compose(cluster) -> str:
    """Template: "<genres> — <keywords>". Genre names keep canonical capitalisation."""
    gs, ks = _attrs(cluster)
    phrase = ", ".join(gs)
    if ks:
        phrase = (phrase + " — " + ", ".join(ks)) if phrase else ", ".join(ks)
    return phrase.strip(" —") or (cluster.label or cluster.dominant_vertical)


def llm_compose(cluster) -> str:
    """Natural-language phrase from the same attributes via Endpoint 1's LLM. Cached; raises on failure."""
    gs, ks = _attrs(cluster)
    key = (cluster.dominant_vertical, tuple(gs), tuple(ks))
    if key in _LLM_CACHE:
        return _LLM_CACHE[key]
    system = ("You write ONE short natural search phrase (<=18 words, no preamble, no quotes) describing "
              f"the kind of {cluster.dominant_vertical} a person enjoys, given genres and keywords. "
              "Output only the phrase.")
    user = f"genres: {', '.join(gs)}\nkeywords: {', '.join(ks)}"
    txt = (llm_complete_short(system, user) or "").strip().strip('"').replace("\n", " ").strip()
    if not txt:
        raise LLMComposeError("empty LLM phrase")
    _LLM_CACHE[key] = txt
    return txt


def compose_query(cluster, composer: str = None) -> Tuple[str, str]:
    """Compose the cluster's query phrase. Returns (phrase, composer_used). llm falls back to deterministic
    on any failure so retrieval never blocks on the LLM."""
    composer = (composer or config.V2_STRING_COMPOSER).lower()
    if composer == "llm":
        try:
            return llm_compose(cluster), "llm"
        except LLMComposeError:
            return deterministic_compose(cluster), "deterministic"   # transparent fallback
    return deterministic_compose(cluster), "deterministic"
