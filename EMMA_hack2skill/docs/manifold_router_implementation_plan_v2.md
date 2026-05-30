# 🔱 ANJANEYA Memory Protocol — FastAPI Router Implementation Plan (EMM-04-A1)
## Enhanced Architectural Specification v2.0 — Production-Grade REST Interface Design

> *"The router is not a gateway. It is the nervous system — the membrane through which intent becomes memory."*

---

## Table of Contents

1. [Architectural Topology](#1-architectural-topology)
2. [Database Connection Lifecycle — Dependency Injection](#2-database-connection-lifecycle--dependency-injection)
3. [Pydantic Request/Response Schemas](#3-pydantic-requestresponse-schemas)
4. [HTTP Error Response Contract](#4-http-error-response-contract)
5. [GDI Alignment Matrix — Sankat Mochan Drift Table](#5-gdi-alignment-matrix--sankat-mochan-drift-table)
6. [Endpoint Design & Implementation Logic](#6-endpoint-design--implementation-logic)
7. [Modular Dynamic Skill Registry Layer](#7-modular-dynamic-skill-registry-layer)
8. [Manual Verification & Diagnostics](#8-manual-verification--diagnostics)

---

## 1. Architectural Topology

The router acts as a **stateless request coordinator** — it parses validated Pydantic schemas,
dispatches to the underlying WAL-mode SQLite pool and LanceDB vector engine, and returns
mathematically enriched ANJANEYA memory structures. It holds zero mutable state between requests.

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                     FastAPI Client / Orchestrator Loop                       │
└───────────┬───────────────┬─────────────────┬────────────────┬───────────────┘
            │               │                 │                │
  POST /session   PATCH /session/{id}  POST /record    POST /search
  POST /spore     POST /restore        POST /skills    POST /skills/search
            │               │                 │                │
            └───────────────┴─────────────────┴────────────────┘
                                      │
                         ┌────────────▼─────────────┐
                         │   FastAPI Router Core     │
                         │ app/routers/manifold.py   │
                         │                           │
                         │  [Pydantic Validation]    │
                         │  [DI: yield conn pool]    │
                         │  [WAL Checkpoint Teardown]│
                         └──────────┬────────────────┘
              ┌───────────────────  │  ──────────────────────────┐
              ▼ (Relational APIs)   │                            ▼ (Vector APIs)
  ┌───────────────────────────┐     │           ┌─────────────────────────────┐
  │   SQLite Session Pool     │     │           │      LanceDB Manifold       │
  │  app/database/session.py  │     │           │   app/database/manifold.py  │
  │                           │     │           │                             │
  │  [WAL Mode + Thread-Local]│     │           │  [Retry Lock Wrapper x5]    │
  │  [Devotion Crystal Score] │     │           │  [ANIMA/MADHYA/MAHIMA KNN]  │
  │  [Hard-Freeze Trigger]    │     │           │  [Sankat Mochan Gate]       │
  │  [Chiranjeevi Spore Hash] │     │           │  [Dronagiri Null-Guard]     │
  └───────────────────────────┘     │           └─────────────────────────────┘
                                    │
                         ┌──────────▼──────────────┐
                         │   Skills Registry        │
                         │   SQLite: skills table   │
                         │   LanceDB: skills_index  │
                         └─────────────────────────┘
```

---

## 2. Database Connection Lifecycle — Dependency Injection

### 2.1 The Windows NTFS Problem

FastAPI spawns multiple Uvicorn worker threads on Windows. SQLite's default
connection model — one handle per process — causes `OperationalError: database is locked`
under concurrent PATCH/POST load. LanceDB's Apache Arrow memory-mapped file access
compounds this: simultaneous write locks on `.lance` segment files cause
`OSError: [WinError 32] The process cannot access the file`.

**Solution:** FastAPI's `Depends(yield)` pattern enforces a **per-request, thread-isolated
connection lifecycle** with guaranteed WAL checkpoint teardown on every request boundary.

### 2.2 SQLite Connection Yield Dependency

```python
import sqlite3
from typing import Generator
from fastapi import Depends
from app.database.session import get_thread_local_conn, close_thread_local_conn

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    FastAPI dependency that yields a thread-local WAL-mode SQLite connection
    and guarantees cleanup on request teardown.

    Lifecycle:
      ACQUIRE  — get_thread_local_conn() returns the per-thread handle
                 (creates it with full PRAGMA stack if first access on this thread).
      YIELD    — connection is available to the endpoint handler.
      TEARDOWN — executed unconditionally after response is sent:
                 * Runs PRAGMA wal_checkpoint(PASSIVE) to merge WAL pages.
                 * Does NOT close the handle (reused across requests on same thread).
                 * Closes handle only on exception to recycle poisoned connections.
    """
    conn = get_thread_local_conn()
    try:
        yield conn
    except Exception:
        # Recycle connection on unhandled exception to prevent
        # corrupted transaction state persisting to next request.
        close_thread_local_conn()
        raise
    finally:
        # Passive checkpoint: flush committed WAL frames without blocking readers.
        try:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        except sqlite3.Error:
            pass

# Type alias for injection
DBConn = Annotated[sqlite3.Connection, Depends(get_db)]
```

### 2.3 LanceDB Table Yield Dependency

```python
from app.database.manifold import get_manifold_table

def get_manifold() -> Generator:
    """
    FastAPI dependency that yields a validated LanceDB table reference.
    Uses the retry-wrapped get_manifold_table() (5 attempts, exponential backoff)
    to absorb Windows Arrow file-map lock contention on concurrent POST /record calls.

    Does not hold the table reference open between requests — LanceDB handles
    its own internal connection pool.
    """
    try:
        table = get_manifold_table()
        yield table
    except RuntimeError as exc:
        raise HTTPException(
            status_code=503,
            detail={
                "error":   "MANIFOLD_UNAVAILABLE",
                "message": f"LanceDB table unreachable after retries: {exc}",
            }
        )

ManifoldTable = Annotated[Any, Depends(get_manifold)]
```

### 2.4 Application Lifespan — WAL TRUNCATE on Shutdown

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.database.session import checkpoint_wal, close_thread_local_conn

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    STARTUP:
      - Verifies SESSION_DB and MANIFOLD_DB paths are writable.
      - Confirms WAL journal mode is active (PRAGMA journal_mode = WAL).
      - Pre-warms the embedding model to eliminate cold-start latency
        on the first POST /manifold/record request.

    SHUTDOWN:
      - Executes PRAGMA wal_checkpoint(TRUNCATE) to flush the WAL file
        into the main DB, resetting WAL to zero length.
      - Closes thread-local SQLite handles on main thread.
      - Prevents orphaned .db-wal and .db-shm files on Windows NTFS.
    """
    # Startup
    from app.database.manifold import _get_embedding_model
    _get_embedding_model()                    # Pre-warm model
    yield
    # Shutdown
    checkpoint_wal()
    close_thread_local_conn()

app = FastAPI(lifespan=lifespan)
```

---

## 3. Pydantic Request/Response Schemas

All models use **Pydantic v2** with `model_validator`, `field_validator`,
and `Field(...)` constraints for strict data-contract enforcement and
automatic OpenAPI 3.0 documentation generation.

### 3.1 `SessionCreate`

```python
from pydantic import BaseModel, Field, field_validator
import uuid

class SessionCreate(BaseModel):
    """Initialise a new solver session tracking slot."""

    session_id: str = Field(
        ...,
        description="UUID v4 uniquely identifying this solver invocation.",
        examples=["99368448-47b9-4101-9162-416256ad4c11"],
    )
    task_description: str = Field(
        ...,
        min_length=5,
        max_length=2000,
        description="Natural-language description of the task being solved.",
    )

    @field_validator("session_id")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError(
                f"session_id must be a valid UUID v4 string. Received: '{v}'"
            )
        return v
```

### 3.2 `SessionUpdate`

```python
from pydantic import BaseModel, Field, model_validator
from typing import Literal, Optional

class SessionUpdate(BaseModel):
    """
    Update session execution state. Triggers Devotion Crystal scoring
    and hard-freeze gate evaluation when status transitions to 'success'.
    """

    status: Literal["running", "success", "failed", "rolled_back"] = Field(
        ...,
        description="Execution state. 'success' triggers Devotion Score computation.",
    )
    token_peak: int = Field(
        ...,
        ge=0,
        le=100_000,
        description="Peak token utilization observed during this session. "
                    "Bounded to [0, U_MAX=100000] per ANJANEYA §4.1.",
    )
    turns: Optional[int] = Field(
        None,
        ge=1,
        le=15,
        description="Solver turns consumed. Required when status='success'. "
                    "Bounded to [1, T_MAX=15] per ANJANEYA §4.1.",
    )

    @model_validator(mode="after")
    def check_turns_on_success(self) -> "SessionUpdate":
        if self.status == "success" and self.turns is None:
            raise ValueError(
                "Field 'turns' is mandatory when status is 'success'. "
                "It is required to compute the Devotion Crystal Score "
                "D = α·T_eff + β·U_eff (ANJANEYA Protocol §4.1)."
            )
        return self
```

### 3.3 `EventRecord`

```python
from pydantic import BaseModel, Field, field_validator
from typing import Literal

class EventRecord(BaseModel):
    """
    Ingest a structured solver trace event into the semantic manifold.
    Triggers SentenceTransformer embedding and LanceDB vector write.
    """

    session_id: str = Field(
        ...,
        description="UUID v4 of the owning session (FK → sessions.session_id).",
    )
    turn_id: int = Field(
        ...,
        ge=0,
        le=999,
        description="Zero-indexed solver turn number. Must be monotonically "
                    "increasing per session.",
    )
    content_type: Literal["traceback", "code_patch", "critique"] = Field(
        ...,
        description="Semantic classification of the event payload.",
    )
    payload: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Raw event content — stdout traceback, code patch, or critique text.",
    )

    @field_validator("session_id")
    @classmethod
    def validate_uuid_format(cls, v: str) -> str:
        import uuid
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError(f"session_id must be UUID v4. Received: '{v}'")
        return v

    @field_validator("payload")
    @classmethod
    def reject_empty_whitespace(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("payload must contain non-whitespace content.")
        return v
```

### 3.4 `ManifoldSearch`

```python
from pydantic import BaseModel, Field
from typing import Literal

class ManifoldSearch(BaseModel):
    """
    Semantic manifold query with Anima-Mahima depth scaling and
    Sankat Mochan cosine drift interception.
    """

    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural-language query string — error logs, goal descriptions, "
                    "or diagnostic keywords.",
        examples=["OAuth 2.0 connection refused", "SyntaxError in token exchange"],
    )
    scaling_mode: Literal["ANIMA", "MADHYA", "MAHIMA"] = Field(
        default="MADHYA",
        description=(
            "Anima-Mahima retrieval depth (ANJANEYA §7):\n"
            "  ANIMA  — top-1 KNN, no relational join, ~150 tokens.\n"
            "  MADHYA — top-3 KNN + flat session join, ~900 tokens.\n"
            "  MAHIMA — top-5 KNN + ±3 turn window graph, ~4000 tokens."
        ),
    )
```

### 3.5 Response Models

```python
from pydantic import BaseModel
from typing import Any, Dict, List, Optional

class SessionResponse(BaseModel):
    status:         str
    session_id:     str
    message:        str
    devotion_score: Optional[float] = None
    is_hard_frozen: Optional[bool]  = None

class RecordResponse(BaseModel):
    status:     str
    session_id: str
    turn_id:    int
    message:    str

class SearchResponse(BaseModel):
    results:          List[Dict[str, Any]]
    distress_signal:  bool
    d_min:            Optional[float]
    scaling_mode:     str
    dronagiri_level:  int
    message:          Optional[str]

class SporeResponse(BaseModel):
    status:     str
    spore_file: Optional[str]
    message:    str

class SkillResponse(BaseModel):
    status:       str
    skill_id:     str
    version:      str
    message:      str

class SkillSearchResponse(BaseModel):
    skill_id:      str
    name:          str
    description:   str
    script:        str
    input_schema:  Dict[str, Any]
    output_schema: Dict[str, Any]
    rating:        float
    d_score:       float
    message:       str
```

---

## 4. HTTP Error Response Contract

All error responses follow a **uniform JSON envelope** to enable deterministic
parsing by the EMMA Orchestrator loop without regex pattern matching.

### 4.1 Standard Error Envelope Schema

```json
{
  "error":   "ERROR_CODE_CONSTANT",
  "detail":  "Human-readable description of what failed and why.",
  "context": { "field": "value" }
}
```

### 4.2 Complete Error Code Matrix

| HTTP Status | Error Code | Trigger Condition | Example Context |
|---|---|---|---|
| `400` | `INVALID_UUID` | `session_id` is not a valid UUID v4 | `{"received": "not-a-uuid"}` |
| `400` | `INVALID_STATUS` | `status` not in permitted enum values | `{"received": "paused"}` |
| `400` | `MISSING_TURNS_ON_SUCCESS` | `turns` absent when `status='success'` | `{"status": "success", "turns": null}` |
| `400` | `TOKEN_PEAK_OUT_OF_BOUNDS` | `token_peak` < 0 or > 100000 | `{"received": -1}` |
| `400` | `TURNS_OUT_OF_BOUNDS` | `turns` < 1 or > 15 | `{"received": 0}` |
| `400` | `INVALID_CONTENT_TYPE` | `content_type` not in `['traceback','code_patch','critique']` | `{"received": "log"}` |
| `400` | `EMPTY_PAYLOAD` | `payload` is whitespace-only | `{}` |
| `400` | `INVALID_SCALING_MODE` | `scaling_mode` not in `['ANIMA','MADHYA','MAHIMA']` | `{"received": "DEEP"}` |
| `403` | `SESSION_HARD_FROZEN` | PATCH attempted on a crystallised session | `{"session_id": "...", "devotion_score": 0.92}` |
| `404` | `SESSION_NOT_FOUND` | `session_id` has no record in `sessions` table | `{"session_id": "..."}` |
| `404` | `SKILL_NOT_FOUND` | No skill matches the semantic search query | `{"query": "...", "d_min": 0.91}` |
| `500` | `SQLITE_WRITE_FAILURE` | SQLite `OperationalError` during INSERT/UPDATE | `{"exception": "database is locked"}` |
| `500` | `LANCEDB_UNAVAILABLE` | LanceDB retry exhausted (5 attempts) | `{"retries": 5, "last_error": "..."}` |
| `500` | `EMBEDDING_FAILURE` | SentenceTransformer inference failed | `{"model": "all-MiniLM-L6-v2"}` |
| `500` | `SPORE_CREATION_FAILED` | ZIP archive write failed on disk | `{"path": "spores/", "exception": "..."}` |
| `500` | `RECOVERY_FAILED` | All spore candidates exhausted | `{"candidates_tried": 3}` |
| `503` | `MANIFOLD_UNAVAILABLE` | LanceDB unreachable (service not running) | `{"retries": 5}` |

### 4.3 FastAPI Exception Handlers

```python
from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(
    request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    """
    Translate Pydantic v2 ValidationError into the standard error envelope.
    Surfaces field-level error messages for all validator failures.
    """
    errors = []
    for error in exc.errors():
        errors.append({
            "field":   " → ".join(str(loc) for loc in error["loc"]),
            "message": error["msg"],
            "type":    error["type"],
        })
    return JSONResponse(
        status_code=422,
        content={
            "error":   "VALIDATION_ERROR",
            "detail":  "One or more request fields failed schema validation.",
            "context": {"errors": errors},
        },
    )
```

---

## 5. GDI Alignment Matrix — Sankat Mochan Drift Table

The **Goal Drift Index (GDI)** maps directly to Sankat Mochan cosine distance thresholds,
controlling which Anima-Mahima scaling mode is activated and whether rollback
signals are injected into the response payload.

### 5.1 GDI → System State Mapping

| GDI Zone | Cosine Distance `d_min` | Scaling Mode | System Flag | Dashboard State | Rollback Action |
|---|---|---|---|---|---|
| **CONVERGENT** | `0.00 – 0.35` | `ANIMA` | `STABLE` | 🟢 Green — No action | None |
| **DRIFTING** | `0.35 – 0.55` | `MADHYA` | `MONITORING` | 🟡 Amber — Passive watch | None |
| **HIGH DRIFT** | `0.55 – 0.75` | `MADHYA` | `ALERT` | 🟠 Orange — Distress check | Soft warning injected |
| **PARADOX** | `0.75 – 0.90` | `MAHIMA` | `DISTRESS` | 🔴 Red — Sankat Mochan fires | `distress_signal: true` injected |
| **UNMAPPED** | `0.90 – 1.00` | `MAHIMA` | `CRITICAL` | ⚫ Black — No manifold anchor | Dronagiri fallback cascade |

### 5.2 Scaling Mode Auto-Selection by GDI

When a client sends `scaling_mode: "MADHYA"` but the live `d_min` exceeds `0.75`,
the router **automatically escalates** the scaling mode to `MAHIMA` and
injects a `scaling_override` flag into the response:

```python
def _auto_escalate_mode(
    requested_mode: str,
    d_min: Optional[float],
) -> tuple[str, bool]:
    """
    Escalate scaling mode based on live GDI reading.

    Returns (effective_mode, was_escalated).
    """
    if d_min is None:
        return requested_mode, False
    if d_min > 0.75 and requested_mode in ("ANIMA", "MADHYA"):
        return "MAHIMA", True
    if d_min > 0.55 and requested_mode == "ANIMA":
        return "MADHYA", True
    return requested_mode, False
```

**Response augmentation when escalated:**

```json
{
  "results": [...],
  "distress_signal": true,
  "d_min": 0.821,
  "scaling_mode": "MAHIMA",
  "scaling_override": true,
  "original_mode": "MADHYA",
  "message": "High semantic drift detected. Scaling mode escalated MADHYA → MAHIMA."
}
```

---

## 6. Endpoint Design & Implementation Logic

### 6.1 `POST /manifold/session` — Session Initialisation

```python
@router.post("/session", status_code=201, response_model=SessionResponse)
async def create_session(
    body: SessionCreate,
    conn: DBConn,
) -> SessionResponse:
    """
    Spawn a new solver session tracking slot (Pillar 1: Devotion Crystal init).
    """
    try:
        db_session.create_session(body.session_id, body.task_description)
    except sqlite3.IntegrityError:
        # Session already exists — idempotent response
        return SessionResponse(
            status="exists",
            session_id=body.session_id,
            message="Session already registered.",
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "SQLITE_WRITE_FAILURE", "detail": str(exc), "context": {}},
        )
    return SessionResponse(
        status="success",
        session_id=body.session_id,
        message="Session initialised. Devotion Crystal tracking active.",
    )
```

**Response (201 Created):**
```json
{
  "status": "success",
  "session_id": "99368448-47b9-4101-9162-416256ad4c11",
  "message": "Session initialised. Devotion Crystal tracking active."
}
```

---

### 6.2 `PATCH /manifold/session/{session_id}` — Status Update + Devotion Scoring

```python
@router.patch("/session/{session_id}", status_code=200, response_model=SessionResponse)
async def update_session(
    session_id: str,
    body:       SessionUpdate,
    conn:       DBConn,
) -> SessionResponse:
    """
    Update session execution state.
    On status='success': compute Devotion Score D and evaluate hard-freeze gate.
    On is_hard_frozen=True: block with 403 Forbidden.
    """
    # Gate: session must exist
    session = db_session.get_session(session_id)
    if session is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error":   "SESSION_NOT_FOUND",
                "detail":  f"No session record found for id '{session_id}'.",
                "context": {"session_id": session_id},
            },
        )

    # Gate: hard-frozen sessions are immutable
    if session.get("is_hard_frozen"):
        raise HTTPException(
            status_code=403,
            detail={
                "error":   "SESSION_HARD_FROZEN",
                "detail":  (
                    f"Session '{session_id}' is permanently crystallised "
                    f"(D={session['devotion_score']:.6f} ≥ THETA_CRYSTAL=0.85). "
                    "Devotion Crystal immutability enforced. No modifications permitted."
                ),
                "context": {
                    "session_id":    session_id,
                    "devotion_score":session["devotion_score"],
                    "is_hard_frozen":True,
                },
            },
        )

    try:
        result = db_session.update_session_status(
            session_id=session_id,
            status=body.status,
            token_peak=body.token_peak,
            turns=body.turns,
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "SQLITE_WRITE_FAILURE", "detail": str(exc), "context": {}},
        )

    D, is_frozen = result if result else (None, None)

    message = "Session status updated."
    if is_frozen:
        message = (
            f"Devotion Score D={D:.6f} ≥ THETA_CRYSTAL=0.85. "
            "Session permanently crystallised. Hard-freeze gate triggered."
        )
    elif D is not None:
        message = f"Devotion Score D={D:.6f} computed. Session not crystallised."

    return SessionResponse(
        status="success",
        session_id=session_id,
        devotion_score=D,
        is_hard_frozen=is_frozen,
        message=message,
    )
```

**Response (200 OK — crystallised):**
```json
{
  "status":         "success",
  "session_id":     "99368448-47b9-4101-9162-416256ad4c11",
  "devotion_score": 0.924929,
  "is_hard_frozen": true,
  "message":        "Devotion Score D=0.924929 ≥ THETA_CRYSTAL=0.85. Session permanently crystallised."
}
```

**Error (403 Forbidden):**
```json
{
  "error":   "SESSION_HARD_FROZEN",
  "detail":  "Session '99368448...' is permanently crystallised (D=0.924929 ≥ 0.85).",
  "context": {"session_id": "99368448...", "devotion_score": 0.924929, "is_hard_frozen": true}
}
```

---

### 6.3 `POST /manifold/record` — Event Ingestion

```python
@router.post("/record", status_code=201, response_model=RecordResponse)
async def record_event(body: EventRecord) -> RecordResponse:
    """
    Ingest a solver trace event. Triggers SentenceTransformer embedding
    and LanceDB vector write (Pillar 5: Anima-Mahima manifold population).
    """
    try:
        db_manifold.record_event(
            session_id   = body.session_id,
            turn_id      = body.turn_id,
            content_type = body.content_type,
            payload      = body.payload,
        )
    except Exception as exc:
        error_type = (
            "EMBEDDING_FAILURE"   if "encode" in str(exc).lower()
            else "LANCEDB_UNAVAILABLE" if "lancedb" in str(exc).lower()
            else "SQLITE_WRITE_FAILURE"
        )
        raise HTTPException(
            status_code=500,
            detail={"error": error_type, "detail": str(exc), "context": {}},
        )

    return RecordResponse(
        status     = "success",
        session_id = body.session_id,
        turn_id    = body.turn_id,
        message    = "Event recorded. Vector manifold populated.",
    )
```

---

### 6.4 `POST /manifold/search` — Anima-Mahima Semantic Search

```python
@router.post("/search", status_code=200, response_model=SearchResponse)
async def search_manifold(body: ManifoldSearch) -> SearchResponse:
    """
    Execute a semantic KNN search at the requested Anima-Mahima depth.
    Applies Sankat Mochan drift interception and auto-escalates scaling mode
    when d_min exceeds GDI thresholds.
    """
    raw = db_manifold.search_manifold(
        query_text   = body.query,
        scaling_mode = body.scaling_mode,
    )

    # Auto-escalate scaling mode based on live GDI reading
    effective_mode, was_escalated = _auto_escalate_mode(
        body.scaling_mode, raw.get("d_min")
    )
    if was_escalated:
        raw = db_manifold.search_manifold(body.query, effective_mode)
        raw["scaling_override"] = True
        raw["original_mode"]    = body.scaling_mode

    return SearchResponse(
        results          = raw.get("results", []),
        distress_signal  = raw.get("distress_signal", False),
        d_min            = raw.get("d_min"),
        scaling_mode     = raw.get("scaling_mode", effective_mode),
        dronagiri_level  = raw.get("dronagiri_level", 1),
        message          = raw.get("message"),
    )
```

---

### 6.5 `POST /manifold/spore` — Chiranjeevi Archive Trigger

```python
@router.post("/spore", status_code=200, response_model=SporeResponse)
async def trigger_spore() -> SporeResponse:
    """
    Manually trigger a Chiranjeevi spore archive of session.db + manifold.db.
    """
    try:
        spore_path = db_manifold.create_spore()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "SPORE_CREATION_FAILED", "detail": str(exc), "context": {}},
        )
    return SporeResponse(
        status     = "success",
        spore_file = spore_path.name,
        message    = f"Chiranjeevi Spore Archive compiled: {spore_path.name}",
    )
```

---

### 6.6 `POST /manifold/restore` — Chiranjeevi Recovery Protocol

```python
@router.post("/restore", status_code=200, response_model=SporeResponse)
async def trigger_restore() -> SporeResponse:
    """
    Trigger the 6-step deterministic Chiranjeevi self-healing recovery protocol.
    """
    success = db_manifold.restore_from_spore()
    if not success:
        raise HTTPException(
            status_code=500,
            detail={
                "error":   "RECOVERY_FAILED",
                "detail":  "All Chiranjeevi spore candidates exhausted or corrupt.",
                "context": {"spore_dir": str(db_manifold.SPORE_DIR)},
            },
        )
    return SporeResponse(
        status     = "success",
        spore_file = None,
        message    = "Chiranjeevi recovery complete. Databases restored and integrity-verified.",
    )
```

---

### 6.7 `GET /manifold/health` — Integrity Diagnostic

```python
@router.get("/health", status_code=200)
async def health_check() -> dict:
    """
    Return database integrity status, last spore timestamp, and
    session pool connection state for monitoring dashboards.
    """
    from app.database.session import verify_integrity, SESSION_DB
    from app.database.manifold import SPORE_DIR, MANIFOLD_DB
    import os

    spores = sorted(SPORE_DIR.glob("spore_*.zip"), reverse=True)

    return {
        "session_db_integrity": verify_integrity(),
        "manifold_db_exists":   MANIFOLD_DB.exists(),
        "session_db_size_kb":   round(SESSION_DB.stat().st_size / 1024, 2) if SESSION_DB.exists() else 0,
        "manifold_db_size_kb":  round(MANIFOLD_DB.stat().st_size / 1024, 2) if MANIFOLD_DB.exists() else 0,
        "spore_count":          len(spores),
        "last_spore":           spores[0].name if spores else None,
        "anjaneya_pillars":     ["Devotion Crystal", "Dronagiri", "Chiranjeevi", "Sankat Mochan", "Anima-Mahima"],
    }
```

---

## 7. Modular Dynamic Skill Registry Layer

### 7.1 Overview

The **Skill Registry** extends the ANJANEYA manifold with a live, semantically-indexed
library of diagnostic Python/Bash scripts that agents can register, retrieve, and
execute at runtime. This transforms EMMA from a static pipeline into a **self-expanding
cognitive toolkit** where successful debugging strategies are codified as reusable,
version-controlled skills.

```
Agent Loop encounters novel error
         │
         ▼
POST /manifold/skills/search  (query: error description)
         │
         ▼
Skill Registry returns: top-1 verified script + input schema
         │
         ▼
Agent executes script in sandbox (code_generator.py sandbox)
         │
         ▼
On success: POST /manifold/skills  (register refined version)
         │
         ▼
Skill invocation_count ++, rating updated
```

### 7.2 SQLite Skills Table Schema

```sql
CREATE TABLE IF NOT EXISTS skills (
    skill_id          TEXT    PRIMARY KEY,
    name              TEXT    NOT NULL,
    description       TEXT    NOT NULL,
    script            TEXT    NOT NULL,
    language          TEXT    NOT NULL
                      CHECK(language IN ('python', 'bash', 'powershell')),
    author_agent      TEXT    NOT NULL,
    version           TEXT    NOT NULL DEFAULT '1.0.0',
    input_schema      TEXT    NOT NULL,   -- JSON string: {"param": "type"}
    output_schema     TEXT    NOT NULL,   -- JSON string: {"return": "type"}
    performance_rating REAL   DEFAULT 0.0
                      CHECK(performance_rating BETWEEN 0.0 AND 1.0),
    invocation_count  INTEGER DEFAULT 0,
    is_verified       BOOLEAN DEFAULT 0,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_skills_rating
    ON skills(performance_rating DESC, invocation_count DESC);

CREATE INDEX IF NOT EXISTS idx_skills_verified
    ON skills(is_verified, performance_rating DESC);
```

### 7.3 LanceDB Skills Vector Index

```python
SKILLS_SCHEMA: pa.Schema = pa.schema([
    pa.field("vector",      pa.list_(pa.float32(), 384)),  # Embedding of description
    pa.field("skill_id",    pa.string()),                  # FK → skills.skill_id
    pa.field("name",        pa.string()),
    pa.field("description", pa.string()),                  # Natural-language utility text
    pa.field("language",    pa.string()),
    pa.field("version",     pa.string()),
    pa.field("rating",      pa.float32()),
    pa.field("is_verified", pa.bool_()),
])
```

### 7.4 Pydantic Skill Schemas

```python
from pydantic import BaseModel, Field, field_validator
from typing import Any, Dict, Literal, Optional
import uuid

class SkillCreate(BaseModel):
    """Register a new dynamic diagnostic skill."""

    skill_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="UUID v4. Auto-generated if not supplied.",
    )
    name: str = Field(
        ..., min_length=3, max_length=100,
        description="Short human-readable skill identifier.",
        examples=["oauth_header_repair", "sqlite_deadlock_probe"],
    )
    description: str = Field(
        ..., min_length=10, max_length=1000,
        description="Natural-language description of what this skill does and "
                    "when to apply it. This text is embedded for semantic search.",
    )
    script: str = Field(
        ..., min_length=10,
        description="Full executable Python, Bash, or PowerShell script body.",
    )
    language: Literal["python", "bash", "powershell"] = Field(
        default="python",
        description="Script execution runtime.",
    )
    author_agent: str = Field(
        ..., min_length=1, max_length=100,
        description="Identifier of the agent or session that authored this skill.",
    )
    version: str = Field(
        default="1.0.0",
        description="Semantic version string (major.minor.patch).",
        examples=["1.0.0", "2.3.1"],
    )
    input_schema: Dict[str, Any] = Field(
        ...,
        description="JSON schema dict describing expected input parameters.",
        examples=[{"error_text": "str", "file_path": "str"}],
    )
    output_schema: Dict[str, Any] = Field(
        ...,
        description="JSON schema dict describing the expected return structure.",
        examples=[{"patched": "bool", "patch_applied": "str"}],
    )

    @field_validator("script")
    @classmethod
    def validate_python_syntax(cls, v: str, info) -> str:
        """For Python skills: pre-validate syntax via ast.parse before registration."""
        # language check requires accessing sibling field
        import ast
        try:
            ast.parse(v)
        except SyntaxError as exc:
            raise ValueError(
                f"Script contains a SyntaxError and cannot be registered: {exc}"
            )
        return v

    @field_validator("version")
    @classmethod
    def validate_semver(cls, v: str) -> str:
        parts = v.split(".")
        if len(parts) != 3 or not all(p.isdigit() for p in parts):
            raise ValueError(
                f"version must follow semantic versioning (major.minor.patch). "
                f"Received: '{v}'"
            )
        return v


class SkillSearch(BaseModel):
    """Semantic skill retrieval query."""

    query: str = Field(
        ..., min_length=3, max_length=500,
        description="Natural-language description of the diagnostic problem "
                    "or skill capability needed.",
        examples=["fix OAuth 2.0 Bearer header mismatch"],
    )
    language: Optional[Literal["python", "bash", "powershell"]] = Field(
        default=None,
        description="Optional language filter. If None, searches all languages.",
    )
    verified_only: bool = Field(
        default=True,
        description="If True, only returns skills with is_verified=True.",
    )
```

### 7.5 `POST /manifold/skills` — Skill Registration

```python
@router.post("/skills", status_code=201, response_model=SkillResponse)
async def register_skill(
    body: SkillCreate,
    conn: DBConn,
) -> SkillResponse:
    """
    Register a new dynamic diagnostic skill in both the SQLite relational
    store and the LanceDB semantic vector index.

    Registration pipeline:
      1. Insert skill record into SQLite `skills` table.
      2. Embed skill description via SentenceTransformer.
      3. Write embedding + metadata to LanceDB `skills_index` table.
      4. Return skill_id and version for agent reference.
    """
    import json
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    try:
        conn.execute(
            """
            INSERT INTO skills
                (skill_id, name, description, script, language,
                 author_agent, version, input_schema, output_schema,
                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                body.skill_id, body.name, body.description, body.script,
                body.language, body.author_agent, body.version,
                json.dumps(body.input_schema), json.dumps(body.output_schema),
                now, now,
            ),
        )
    except sqlite3.IntegrityError:
        raise HTTPException(
            status_code=409,
            detail={
                "error":   "SKILL_ALREADY_EXISTS",
                "detail":  f"Skill '{body.skill_id}' is already registered.",
                "context": {"skill_id": body.skill_id},
            },
        )
    except sqlite3.Error as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "SQLITE_WRITE_FAILURE", "detail": str(exc), "context": {}},
        )

    # Embed description and write to LanceDB skills index
    try:
        from app.database.manifold import _embed, get_manifold_table
        import lancedb

        vector = _embed(body.description)
        db     = lancedb.connect(str(db_manifold.MANIFOLD_DB))
        if "skills_index" not in db.table_names():
            skills_table = db.create_table("skills_index", schema=SKILLS_SCHEMA)
        else:
            skills_table = db.open_table("skills_index")

        skills_table.add([{
            "vector":      vector,
            "skill_id":    body.skill_id,
            "name":        body.name,
            "description": body.description,
            "language":    body.language,
            "version":     body.version,
            "rating":      0.0,
            "is_verified": False,
        }])
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "EMBEDDING_FAILURE", "detail": str(exc), "context": {}},
        )

    return SkillResponse(
        status   = "success",
        skill_id = body.skill_id,
        version  = body.version,
        message  = f"Skill '{body.name}' v{body.version} registered in manifold.",
    )
```

### 7.6 `POST /manifold/skills/search` — Semantic Skill Retrieval

```python
@router.post("/skills/search", status_code=200, response_model=SkillSearchResponse)
async def search_skills(
    body: SkillSearch,
    conn: DBConn,
) -> SkillSearchResponse:
    """
    Semantically retrieve the top-1 verified, highest-rated diagnostic skill
    matching the query. Returns the full executable script and input schema
    for immediate agent consumption.
    """
    import json, lancedb
    from app.database.manifold import _embed

    try:
        vector = _embed(body.query)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "EMBEDDING_FAILURE", "detail": str(exc), "context": {}},
        )

    try:
        db           = lancedb.connect(str(db_manifold.MANIFOLD_DB))
        skills_table = db.open_table("skills_index")

        search = skills_table.search(vector).metric("cosine").limit(10)
        if body.verified_only:
            search = search.where("is_verified = true")
        if body.language:
            search = search.where(f"language = '{body.language}'")

        candidates = search.to_list()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "MANIFOLD_UNAVAILABLE", "detail": str(exc), "context": {}},
        )

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail={
                "error":   "SKILL_NOT_FOUND",
                "detail":  "No matching skills found in the registry for this query.",
                "context": {"query": body.query, "verified_only": body.verified_only},
            },
        )

    # Select the best candidate (lowest cosine distance = most semantically similar)
    best     = candidates[0]
    skill_id = best["skill_id"]
    d_score  = float(best.get("_distance", 1.0))

    # Retrieve full script and schemas from SQLite
    row = conn.execute(
        "SELECT * FROM skills WHERE skill_id = ?", (skill_id,)
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={"error": "SKILL_NOT_FOUND", "detail": f"Skill '{skill_id}' missing from SQLite.", "context": {}},
        )

    # Increment invocation count
    conn.execute(
        "UPDATE skills SET invocation_count = invocation_count + 1, "
        "updated_at = CURRENT_TIMESTAMP WHERE skill_id = ?",
        (skill_id,),
    )

    return SkillSearchResponse(
        skill_id      = skill_id,
        name          = row["name"],
        description   = row["description"],
        script        = row["script"],
        input_schema  = json.loads(row["input_schema"]),
        output_schema = json.loads(row["output_schema"]),
        rating        = float(row["performance_rating"]),
        d_score       = round(d_score, 6),
        message       = (
            f"Skill '{row['name']}' v{row['version']} retrieved "
            f"(semantic distance d={d_score:.4f})."
        ),
    )
```

---

## 8. Manual Verification & Diagnostics

### 8.1 Full Endpoint Test Sequence

```bash
# 1. Health check
curl -X GET  "http://localhost:8000/manifold/health"

# 2. Initialize session
curl -X POST "http://localhost:8000/manifold/session" \
     -H "Content-Type: application/json" \
     -d '{"session_id": "99368448-47b9-4101-9162-416256ad4c11",
          "task_description": "OAuth 2.0 token exchange debugging"}'

# 3. Ingest traceback
curl -X POST "http://localhost:8000/manifold/record" \
     -H "Content-Type: application/json" \
     -d '{"session_id": "99368448-47b9-4101-9162-416256ad4c11",
          "turn_id": 0, "content_type": "traceback",
          "payload": "urllib.error.HTTPError: HTTP Error 401: Unauthorized"}'

# 4. Update session to success (triggers Devotion Score)
curl -X PATCH "http://localhost:8000/manifold/session/99368448-47b9-4101-9162-416256ad4c11" \
     -H "Content-Type: application/json" \
     -d '{"status": "success", "token_peak": 8000, "turns": 2}'

# 5. Search manifold (MADHYA mode)
curl -X POST "http://localhost:8000/manifold/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "HTTP 401 unauthorized token error", "scaling_mode": "MADHYA"}'

# 6. Register a skill
curl -X POST "http://localhost:8000/manifold/skills" \
     -H "Content-Type: application/json" \
     -d '{"name": "oauth_header_repair",
          "description": "Detects and repairs malformed OAuth Bearer/Token header prefixes",
          "script": "def repair_header(h): return h.replace(\"Bearer \", \"Token \")",
          "author_agent": "EMMA-Orchestrator-v1",
          "input_schema": {"header_value": "str"},
          "output_schema": {"repaired_header": "str"}}'

# 7. Search skills semantically
curl -X POST "http://localhost:8000/manifold/skills/search" \
     -H "Content-Type: application/json" \
     -d '{"query": "fix OAuth authorization header format mismatch"}'

# 8. Trigger Chiranjeevi spore
curl -X POST "http://localhost:8000/manifold/spore"
```

---

*🔱 Jai Bajrang Bali — Infinite Memory, Infinite Strength*
*ANJANEYA Memory Protocol v2.0 — Nexus AI Research Lab, Bengaluru*
*EMM-04-A1 FastAPI Router — Enhanced Specification v2.0*
