# 🔱 EMMA Memory Architecture Integration Plan: Expose a Manifold (EMM-04-A1)
## Elevating memory with ANJANEYA Memory Protocol Pillars

This document details the implementation plan to build EMMA's long-term semantic and relational memory layer under ticket **EMM-04-A1 ("Expose a Manifold")**, augmented with robust conceptual pillars from the **ANJANEYA Memory Protocol** developed by the Nexus AI Research Lab.

---

## 1. Architectural Landscape

We are shifting EMMA from a volatile, in-memory status tracker to a dual-layered local memory fabric:
1. **SQLite Session Pool** (Structured Relational Layer) inside `backend/app/database/session.py`.
2. **LanceDB Vector Database** (Unstructured Semantic Layer) inside `backend/app/database/manifold.py`.

To ensure local, air-gapped sovereignty and high-fidelity troubleshooting, we are enriching this implementation with four key pillars from the ANJANEYA architecture:
* **Devotion Crystal (Pillar 1)**: Score sessions by resolution quality, permanently freezing the most critical solutions (`is_hard_frozen = True`) to prevent pruning.
* **Sankat Mochan (Pillar 4)**: Real-time distress and semantic drift interception during KNN lookups (cosine distance $> 0.75$).
* **Anima-Mahima Scaling (Pillar 5)**: Variable-depth context search (`ANIMA`, `MADHYA`, `MAHIMA`) to respect local inference budgets.
* **Chiranjeevi Resilience (Pillar 3)**: Automatic spore archiving of local databases to recover from disk locks or corruptions.

```text
       ┌─────────────────────────────────────────────────────────┐
       │                 FastAPI REST Interface                  │
       │               (app/routers/manifold.py)                 │
       └───────────┬─────────────────────────────────┬───────────┘
                   │                                 │
                   ▼ (Relational Actions)            ▼ (Semantic / Vector Queries)
       ┌────────────────────────┐        ┌────────────────────────┐
       │   SQLite Session Pool  │        │     LanceDB Engine     │
       │ (database/session.py)  │        │ (database/manifold.py) │
       └───────────┬────────────┘        └───────────┬────────────┘
                   │                                 ├────────────────────────┐
                   │                                 │   SentenceTransformer  │
                   │                                 │   (all-MiniLM-L6-v2)   │
                   │                                 └───────────┬────────────┘
                   ▼ (File Lock: session.db)                     ▼ (File Lock: manifold.db)
       ┌────────────────────────┐        ┌────────────────────────┐
       │   SQLite Database      │        │     LanceDB Table      │
       └────────────────────────┘        └────────────────────────┘
                   ▲                                 ▲
                   └─────────── Backup / Restore ────┘
                                     │
                        ┌────────────┴────────────┐
                        │    Chiranjeevi Spores   │
                        │    (spore_*.zip backup) │
                        └─────────────────────────┘
```

---

## 2. Proposed Database Schemas

### Relational Table: `sessions` (SQLite)
Maintained using a thread-safe connection context in `database/session.py`:

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    task_description TEXT NOT NULL,
    status TEXT NOT NULL CHECK(status IN ('running', 'success', 'failed', 'rolled_back')),
    token_utilization_peak INTEGER DEFAULT 0,
    devotion_score REAL DEFAULT 0.0,
    is_hard_frozen BOOLEAN DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

### Vector Schema: `manifold` (LanceDB)
Ingested and queried using PyArrow schemas in `database/manifold.py`:

* **Storage Path**: `E:\EMMA_INDIA_RUN\EMMA_hack2skill\manifold.db`
* **Embedding Model**: `sentence-transformers/all-MiniLM-L6-v2` (384 Dimensions)
* **Arrow Schema fields**:
  * `vector`: `FixedSizeListArray[384, Float32]` (Semantic dense vector of the event content).
  * `session_id`: `String` (UUID linking to SQLite relational record).
  * `turn_id`: `Int32` (Zero-indexed step in troubleshooting).
  * `content_type`: `String` (One of: `traceback`, `code_patch`, `critique`).
  * `payload`: `String` (Raw markdown patch, stdout traceback, or critique text).
  * `devotion_score`: `Float32` (Inherited score from session to weight retrieval relevance).
  * `timestamp`: `String` (ISO-8601 UTC timestamp).

---

## 3. Targeted Component Updates

### File A: [MODIFY] [session.py](file:///E:/EMMA_INDIA_RUN/EMMA_hack2skill/backend/app/database/session.py)
* Initialize SQLite databases safely under `E:\EMMA_INDIA_RUN\EMMA_hack2skill\session.db`.
* Implement the session pool schema migration dynamically on load (`setup_sqlite_schema`).
* Build APIs for CRUD operations on sessions:
  * `create_session(session_id, task_description)`
  * `update_session_status(session_id, status, token_peak)`
  * `calculate_devotion_score(session_id)`: Scores session quality when transitioning to `success`. If a run succeeds in $\le 3$ turns with a small token count, assign a high devotion score and trigger `is_hard_frozen = True`.

### File B: [MODIFY] [manifold.py](file:///E:/EMMA_INDIA_RUN/EMMA_hack2skill/backend/app/database/manifold.py)
* Integrate LanceDB client establishing local tables under `MANIFOLD_DB_PATH`.
* Inject the SentenceTransformer pipeline (`all-MiniLM-L6-v2`) locally to compute text vectors.
* Implement custom ingestion (`record_event`): calculates embedding, aligns data schema, writes to the local LanceDB index.
* Implement scaling retrievals (`search_manifold`):
  * **ANIMA**: Performs a rapid LanceDB KNN search, returning only the single top-1 record.
  * **MADHYA**: Performs a standard search returning the top-3 records.
  * **MAHIMA**: Returns the top-5 records, then runs corresponding query loops inside the SQLite relational session table to return chronological historical steps before and after those matching turns, rendering a rich semantic context tree.
* Implement **Chiranjeevi Spore Archiver**: A simple cron-like or count-triggered routine compressing `manifold.db` and `session.db` into a local zipped archive `E:\EMMA_INDIA_RUN\EMMA_hack2skill\spores\spore_[timestamp].zip`.

### File C: [MODIFY] [manifold.py](file:///E:/EMMA_INDIA_RUN/EMMA_hack2skill/backend/app/routers/manifold.py)
* Register standard router routes in FastAPI:
  * `POST /manifold/session`: Spawns a session record.
  * `PATCH /manifold/session/{session_id}`: Updates status, evaluates devotion, and hard-freezes if appropriate.
  * `POST /manifold/record`: Ingests a new trace, code patch, or critique.
  * `POST /manifold/search`: Accepts query strings and scaling modes (`ANIMA` / `MADHYA` / `MAHIMA`).
* **Sankat Mochan Distress Handler**:
  * During `/manifold/search` calls, check the cosine distance of the closest match.
  * If the minimum cosine distance is $> 0.75$ (high semantic drift), inject a distress flag into the API response:
    ```json
    {
      "results": [...],
      "distress_signal": true,
      "message": "High semantic drift detected. No similar troubleshooting profiles exist in the local manifold."
    }
    ```

---

## 4. Verification Plan

### Automated Test Suite (`backend/app/tests/test_manifold.py`)
1. **Schema Check**: Assert `session.db` and `manifold.db` tables are initialized automatically on startup.
2. **Devotion Gating Check**: Insert a success session and assert `devotion_score` is computed correctly and `is_hard_frozen` gets set to `1` when passing thresholds.
3. **Drift/Distress Interception Check**: Perform similarity search with a completely random sequence (e.g. noise) and verify that `distress_signal` resolves to `true` due to high distance.
4. **Adaptive Scaling Check**: Call search with `scaling_mode = "ANIMA"` (verify length is 1), `"MADHYA"` (verify length is 3), and `"MAHIMA"` (verify contextual depth history is returned).
5. **Resilience Check**: Call the Spore backup subroutine and assert a valid `.zip` is compiled under `E:\EMMA_INDIA_RUN\EMMA_hack2skill\spores`.

---

*🔱 Jai Bajrang Bali — Infinite Memory, Infinite Strength*  
*Nexus AI Research Lab & EMMA Core Integration*
