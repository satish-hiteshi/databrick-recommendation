"""Regenerate the in-memory embeddings parquet from the (Qwen) corpus vectors.

The collapsed serving bundle loads `embeddings_qwen_57k.parquet` into memory
(databricks_deploy/serving/inmemory_store.py) to power score_set / neighbors / BM25 / entity
resolution. That parquet must be rebuilt whenever the embedding model changes — these vectors and the
Vector Search index vectors come from the SAME model, so they stay comparable.

Run AFTER `generate_embeddings()` has written the new embeddings_v2.npy to the SRC volume, and pair it
with `build_index.py` (which rebuilds the Delta table + Vector Search index from the same npy).

    python build_parquet.py        # writes <SRC_VOLUME>/embeddings_qwen_57k.parquet

Reuses build_index._merge_records() so the row set + embedding column are identical to the index.
"""
import os

import pyarrow as pa
import pyarrow.parquet as pq

from build_index import SRC, _merge_records

OUT_NAME = os.getenv("EMBEDDINGS_PARQUET_NAME", "embeddings_qwen_57k.parquet")
OUT_PATH = os.getenv("EMBEDDINGS_PARQUET_OUT", os.path.join(SRC, OUT_NAME))


def main():
    records = _merge_records()
    print(f"Merged {len(records)} records; writing {OUT_PATH} …")

    # inmemory_store reads exactly these columns (columns=[entity_id, name, vertical, embedding,
    # bm25_keywords]); keep the schema to that set so the loader's zero-copy reshape stays valid.
    cols = {
        "entity_id": [r["entity_id"] for r in records],
        "name": [r["name"] for r in records],
        "vertical": [r["vertical"] for r in records],
        "bm25_keywords": [r.get("bm25_keywords") or [] for r in records],
        "embedding": [r["embedding"] for r in records],   # list[float], fixed 1024-dim
    }
    table = pa.table(cols)
    pq.write_table(table, OUT_PATH)
    print(f"Wrote {OUT_PATH} ({table.num_rows} rows, {len(records[0]['embedding'])}-dim embeddings).")
    print("Next: upload this parquet to the Volume and point EMBEDDINGS_PARQUET_SRC at it for register.py.")


if __name__ == "__main__":
    main()
