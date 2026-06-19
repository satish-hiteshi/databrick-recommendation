"""V2-P3 STEP 0 — retrieval-quality probe (run BEFORE building Source 2/3).

Verifies the core assumption: a composed taste-phrase retrieves RELEVANT properties via /api/retrieve.
Probes: (1) per-cluster phrase → retrieve, print names; (2) per-cluster vs ONE blended phrase (mush?);
(3) deterministic phrase vs LLM-written phrase (reuse Endpoint 1's LLM). Read-only; no writes.
Run:  .venv/bin/python discovery_api/probe_v2p3_step0.py
"""
import sys
import time
from datetime import timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from discovery_api.src import timeutil
from discovery_api.src.data_access.csv_source import CsvDataSource
from discovery_api.src.data_access.substrate_client import SubstrateClient
from discovery_api.src.feed.taste_profile import (
    SIGNAL_FOLLOW, build_taste_profile, build_taste_profile_from_log, make_engagement)


def det_phrase(cluster) -> str:
    """Deterministic composer (template): top genres + top keywords. Genre intent lives in the phrase."""
    gs = [g for g, _ in cluster.top_genres[:3]]
    ks = [k for k, _ in cluster.top_keywords[:6]]
    return (", ".join(gs) + " — " + ", ".join(ks)).strip(" —")


def blended_phrase(clusters) -> str:
    gs, ks = [], []
    for c in clusters:
        gs += [g for g, _ in c.top_genres[:2]]
        ks += [k for k, _ in c.top_keywords[:3]]
    seen = set()
    gs = [g for g in gs if not (g in seen or seen.add(g))]
    seen = set()
    ks = [k for k in ks if not (k in seen or seen.add(k))]
    return ", ".join(gs) + " — " + ", ".join(ks)


def llm_phrase(vertical, cluster):
    """Reuse Endpoint 1's LLM seam (agent_recs/src/llm.py) to turn the SAME attributes into a sentence."""
    if str(ROOT / "agent_recs" / "src") not in sys.path:
        sys.path.append(str(ROOT / "agent_recs" / "src"))
    import llm as agent_llm
    gs = [g for g, _ in cluster.top_genres[:3]]
    ks = [k for k, _ in cluster.top_keywords[:6]]
    system = ("You write ONE short natural search phrase (<=18 words, no preamble, no quotes) describing "
              f"the kind of {vertical} a person enjoys, given genres and keywords. Output only the phrase.")
    user = f"genres: {', '.join(gs)}\nkeywords: {', '.join(ks)}"
    return agent_llm.llm_complete(system, user, json_mode=False, max_tokens=50).strip().strip('"')


def retrieve(client, phrase, vertical, k=15):
    t0 = time.time()
    res = client.vector_retrieve(phrase, vertical=vertical, top_k=k)
    return res, (time.time() - t0)


def names(res, n=12):
    return [f"{r['name']}" for r in res[:n]]


def build_cross_vertical(ds, now):
    def pick(vert, genre, n, exclude=()):
        out = []
        for e in ds.get_entities_by_vertical(vert):
            if e.entity_id in exclude:
                continue
            if genre in e.canonical_genres and e.bm25_keywords and ds.entity_id_to_property_id(e.entity_id):
                out.append(e.entity_id)
                if len(out) >= n:
                    break
        return out
    older = now - timedelta(days=45)
    recent = now - timedelta(days=2)
    comedy = pick("movie", "Comedy", 3) + pick("tv", "Comedy", 2)
    horror = pick("movie", "Horror", 3, exclude=set(comedy)) + pick("tv", "Horror", 2)
    log = ([make_engagement(e, SIGNAL_FOLLOW, older, now) for e in comedy] +
           [make_engagement(e, SIGNAL_FOLLOW, recent, now) for e in horror])
    return build_taste_profile_from_log(log, ds, now, user_id=900001, resolution_stats={"synthetic": len(log)})


def main():
    ds = CsvDataSource().load()
    now = timeutil.now()
    client = SubstrateClient()
    if not client.is_up():
        print("SUBSTRATE DOWN (:8000/:8010) — start per shared/README, then re-run.")
        return 2

    p12305 = build_taste_profile(12305, now, ds)
    pcv = build_cross_vertical(ds, now)

    print("="*96)
    print("PROBE 1 — per-cluster composed phrase → /api/retrieve (vertical-filtered)")
    print("="*96)
    for tag, prof, picks in [("12305", p12305, p12305.clusters[:2]),
                             ("cross-vertical", pcv, pcv.clusters[:2])]:
        for c in picks:
            ph = det_phrase(c)
            res, dt = retrieve(client, ph, c.dominant_vertical)
            print(f"\n[{tag}] cluster «{c.label}» (vertical={c.dominant_vertical}, share={c.cluster_share})")
            print(f'   phrase: "{ph}"')
            print(f"   {len(res)} hits in {dt*1000:.0f}ms, score[{res[0]['score']:.3f}..{res[-1]['score']:.3f}]:")
            print(f"   {names(res)}")

    print("\n" + "="*96)
    print("PROBE 2 — ONE-vs-MANY (cross-vertical user): per-cluster phrases vs ONE blended phrase")
    print("="*96)
    for c in pcv.clusters:
        ph = det_phrase(c)
        res, _ = retrieve(client, ph, c.dominant_vertical)
        print(f"\n  PER-CLUSTER «{c.label}» (vertical={c.dominant_vertical}): \"{ph}\"")
        print(f"     {names(res, 8)}")
    bph = blended_phrase(pcv.clusters)
    for vert in {c.dominant_vertical for c in pcv.clusters}:
        res, _ = retrieve(client, bph, vert)
        print(f"\n  BLENDED (vertical={vert}): \"{bph}\"")
        print(f"     {names(res, 8)}")

    print("\n" + "="*96)
    print("PROBE 3 — DETERMINISTIC vs LLM phrase (one cluster)")
    print("="*96)
    c = pcv.clusters[0]
    dph = det_phrase(c)
    dres, _ = retrieve(client, dph, c.dominant_vertical)
    print(f"\n  cluster «{c.label}» (vertical={c.dominant_vertical})")
    print(f'  DETERMINISTIC: "{dph}"')
    print(f"     {names(dres, 10)}")
    try:
        lph = llm_phrase(c.dominant_vertical, c)
        lres, _ = retrieve(client, lph, c.dominant_vertical)
        overlap = len({r['entity_id'] for r in dres} & {r['entity_id'] for r in lres})
        print(f'  LLM:           "{lph}"')
        print(f"     {names(lres, 10)}")
        print(f"  → overlap of top-15 sets: {overlap}/15")
    except Exception as e:
        print(f"  LLM phrase unavailable ({type(e).__name__}: {str(e)[:120]}) — would fall back to deterministic.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
