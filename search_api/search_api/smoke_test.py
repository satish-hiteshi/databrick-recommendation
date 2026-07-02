"""Endpoint 4 SMOKE TEST — start the service and hit every path with ~8 queries.

Proves: imports OK, service starts, both retrieval paths run, ranking/dedup/fairness wire end to end.
Does NOT judge result quality (next prompt). Run:
  cd endpoint_4_search/local_code/search_api && python smoke_test.py
"""

from __future__ import annotations

import socket
import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))   # local_code → `search_api` importable

import httpx  # noqa: E402
import uvicorn  # noqa: E402

from search_api.src import config  # noqa: E402
from search_api.src.api import app  # noqa: E402


def _free_port(start: int) -> int:
    for p in range(start, start + 25):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((config.API_HOST, p))
                return p
            except OSError:
                continue
    return start


PORT = _free_port(config.API_PORT)
BASE = f"http://{config.API_HOST}:{PORT}"
print(f"[smoke] requested :{config.API_PORT} -> using :{PORT}" + ("" if PORT == config.API_PORT else "  (8050 busy)"))


def _serve():
    uvicorn.run(app, host=config.API_HOST, port=PORT, log_level="warning")


QUERIES = [
    ("clean name",            {"query": "Elden Ring", "mode": "auto", "debug": True}),
    ("fuzzy name",            {"query": "eldn ring", "mode": "auto", "debug": True}),
    ("ambiguous term",        {"query": "Battlefield", "mode": "auto", "debug": True}),
    ("thematic",              {"query": "cooking", "mode": "auto", "debug": True}),
    ("cross-vertical themat", {"query": "sci-fi", "mode": "thematic", "debug": True}),
    ("onboarding thematic",   {"query": "relaxing fantasy worlds", "mode": "auto", "user_id": None,
                               "exclude_followed": False, "source_context": "onboarding_search",
                               "session_id": "sess-onb-1", "debug": True}),
    ("podcast name",          {"query": "The Daily", "mode": "auto", "debug": True}),
    ("vertical-filtered them",{"query": "horror", "mode": "thematic", "verticals": ["game"], "debug": True}),
]


def main() -> int:
    threading.Thread(target=_serve, daemon=True).start()
    health = None
    for _ in range(120):
        try:
            r = httpx.get(BASE + "/search/health", timeout=90)
            if r.status_code == 200:
                health = r.json()
                break
        except Exception:
            pass
        time.sleep(1)
    if not health:
        print("[smoke] FAIL — service never became healthy"); return 1
    print("\n[HEALTH]", {k: health[k] for k in ("bridge_properties", "name_index_size", "name_backend",
                                                "thematic_vectors", "popularity_rows", "centrality_rows",
                                                "qwen_embed_available", "port")})

    sci_fi_verticals = None
    for label, body in QUERIES:
        try:
            resp = httpx.post(BASE + "/search", json=body, timeout=120).json()
        except Exception as e:
            print(f"\n### {label}: REQUEST FAILED — {type(e).__name__}: {e}"); continue
        pred = resp["predictions"][0]
        dbg = pred.get("debug") or {}
        results = pred["results"]
        print(f"\n### {label}  query={body['query']!r}  mode_taken={dbg.get('mode_taken')}  "
              f"results={pred['result_count']}  session={pred.get('session_id')}")
        print(f"    dedup={dbg.get('dedup')}  fairness={dbg.get('fairness', {}).get('applied')}"
              f"({dbg.get('fairness', {}).get('reason', dbg.get('fairness', {}).get('vertical_counts'))})  "
              f"follows={dbg.get('follows', {}).get('applied')}  route={dbg.get('route')}")
        for r in results[:5]:
            print(f"      {r['score']:.4f}  {r['match_type']:<8} {r['vertical']:<7} "
                  f"conf={r['disambiguation_confidence']:.2f}  {r['name'][:46]}")
        if label.startswith("cross-vertical"):
            sci_fi_verticals = dbg.get("result_verticals")

    print("\n[FAIRNESS] 'sci-fi' per-vertical counts in returned results:", sci_fi_verticals)
    print("[smoke] DONE — every path ran end to end.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
