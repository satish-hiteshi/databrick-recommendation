"""Offline proof of the Postgres-free resolver — runs against the REAL data_v2 files, no DB needed.

    python databricks_deploy/serving/test_inmemory_store.py
"""

import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))                        # databricks_deploy/serving
sys.path.insert(0, os.path.join(os.path.dirname(_HERE), "engines", "vector"))  # vendored: make `pipeline` importable
sys.path.insert(0, _HERE)

import inmemory_store as S
from pipeline.config import EMBEDDING_DIMENSION


def main():
    # exact (case-insensitive)
    r = S.resolve_entity("Elden Ring Nightreign")
    assert r and r["match_type"] == "exact", r
    assert r["embedding"] is not None and len(r["embedding"]) == EMBEDDING_DIMENSION
    assert r["entity_id"] and r["vertical"], r
    print(f"ok  exact      → {r['name']} ({r['vertical']}) emb_dim={len(r['embedding'])} kw={len(r['bm25_keywords'])}")

    # case-insensitive exact
    r2 = S.resolve_entity("elden ring nightreign")
    assert r2 and r2["entity_id"] == r["entity_id"], "case-insensitive exact must match"
    print(f"ok  caseless   → same id ({r2['match_type']})")

    # contains / prefix (partial name)
    r3 = S.resolve_entity("Doom")
    assert r3 and r3["match_type"] in ("exact", "prefix", "contains"), r3
    print(f"ok  partial    → 'Doom' resolved to {r3['name']} [{r3['match_type']}]")

    # miss
    assert S.resolve_entity("zzzzz no such title zzzzz") is None
    assert S.resolve_entity("") is None
    print("ok  miss/empty → None")

    # batch fetch returns the same stored vectors
    ids = [r["entity_id"], r3["entity_id"]]
    b = S.batch_fetch_entities(ids)
    assert set(b) == set(ids), b.keys()
    assert all(b[i]["embedding"] is not None and len(b[i]["embedding"]) == EMBEDDING_DIMENSION for i in ids)
    assert all("composed_text" in b[i] for i in ids)
    print(f"ok  batch      → {len(b)} entities, vectors + composed_text present")

    print("\nALL PASS — Postgres-free resolver verified against real data_v2.")


if __name__ == "__main__":
    main()
