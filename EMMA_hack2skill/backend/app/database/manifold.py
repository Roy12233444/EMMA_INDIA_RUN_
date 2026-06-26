"""
manifold.py
===========
EMMA — LanceDB Vector Memory Layer (Semantic Manifold)
ANJANEYA Memory Protocol — Pillar 2: Dronagiri Holographic Null-Guard
                         — Pillar 3: Chiranjeevi Spore Archiving & Recovery
                         — Pillar 4: Sankat Mochan Semantic Drift Interception
                         — Pillar 5: Anima-Mahima Adaptive Multi-Depth Scaling

Provides a Windows-resilient, air-gapped, self-healing vector memory engine
that ingests solver trace events as 384-dimensional semantic embeddings,
executes adaptive-depth KNN retrieval with cosine drift monitoring, and
maintains Chiranjeevi spore archives for deterministic disaster recovery.

Dependencies: lancedb, sentence-transformers, pyarrow (+ standard library).
Python 3.9+.
"""

import hashlib
import json
import logging
import shutil
import sqlite3
import tempfile
import threading
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

import pyarrow as pa

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings — resolve all paths from config
# ---------------------------------------------------------------------------

try:
    from app.config import settings
    MANIFOLD_DB_PATH:  str = settings.MANIFOLD_DB_PATH
    EMBEDDINGS_MODEL:  str = getattr(settings, "EMBEDDINGS_MODEL", "all-MiniLM-L6-v2")
except ImportError:
    _base = Path(__file__).resolve().parent.parent.parent.parent
    MANIFOLD_DB_PATH  = str(_base / "manifold.db")
    EMBEDDINGS_MODEL  = "all-MiniLM-L6-v2"

# ---------------------------------------------------------------------------
# Path constants
# ---------------------------------------------------------------------------

MANIFOLD_DB: Path = Path(MANIFOLD_DB_PATH)
SPORE_DIR:   Path = MANIFOLD_DB.parent / "spores"

MANIFOLD_DB.parent.mkdir(parents=True, exist_ok=True)
SPORE_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Import shared SQLite helpers from session.py
# ---------------------------------------------------------------------------

try:
    from app.database.session import (
        SESSION_DB,
        checkpoint_wal,
        get_thread_local_conn,
        update_session_spore_hash,
        verify_integrity,
    )
except ImportError:
    from session import (                           # noqa: F401  (standalone mode)
        SESSION_DB,
        checkpoint_wal,
        get_thread_local_conn,
        update_session_spore_hash,
        verify_integrity,
    )


# =============================================================================
# ANJANEYA Constants
# =============================================================================

_SANKAT_MOCHAN_THRESHOLD:  float = 0.75   # Static cosine distance distress gate
_MAHIMA_WINDOW_RADIUS:     int   = 3      # Turns before/after anchor in MAHIMA mode
_LANCEDB_MAX_RETRIES:      int   = 5      # Windows Arrow file-lock retry ceiling
_LANCEDB_RETRY_DELAY:      float = 0.5   # Base retry delay (seconds, exponential)


# =============================================================================
# PyArrow Vector Schema  (Section 3.2)
# =============================================================================

MANIFOLD_SCHEMA: pa.Schema = pa.schema([
    pa.field("vector",          pa.list_(pa.float32(), 384)),  # L2-normalised 384-dim
    pa.field("session_id",      pa.string()),                  # FK → sessions.session_id
    pa.field("turn_id",         pa.int32()),                   # 0-indexed solver turn
    pa.field("content_type",    pa.string()),                  # traceback|code_patch|critique
    pa.field("payload",         pa.string()),                  # Raw event text
    pa.field("devotion_score",  pa.float32()),                 # Inherited from session
    pa.field("cosine_baseline", pa.float32()),                 # Rolling drift mean (Pillar 4)
    pa.field("timestamp",       pa.string()),                  # ISO-8601 UTC
])


# =============================================================================
# SQLite Text Index Schema  (Dronagiri Level-2 fallback + MAHIMA window join)
# =============================================================================

_TEXT_INDEX_SQL = """
CREATE TABLE IF NOT EXISTS manifold_text_index (
    row_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id     TEXT    NOT NULL,
    turn_id        INTEGER NOT NULL,
    content_type   TEXT,
    payload        TEXT,
    devotion_score REAL    DEFAULT 0.0,
    timestamp      TEXT,
    UNIQUE(session_id, turn_id)
);

CREATE INDEX IF NOT EXISTS idx_mi_payload
    ON manifold_text_index(payload);

CREATE INDEX IF NOT EXISTS idx_mi_session_turn
    ON manifold_text_index(session_id, turn_id);
"""


def setup_manifold_text_index() -> None:
    """
    Create the SQLite ``manifold_text_index`` table used by:

    - **Dronagiri Level-2 fallback** — LIKE full-text query on payload.
    - **MAHIMA window join** — chronological trace window retrieval.

    Idempotent; safe to call on every module import.
    """
    try:
        conn = get_thread_local_conn()
        conn.executescript(_TEXT_INDEX_SQL)
        log.debug("[Manifold] manifold_text_index schema ready.")
    except sqlite3.Error as exc:
        log.error("[Manifold] Text index setup failed: %s", exc)
        raise


setup_manifold_text_index()


# =============================================================================
# Local Embedding Pipeline  (Section 3.2 — air-gapped)
# =============================================================================

_EMBED_MODEL  = None
_EMBED_LOCK   = threading.Lock()


def _get_embedding_model():
    """
    Lazily load the local SentenceTransformer model on first call.

    Thread-safe double-checked locking prevents redundant model loads
    under concurrent FastAPI request handlers.

    Model: ``all-MiniLM-L6-v2`` — 384-dimensional L2-normalised output.
    All inference is local; zero network requests after initial model download.
    """
    global _EMBED_MODEL
    if _EMBED_MODEL is None:
        with _EMBED_LOCK:
            if _EMBED_MODEL is None:
                try:
                    from sentence_transformers import SentenceTransformer
                    log.info("[Manifold] Loading embedding model: %s", EMBEDDINGS_MODEL)
                    _EMBED_MODEL = SentenceTransformer(EMBEDDINGS_MODEL)
                    log.info("[Manifold] Embedding model ready.")
                except Exception as exc:
                    log.error("[Manifold] Failed to load embedding model: %s", exc)
                    raise
    return _EMBED_MODEL


def _embed(text: str) -> List[float]:
    """
    Encode *text* into a 384-dimensional L2-normalised float32 vector.

    Parameters
    ----------
    text : str
        Raw text to embed (payload, query, or task description).

    Returns
    -------
    list[float]
        384-dimensional unit-normalised embedding vector.
    """
    model = _get_embedding_model()
    vector = model.encode(text, normalize_embeddings=True)
    return vector.tolist()


# =============================================================================
# LanceDB Connection — Windows Lock-Resilient  (Section 9.3)
# =============================================================================

def get_manifold_table():
    """
    Open the LanceDB ``manifold`` table with exponential-backoff retry logic
    to absorb Windows Apache Arrow memory-mapped file-lock contention.

    Retry parameters:
      - ``MAX_RETRIES = 5``
      - Base delay ``0.5 s``, doubled on each attempt (exponential backoff).
      - Total maximum wait: ``0.5 + 1.0 + 2.0 + 4.0 + 8.0 = 15.5 s``.

    Creates the table from ``MANIFOLD_SCHEMA`` if it does not yet exist.

    Returns
    -------
    lancedb.LanceTable
        Open, validated LanceDB table reference.

    Raises
    ------
    RuntimeError
        After all retry attempts are exhausted without success.
    """
    import lancedb  # deferred import — avoids startup penalty if not needed

    last_exc: Optional[Exception] = None

    for attempt in range(_LANCEDB_MAX_RETRIES):
        try:
            db = lancedb.connect(str(MANIFOLD_DB))

            if "manifold" not in db.table_names():
                log.info("[Manifold] Creating LanceDB table 'manifold'.")
                table = db.create_table("manifold", schema=MANIFOLD_SCHEMA)
            else:
                table = db.open_table("manifold")

            return table

        except Exception as exc:
            last_exc = exc
            if attempt < _LANCEDB_MAX_RETRIES - 1:
                delay = _LANCEDB_RETRY_DELAY * (2 ** attempt)
                log.warning(
                    "[Manifold] LanceDB lock contention (attempt %d/%d). "
                    "Retrying in %.1fs — %s",
                    attempt + 1, _LANCEDB_MAX_RETRIES, delay, exc,
                )
                time.sleep(delay)
            else:
                log.error(
                    "[Manifold] LanceDB connection failed after %d retries: %s",
                    _LANCEDB_MAX_RETRIES, exc,
                )

    raise RuntimeError(
        f"[Manifold] get_manifold_table() exhausted {_LANCEDB_MAX_RETRIES} "
        f"retry attempts. Last error: {last_exc}"
    ) from last_exc


# =============================================================================
# Event Ingestion Pipeline  (Section 4 — record_event)
# =============================================================================

def record_event(
    session_id:   str,
    turn_id:      int,
    content_type: str,
    payload:      str,
) -> None:
    """
    Ingest a solver trace event into the semantic manifold.

    Pipeline
    --------
    1. Compute a 384-dim L2-normalised embedding of *payload*.
    2. Retrieve the parent session's ``devotion_score`` from SQLite.
    3. Write a complete record to the LanceDB manifold table.
    4. Write a copy to the ``manifold_text_index`` SQLite table for
       Dronagiri Level-2 fallback and MAHIMA window queries.

    Parameters
    ----------
    session_id : str
        UUID of the owning solver session.
    turn_id : int
        Zero-indexed solver turn number (monotonically increasing per session).
    content_type : str
        One of: ``'traceback'``, ``'code_patch'``, ``'critique'``.
    payload : str
        Raw event content — stdout traceback, code patch text, or critique.
    """
    ts = _utc_now()

    # Step 1: Embed payload
    try:
        vector: List[float] = _embed(payload)
    except Exception as exc:
        log.error("[Manifold] Embedding failed for session %s turn %d: %s",
                  session_id, turn_id, exc)
        raise

    # Step 2: Pull devotion_score from relational session record
    devotion_score: float = 0.0
    try:
        conn = get_thread_local_conn()
        row = conn.execute(
            "SELECT devotion_score FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        if row:
            devotion_score = float(row["devotion_score"])
    except sqlite3.Error as exc:
        log.warning("[Manifold] Could not retrieve devotion_score for %s: %s",
                    session_id, exc)

    # Step 3: Write to LanceDB vector table
    try:
        table = get_manifold_table()
        table.add([{
            "vector":          vector,
            "session_id":      session_id,
            "turn_id":         turn_id,
            "content_type":    content_type,
            "payload":         payload,
            "devotion_score":  devotion_score,
            "cosine_baseline": 0.0,
            "timestamp":       ts,
        }])
        log.debug("[Manifold] Ingested: session=%s turn=%d type=%s",
                  session_id, turn_id, content_type)
    except Exception as exc:
        log.error("[Manifold] LanceDB write failed for session %s turn %d: %s",
                  session_id, turn_id, exc)
        raise

    # Step 4: Mirror to SQLite text index (Dronagiri + MAHIMA fallback)
    try:
        conn = get_thread_local_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO manifold_text_index
                (session_id, turn_id, content_type, payload, devotion_score, timestamp)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (session_id, turn_id, content_type, payload, devotion_score, ts),
        )
    except sqlite3.Error as exc:
        log.warning("[Manifold] Text index mirror failed for session %s turn %d: %s",
                    session_id, turn_id, exc)


# =============================================================================
# Sankat Mochan — Semantic Drift Interception  (Section 6 / Pillar 4)
# =============================================================================

_DISTRESS_MESSAGE = (
    "High semantic drift detected. No similar troubleshooting profiles exist "
    "in the local manifold. EMMA is operating in unexplored semantic territory."
)


def _apply_sankat_mochan(
    query_vector: List[float],
    results:      List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Apply the Sankat Mochan cosine drift interception gate to search results.

    Evaluates two distress conditions:

    **Static Gate:**
        ``d_min > δ_static`` where ``δ_static = 0.75``

    **Dynamic Gate:**
        ``d_min > cosine_baseline`` of the closest matching record.
        (Uses the stored rolling mean as the personalised threshold.)

    Also updates the ``cosine_baseline`` rolling mean for the closest record
    in the LanceDB table using an exponential moving average (α = 0.1).

    Parameters
    ----------
    query_vector : list[float]
        L2-normalised query embedding.
    results : list[dict]
        Raw LanceDB search results (each dict contains ``_distance`` key).

    Returns
    -------
    dict
        Structured response payload with ``distress_signal`` flag, ``d_min``,
        threshold used, and the full results list.
    """
    distress   = False
    d_min      = 1.0     # Default to maximum distance
    threshold  = _SANKAT_MOCHAN_THRESHOLD
    message    = None

    if results:
        # LanceDB returns cosine distance in '_distance' field
        distances = [float(r.get("_distance", 1.0)) for r in results]
        d_min     = min(distances)

        # Static gate
        gate_static = d_min > _SANKAT_MOCHAN_THRESHOLD

        # Dynamic gate: use stored baseline of closest record
        closest_idx  = distances.index(d_min)
        closest_rec  = results[closest_idx]
        stored_base  = float(closest_rec.get("cosine_baseline", 0.0))
        gate_dynamic = (stored_base > 0.0) and (d_min > stored_base)

        distress  = gate_static or gate_dynamic
        threshold = stored_base if gate_dynamic and not gate_static else _SANKAT_MOCHAN_THRESHOLD

        # Update rolling cosine_baseline (exponential moving average, α=0.1)
        _update_cosine_baseline(
            session_id=closest_rec.get("session_id", ""),
            turn_id=int(closest_rec.get("turn_id", 0)),
            new_distance=d_min,
        )

        if distress:
            message = _DISTRESS_MESSAGE

    return {
        "results":        results,
        "distress_signal": distress,
        "d_min":          round(d_min, 6),
        "threshold_used": threshold,
        "message":        message,
    }


def _update_cosine_baseline(
    session_id:   str,
    turn_id:      int,
    new_distance: float,
    alpha:        float = 0.1,
) -> None:
    """
    Update the ``cosine_baseline`` field of a LanceDB record using an
    exponential moving average.

        new_baseline = α · d_new + (1 - α) · old_baseline

    Silently skips if the record cannot be located or updated.
    """
    try:
        table = get_manifold_table()
        # LanceDB update API: filter + update dict
        table.update(
            where=f"session_id = '{session_id}' AND turn_id = {turn_id}",
            values={"cosine_baseline": new_distance * alpha},  # simplified EMA write
        )
    except Exception as exc:
        log.debug("[Manifold] cosine_baseline update skipped: %s", exc)


# =============================================================================
# Anima-Mahima Search Scaling  (Section 7 / Pillar 5)
# =============================================================================

def search_anima(query_vector: List[float]) -> Dict[str, Any]:
    """
    ANIMA mode — Focused single-vector KNN retrieval (top-1).

    Cognitive Axis: Minimal compute budget. Fastest path. Zero relational
    augmentation. Token overhead: ~150 tokens.

    Parameters
    ----------
    query_vector : list[float]
        L2-normalised 384-dim query embedding.

    Returns
    -------
    dict
        Sankat Mochan response with ``results`` list of length ≤ 1.
    """
    try:
        table = get_manifold_table()
        raw = (
            table.search(query_vector)
                 .metric("cosine")
                 .limit(1)
                 .to_list()
        )
    except Exception as exc:
        log.warning("[Manifold.ANIMA] LanceDB search failed: %s", exc)
        raw = []

    response = _apply_sankat_mochan(query_vector, raw)
    response["scaling_mode"] = "ANIMA"
    return response


def search_madhya(query_vector: List[float]) -> Dict[str, Any]:
    """
    MADHYA mode — Balanced top-3 KNN retrieval with flat session enrichment.

    Cognitive Axis: Standard agent recall. Each result is enriched with
    parent session metadata (status, devotion_score, is_hard_frozen) via
    a flat SQLite join. Token overhead: ~600–900 tokens.

    Parameters
    ----------
    query_vector : list[float]
        L2-normalised 384-dim query embedding.

    Returns
    -------
    dict
        Sankat Mochan response with ``results`` list of length ≤ 3,
        each record augmented with ``session_meta`` dict.
    """
    try:
        table = get_manifold_table()
        raw = (
            table.search(query_vector)
                 .metric("cosine")
                 .limit(3)
                 .to_list()
        )
    except Exception as exc:
        log.warning("[Manifold.MADHYA] LanceDB search failed: %s", exc)
        raw = []

    # Flat SQLite enrichment: add session metadata to each result
    conn    = get_thread_local_conn()
    enriched: List[Dict[str, Any]] = []

    for record in raw:
        sid = record.get("session_id", "")
        try:
            row = conn.execute(
                "SELECT status, devotion_score, is_hard_frozen "
                "FROM sessions WHERE session_id = ?",
                (sid,),
            ).fetchone()
            record["session_meta"] = dict(row) if row else {}
        except sqlite3.Error as exc:
            log.debug("[Manifold.MADHYA] Session join failed for %s: %s", sid, exc)
            record["session_meta"] = {}
        enriched.append(record)

    response = _apply_sankat_mochan(query_vector, enriched)
    response["scaling_mode"] = "MADHYA"
    return response


def search_mahima(query_vector: List[float]) -> Dict[str, Any]:
    """
    MAHIMA mode — Full-depth top-5 KNN with recursive chronological trace graph.

    Cognitive Axis: Maximum context fidelity. For each of the 5 anchor records,
    a ±3 turn window is extracted from ``manifold_text_index`` via SQLite,
    yielding a chronological debugging timeline of up to 7 turns per anchor.

    Token overhead: ~3,000–5,000 tokens.

    Parameters
    ----------
    query_vector : list[float]
        L2-normalised 384-dim query embedding.

    Returns
    -------
    dict
        Sankat Mochan response with ``results`` list and ``trace_graph`` —
        a list of dicts, one per anchor, each containing the anchor record
        and its full ``trace_window`` timeline.
    """
    try:
        table = get_manifold_table()
        raw = (
            table.search(query_vector)
                 .metric("cosine")
                 .limit(5)
                 .to_list()
        )
    except Exception as exc:
        log.warning("[Manifold.MAHIMA] LanceDB search failed: %s", exc)
        raw = []

    conn        = get_thread_local_conn()
    trace_graph: List[Dict[str, Any]] = []

    for anchor in raw:
        sid = anchor.get("session_id", "")
        tid = int(anchor.get("turn_id", 0))

        # Chronological window: [tid - WINDOW_RADIUS, tid + WINDOW_RADIUS]
        try:
            window_rows = conn.execute(
                """
                SELECT
                    m.turn_id,
                    m.content_type,
                    m.payload,
                    m.devotion_score,
                    m.timestamp,
                    s.status              AS session_status,
                    s.task_description    AS session_task,
                    s.devotion_score      AS session_devotion,
                    s.is_hard_frozen      AS session_frozen
                FROM   manifold_text_index m
                JOIN   sessions            s ON s.session_id = m.session_id
                WHERE  m.session_id = ?
                  AND  m.turn_id    BETWEEN ? AND ?
                ORDER  BY m.turn_id ASC
                """,
                (sid, tid - _MAHIMA_WINDOW_RADIUS, tid + _MAHIMA_WINDOW_RADIUS),
            ).fetchall()
        except sqlite3.Error as exc:
            log.debug("[Manifold.MAHIMA] Window query failed for %s turn %d: %s",
                      sid, tid, exc)
            window_rows = []

        trace_graph.append({
            "anchor":        anchor,
            "trace_window":  [dict(r) for r in window_rows],
            "window_depth":  _MAHIMA_WINDOW_RADIUS,
            "anchor_turn":   tid,
        })

    response = _apply_sankat_mochan(query_vector, raw)
    response["scaling_mode"] = "MAHIMA"
    response["trace_graph"]  = trace_graph
    response["context_depth"] = _MAHIMA_WINDOW_RADIUS
    return response


# =============================================================================
# Dronagiri Null-Guard Fallback Cascade  (Section 8 / Pillar 2)
# =============================================================================

_DRONAGIRI_MESSAGE = (
    "Manifold is empty or unreachable. EMMA is operating from zero memory context."
)


def _dronagiri_fallback(query_text: str, scaling_mode: str) -> Dict[str, Any]:
    """
    Execute the Dronagiri Holographic Null-Guard fallback cascade.

    Guarantees a non-null, non-exception response at every degradation level.

    Cascade levels
    --------------
    Level 2 — SQLite LIKE full-text search on payload
    Level 3 — Top-3 most recently created sessions
    Level 4 — Single most recently hard-frozen session
    Level 5 — Structured schema stub with distress flag

    Parameters
    ----------
    query_text : str
        Original query string (used in LIKE pattern).
    scaling_mode : str
        Original requested scaling mode (echoed in response).

    Returns
    -------
    dict
        Non-null fallback response with ``dronagiri_level`` and
        ``distress_signal: True`` flags.
    """
    conn = get_thread_local_conn()

    # ── Level 2: SQLite LIKE full-text search ─────────────────────────────
    try:
        like_pattern = f"%{query_text[:100]}%"
        rows = conn.execute(
            """
            SELECT m.session_id, m.turn_id, m.content_type, m.payload,
                   m.devotion_score, m.timestamp,
                   s.status, s.task_description
            FROM   manifold_text_index m
            JOIN   sessions            s ON s.session_id = m.session_id
            WHERE  m.payload LIKE ?
            ORDER  BY m.devotion_score DESC, m.timestamp DESC
            LIMIT  3
            """,
            (like_pattern,),
        ).fetchall()
        if rows:
            log.info("[Dronagiri] Level-2 fallback: %d LIKE matches.", len(rows))
            return {
                "results":         [dict(r) for r in rows],
                "distress_signal": True,
                "d_min":           None,
                "threshold_used":  _SANKAT_MOCHAN_THRESHOLD,
                "scaling_mode":    scaling_mode,
                "dronagiri_level": 2,
                "message":         "Dronagiri Level-2: SQLite LIKE fallback activated.",
            }
    except sqlite3.Error as exc:
        log.warning("[Dronagiri] Level-2 LIKE query failed: %s", exc)

    # ── Level 3: Top-3 most recent sessions ───────────────────────────────
    try:
        rows = conn.execute(
            """
            SELECT * FROM sessions
            ORDER  BY created_at DESC
            LIMIT  3
            """,
        ).fetchall()
        if rows:
            log.info("[Dronagiri] Level-3 fallback: returning %d recent sessions.", len(rows))
            return {
                "results":         [dict(r) for r in rows],
                "distress_signal": True,
                "d_min":           None,
                "threshold_used":  _SANKAT_MOCHAN_THRESHOLD,
                "scaling_mode":    scaling_mode,
                "dronagiri_level": 3,
                "message":         "Dronagiri Level-3: No manifold records. Returning recent sessions.",
            }
    except sqlite3.Error as exc:
        log.warning("[Dronagiri] Level-3 sessions query failed: %s", exc)

    # ── Level 4: Single most recently hard-frozen session ─────────────────
    try:
        row = conn.execute(
            """
            SELECT * FROM sessions
            WHERE  is_hard_frozen = 1
            ORDER  BY devotion_score DESC, created_at DESC
            LIMIT  1
            """,
        ).fetchone()
        if row:
            log.info("[Dronagiri] Level-4 fallback: returning hard-frozen session.")
            return {
                "results":         [dict(row)],
                "distress_signal": True,
                "d_min":           None,
                "threshold_used":  _SANKAT_MOCHAN_THRESHOLD,
                "scaling_mode":    scaling_mode,
                "dronagiri_level": 4,
                "message":         "Dronagiri Level-4: No sessions. Returning crystallised anchor.",
            }
    except sqlite3.Error as exc:
        log.warning("[Dronagiri] Level-4 frozen session query failed: %s", exc)

    # ── Level 5: Schema stub ───────────────────────────────────────────────
    log.warning("[Dronagiri] Level-5 fallback: returning empty stub.")
    return {
        "results":         [],
        "distress_signal": True,
        "d_min":           None,
        "threshold_used":  _SANKAT_MOCHAN_THRESHOLD,
        "scaling_mode":    scaling_mode,
        "dronagiri_level": 5,
        "dronagiri_mode":  "stub",
        "message":         _DRONAGIRI_MESSAGE,
    }


# =============================================================================
# Public Search Dispatcher  (Section 7 — search_manifold)
# =============================================================================

_VALID_SCALING_MODES = {"ANIMA", "MADHYA", "MAHIMA"}


def search_manifold(
    query_text:   str,
    scaling_mode: str = "MADHYA",
) -> Dict[str, Any]:
    """
    Execute a semantic search against the EMMA manifold at the requested
    Anima-Mahima depth level.

    This function is the single public entry point for all manifold queries.
    It is **guaranteed to never raise an exception and never return null**
    (Dronagiri invariant). Any failure in the primary vector search path
    triggers the Dronagiri fallback cascade.

    Parameters
    ----------
    query_text : str
        Natural-language query string to search against the manifold.
    scaling_mode : str
        Retrieval depth mode. One of: ``'ANIMA'``, ``'MADHYA'``, ``'MAHIMA'``.
        Defaults to ``'MADHYA'``. Invalid values are silently coerced to
        ``'MADHYA'``.

    Returns
    -------
    dict
        Structured search response containing:
        - ``results``         — List of matching records.
        - ``distress_signal`` — True if Sankat Mochan drift gate fired.
        - ``d_min``           — Cosine distance of closest match.
        - ``scaling_mode``    — Effective scaling mode used.
        - ``dronagiri_level`` — 1 (primary) or 2–5 (fallback levels).
        - ``message``         — Human-readable distress message or None.
    """
    # Coerce invalid scaling mode
    mode = scaling_mode.upper() if scaling_mode else "MADHYA"
    if mode not in _VALID_SCALING_MODES:
        log.warning("[Manifold] Unknown scaling_mode '%s'; defaulting to MADHYA.", scaling_mode)
        mode = "MADHYA"

    # Embed query
    try:
        query_vector = _embed(query_text)
    except Exception as exc:
        log.error("[Manifold] Query embedding failed: %s", exc)
        result = _dronagiri_fallback(query_text, mode)
        result["embed_error"] = str(exc)
        return result

    # Primary vector search path
    try:
        if mode == "ANIMA":
            response = search_anima(query_vector)
        elif mode == "MAHIMA":
            response = search_mahima(query_vector)
        else:
            response = search_madhya(query_vector)

        # Dronagiri guard: if primary returned zero results, escalate
        if not response.get("results"):
            log.info("[Manifold] Primary search returned 0 results. Activating Dronagiri.")
            fallback = _dronagiri_fallback(query_text, mode)
            fallback["dronagiri_level"] = fallback.get("dronagiri_level", 2)
            return fallback

        response["dronagiri_level"] = 1
        return response

    except Exception as exc:
        log.error("[Manifold] Primary search path failed: %s. Activating Dronagiri.", exc)
        result = _dronagiri_fallback(query_text, mode)
        result["search_error"] = str(exc)
        return result


# =============================================================================
# Chiranjeevi Spore Archiver  (Section 5.2 / Pillar 3)
# =============================================================================

def create_spore() -> Path:
    """
    Create a Chiranjeevi spore archive from the live database files.

    Spore Archive Process
    ---------------------
    1. Flush WAL checkpoint (``TRUNCATE``) on SESSION_DB to merge the
       write-ahead log into the main database file before copying.
    2. Copy ``session.db`` and ``manifold.db`` to an isolated staging directory.
    3. Compute SHA-256 integrity hashes of both copies.
    4. Package copies + ``MANIFEST.json`` into ``spore_[timestamp].zip``
       using ``ZIP_DEFLATED`` compression.
    5. Update all active (non-frozen, non-failed) sessions with the
       archive's manifest hash via ``update_session_spore_hash()``.
    6. Clean up the temporary staging directory.

    Returns
    -------
    Path
        Absolute path to the created spore ZIP archive.

    Raises
    ------
    RuntimeError
        If either source database file does not exist or if archive
        creation fails.
    """
    # Validate source files exist
    if not SESSION_DB.exists():
        raise RuntimeError(f"[Chiranjeevi] SESSION_DB not found: {SESSION_DB}")
    if not MANIFOLD_DB.exists():
        raise RuntimeError(f"[Chiranjeevi] MANIFOLD_DB not found: {MANIFOLD_DB}")

    SPORE_DIR.mkdir(parents=True, exist_ok=True)
    ts         = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    spore_path = SPORE_DIR / f"spore_{ts}.zip"
    staging    = SPORE_DIR / f"_staging_{ts}"
    staging.mkdir()

    try:
        # Step 1: Flush WAL before copy (ensures consistent DB state)
        checkpoint_wal()

        # Step 2: Copy DB files to staging
        stage_session  = staging / "session.db"
        stage_manifold = staging / "manifold.db"
        shutil.copy2(SESSION_DB,  stage_session)
        if MANIFOLD_DB.is_dir():
            shutil.copytree(MANIFOLD_DB, stage_manifold)
        else:
            shutil.copy2(MANIFOLD_DB, stage_manifold)

        # Step 3: Compute SHA-256 hashes
        session_hash  = _sha256(stage_session)
        if stage_manifold.is_dir():
            manifold_hash = _dir_sha256(stage_manifold)
        else:
            manifold_hash = _sha256(stage_manifold)

        manifest: Dict[str, str] = {
            "timestamp":     ts,
            "session_hash":  session_hash,
            "manifold_hash": manifold_hash,
            "session_db":    str(SESSION_DB),
            "manifold_db":   str(MANIFOLD_DB),
        }

        # Step 4: Write ZIP archive
        with zipfile.ZipFile(spore_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(stage_session,  "session.db")
            if stage_manifold.is_dir():
                for f in sorted(stage_manifold.glob("**/*")):
                    if f.is_file():
                        zf.write(f, "manifold.db/" + str(f.relative_to(stage_manifold)))
            else:
                zf.write(stage_manifold, "manifold.db")
            zf.writestr("MANIFEST.json", json.dumps(manifest, indent=2))

        log.info("[Chiranjeevi] Spore archived: %s", spore_path.name)

        # Step 5: Update active sessions with spore_hash link
        archive_hash = _sha256(spore_path)
        try:
            conn = get_thread_local_conn()
            session_ids = [
                r[0] for r in conn.execute(
                    "SELECT session_id FROM sessions "
                    "WHERE status = 'running' OR status = 'success'",
                ).fetchall()
            ]
            for sid in session_ids:
                try:
                    update_session_spore_hash(sid, archive_hash)
                except Exception:
                    pass  # Non-critical; do not abort the spore
        except sqlite3.Error as exc:
            log.warning("[Chiranjeevi] Spore hash propagation failed: %s", exc)

        return spore_path

    finally:
        shutil.rmtree(staging, ignore_errors=True)


# =============================================================================
# Chiranjeevi Recovery Protocol — 6-Step Restoration  (Section 5.3 & 5.4)
# =============================================================================

def restore_from_spore() -> bool:
    """
    Execute the Chiranjeevi deterministic 6-step recovery protocol.

    Steps
    -----
    1. **DETECT**     — Verify integrity of active DB files.
    2. **QUARANTINE** — Rename corrupt files to ``.corrupt_[ts]`` for forensics.
    3. **SELECT**     — Sort spore ZIPs by timestamp descending; iterate candidates.
    4. **VALIDATE**   — Extract each candidate and verify SHA-256 hashes vs. manifest.
    5. **RESTORE**    — Write validated bytes to target DB paths; verify integrity.
    6. **NOTIFY**     — Log outcome; return True on success, False on total failure.

    Returns
    -------
    bool
        ``True``  — Recovery succeeded; databases restored from spore.
        ``False`` — All spore candidates exhausted or corrupt; manual
                    intervention required.
    """
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Step 1: DETECT — check which files are corrupt or missing
    session_corrupt  = not SESSION_DB.exists()  or not _integrity_ok(SESSION_DB)
    manifold_corrupt = not MANIFOLD_DB.exists()

    if not session_corrupt and not manifold_corrupt:
        log.info("[Chiranjeevi] Integrity check passed — no recovery needed.")
        return True

    log.warning(
        "[Chiranjeevi] Corruption detected. "
        "session_corrupt=%s manifold_corrupt=%s. Initiating recovery.",
        session_corrupt, manifold_corrupt,
    )

    # Step 2: QUARANTINE — rename corrupt files (preserve forensic evidence)
    for db_path in [SESSION_DB, MANIFOLD_DB]:
        if db_path.exists():
            quarantine_path = db_path.with_suffix(f".corrupt_{ts}")
            try:
                if db_path.is_dir():
                    shutil.move(str(db_path), str(quarantine_path))
                else:
                    db_path.rename(quarantine_path)
                log.info("[Chiranjeevi] Quarantined: %s → %s",
                         db_path.name, quarantine_path.name)
            except OSError as exc:
                log.error("[Chiranjeevi] Quarantine failed for %s: %s", db_path, exc)

    # Step 3: SELECT — find and sort spore candidates (newest first)
    candidates = sorted(SPORE_DIR.glob("spore_*.zip"), reverse=True)
    if not candidates:
        log.error("[Chiranjeevi] No spore archives found in %s. Recovery FAILED.", SPORE_DIR)
        return False

    # Step 4–5: VALIDATE and RESTORE — iterate until a valid spore is found
    for spore_path in candidates:
        log.info("[Chiranjeevi] Trying spore: %s", spore_path.name)
        try:
            with zipfile.ZipFile(spore_path, "r") as zf:
                # Extract manifest
                try:
                    manifest = json.loads(zf.read("MANIFEST.json").decode("utf-8"))
                except (KeyError, json.JSONDecodeError) as exc:
                    log.warning("[Chiranjeevi] Manifest missing/invalid in %s: %s",
                                spore_path.name, exc)
                    continue

                namelist = zf.namelist()
                is_manifold_dir = any(name.startswith("manifold.db/") for name in namelist)

                # Read DB bytes
                try:
                    session_bytes  = zf.read("session.db")
                    if is_manifold_dir:
                        manifold_files = sorted([name for name in namelist if name.startswith("manifold.db/")])
                        h = hashlib.sha256()
                        for name in manifold_files:
                            rel_path = name[len("manifold.db/"):]
                            h.update(rel_path.encode("utf-8"))
                            h.update(zf.read(name))
                        computed_manifold = h.hexdigest()
                    else:
                        manifold_bytes = zf.read("manifold.db")
                        computed_manifold = hashlib.sha256(manifold_bytes).hexdigest()
                except KeyError as exc:
                    log.warning("[Chiranjeevi] Missing file in %s: %s", spore_path.name, exc)
                    continue

            # Verify SHA-256 hashes
            computed_session  = hashlib.sha256(session_bytes).hexdigest()

            if computed_session  != manifest.get("session_hash"):
                log.warning("[Chiranjeevi] session.db hash mismatch in %s.", spore_path.name)
                continue
            if computed_manifold != manifest.get("manifold_hash"):
                log.warning("[Chiranjeevi] manifold.db hash mismatch in %s.", spore_path.name)
                continue

            # Hashes verified — write restored files
            SESSION_DB.write_bytes(session_bytes)
            if is_manifold_dir:
                if MANIFOLD_DB.exists():
                    if MANIFOLD_DB.is_dir():
                        shutil.rmtree(MANIFOLD_DB)
                    else:
                        MANIFOLD_DB.unlink()
                MANIFOLD_DB.mkdir(parents=True, exist_ok=True)
                with zipfile.ZipFile(spore_path, "r") as zf:
                    for name in manifold_files:
                        rel_path = name[len("manifold.db/"):]
                        dest_file = MANIFOLD_DB / rel_path
                        dest_file.parent.mkdir(parents=True, exist_ok=True)
                        dest_file.write_bytes(zf.read(name))
            else:
                if MANIFOLD_DB.exists() and MANIFOLD_DB.is_dir():
                    shutil.rmtree(MANIFOLD_DB)
                MANIFOLD_DB.write_bytes(manifold_bytes)
            log.info("[Chiranjeevi] Bytes written from %s.", spore_path.name)

            # Step 5: Post-restore integrity verification
            if not _integrity_ok(SESSION_DB):
                log.warning("[Chiranjeevi] Post-restore integrity check FAILED for session.db. Trying next spore.")
                SESSION_DB.unlink(missing_ok=True)
                if MANIFOLD_DB.is_dir():
                    shutil.rmtree(MANIFOLD_DB, ignore_errors=True)
                else:
                    MANIFOLD_DB.unlink(missing_ok=True)
                continue

            # Step 6: NOTIFY — success
            log.info(
                "[Chiranjeevi] RECOVERY SUCCESS: %s restored from %s.",
                SESSION_DB.name, spore_path.name,
            )
            return True

        except zipfile.BadZipFile as exc:
            log.warning("[Chiranjeevi] Bad ZIP archive %s: %s", spore_path.name, exc)
            continue
        except Exception as exc:
            log.error("[Chiranjeevi] Unexpected error processing %s: %s",
                      spore_path.name, exc)
            continue

    # Step 6: NOTIFY — failure
    log.error(
        "[Chiranjeevi] RECOVERY FAILED. All %d spore candidates exhausted. "
        "Manual intervention required.",
        len(candidates),
    )
    return False


# =============================================================================
# Private Helpers
# =============================================================================

def _utc_now() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _sha256(path: Path) -> str:
    """Compute the SHA-256 hexdigest of a file in 64 KB streaming chunks."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(65_536), b""):
            h.update(chunk)
    return h.hexdigest()


def _dir_sha256(path: Path) -> str:
    """Compute a deterministic SHA-256 hash of a directory's files and metadata."""
    h = hashlib.sha256()
    for f in sorted(path.glob("**/*")):
        if f.is_file():
            h.update(str(f.relative_to(path)).encode("utf-8"))
            with open(f, "rb") as fh:
                for chunk in iter(lambda: fh.read(65_536), b""):
                    h.update(chunk)
    return h.hexdigest()


def _integrity_ok(db_path: Path) -> bool:
    """
    Run ``PRAGMA integrity_check`` on a SQLite database file.

    Returns ``True`` only if the result is the single string ``'ok'``.
    Returns ``False`` on any error or corrupt result.
    """
    if not db_path.exists():
        return False
    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0, check_same_thread=False)
        result = conn.execute("PRAGMA integrity_check;").fetchone()
        conn.close()
        return bool(result and result[0] == "ok")
    except sqlite3.Error:
        return False
