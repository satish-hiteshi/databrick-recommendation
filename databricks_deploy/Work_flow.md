```text
USER: "recommend me a co-op game, not too competitive"
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. REQUEST ARRIVES at the endpoint (parrot-api-hitashi-dev)  │
│ Comes in the fixed "Parrot" message format                   │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. parrot_adapter.py — UNPACK                                │
│ Translates the incoming message into what the                │
│ router understands.                                          │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. LLM UNDERSTANDS (Llama 70B on Databricks)                 │
│ "co-op game, not competitive" →                              │
│ intent: {vertical: game, feature: co-op,                     │
│ avoid: competitive}                                          │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. ASSEMBLER PLANS (assembler.py)                            │
│ Picks the strategy: which engine "establishes"               │
│ the candidate list, which ones "refine" it.                  │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. ESTABLISH — build the big candidate list                  │
│ ┌──────────────┐         ┌──────────────┐                    │
│ │ Vector Search│         │ Neo4j Graph  │                    │
│ │ (similar     │         │ (related     │                    │
│ │  meaning)    │         │  items)      │                    │
│ └──────────────┘         └──────────────┘                    │
│ (Voyage turns the query into numbers first)                  │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 6. REFINE — reorder that list                                │
│ • Graph re-rank (boost well-connected items)                 │
│ • Negation (drop "competitive" ones)                         │
│ • Semantic re-rank                                            │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. parrot_adapter.py — PACK                                  │
│ Wraps results back into the Parrot format.                   │
│ • labels everything entity_type = "property"                 │
│ • interleaves verticals (game/movie/tv/podcast)              │
└─────────────────────────────────────────────────────────────┘
                               │
                               ▼
USER gets a ranked list of recommendations
```

## The same flow in one sentence each

1. Request comes in → in the fixed Parrot format.

2. Adapter unpacks it → parrot_adapter.py translates to the router's language.

3. LLM reads it → turns plain English into structured intent.

4. Assembler plans → decides which engine builds the list and which ones reorder it.

5. Establish → Vector Search (similar) or Graph (related) builds the candidate universe.

6. Refine → re-rank, drop unwanted items, reorder within that universe.

7. Adapter packs it → wraps results back into Parrot format and sends them out.

## Two things that make it special

1. It's all in ONE container. Steps 3–6 used to be separate web servers calling each other. Now they're just function calls inside the same box (inprocess_engines.py does that). Faster and simpler.

2. The 57k items live in memory. Loaded from one parquet file at startup (inmemory_store.py), so no database server is needed while running.
