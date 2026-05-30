# 🔱 ANJANEYA Memory Protocol — FastAPI Router Implementation Plan (EMM-04-A1)

This document establishes the granular technical design for **Step 1: The FastAPI Router (`backend/app/routers/manifold.py`)**. This component serves as the core REST interface for EMMA's local relational and vector database systems, binding the five cognitive pillars of the **ANJANEYA Memory Protocol (AMP)** to high-frequency, thread-safe endpoints.

---

## 🗺️ Architectural Topology

The router acts as a stateless request coordinator, parsing incoming JSON schemas, enforcing data types, dispatching commands to the underlying connection pools, and returning mathematically enriched memory structures.

```text
               ┌────────────────────────────────────────────────────────┐
               │              FastAPI Client / Orchestrator             │
               └───────────┬──────────────┬──────────────┬──────────────┘
                           │              │              │
         POST /session ────┘              │              │
        PATCH /session/{id} ──────────────┘              │
         POST /record ───────────────────────────────────┘
         POST /search (GDI Alerts & Scaling) ────────────┐
         POST /spore & /restore (Persistence) ───────────┴──────────────┐
                                                                        ▼
                                                   ┌──────────────────────────┐
                                                   │   FastAPI Router Core    │
                                                   │ (app/routers/manifold.py)│
                                                   └────────────┬─────────────┘
                                           ┌────────────────────┴────────────────────┐
                                           ▼ (Relational APIs)                       ▼ (Vector APIs)
                               ┌─────────────────────────┐               ┌─────────────────────────┐
                               │   SQLite Session Pool   │               │     LanceDB Manifold    │
                               │  (app/database/session) │               │ (app/database/manifold) │
                               └─────────────────────────┘               └─────────────────────────┘
```

---

## 📦 Pydantic Request/Response Schemas

FastAPI will enforce static data validation and automatic documentation (OpenAPI 3.0) using the following model specifications:

### 1. `SessionCreate`
* **Purpose:** Initialise a tracking slot for a solver session.
* **Fields:**
  * `session_id` (`str`): UUID identifying the solver invocation. Required.
  * `task_description` (`str`): Descriptive natural-language prompt. Required.

### 2. `SessionUpdate`
* **Purpose:** Update status, calculate Devotion Score, and check hard-freeze threshold.
* **Fields:**
  * `status` (`str`): Execution state. Must be one of `['running', 'success', 'failed', 'rolled_back']`. Required.
  * `token_peak` (`int`): Maximum tokens consumed during execution. Minimum: `0`. Required.
  * `turns` (`Optional[int]`): Total turns consumed. Required only when `status = 'success'`.

### 3. `EventRecord`
* **Purpose:** Ingest structured traces, code patches, or criticism loops.
* **Fields:**
  * `session_id` (`str`): UUID linking to SQLite relational parent. Required.
  * `turn_id` (`int`): 0-indexed solver step. Minimum: `0`. Required.
  * `content_type` (`str`): Context type. Must be one of `['traceback', 'code_patch', 'critique']`. Required.
  * `payload` (`str`): Raw trace content or code string. Required.

### 4. `ManifoldSearch`
* **Purpose:** Query the semantic manifold with dynamic scale limits.
* **Fields:**
  * `query` (`str`): Query string (error logs or goal details). Required.
  * `scaling_mode` (`str`): Scaling depth. Must be one of `['ANIMA', 'MADHYA', 'MAHIMA']`. Defaults to `'MADHYA'`.

---

## 🛡️ Endpoint Design & Implementation Logic

### 1. `POST /manifold/session`
* **Behavior:** Invokes `db_session.create_session(session_id, task_description)`.
* **Error Handling:** Returns `500 Internal Server Error` if the SQLite write fails.
* **Response (201 Created):**
  ```json
  {
    "status": "success",
    "session_id": "99368448-47b9-4101-9162-416256ad4c11",
    "message": "Session initialized."
  }
  ```

### 2. `PATCH /manifold/session/{session_id}`
* **Behavior:**
  1. Validates status payload.
  2. Asserts session exists and `is_hard_frozen` is not active (toggled on prior success). If frozen, blocks the request and raises a `403 Forbidden` exception.
  3. Calls `db_session.update_session_status()`.
  4. If status is `'success'`, returns the calculated devotion score and tells the client whether a hard-freeze gate was triggered.
* **Response (200 OK):**
  ```json
  {
    "status": "success",
    "session_id": "99368448-47b9-4101-9162-416256ad4c11",
    "devotion_score": 0.924929,
    "is_hard_frozen": true,
    "message": "Devotion score evaluated. Session hard-frozen!"
  }
  ```

### 3. `POST /manifold/record`
* **Behavior:** Invokes `db_manifold.record_event()`, triggering background SentenceTransformer embedding, LanceDB vector storage, and SQLite text indexing.
* **Error Handling:** Returns `400 Bad_Request` for malformed content types; returns `500` if the Arrow vector table connection times out or breaks.
* **Response (201 Created):**
  ```json
  {
    "status": "success",
    "session_id": "99368448-47b9-4101-9162-416256ad4c11",
    "turn_id": 1,
    "message": "Event recorded and vector manifold populated."
  }
  ```

### 4. `POST /manifold/search`
* **Behavior:**
  1. Invokes `db_manifold.search_manifold(query, scaling_mode)`.
  2. Implements **Pillar 4 (Sankat Mochan) Interception**: Checks if minimum cosine distance $d_{\min} > 0.75$. If true, injects `distress_signal: true` and attaches the distress warning message.
* **Response (200 OK):**
  ```json
  {
    "results": [...],
    "distress_signal": true,
    "d_min": 0.7812,
    "scaling_mode": "MADHYA",
    "message": "High semantic drift detected. No similar troubleshooting profiles exist in the local manifold."
  }
  ```

### 5. `POST /manifold/spore` (Pillar 3 resilience trigger)
* **Behavior:** Triggers a manual zipped spore archive of both active SQLite and LanceDB files.
* **Response (200 OK):**
  ```json
  {
    "status": "success",
    "spore_file": "spore_20260530T203000Z.zip",
    "message": "Chiranjeevi Spore Archive successfully compiled."
  }
  ```

### 6. `POST /manifold/restore` (Pillar 3 disaster recovery trigger)
* **Behavior:** Triggers the 6-step deterministic self-healing recovery protocol.
* **Response (200 OK):**
  ```json
  {
    "status": "success",
    "message": "Chiranjeevi recovery completed. All active databases have been successfully restored and verified."
  }
  ```

---

## 🔬 Manual Verification & Diagnostics

Once written, the router functionality can be validated manually using curl commands or the FastAPI `/docs` Swagger UI interface:

```bash
# 1. Initialize session
curl -X POST "http://localhost:8000/manifold/session" \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test-uuid-1", "task_description": "OAuth 2.0 debugging"}'

# 2. Ingest trace event
curl -X POST "http://localhost:8000/manifold/record" \
     -H "Content-Type: application/json" \
     -d '{"session_id": "test-uuid-1", "turn_id": 0, "content_type": "traceback", "payload": "OperationalError: connection lost"}'

# 3. Query the manifold (MADHYA mode)
curl -X POST "http://localhost:8000/manifold/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "connection error", "scaling_mode": "MADHYA"}'
```

---

*🔱 Jai Bajrang Bali — Infinite Memory, Infinite Strength*  
*Nexus AI Research Lab & EMMA Core Integration Plan*
