"""
routers/manifold.py
===================
EMMA — ANJANEYA Memory Protocol FastAPI Router  (EMM-04-A1)

Stateless REST coordinator connecting FastAPI handlers to:
  - SQLite WAL-mode session pool  (app/database/session.py)
  - LanceDB vector semantic manifold  (app/database/manifold.py)
  - Modular dynamic Skill Registry (SQLite + LanceDB skills_index)

All endpoints use per-request dependency injection for database connections.
All error responses follow the uniform JSON error envelope contract.

Endpoints
---------
POST   /manifold/session                 — Spawn solver session (Devotion Crystal init)
GET    /manifold/session/{session_id}    — Retrieve single session
GET    /manifold/sessions                — List all sessions
PATCH  /manifold/session/{session_id}    — Update status + Devotion Scoring + hard-freeze gate
POST   /manifold/record                  — Ingest vector event (embedding pipeline)
POST   /manifold/search                  — Anima-Mahima KNN search + Sankat Mochan drift gate
POST   /manifold/spore                   — Chiranjeevi archive trigger
POST   /manifold/restore                 — Chiranjeevi 6-step self-healing recovery
GET    /manifold/health                  — DB integrity + spore diagnostics
POST   /manifold/skills                  — Register dynamic diagnostic skill
POST   /manifold/skills/search           — Semantic skill retrieval
"""

import ast
import json
import logging
import sqlite3
from pathlib import Path
from typing import Annotated, Any, Dict, Generator, List, Literal, Optional

import pyarrow as pa
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator, model_validator

import app.database.session as db_session
import app.database.manifold as db_manifold
from app.database.session import (
    checkpoint_wal,
    close_thread_local_conn,
    get_thread_local_conn,
    verify_integrity,
)
from app.database.manifold import (
    _embed,
    get_manifold_table,
    record_event,
    search_manifold,
    create_spore,
    restore_from_spore,
)

log = logging.getLogger(__name__)

router = APIRouter()


# =============================================================================
# LanceDB Skills Index Schema
# =============================================================================

SKILLS_SCHEMA: pa.Schema = pa.schema([
    pa.field("vector",      pa.list_(pa.float32(), 384)),
    pa.field("skill_id",    pa.string()),
    pa.field("name",        pa.string()),
    pa.field("description", pa.string()),
    pa.field("language",    pa.string()),
    pa.field("version",     pa.string()),
    pa.field("rating",      pa.float32()),
    pa.field("is_verified", pa.bool_()),
])


# =============================================================================
# Dependency Injection — Database Connection Lifecycle
# =============================================================================

def get_db() -> Generator[sqlite3.Connection, None, None]:
    """
    Per-request thread-local WAL-mode SQLite connection.
    Runs PRAGMA wal_checkpoint(PASSIVE) teardown after every response.
    Recycles poisoned connections on exception.
    """
    conn = get_thread_local_conn()
    try:
        yield conn
    except Exception:
        close_thread_local_conn()
        raise
    finally:
        try:
            conn.execute("PRAGMA wal_checkpoint(PASSIVE);")
        except sqlite3.Error:
            pass


def get_manifold() -> Generator[Any, None, None]:
    """
    Per-request LanceDB table reference with retry-wrapped acquisition.
    Raises 503 if the manifold table is unreachable after all retries.
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
            },
        )


# Type aliases for clean injection signatures
DBConn        = Annotated[sqlite3.Connection, Depends(get_db)]
ManifoldTable = Annotated[Any, Depends(get_manifold)]


# =============================================================================
# Pydantic Request Schemas
# =============================================================================

class SessionCreate(BaseModel):
    """Spawn a new solver session tracking slot."""
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
        import uuid
        try:
            uuid.UUID(v, version=4)
        except ValueError:
            raise ValueError(
                f"session_id must be a valid UUID v4 string. Received: '{v}'"
            )
        return v


class SessionUpdate(BaseModel):
    """Update session execution state. Triggers Devotion Crystal scoring on 'success'."""
    status: Literal["running", "success", "failed", "rolled_back"] = Field(
        ...,
        description="Execution state. 'success' triggers Devotion Score computation.",
    )
    token_peak: int = Field(
        ...,
        ge=0,
        le=100_000,
        description="Peak token utilization. Bounded to [0, U_MAX=100000].",
    )
    turns: Optional[int] = Field(
        None,
        ge=1,
        le=15,
        description="Solver turns consumed. Required when status='success'.",
    )

    @model_validator(mode="after")
    def check_turns_on_success(self) -> "SessionUpdate":
        if self.status == "success" and self.turns is None:
            raise ValueError(
                "Field 'turns' is mandatory when status is 'success'. "
                "Required to compute Devotion Score D = α·T_eff + β·U_eff."
            )
        return self


class EventRecord(BaseModel):
    """Ingest a structured solver trace event into the semantic manifold."""
    session_id: str = Field(..., description="UUID v4 of the owning session.")
    turn_id: int = Field(..., ge=0, le=999, description="Zero-indexed solver turn number.")
    content_type: Literal["traceback", "code_patch", "critique"] = Field(
        ..., description="Semantic classification of the event payload.",
    )
    payload: str = Field(
        ...,
        min_length=1,
        max_length=50_000,
        description="Raw event content — traceback, code patch, or critique text.",
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


class ManifoldSearch(BaseModel):
    """Semantic manifold query with Anima-Mahima depth scaling."""
    query: str = Field(
        ...,
        min_length=3,
        max_length=1000,
        description="Natural-language query string.",
    )
    scaling_mode: Literal["ANIMA", "MADHYA", "MAHIMA"] = Field(
        default="MADHYA",
        description=(
            "Anima-Mahima retrieval depth:\n"
            "  ANIMA  — top-1 KNN, ~150 tokens.\n"
            "  MADHYA — top-3 KNN + session join, ~900 tokens.\n"
            "  MAHIMA — top-5 KNN + ±3 turn window graph, ~4000 tokens."
        ),
    )


class SkillCreate(BaseModel):
    """Register a new dynamic diagnostic skill."""
    skill_id: str = Field(
        default_factory=lambda: __import__("uuid").uuid4().__str__(),
        description="UUID v4. Auto-generated if not supplied.",
    )
    name: str = Field(..., min_length=3, max_length=100)
    description: str = Field(..., min_length=10, max_length=1000)
    script: str = Field(..., min_length=10)
    language: Literal["python", "bash", "powershell"] = Field(default="python")
    author_agent: str = Field(..., min_length=1, max_length=100)
    version: str = Field(default="1.0.0")
    input_schema: Dict[str, Any] = Field(...)
    output_schema: Dict[str, Any] = Field(...)

    @field_validator("script")
    @classmethod
    def validate_python_syntax(cls, v: str) -> str:
        """AST pre-validation for Python skills before registration."""
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
                f"version must follow semantic versioning (major.minor.patch). Received: '{v}'"
            )
        return v


class SkillSearch(BaseModel):
    """Semantic skill retrieval query."""
    query: str = Field(..., min_length=3, max_length=500)
    language: Optional[Literal["python", "bash", "powershell"]] = Field(default=None)
    verified_only: bool = Field(default=True)


# =============================================================================
# Pydantic Response Models
# =============================================================================

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
    results:         List[Dict[str, Any]]
    distress_signal: bool
    d_min:           Optional[float]
    scaling_mode:    str
    dronagiri_level: int
    message:         Optional[str] = None


class SporeResponse(BaseModel):
    status:     str
    spore_file: Optional[str]
    message:    str


class SkillResponse(BaseModel):
    status:   str
    skill_id: str
    version:  str
    message:  str


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


# =============================================================================
# GDI Auto-Escalation Helper  (Sankat Mochan Drift Gate)
# =============================================================================

def _auto_escalate_mode(
    requested_mode: str,
    d_min: Optional[float],
) -> tuple:
    """
    Escalate scaling mode based on live GDI cosine distance reading.
    Returns (effective_mode, was_escalated).

      d_min > 0.75  → escalate to MAHIMA  (PARADOX zone)
      d_min > 0.55  → escalate to MADHYA  (HIGH DRIFT zone, only from ANIMA)
    """
    if d_min is None:
        return requested_mode, False
    if d_min > 0.75 and requested_mode in ("ANIMA", "MADHYA"):
        return "MAHIMA", True
    if d_min > 0.55 and requested_mode == "ANIMA":
        return "MADHYA", True
    return requested_mode, False


# =============================================================================
# SESSION ENDPOINTS
# =============================================================================

@router.post("/session", status_code=201, response_model=SessionResponse)
async def create_session(body: SessionCreate, conn: DBConn) -> SessionResponse:
    """
    POST /manifold/session
    Spawn a new solver session tracking slot (Pillar 1: Devotion Crystal init).
    Idempotent — duplicate session_ids return status='exists'.
    """
    try:
        db_session.create_session(body.session_id, body.task_description)
    except sqlite3.IntegrityError:
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


@router.get("/session/{session_id}", status_code=200)
async def get_session(session_id: str, conn: DBConn) -> dict:
    """
    GET /manifold/session/{session_id}
    Retrieve a single session record by UUID.
    """
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
    return {"status": "success", "session": session}


@router.get("/sessions", status_code=200)
async def list_sessions(conn: DBConn) -> dict:
    """
    GET /manifold/sessions
    Return all session records ordered by creation time (newest first).
    """
    sessions = db_session.list_all_sessions()
    return {"status": "success", "count": len(sessions), "sessions": sessions}


@router.patch("/session/{session_id}", status_code=200, response_model=SessionResponse)
async def update_session(
    session_id: str,
    body: SessionUpdate,
    conn: DBConn,
) -> SessionResponse:
    """
    PATCH /manifold/session/{session_id}
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

    # Gate: hard-frozen sessions are permanently immutable (Devotion Crystal)
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
                    "devotion_score": session["devotion_score"],
                    "is_hard_frozen": True,
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


# =============================================================================
# EVENT INGESTION & SEARCH ENDPOINTS
# =============================================================================

@router.post("/record", status_code=201, response_model=RecordResponse)
async def record_event_endpoint(body: EventRecord) -> RecordResponse:
    """
    POST /manifold/record
    Ingest a solver trace event. Triggers SentenceTransformer embedding and
    LanceDB vector write (Pillar 5: Anima-Mahima manifold population).
    """
    try:
        record_event(
            session_id=body.session_id,
            turn_id=body.turn_id,
            content_type=body.content_type,
            payload=body.payload,
        )
    except Exception as exc:
        error_type = (
            "EMBEDDING_FAILURE"    if "encode" in str(exc).lower()
            else "LANCEDB_UNAVAILABLE" if "lancedb" in str(exc).lower()
            else "SQLITE_WRITE_FAILURE"
        )
        raise HTTPException(
            status_code=500,
            detail={"error": error_type, "detail": str(exc), "context": {}},
        )
    return RecordResponse(
        status="success",
        session_id=body.session_id,
        turn_id=body.turn_id,
        message="Event recorded. Vector manifold populated.",
    )


@router.post("/search", status_code=200, response_model=SearchResponse)
async def search_manifold_endpoint(body: ManifoldSearch) -> SearchResponse:
    """
    POST /manifold/search
    Execute semantic KNN search at the requested Anima-Mahima depth.
    Applies Sankat Mochan drift interception and auto-escalates scaling mode
    when d_min exceeds GDI thresholds (Pillar 4 & 5).
    """
    raw = search_manifold(
        query_text=body.query,
        scaling_mode=body.scaling_mode,
    )

    # Auto-escalate scaling mode based on live GDI reading
    effective_mode, was_escalated = _auto_escalate_mode(
        body.scaling_mode, raw.get("d_min")
    )
    if was_escalated:
        raw = search_manifold(body.query, effective_mode)
        raw["scaling_override"] = True
        raw["original_mode"]    = body.scaling_mode

    return SearchResponse(
        results=raw.get("results", []),
        distress_signal=raw.get("distress_signal", False),
        d_min=raw.get("d_min"),
        scaling_mode=raw.get("scaling_mode", effective_mode),
        dronagiri_level=raw.get("dronagiri_level", 1),
        message=raw.get("message"),
    )


# =============================================================================
# CHIRANJEEVI SPORE BACKUP & RECOVERY ENDPOINTS  (Pillar 3)
# =============================================================================

@router.post("/spore", status_code=200, response_model=SporeResponse)
async def trigger_spore() -> SporeResponse:
    """
    POST /manifold/spore
    Manually trigger a Chiranjeevi spore archive of session.db + manifold.db.
    Creates an integrity-verified ZIP in the spores/ directory.
    """
    try:
        spore_path = db_manifold.create_spore()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "SPORE_CREATION_FAILED", "detail": str(exc), "context": {}},
        )
    return SporeResponse(
        status="success",
        spore_file=spore_path.name,
        message=f"Chiranjeevi Spore Archive compiled: {spore_path.name}",
    )


@router.post("/restore", status_code=200, response_model=SporeResponse)
async def trigger_restore() -> SporeResponse:
    """
    POST /manifold/restore
    Trigger the 6-step deterministic Chiranjeevi self-healing recovery protocol.
    Validates SHA-256 hashes of spore candidates before restoring.
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
        status="success",
        spore_file=None,
        message="Chiranjeevi recovery complete. Databases restored and integrity-verified.",
    )


# =============================================================================
# HEALTH DIAGNOSTIC ENDPOINT
# =============================================================================

@router.get("/health", status_code=200)
async def health_check() -> dict:
    """
    GET /manifold/health
    Return database integrity status, last spore timestamp, and
    session pool connection state for monitoring dashboards.
    """
    spores = sorted(db_manifold.SPORE_DIR.glob("spore_*.zip"), reverse=True)
    return {
        "status":                "healthy",
        "session_db_integrity":  verify_integrity(),
        "manifold_db_exists":    db_manifold.MANIFOLD_DB.exists(),
        "session_db_size_kb":    round(db_session.SESSION_DB.stat().st_size / 1024, 2) if db_session.SESSION_DB.exists() else 0,
        "manifold_db_size_kb":   round(db_manifold.MANIFOLD_DB.stat().st_size / 1024, 2) if db_manifold.MANIFOLD_DB.exists() else 0,
        "spore_count":           len(spores),
        "last_spore":            spores[0].name if spores else None,
        "anjaneya_pillars":      [
            "Devotion Crystal",
            "Dronagiri",
            "Chiranjeevi",
            "Sankat Mochan",
            "Anima-Mahima",
        ],
    }


# =============================================================================
# SKILL REGISTRY ENDPOINTS  (Modular Dynamic Skill Registry)
# =============================================================================

def _get_skills_table():
    """
    Open or create the LanceDB 'skills_index' table.
    Creates the table from SKILLS_SCHEMA on first call.
    """
    import lancedb
    db = lancedb.connect(str(db_manifold.MANIFOLD_DB))
    if "skills_index" not in db.table_names():
        log.info("[SkillRegistry] Creating LanceDB skills_index table.")
        return db.create_table("skills_index", schema=SKILLS_SCHEMA)
    return db.open_table("skills_index")


@router.post("/skills", status_code=201, response_model=SkillResponse)
async def register_skill(body: SkillCreate, conn: DBConn) -> SkillResponse:
    """
    POST /manifold/skills
    Register a new dynamic diagnostic skill in both the SQLite relational
    store and the LanceDB semantic vector index.

    Pipeline:
      1. Insert skill record into SQLite 'skills' table (with AST-validated script).
      2. Embed skill description via SentenceTransformer.
      3. Write embedding + metadata to LanceDB 'skills_index' table.
    """
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")

    # Step 1: Persist to SQLite skills table
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

    # Step 2 & 3: Embed description and write to LanceDB skills index
    try:
        vector = _embed(body.description)
        skills_table = _get_skills_table()
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
        # Roll back SQLite insert if vector write fails
        try:
            conn.execute("DELETE FROM skills WHERE skill_id = ?", (body.skill_id,))
        except sqlite3.Error:
            pass
        raise HTTPException(
            status_code=500,
            detail={"error": "EMBEDDING_FAILURE", "detail": str(exc), "context": {}},
        )

    return SkillResponse(
        status="success",
        skill_id=body.skill_id,
        version=body.version,
        message=f"Skill '{body.name}' v{body.version} registered in manifold.",
    )


@router.post("/skills/search", status_code=200, response_model=SkillSearchResponse)
async def search_skills(body: SkillSearch, conn: DBConn) -> SkillSearchResponse:
    """
    POST /manifold/skills/search
    Semantically retrieve the top-1 highest-rated diagnostic skill matching
    the query. Returns the full executable script and schemas for agent use.
    """
    # Step 1: Embed the query
    try:
        vector = _embed(body.query)
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail={"error": "EMBEDDING_FAILURE", "detail": str(exc), "context": {}},
        )

    # Step 2: KNN search on skills_index
    try:
        skills_table = _get_skills_table()
        search_query = skills_table.search(vector).metric("cosine").limit(10)
        candidates   = search_query.to_list()
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail={"error": "MANIFOLD_UNAVAILABLE", "detail": str(exc), "context": {}},
        )

    # Step 3: Filter by verified_only and language if requested
    if body.verified_only:
        candidates = [c for c in candidates if c.get("is_verified", False)]
    if body.language:
        candidates = [c for c in candidates if c.get("language") == body.language]

    if not candidates:
        raise HTTPException(
            status_code=404,
            detail={
                "error":   "SKILL_NOT_FOUND",
                "detail":  "No matching skills found in the registry for this query.",
                "context": {"query": body.query, "verified_only": body.verified_only},
            },
        )

    best     = candidates[0]
    skill_id = best["skill_id"]
    d_score  = float(best.get("_distance", 1.0))

    # Step 4: Retrieve full skill record from SQLite
    row = conn.execute(
        "SELECT * FROM skills WHERE skill_id = ?", (skill_id,)
    ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=404,
            detail={
                "error":   "SKILL_NOT_FOUND",
                "detail":  f"Skill '{skill_id}' missing from SQLite index.",
                "context": {},
            },
        )

    # Step 5: Increment invocation count for usage tracking
    conn.execute(
        "UPDATE skills SET invocation_count = invocation_count + 1, "
        "updated_at = CURRENT_TIMESTAMP WHERE skill_id = ?",
        (skill_id,),
    )

    return SkillSearchResponse(
        skill_id=skill_id,
        name=row["name"],
        description=row["description"],
        script=row["script"],
        input_schema=json.loads(row["input_schema"]),
        output_schema=json.loads(row["output_schema"]),
        rating=float(row["performance_rating"]),
        d_score=round(d_score, 6),
        message=(
            f"Skill '{row['name']}' v{row['version']} retrieved "
            f"(semantic distance d={d_score:.4f})."
        ),
    )
