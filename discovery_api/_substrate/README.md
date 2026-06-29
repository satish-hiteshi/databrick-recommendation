# _substrate — vendored copy of E1's collapsed engines (DO NOT EDIT HERE)

This is a self-contained copy of the E1 (parrot) vector/graph substrate that Endpoint 2 (discovery)
runs its feed on top of, so discovery deploys **independently** (no reach into `databricks_deploy/`).

Source of truth is E1's `databricks_deploy/`:
  serving/{inprocess_engines,inmemory_store,timing,otel_setup}.py · vector_search/vs_store.py ·
  engines/{router_src, vector/pipeline, graph_src}/*.py

When E1's substrate changes, re-vendor this folder (copy the same set) and re-register E2.
