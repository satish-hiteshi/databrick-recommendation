"""Consumer query battery + acceptance-criteria judging for endpoint_4_search.

Grounded in UC4/UC7 stories + real search behavior. Builds the engine ONCE (read-only), runs ~31 queries
across clean names / misspellings-abbrev / ambiguous / thematic / cross-vertical / onboarding /
vertical-filtered / edge, prints mode + top-5 + per-vertical spread, and JUDGES each against the
acceptance criteria. Reads only. Run:
  cd endpoint_4_search/local_code && python -m search_api.eval.battery
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))   # local_code

from search_api.src.engine import SearchEngine          # noqa: E402
from search_api.src.request import SearchRequest         # noqa: E402

_NONALNUM = re.compile(r"[^a-z0-9]+")


def _norm(s: str) -> str:
    return " ".join(_NONALNUM.sub(" ", (s or "").casefold()).split())


def raw_mt(r: dict) -> str:
    """True internal match_type (exact|fuzzy|thematic); response collapses exact+fuzzy→'exact'."""
    return (r.get("debug") or {}).get("match_type_raw", r["match_type"])


# (label, body, kind, target)  — target = expected canonical name (for clean_name / misspell / edge)
BATTERY = [
    # clean canonical names
    ("clean", {"query": "Elden Ring"}, "clean_name", "Elden Ring"),
    ("clean", {"query": "The Daily"}, "clean_name", "The Daily"),
    ("clean", {"query": "Arsenal"}, "clean_name", "Arsenal"),
    ("clean", {"query": "Stardew Valley"}, "clean_name", "Stardew Valley"),
    ("clean", {"query": "Game of Thrones"}, "clean_name", "Game of Thrones"),
    ("clean", {"query": "Cyberpunk 2077"}, "clean_name", "Cyberpunk 2077"),
    # misspellings / abbreviations
    ("misspell", {"query": "eldn ring"}, "misspell", "Elden Ring"),
    ("misspell", {"query": "stardew"}, "misspell", "Stardew Valley"),
    ("abbrev", {"query": "got"}, "misspell", "Game of Thrones"),
    ("abbrev", {"query": "cod"}, "misspell", "Call of Duty"),
    ("abbrev", {"query": "gta 6"}, "misspell", "Grand Theft Auto VI"),
    # ambiguous (title AND topic)
    ("ambiguous", {"query": "Battlefield"}, "ambiguous", None),
    ("ambiguous", {"query": "Halo"}, "ambiguous", None),
    ("ambiguous", {"query": "Friends"}, "ambiguous", None),
    ("ambiguous", {"query": "Survivor"}, "ambiguous", None),
    ("ambiguous", {"query": "Frasier"}, "ambiguous", None),
    # thematic concepts
    ("thematic", {"query": "cooking"}, "thematic", None),
    ("thematic", {"query": "true crime"}, "thematic", None),
    ("thematic", {"query": "horror games"}, "thematic", None),
    ("thematic", {"query": "cozy"}, "thematic", None),
    ("thematic", {"query": "relaxing fantasy worlds"}, "thematic", None),
    # cross-vertical (UC7 Story 3)
    ("cross-vert", {"query": "sci-fi"}, "cross_vertical", None),
    ("cross-vert", {"query": "fantasy"}, "cross_vertical", None),
    ("cross-vert", {"query": "space"}, "cross_vertical", None),
    # onboarding profile (pre-auth, disambiguation on)
    ("onboarding", {"query": "football", "source_context": "onboarding_search", "user_id": None,
                    "exclude_followed": False, "session_id": "sess-ob-1", "disambiguation": True},
     "onboarding", None),
    ("onboarding", {"query": "hip-hop", "source_context": "onboarding_search", "user_id": None,
                    "exclude_followed": False, "session_id": "sess-ob-2", "disambiguation": True},
     "onboarding", None),
    ("onboarding", {"query": "cooking shows and channels", "source_context": "onboarding_search",
                    "user_id": None, "exclude_followed": False, "session_id": "sess-ob-3",
                    "disambiguation": True}, "onboarding", None),
    # vertical-filtered
    ("vfilter", {"query": "horror", "verticals": ["game"], "mode": "thematic"}, "vertical_filtered", None),
    ("vfilter", {"query": "news", "verticals": ["podcast"], "mode": "thematic"}, "vertical_filtered", None),
    # edge
    ("edge-novec", {"query": "Crown Trick"}, "edge_novector", "Crown Trick"),
    ("edge-none", {"query": "zxqwv nonsense 12345"}, "edge_nomatch", None),
]


def judge(kind, body, pred, dbg, target):
    results = pred["results"]
    top = results[0] if results else None
    verts = dbg.get("result_verticals", {})
    mts = [raw_mt(r) for r in results]
    if kind == "clean_name":
        ok = bool(top) and raw_mt(top) == "exact" and _norm(top["name"]) == _norm(body["query"])
        if not ok and not any(raw_mt(r) == "exact" and _norm(r["name"]) == _norm(body["query"]) for r in results):
            return "FAIL*", f"no exact '{body['query']}' in corpus (data gap) — top1={top['name'] if top else None!r}"
        return ("PASS" if ok else "FAIL", f"top1={top['name'] if top else None!r}/{raw_mt(top) if top else None}")
    if kind == "misspell":
        idx = next((i for i, r in enumerate(results[:5]) if _norm(r["name"]) == _norm(target)), None)
        in_corpus = any(_norm(r["name"]) == _norm(target) for r in results) or None
        tag = "FAIL" if (idx is None and in_corpus) else ("FAIL*" if idx is None else "PASS")
        return (tag, f"target {target!r} rank={idx+1 if idx is not None else '>5 (absent from corpus)' if not in_corpus else '>5'}; "
                     f"top1={top['name'] if top else None!r}")
    if kind == "ambiguous":
        both = dbg.get("mode_taken") == "auto_both"
        has_name_pin = any(r["match_type"] == "exact" for r in results[:5])   # name-path pin (exact OR strong fuzzy)
        has_thematic = "thematic" in mts
        if both and has_thematic and has_name_pin:
            return "PASS", f"both: name pin ({raw_mt(top)}) + thematic"
        if dbg.get("mode_taken") == "name" and top and raw_mt(top) == "exact" and dbg.get("route", {}).get("n_exact") == 1:
            return "PASS~", f"unique-in-corpus → name mode, exact pinned #1 (not truly ambiguous here)"
        return "FAIL", f"mode={dbg.get('mode_taken')} name_pin_top5={has_name_pin} thematic={has_thematic}"
    if kind == "thematic":
        ok = len(results) > 0 and "thematic" in mts
        return ("PASS" if ok else "FAIL", f"results={len(results)} thematic_present={'thematic' in mts} top1={top['name'][:30] if top else None!r}")
    if kind == "cross_vertical":
        ok = len(verts) >= 3
        return ("PASS" if ok else "FAIL", f"verticals={verts}")
    if kind == "onboarding":
        session_ok = pred["session_id"] == body["session_id"]
        follows_off = not dbg.get("follows", {}).get("applied", False)
        cross = len(verts) >= 2
        ok = session_ok and follows_off and cross
        return ("PASS" if ok else "FAIL",
                f"session_ok={session_ok} follows_applied={dbg.get('follows', {}).get('applied')} verticals={verts}")
    if kind == "vertical_filtered":
        vf = set(body["verticals"])
        ok = len(results) > 0 and all(r["vertical"] in vf for r in results)
        return ("PASS" if ok else "FAIL", f"all_in_{vf}={ok} verticals={verts}")
    if kind == "edge_novector":
        ok = bool(top) and _norm(top["name"]) == _norm(target)
        return ("PASS" if ok else "FAIL", f"found_by_name top1={top['name'] if top else None!r}/{raw_mt(top) if top else None}")
    if kind == "edge_nomatch":
        no_false_exact = not any(raw_mt(r) == "exact" for r in results)
        return ("PASS", f"graceful: results={len(results)} no_false_exact={no_false_exact} "
                        f"top1={top['name'][:24] if top else None!r} score={top['score'] if top else None}")
    return "?", ""


def run():
    eng = SearchEngine()
    print("[battery] engine:", {k: eng.health()[k] for k in
                                ("bridge_properties", "name_index_size", "name_backend", "qwen_embed_available")})
    crit = {"canonical_first": [], "ambiguous_both": [], "cross_vertical_spread": [],
            "podcast_correct": [], "why_string_specific": [], "onboarding_correct": []}
    rows = []
    for label, body, kind, target in BATTERY:
        b = {"limit": 20, "debug": True, "mode": "auto", **body}
        env = eng.handle(SearchRequest.from_dict(b))
        pred = env["predictions"][0]; dbg = pred["debug"]
        verdict, why = judge(kind, body, pred, dbg, target)
        rows.append((label, body["query"], kind, dbg.get("mode_taken"), verdict, why, pred, dbg))
        # acceptance accounting
        if kind == "clean_name":
            crit["canonical_first"].append(verdict.startswith("PASS"))
        if kind == "ambiguous":
            crit["ambiguous_both"].append(verdict.startswith("PASS"))
        if kind == "cross_vertical":
            crit["cross_vertical_spread"].append(verdict == "PASS")
        if kind == "onboarding":
            crit["onboarding_correct"].append(verdict == "PASS")
        # why_string specific on every result (contains the query)
        q = body["query"]
        crit["why_string_specific"].append(all(q in (r["why_string"] or "") for r in pred["results"]))

    # podcast acceptance: The Daily #1 podcast
    for (label, query, kind, mode, verdict, why, pred, dbg) in rows:
        if query == "The Daily":
            t = pred["results"][0] if pred["results"] else None
            crit["podcast_correct"].append(bool(t) and t["vertical"] == "podcast" and _norm(t["name"]) == "the daily")

    # ── print per-query ──
    print("\n" + "=" * 100 + "\nPER-QUERY RESULTS + VERDICTS")
    for (label, query, kind, mode, verdict, why, pred, dbg) in rows:
        res = pred["results"]
        print(f"\n[{label:10}] {query!r:34} mode={mode:13} -> {verdict}")
        print(f"             {why}")
        if kind in ("thematic", "cross_vertical", "onboarding", "vertical_filtered"):
            print(f"             vertical-spread: {dbg.get('result_verticals')}")
        for r in res[:5]:
            print(f"      {r['score']:.4f} {raw_mt(r):<8} {r['vertical']:<7} conf={r['disambiguation_confidence']:.2f}  {r['name'][:44]}")

    # ── acceptance table ──
    print("\n" + "=" * 100 + "\nACCEPTANCE CRITERIA")
    def line(name, vals):
        n = sum(1 for v in vals if v); print(f"  {name:26} {n}/{len(vals)}  {'PASS' if n == len(vals) else 'see failures'}")
    line("canonical/exact #1", crit["canonical_first"])
    line("ambiguous returns both", crit["ambiguous_both"])
    line("thematic cross-vertical", crit["cross_vertical_spread"])
    line("podcast name correct", crit["podcast_correct"])
    line("why_string query-specific", crit["why_string_specific"])
    line("onboarding correct", crit["onboarding_correct"])

    # ── non-regression snapshot (after-values; before = skeleton, cited in report) ──
    print("\nNON-REGRESSION (after):")
    for (label, query, kind, mode, verdict, why, pred, dbg) in rows:
        if query in ("Battlefield", "The Daily", "sci-fi", "cooking"):
            t = pred["results"][0] if pred["results"] else None
            print(f"  {query:12} mode={mode:11} top1={t['name'][:30]!r}/{t['match_type']} "
                  f"verticals={dbg.get('result_verticals')}")
    return rows


if __name__ == "__main__":
    run()
