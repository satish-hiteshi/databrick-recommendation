"""The single entry point for the unified router (ROUTER_PLAN §9 step 5, CONTEXT §1–§7).

    route(query) -> structured response

Flow:  query
         -> extract           (LLM → intent JSON; the ONLY language-understanding step)
         -> assemble_query    (deterministic establish-then-refine; picks the bounded path)
         -> response          { query, path_taken, universe_establisher, refinements_applied,
                                results (each tagged exact|related) + exact_vs_related, intent }

The LLM only fills the intent JSON; ALL decisioning is the deterministic assembler's. This module
adds nothing to that logic — it just wires extract→assemble and handles the one failure mode the
composed system must survive: the LLM being unavailable / emitting unparseable output.

GRACEFUL DEGRADATION (extraction failure):
  If `extract` raises (LLM down, timeout, or unparseable after its own retry), we DO NOT crash and
  we DO NOT guess a structured plan. We fall back to a single `vector_constrain` on the RAW query —
  the safest universe when intent is unknown (vector tolerates free text) — and flag it loudly:
  `extraction_ok=False`, `path_taken="FALLBACK__VECTOR_CONSTRAIN(raw_query)"`. The caller can always
  see the system degraded rather than silently returning a different kind of answer.
"""

import sys
import time
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))   # allow `python route.py` from anywhere

import blocks as B
import no_signal
from assembler import assemble_query
from extract import extract


def _fallback_vector(query: str, top_k: int, error: str) -> dict:
    """Extraction unavailable → degrade to one vector_constrain on the raw query, clearly flagged.
    (Restored to the pre-gibberish-fix behavior — the ONLY no-signal routing now is the LLM
    is_gibberish flag handled in route().)"""
    try:
        items = B.vector_constrain(query, vertical=None, top_n=top_k)
    except Exception as e:                                  # even the safe path can fail (engine down)
        items, error = [], f"{error}; fallback retrieval also failed: {type(e).__name__}: {e}"
    results = [dict(it, result_type="exact") for it in items[:top_k]]
    return {
        "query": query,
        "extraction_ok": False,
        "extraction_error": error,
        "path_taken": "FALLBACK__VECTOR_CONSTRAIN(raw_query)",
        "universe_establisher": "vector_constrain",
        "refinements_applied": [],
        "results": results,
        "exact_vs_related": {"exact": len(results), "related": 0, "backfill": False},
        "intent": None,
    }


def route(query: str, top_k: int = 10, backfill_threshold: Optional[int] = None) -> dict:
    """Run a query through the full unified router. Returns one structured response dict.

    `extraction_ok` is True on the normal path (intent JSON → assembled path); False when the LLM
    failed and we degraded to the raw-query vector fallback. `timing_ms` is wall-clock end to end.
    """
    t0 = time.time()

    # ── 1. EXTRACT (the only LLM step). On failure → graceful vector fallback. ──
    try:
        intents = extract(query)
    except Exception as e:
        out = _fallback_vector(query, top_k, f"{type(e).__name__}: {e}")
        out["timing_ms"] = round((time.time() - t0) * 1000)
        return out

    # ── 1b. GIBBERISH (the ONLY no-signal branch): if the LLM flagged the input as genuinely
    #        unintelligible (is_gibberish=true), serve the recent-mixed fallback. No score/vertical/
    #        name checks — one branch, driven by the LLM flag. Any real request flows on normally. ──
    if intents and getattr(intents[0], "is_gibberish", False):
        out = no_signal.build_response(
            intents[0], top_k, "LLM flagged input as gibberish (is_gibberish=true) → recent-mixed fallback")
        out.update({"query": query, "extraction_ok": True, "is_gibberish": True,
                    "timing_ms": round((time.time() - t0) * 1000)})
        return out

    # ── 2. ASSEMBLE (deterministic establish-then-refine; 1 intent → single universe, >1 → merge) ──
    kwargs = {"top_k": top_k}
    if backfill_threshold is not None:
        kwargs["backfill_threshold"] = backfill_threshold
    out = dict(assemble_query(intents, **kwargs))

    # ── 3. annotate with entry-point metadata (assembler output is otherwise passed through verbatim) ──
    out["query"] = query
    out["extraction_ok"] = True
    out["timing_ms"] = round((time.time() - t0) * 1000)
    return out


# ── pretty trace (used by the worked-examples runner and `python route.py "<query>"`) ──
def format_trace(resp: dict, top: int = 10) -> str:
    L = []
    L.append(f'QUERY: "{resp.get("query", "")}"')
    L.append(f'  extraction_ok : {resp.get("extraction_ok")}'
             + ("" if resp.get("extraction_ok", True) else f'  ({resp.get("extraction_error")})'))
    L.append(f'  path_taken    : {resp.get("path_taken")}')

    if resp.get("path_taken") == "MULTI_INTENT":              # independent multi-intent → grouped
        L.append(f'  n_intents     : {resp.get("n_intents")}')
        for g in resp.get("groups", []):
            ev = g.get("exact_vs_related", {})
            L.append(f'\n  ── group: {g["group"]}  [{g["path_taken"]}]  '
                     f'establisher={g["universe_establisher"]}  '
                     f'(exact {ev.get("exact")}, related {ev.get("related")})')
            for r in g["results"][:top]:
                tag = r.get("result_type", "exact")
                L.append(f'      [{tag:<7}] {r["name"]}  ({r["vertical"]})  — {r.get("why","")}')
        return "\n".join(L)

    L.append(f'  establisher   : {resp.get("universe_establisher")}')
    for r in resp.get("refinements_applied", []):
        L.append(f'  refine        : {r}')
    ev = resp.get("exact_vs_related", {})
    L.append(f'  exact/related : {ev.get("exact")} exact, {ev.get("related")} related '
             f'(backfill={ev.get("backfill")})')
    L.append("  results:")
    for i, r in enumerate(resp.get("results", [])[:top], 1):
        tag = r.get("result_type", "exact")
        L.append(f'    {i:>2}. [{tag:<7}] {r["name"]}  ({r["vertical"]})')
        L.append(f'         why: {r.get("why","")}')
    return "\n".join(L)


if __name__ == "__main__":
    import json
    q = " ".join(sys.argv[1:]) or "Final Fantasy games"
    resp = route(q)
    print(format_trace(resp))
    if "--json" in sys.argv:
        print("\n--- intent JSON ---")
        print(json.dumps(resp.get("intent"), indent=2, ensure_ascii=False))
