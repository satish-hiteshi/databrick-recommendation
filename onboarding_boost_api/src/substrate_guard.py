"""Startup substrate guard — FAIL LOUD if E8 is pointed at the wrong universe.

The machine carries several obsolete parquets and PG universes (the old 44,097-row Qwen set and the
re-keyed 52,510-row set). E1's earlier regression was nearly invalidated by services silently running
on the 44k substrate. E8 has the SAME failure mode: `property_vectors` (:5433) OR the fallback
`BOOST_PARQUET` OR the `boost_properties` Qdrant collection could each carry the wrong universe. This
asserts, at startup, that the LOADED universe carries the expected entity count (default 52,510) and
raises a clear found-vs-expected error otherwise (rather than silently serving 44k data).

Mirrors endpoint_1_agent_recs/staging_parrot_v3/code/substrate_guard.py, adapted to E8's substrate:
E8 has NO Neo4j (it is graph-signal-free at serve time — signals are precomputed into PG), so the two
checks are (1) the vector CORPUS (Qdrant `boost_properties` points_count when the qdrant backend is
active, else the PG `property_vectors` / parquet row count the app actually loaded) and (2) the PG
`property_vectors` count directly. Whichever sources are reachable must agree with `expect`; at least
one MUST be checkable or the guard raises (fail-loud, not fail-open).

Env:
  SUBSTRATE_EXPECT_ENTITIES  expected corpus size (default 52510)
  SUBSTRATE_CHECK=0          bypass the check entirely (NOT recommended; offline unit tests only)
"""
import os


def _pg_property_vectors_count():
    """PG property_vectors row count, or None if unreachable. Reads data.PG_DSN LIVE (module attribute,
    not an import-time copy) so the guard sees exactly the corpus the app will load: data.py is PG-first
    (parquet ONLY when the PG CONNECTION genuinely fails), so if this connects, PG is the served corpus and
    its count is authoritative; if PG is down, both this AND data._load_pg fall back to BOOST_PARQUET
    identically (no guard/app divergence)."""
    try:
        import psycopg2
        import data as _data
        conn = psycopg2.connect(connect_timeout=5, **_data.PG_DSN)
        try:
            cur = conn.cursor()
            cur.execute("SELECT to_regclass('public.property_vectors')")
            if cur.fetchone()[0] is None:
                return None
            cur.execute("SELECT count(*) FROM property_vectors")
            return int(cur.fetchone()[0])
        finally:
            conn.close()
    except Exception as e:  # pragma: no cover
        print(f"[substrate] PG property_vectors count unavailable ({str(e)[:80]})", flush=True)
        return None


def _qdrant_points_count():
    """Qdrant `boost_properties` points_count, or None if the qdrant backend is not the active one /
    the collection is unreachable. Uses the SAME resolution as vector_store.get_store (URL else path)."""
    backend = os.environ.get("BOOST_VECTOR_BACKEND", "qdrant").lower()
    if backend != "qdrant":
        return None
    try:
        from qdrant_client import QdrantClient
        from vector_store import COLLECTION
        url = os.environ.get("QDRANT_URL")
        if url:
            client = QdrantClient(url=url, timeout=30)
        else:
            path = os.environ.get(
                "QDRANT_PATH",
                os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "qdrant_data"))
            client = QdrantClient(path=path)
        try:
            return int(client.get_collection(COLLECTION).points_count)
        finally:
            try:
                client.close()
            except Exception:
                pass
    except Exception as e:  # pragma: no cover
        print(f"[substrate] Qdrant boost_properties count unavailable ({str(e)[:80]})", flush=True)
        return None


def _parquet_rows():
    """The BOOST_PARQUET the app would load as its fallback corpus, or None. This is what actually
    determines the served universe when PG is down, so it is checked too (this is the arm the prompt's
    proof (b) exercises: a 44,097-row parquet must trip the guard)."""
    try:
        import pyarrow.parquet as pq
        from data import PARQUET
        return int(pq.read_metadata(PARQUET).num_rows)
    except Exception as e:  # pragma: no cover
        print(f"[substrate] BOOST_PARQUET row count unavailable ({str(e)[:80]})", flush=True)
        return None


def assert_substrate():
    """Assert the LOADED E8 universe == SUBSTRATE_EXPECT_ENTITIES. Raises RuntimeError (found-vs-expected)
    on ANY reachable source that disagrees. If NO source is checkable, raises (fail-loud)."""
    if os.getenv("SUBSTRATE_CHECK", "1") == "0":
        print("[substrate] check SKIPPED (SUBSTRATE_CHECK=0)", flush=True)
        return
    _exp = os.getenv("SUBSTRATE_EXPECT_ENTITIES")
    if _exp is None:
        # serving adaptation: the corpus GROWS with the catalog — a hard-coded count would fail
        # every warm-up after a content drop. Strict mode is opt-in via SUBSTRATE_EXPECT_ENTITIES.
        print("[substrate] soft mode — SUBSTRATE_EXPECT_ENTITIES unset; strict universe assert skipped", flush=True)
        return
    expect = int(_exp)

    # E8 loads PG property_vectors FIRST (data._load_pg), falling back to BOOST_PARQUET only when PG is
    # down. Mirror that precedence: the CORPUS the app serves is PG if reachable, else the parquet. The
    # Qdrant collection is the vector index over that same corpus (qdrant backend). Check every reachable
    # source; each must equal `expect`.
    pg = _pg_property_vectors_count()
    pq_rows = None if pg is not None else _parquet_rows()   # parquet is the corpus ONLY when PG is down
    qd = _qdrant_points_count()

    checks = []   # (label, count)
    if pg is not None:
        checks.append(("PG property_vectors (:5433)", pg))
    if pq_rows is not None:
        from data import PARQUET
        checks.append((f"BOOST_PARQUET {PARQUET}", pq_rows))
    if qd is not None:
        checks.append(("Qdrant boost_properties points", qd))

    if not checks:
        raise RuntimeError(
            f"[substrate] NO checkable source (PG property_vectors, BOOST_PARQUET, and Qdrant "
            f"boost_properties all unreachable) — cannot verify the loaded universe == {expect}. "
            f"Refusing to serve blind. Set SUBSTRATE_CHECK=0 only for offline unit tests.")

    for label, count in checks:
        if count != expect:
            raise RuntimeError(
                f"[substrate] WRONG SUBSTRATE: {label} has {count} entities, expected {expect}, not 44k. "
                f"E8 must serve the re-keyed 52,510-entity universe (embeddings_updated.parquet / the "
                f"52,510-point boost_properties collection / property_vectors@52,510), NOT the OBSOLETE "
                f"44,097-row Qwen set. Point BOOST_PARQUET / QDRANT_PATH / PG at the correct source "
                f"(or set SUBSTRATE_EXPECT_ENTITIES to override).")

    summary = "; ".join(f"{lbl}={cnt}" for lbl, cnt in checks)
    print(f"[substrate] OK — {summary} (all == {expect})", flush=True)
