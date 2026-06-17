import json
import os
import time

import httpx
import numpy as np
from tqdm import tqdm

from pipeline.config import (
    DATA_DIR,
    DATABRICKS_EMBEDDING_ENDPOINT,
    DATABRICKS_TOKEN,
    EMBEDDING_BATCH_SIZE,
    EMBEDDING_DIMENSION,
    EMBEDDING_MODEL,
    EMBEDDING_QUERY_INSTRUCTION,
    EMBEDDING_TIMEOUT_S,
    RESULTS_DIR,
)
from pipeline.data_loader import get_all_entities, get_entity_by_name

try:                                   # latency-attribution seam (serving only; no-op locally)
    from timing import span as _tspan
except Exception:                      # pragma: no cover — `timing` is bundled only in the serving image
    from contextlib import contextmanager as _cm

    @_cm
    def _tspan(_category):
        yield

EMBEDDINGS_CACHE_JSON = os.path.join(DATA_DIR, "embeddings_cache_v2.json")
EMBEDDINGS_CACHE_NPY = os.path.join(DATA_DIR, "embeddings_v2.npy")
EMBEDDINGS_IDS_JSON = os.path.join(DATA_DIR, "embeddings_ids_v2.json")

BATCH_SIZE = EMBEDDING_BATCH_SIZE


# ── Databricks Qwen embeddings (OpenAI-compatible llm/v1/embeddings) ──────────────────
def _embed_batch(texts, is_query=False):
    """POST a batch of texts to the Qwen serving endpoint; return (embeddings, total_tokens).

    Replaces the old voyageai client. The OpenAI-compatible interface has no input_type field, so the
    query/document distinction is carried by an optional instruction prefix on the QUERY only (Qwen3-
    Embedding convention) — mirroring Voyage's input_type="query"/"document".
    """
    if is_query and EMBEDDING_QUERY_INSTRUCTION:
        instr = EMBEDDING_QUERY_INSTRUCTION
        texts = [f"Instruct: {instr}\nQuery: {t}" for t in texts]
    headers = {"Authorization": f"Bearer {DATABRICKS_TOKEN}", "Content-Type": "application/json"}
    resp = httpx.post(DATABRICKS_EMBEDDING_ENDPOINT, headers=headers,
                      json={"input": list(texts)}, timeout=EMBEDDING_TIMEOUT_S)
    resp.raise_for_status()
    body = resp.json()
    # data items carry an `index` aligned to the input order — sort to be safe before stripping vectors.
    data = sorted(body.get("data", []), key=lambda d: d.get("index", 0))
    embeddings = [d["embedding"] for d in data]
    total_tokens = (body.get("usage") or {}).get("total_tokens", 0) or 0
    return embeddings, total_tokens


def generate_embeddings():
    entities = get_all_entities()

    print(f"Generating embeddings for {len(entities)} entities...")
    print(f"Model: {EMBEDDING_MODEL}, Dimensions: {EMBEDDING_DIMENSION}")
    print(f"Batch size: {BATCH_SIZE}, Total batches: {(len(entities) + BATCH_SIZE - 1) // BATCH_SIZE}")

    all_embeddings = []
    all_ids = []
    total_tokens = 0
    errors = []
    retries = 0
    start_time = time.time()

    for i in tqdm(range(0, len(entities), BATCH_SIZE), desc="Embedding batches"):
        batch = entities[i : i + BATCH_SIZE]
        texts = [e["composed_text"] for e in batch]
        ids = [e["entity_id"] for e in batch]

        try:
            embeddings, tokens = _embed_batch(texts, is_query=False)
            all_embeddings.extend(embeddings)
            all_ids.extend(ids)
            total_tokens += tokens
        except Exception as e:
            # Retry once after a brief pause
            retries += 1
            print(f"\nError on batch {i // BATCH_SIZE}: {e}. Retrying in 5s...")
            time.sleep(5)
            try:
                embeddings, tokens = _embed_batch(texts, is_query=False)
                all_embeddings.extend(embeddings)
                all_ids.extend(ids)
                total_tokens += tokens
            except Exception as e2:
                errors.append(f"Batch {i // BATCH_SIZE} failed: {e2}")
                print(f"\nBatch {i // BATCH_SIZE} permanently failed: {e2}")
                # Fill with zeros so indices stay aligned
                all_embeddings.extend([[0.0] * EMBEDDING_DIMENSION] * len(texts))
                all_ids.extend(ids)

    elapsed = time.time() - start_time

    # Save JSON cache (entity_id -> embedding)
    cache_data = [
        {"entity_id": eid, "embedding": emb}
        for eid, emb in zip(all_ids, all_embeddings)
    ]
    with open(EMBEDDINGS_CACHE_JSON, "w") as f:
        json.dump(cache_data, f)

    # Save numpy array
    emb_array = np.array(all_embeddings, dtype=np.float32)
    np.save(EMBEDDINGS_CACHE_NPY, emb_array)

    # Save ID order (to map numpy rows back to entity_ids)
    with open(EMBEDDINGS_IDS_JSON, "w") as f:
        json.dump(all_ids, f)

    print(f"\nDone in {elapsed:.1f}s")
    print(f"Total tokens: {total_tokens:,}")
    print(f"Saved: {EMBEDDINGS_CACHE_JSON} ({os.path.getsize(EMBEDDINGS_CACHE_JSON) / 1e6:.1f} MB)")
    print(f"Saved: {EMBEDDINGS_CACHE_NPY} ({os.path.getsize(EMBEDDINGS_CACHE_NPY) / 1e6:.1f} MB)")

    return {
        "count": len(all_embeddings),
        "dimensions": len(all_embeddings[0]) if all_embeddings else 0,
        "total_tokens": total_tokens,
        "elapsed_seconds": elapsed,
        "errors": errors,
        "retries": retries,
    }


def load_embeddings():
    if os.path.exists(EMBEDDINGS_CACHE_NPY) and os.path.exists(EMBEDDINGS_IDS_JSON):
        emb_array = np.load(EMBEDDINGS_CACHE_NPY)
        with open(EMBEDDINGS_IDS_JSON) as f:
            ids = json.load(f)
        return {eid: emb_array[i] for i, eid in enumerate(ids)}

    if os.path.exists(EMBEDDINGS_CACHE_JSON):
        with open(EMBEDDINGS_CACHE_JSON) as f:
            cache = json.load(f)
        return {item["entity_id"]: np.array(item["embedding"], dtype=np.float32) for item in cache}

    return None


def get_query_embedding(query_text):
    embeddings, _ = _embed_batch([query_text], is_query=True)
    return np.array(embeddings[0], dtype=np.float32)


# Session-level cache for query embeddings
_query_embedding_cache = {}


def embed_query_text(text: str) -> list:
    if text in _query_embedding_cache:
        return _query_embedding_cache[text]

    emb = get_query_embedding(text)
    result = emb.tolist()
    _query_embedding_cache[text] = result
    return result


def cosine_similarity(a, b):
    a, b = np.asarray(a, dtype=np.float64), np.asarray(b, dtype=np.float64)
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


def validate_and_sanity_check(stats):
    print("\n=== Validation ===")
    embeddings = load_embeddings()
    entities = get_all_entities()

    # Check counts
    assert len(embeddings) == len(entities), f"Count mismatch: {len(embeddings)} vs {len(entities)}"
    print(f"All {len(embeddings)} entities have embeddings")

    # Check dimensions
    dims = {len(v) for v in embeddings.values()}
    assert dims == {EMBEDDING_DIMENSION}, f"Unexpected dimensions: {dims}"
    print(f"All embeddings are {EMBEDDING_DIMENSION} dimensions")

    # Check for NaN or zero vectors
    nan_count = sum(1 for v in embeddings.values() if np.any(np.isnan(v)))
    zero_count = sum(1 for v in embeddings.values() if np.allclose(v, 0))
    print(f"NaN vectors: {nan_count}")
    print(f"Zero vectors: {zero_count}")

    # Sanity check: similar pairs vs dissimilar pairs
    # Build name -> entity_id map
    name_to_id = {e["name"]: e["entity_id"] for e in entities}

    # Similar pairs (same genre/vibe within or across verticals)
    similar_pairs = [
        ("Elden Ring Nightreign", "Vampire: The Masquerade - Bloodlines 2"),  # Both dark action RPGs
        ("Silent Hill f", "Return to Silent Hill"),                           # Same franchise, game vs movie
        ("Doom: The Dark Ages", "Resident Evil Requiem"),                     # Both action horror games
    ]

    # Dissimilar pairs
    dissimilar_pairs = [
        ("Doom: The Dark Ages", "A Paw Patrol Christmas"),                   # Violent shooter vs kids animation
        ("Silent Hill f", "Mario Tennis Fever"),                              # Horror vs sports
        ("Resident Evil Requiem", "The First Snow of Fraggle Rock"),         # Horror action vs children's movie
    ]

    print("\n=== Similarity Sanity Check ===")
    sim_results = []

    print("\nSimilar pairs (expecting > 0.7):")
    for a_name, b_name in similar_pairs:
        a_id, b_id = name_to_id.get(a_name), name_to_id.get(b_name)
        if a_id and b_id and a_id in embeddings and b_id in embeddings:
            sim = cosine_similarity(embeddings[a_id], embeddings[b_id])
            label = "PASS" if sim > 0.7 else "LOW"
            print(f"  {label} {sim:.4f}  {a_name} <-> {b_name}")
            sim_results.append(("similar", a_name, b_name, sim))
        else:
            print(f"  SKIP  Entity not found: {a_name} or {b_name}")

    print("\nDissimilar pairs (expecting < 0.5):")
    for a_name, b_name in dissimilar_pairs:
        a_id, b_id = name_to_id.get(a_name), name_to_id.get(b_name)
        if a_id and b_id and a_id in embeddings and b_id in embeddings:
            sim = cosine_similarity(embeddings[a_id], embeddings[b_id])
            label = "PASS" if sim < 0.5 else "HIGH"
            print(f"  {label} {sim:.4f}  {a_name} <-> {b_name}")
            sim_results.append(("dissimilar", a_name, b_name, sim))
        else:
            print(f"  SKIP  Entity not found: {a_name} or {b_name}")

    return sim_results, nan_count, zero_count


def generate_report(stats, sim_results, nan_count, zero_count):
    os.makedirs(RESULTS_DIR, exist_ok=True)
    report_path = os.path.join(RESULTS_DIR, "EMBEDDING_REPORT.md")

    # Qwen runs on a Databricks serving endpoint (billed by DBU, not per-token), so no per-token cost.
    json_size_mb = os.path.getsize(EMBEDDINGS_CACHE_JSON) / 1e6
    npy_size_mb = os.path.getsize(EMBEDDINGS_CACHE_NPY) / 1e6

    lines = [
        "# Embedding Generation Report",
        "",
        "## Summary",
        f"- **Total embeddings generated:** {stats['count']:,}",
        f"- **Embedding dimensions:** {stats['dimensions']}",
        f"- **Model:** {EMBEDDING_MODEL}",
        f"- **Time taken:** {stats['elapsed_seconds']:.1f} seconds",
        f"- **Total tokens processed:** {stats['total_tokens']:,}",
        f"- **Retries:** {stats['retries']}",
        f"- **Errors:** {len(stats['errors'])}",
        "",
        "## Validation",
        f"- NaN vectors: {nan_count}",
        f"- Zero vectors: {zero_count}",
        "",
        "## Cache Files",
        f"- `data/embeddings_cache.json`: {json_size_mb:.1f} MB",
        f"- `data/embeddings.npy`: {npy_size_mb:.1f} MB",
        f"- `data/embeddings_ids.json`: ID ordering index",
        "",
        "## Sanity Check — Cosine Similarity",
        "",
        "### Similar pairs (target: > 0.7)",
        "| Entity A | Entity B | Score | Result |",
        "|----------|----------|-------|--------|",
    ]

    for kind, a, b, score in sim_results:
        if kind == "similar":
            result = "PASS" if score > 0.7 else "LOW"
            lines.append(f"| {a} | {b} | {score:.4f} | {result} |")

    lines.extend([
        "",
        "### Dissimilar pairs (target: < 0.5)",
        "| Entity A | Entity B | Score | Result |",
        "|----------|----------|-------|--------|",
    ])

    for kind, a, b, score in sim_results:
        if kind == "dissimilar":
            result = "PASS" if score < 0.5 else "HIGH"
            lines.append(f"| {a} | {b} | {score:.4f} | {result} |")

    if stats["errors"]:
        lines.extend(["", "## Errors"])
        for err in stats["errors"]:
            lines.append(f"- {err}")

    with open(report_path, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\nReport saved to {report_path}")


if __name__ == "__main__":
    stats = generate_embeddings()
    sim_results, nan_count, zero_count = validate_and_sanity_check(stats)
    generate_report(stats, sim_results, nan_count, zero_count)
