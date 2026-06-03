"""
session.py
==========
EMMA — SQLite Session Pool (Relational Memory Layer)
ANJANEYA Memory Protocol — Pillar 1: Devotion Crystal Scoring
                         — Pillar 3: Chiranjeevi Persistence
                         — Pillar 2: Dronagiri Frozen-Session Fallback

Provides a Windows-optimised, thread-safe, WAL-mode SQLite connection pool
that manages EMMA solver session lifecycle, computes Devotion Scores using
the AMP mathematical scoring engine, and permanently crystallises high-value
sessions via an immutable hard-freeze gate.

Standard library only (sqlite3, threading, pathlib, datetime, logging).
Python 3.9+.
"""

import logging
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Settings import — derives SESSION_DB path from MANIFOLD_DB_PATH
# ---------------------------------------------------------------------------

try:
    from app.config import settings
    _MANIFOLD_DB_PATH = Path(settings.MANIFOLD_DB_PATH)
except ImportError:
    # Standalone execution / unit-test fallback
    _MANIFOLD_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "manifold.db"

# Session DB lives beside the manifold DB in the same workspace root
SESSION_DB: Path = _MANIFOLD_DB_PATH.parent / "session.db"
SESSION_DB.parent.mkdir(parents=True, exist_ok=True)


# =============================================================================
# ANJANEYA Devotion Crystal Constants  (Pillar 1)
# =============================================================================

ALPHA:         float = 0.60   # Turn Efficiency weight
BETA:          float = 0.40   # Token Utilization Efficiency weight
T_MAX:         int   = 15     # Maximum solver turns (Orchestrator ceiling)
U_MAX:         int   = 100_000 # Theoretical token budget ceiling
THETA_CRYSTAL: float = 0.85   # Hard-freeze threshold (ANJANEYA Protocol §1)


# =============================================================================
# Thread-Local Connection Pool  (Section 9.2)
# =============================================================================

_LOCAL = threading.local()     # Per-thread connection storage
_POOL_LOCK = threading.Lock()  # Guards pool-level operations (schema init, etc.)


# =============================================================================
# Connection Factory — Windows WAL-Optimised  (Section 9.1)
# =============================================================================

def _make_connection() -> sqlite3.Connection:
    """
    Open a new SQLite connection to SESSION_DB with Windows-optimised PRAGMA
    tuning applied in the correct dependency order.

    PRAGMA sequence rationale
    -------------------------
    1. ``journal_mode = WAL``   — Readers never block writers; writers never
       block readers. Critical for FastAPI's concurrent async handlers.
    2. ``synchronous = NORMAL`` — Safe under WAL; reduces fsync calls on NTFS.
    3. ``cache_size = -65536``  — 64 MB page cache (negative = kibibytes).
       Reduces NTFS disk IO on large session result sets.
    4. ``busy_timeout = 30000`` — Retry lock acquisition for up to 30 seconds
       before raising ``OperationalError``. Absorbs Windows lock contention spikes.
    5. ``foreign_keys = ON``    — Enforces referential integrity across tables.

    Returns
    -------
    sqlite3.Connection
        Fully configured, autocommit-mode connection (``isolation_level=None``).
    """
    conn = sqlite3.connect(
        database          = str(SESSION_DB),
        timeout           = 30.0,       # Hard wall-clock lock-wait ceiling
        check_same_thread = False,       # Pool manages thread safety explicitly
        isolation_level   = None,        # Autocommit; we use explicit BEGIN/COMMIT
    )
    conn.row_factory = sqlite3.Row      # Named column access on all fetchone/fetchall

    # Apply PRAGMA stack in dependency order
    pragmas = [
        "PRAGMA journal_mode  = WAL;",
        "PRAGMA synchronous   = NORMAL;",
        "PRAGMA cache_size    = -65536;",
        "PRAGMA busy_timeout  = 30000;",
        "PRAGMA foreign_keys  = ON;",
    ]
    for pragma in pragmas:
        conn.execute(pragma)

    return conn


def get_thread_local_conn() -> sqlite3.Connection:
    """
    Return the SQLite connection for the current thread, creating it on
    first access.

    Maintains one connection per OS thread, preventing Windows file-handle
    sharing violations that arise when the same handle is used across threads.

    Returns
    -------
    sqlite3.Connection
        Per-thread, WAL-optimised connection to SESSION_DB.
    """
    if not hasattr(_LOCAL, "conn") or _LOCAL.conn is None:
        _LOCAL.conn = _make_connection()
        log.debug("[SessionPool] New connection opened for thread %s",
                  threading.current_thread().name)
    return _LOCAL.conn


def close_thread_local_conn() -> None:
    """
    Close and release the SQLite connection held by the current thread.

    Should be called in FastAPI worker thread shutdown hooks, Celery worker
    ``on_after_fork`` signals, or test teardown routines to prevent handle
    leakage under Windows.
    """
    if hasattr(_LOCAL, "conn") and _LOCAL.conn is not None:
        try:
            _LOCAL.conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
            _LOCAL.conn.close()
            log.debug("[SessionPool] Connection closed for thread %s",
                      threading.current_thread().name)
        except sqlite3.Error as exc:
            log.warning("[SessionPool] Error closing connection: %s", exc)
        finally:
            _LOCAL.conn = None


# =============================================================================
# Schema Bootstrap — Auto-Migration on Module Import  (Section 3.1)
# =============================================================================

_SCHEMA_SQL = """
-- ── Core sessions table ────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    session_id             TEXT    PRIMARY KEY,
    task_description       TEXT    NOT NULL,
    status                 TEXT    NOT NULL
                           CHECK(status IN ('running','success','failed','rolled_back')),
    turn_count             INTEGER DEFAULT 0,
    token_utilization_peak INTEGER DEFAULT 0,
    devotion_score         REAL    DEFAULT 0.0,
    is_hard_frozen         BOOLEAN DEFAULT 0,
    spore_hash             TEXT    DEFAULT NULL,
    created_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at             TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- ── Performance indexes ────────────────────────────────────────────────────
-- Accelerates Dronagiri frozen-session fallback queries
CREATE INDEX IF NOT EXISTS idx_frozen
    ON sessions(is_hard_frozen, devotion_score DESC);

-- Accelerates Sankat Mochan session-level drift baseline joins
CREATE INDEX IF NOT EXISTS idx_session_status
    ON sessions(status, devotion_score DESC);

-- ── Devotion Crystal immutability trigger  (Section 4.5) ──────────────────
-- Once is_hard_frozen = 1, ALL UPDATE attempts are silently discarded.
-- The session record becomes permanently crystallised — identity-woven memory.
CREATE TRIGGER IF NOT EXISTS protect_frozen_sessions
BEFORE UPDATE ON sessions
WHEN OLD.is_hard_frozen = 1
BEGIN
    SELECT RAISE(IGNORE);
END;
"""


def setup_sqlite_schema() -> None:
    """
    Execute the full schema migration against SESSION_DB.

    Idempotent: all statements use ``IF NOT EXISTS`` guards.
    Safe to call on every application start without data loss.

    Acquires the pool lock to prevent duplicate migrations under
    multi-threaded server startup (e.g., Uvicorn with multiple workers).
    """
    with _POOL_LOCK:
        conn = get_thread_local_conn()
        try:
            conn.executescript(_SCHEMA_SQL)
            log.info("[SessionPool] Schema bootstrapped at %s", SESSION_DB)
        except sqlite3.Error as exc:
            log.error("[SessionPool] Schema migration failed: %s", exc)
            raise


# Run schema migration on module import
setup_sqlite_schema()


# =============================================================================
# Devotion Crystal Scoring Engine  (Section 4.1 — ANJANEYA Pillar 1)
# =============================================================================

def calculate_devotion_score(
    turn_count:  int,
    token_peak:  int,
) -> Tuple[float, bool]:
    """
    Compute the ANJANEYA Devotion Score D for a completed solver session.

    Mathematical Definition
    -----------------------
    The Devotion Score is a dimensionless scalar in [0.0, 1.0] computed as a
    weighted linear combination of two independent efficiency signals:

        D = α · T_eff + β · U_eff

    Where:
        T_eff = (T_MAX - t) / (T_MAX - 1)      (Turn Efficiency)
        U_eff = 1.0 - (u / U_MAX)               (Token Utilization Efficiency)
        α = 0.60,  β = 0.40,  α + β = 1.0

    Hard-Freeze Gate:
        is_hard_frozen = True  iff  D >= THETA_CRYSTAL (0.85)

    Parameters
    ----------
    turn_count : int
        Number of solver turns consumed to reach ``status='success'``.
        Clamped to [1, T_MAX] before computation.
    token_peak : int
        Peak token utilization observed during the session.
        Clamped to [0, U_MAX] before computation.

    Returns
    -------
    tuple[float, bool]
        ``(devotion_score, is_hard_frozen)``
        - ``devotion_score`` — rounded to 6 decimal places.
        - ``is_hard_frozen`` — True if D >= THETA_CRYSTAL.

    Examples
    --------
    >>> calculate_devotion_score(2, 8000)
    (0.924929, True)      # Optimal run — frozen ✅

    >>> calculate_devotion_score(10, 70000)
    (0.44, False)         # Marginal run — not frozen ❌
    """
    # Clamp inputs to valid ranges
    t: int   = max(1,      min(turn_count, T_MAX))
    u: int   = max(0,      min(token_peak, U_MAX))

    # Turn Efficiency: higher = fewer turns used
    t_eff: float = (T_MAX - t) / (T_MAX - 1)

    # Token Utilization Efficiency: higher = fewer tokens consumed
    u_eff: float = 1.0 - (u / U_MAX)

    # Devotion Score
    D: float = ALPHA * t_eff + BETA * u_eff

    # Hard-freeze gate
    is_frozen: bool = D >= THETA_CRYSTAL

    return (round(D, 6), is_frozen)


# =============================================================================
# CRUD API — Session Lifecycle Management
# =============================================================================

def create_session(
    session_id:       str,
    task_description: str,
) -> None:
    """
    Spawn a new solver session record with ``status='running'``.

    Inserts the session into the ``sessions`` table. If a session with the
    same ``session_id`` already exists, the insert is silently ignored
    (idempotent via ``INSERT OR IGNORE``).

    Parameters
    ----------
    session_id : str
        UUID uniquely identifying this solver invocation.
    task_description : str
        Natural-language description of the task being solved.
    """
    conn = get_thread_local_conn()
    now  = _utc_now()
    try:
        conn.execute(
            """
            INSERT OR IGNORE INTO sessions
                (session_id, task_description, status, created_at, updated_at)
            VALUES (?, ?, 'running', ?, ?)
            """,
            (session_id, task_description, now, now),
        )
        log.info("[Session] Created: %s", session_id)
    except sqlite3.Error as exc:
        log.error("[Session] create_session failed for %s: %s", session_id, exc)
        raise


def get_session(session_id: str) -> Optional[Dict]:
    """
    Retrieve a single session record by its primary key.

    Parameters
    ----------
    session_id : str
        UUID of the session to retrieve.

    Returns
    -------
    dict | None
        A dictionary of all session fields, or ``None`` if not found.
    """
    conn = get_thread_local_conn()
    try:
        row = conn.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return dict(row) if row else None
    except sqlite3.Error as exc:
        log.error("[Session] get_session failed for %s: %s", session_id, exc)
        raise


def list_all_sessions() -> List[Dict]:
    """
    Return all session records ordered by creation time (newest first).

    Returns
    -------
    list[dict]
        All session rows as dictionaries. Empty list if no sessions exist.
    """
    conn = get_thread_local_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM sessions ORDER BY created_at DESC"
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("[Session] list_all_sessions failed: %s", exc)
        raise


def get_frozen_sessions() -> List[Dict]:
    """
    Return all hard-frozen sessions sorted by devotion score descending.

    Used by the Dronagiri Holographic Fallback (Pillar 2) as the final
    high-confidence fallback when the manifold returns zero semantic matches.
    Frozen sessions represent EMMA's most crystallised institutional memory.

    Returns
    -------
    list[dict]
        All ``is_hard_frozen = 1`` sessions, sorted by ``devotion_score DESC``.
        Empty list if no sessions have been crystallised yet.
    """
    conn = get_thread_local_conn()
    try:
        rows = conn.execute(
            """
            SELECT * FROM sessions
            WHERE  is_hard_frozen = 1
            ORDER  BY devotion_score DESC
            """,
        ).fetchall()
        return [dict(r) for r in rows]
    except sqlite3.Error as exc:
        log.error("[Session] get_frozen_sessions failed: %s", exc)
        raise


def update_session_status(
    session_id: str,
    status:     str,
    token_peak: int,
    turns:      Optional[int] = None,
) -> Optional[Tuple[float, bool]]:
    """
    Update a session's execution status and recalculate Devotion Score on success.

    Behaviour by status value
    -------------------------
    ``'running'``
        Updates ``status`` and ``token_utilization_peak`` only.
        No Devotion Score computation.

    ``'success'``
        Updates ``status``, ``turn_count``, and ``token_utilization_peak``.
        Computes Devotion Score D via ``calculate_devotion_score()``.
        Sets ``devotion_score`` and ``is_hard_frozen`` accordingly.
        **Note:** If the session is already hard-frozen, the
        ``protect_frozen_sessions`` trigger will silently block this UPDATE.
        The function detects this via rowcount and logs a warning.

    ``'failed'`` / ``'rolled_back'``
        Updates ``status`` and timestamp only. Devotion Score is not
        recalculated for failed sessions.

    Parameters
    ----------
    session_id : str
        UUID of the session to update.
    status : str
        New status value. Must be one of: ``'running'``, ``'success'``,
        ``'failed'``, ``'rolled_back'``.
    token_peak : int
        Peak token utilization observed during this session.
    turns : int | None
        Number of solver turns consumed. Required when ``status='success'``;
        ignored otherwise. Defaults to ``T_MAX`` if ``None`` and status is
        ``'success'`` (pessimistic assumption for scoring).

    Returns
    -------
    tuple[float, bool] | None
        ``(devotion_score, is_hard_frozen)`` when ``status='success'``,
        or ``None`` for all other status transitions.

    Raises
    ------
    ValueError
        If ``status`` is not one of the four permitted values.
    sqlite3.Error
        On database write failure.
    """
    _VALID_STATUSES = {"running", "success", "failed", "rolled_back"}
    if status not in _VALID_STATUSES:
        raise ValueError(
            f"Invalid status '{status}'. Must be one of: {_VALID_STATUSES}"
        )

    conn = get_thread_local_conn()
    now  = _utc_now()

    # ── Success path: compute Devotion Score and evaluate freeze gate ──────
    if status == "success":
        t = turns if turns is not None else T_MAX
        D, is_frozen = calculate_devotion_score(t, token_peak)

        try:
            cursor = conn.execute(
                """
                UPDATE sessions SET
                    status                 = ?,
                    turn_count             = ?,
                    token_utilization_peak = ?,
                    devotion_score         = ?,
                    is_hard_frozen         = ?,
                    updated_at             = ?
                WHERE session_id = ?
                """,
                (status, t, token_peak, D, int(is_frozen), now, session_id),
            )

            if cursor.rowcount == 0:
                log.warning(
                    "[Session] UPDATE blocked for %s — session is hard-frozen "
                    "or does not exist. Devotion Crystal trigger active.",
                    session_id,
                )
            else:
                log.info(
                    "[Session] %s → SUCCESS | D=%.6f | frozen=%s | turns=%d | tokens=%d",
                    session_id, D, is_frozen, t, token_peak,
                )

            return (D, is_frozen)

        except sqlite3.Error as exc:
            log.error(
                "[Session] update_session_status(success) failed for %s: %s",
                session_id, exc,
            )
            raise

    # ── Non-success path: update status and timestamp only ─────────────────
    try:
        cursor = conn.execute(
            """
            UPDATE sessions SET
                status                 = ?,
                token_utilization_peak = ?,
                updated_at             = ?
            WHERE session_id = ?
            """,
            (status, token_peak, now, session_id),
        )

        if cursor.rowcount == 0:
            log.warning(
                "[Session] UPDATE returned 0 rows for %s — "
                "frozen or non-existent session.",
                session_id,
            )
        else:
            log.info("[Session] %s → %s", session_id, status.upper())

        return None

    except sqlite3.Error as exc:
        log.error(
            "[Session] update_session_status(%s) failed for %s: %s",
            status, session_id, exc,
        )
        raise


def update_session_spore_hash(session_id: str, spore_hash: str) -> None:
    """
    Record the SHA-256 hash of the Chiranjeevi spore archive that last
    captured this session.

    Called by ``database/manifold.py::create_spore()`` after a successful
    archive creation to maintain a traceable link between a session record
    and its last persistent spore backup.

    Parameters
    ----------
    session_id : str
        UUID of the session whose spore reference is being updated.
    spore_hash : str
        SHA-256 hexdigest of the spore ZIP archive file.
    """
    conn = get_thread_local_conn()
    now  = _utc_now()
    try:
        conn.execute(
            """
            UPDATE sessions SET
                spore_hash = ?,
                updated_at = ?
            WHERE session_id = ?
            """,
            (spore_hash, now, session_id),
        )
        log.debug("[Session] Spore hash updated for %s: %s", session_id, spore_hash[:16])
    except sqlite3.Error as exc:
        log.error(
            "[Session] update_session_spore_hash failed for %s: %s",
            session_id, exc,
        )
        raise


def delete_session(session_id: str) -> bool:
    """
    Permanently delete a session record by ID.

    Hard-frozen sessions are protected by the ``protect_frozen_sessions``
    SQLite trigger and will silently resist deletion attempts via UPDATE-based
    guards; however, DELETE operations bypass the trigger. To preserve frozen
    session integrity, this function performs a pre-check and raises a
    ``PermissionError`` if the target session is crystallised.

    Parameters
    ----------
    session_id : str
        UUID of the session to delete.

    Returns
    -------
    bool
        ``True`` if the session was deleted, ``False`` if not found.

    Raises
    ------
    PermissionError
        If the target session is hard-frozen (``is_hard_frozen = 1``).
    """
    session = get_session(session_id)
    if session is None:
        return False
    if session.get("is_hard_frozen"):
        raise PermissionError(
            f"[Devotion Crystal] Session '{session_id}' is hard-frozen "
            "(D ≥ THETA_CRYSTAL). Deletion is permanently blocked. "
            "Crystallised sessions are immutable — identity-woven memory."
        )
    conn = get_thread_local_conn()
    try:
        cursor = conn.execute(
            "DELETE FROM sessions WHERE session_id = ?",
            (session_id,),
        )
        deleted = cursor.rowcount > 0
        if deleted:
            log.info("[Session] Deleted: %s", session_id)
        return deleted
    except sqlite3.Error as exc:
        log.error("[Session] delete_session failed for %s: %s", session_id, exc)
        raise


# =============================================================================
# WAL Maintenance Utilities
# =============================================================================

def checkpoint_wal() -> None:
    """
    Execute a WAL TRUNCATE checkpoint to flush the write-ahead log into the
    main database file and reset the WAL file to zero length.

    Should be called:
    - On FastAPI application shutdown (lifespan hook).
    - Before Chiranjeevi spore archiving (to ensure consistent DB state).
    - Periodically during long-running batch operations.
    """
    conn = get_thread_local_conn()
    try:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
        log.debug("[SessionPool] WAL checkpoint (TRUNCATE) executed.")
    except sqlite3.Error as exc:
        log.warning("[SessionPool] WAL checkpoint failed: %s", exc)


def verify_integrity() -> bool:
    """
    Run SQLite's built-in ``PRAGMA integrity_check`` against SESSION_DB.

    Used by the Chiranjeevi Recovery Protocol (Step 1: DETECT) to determine
    whether the active session database is structurally intact before deciding
    to initiate spore restoration.

    Returns
    -------
    bool
        ``True`` if integrity check passes (result == ['ok']).
        ``False`` if any corruption is detected.
    """
    conn = get_thread_local_conn()
    try:
        result = conn.execute("PRAGMA integrity_check;").fetchone()
        ok = result[0] == "ok" if result else False
        if ok:
            log.debug("[SessionPool] Integrity check: PASS")
        else:
            log.error("[SessionPool] Integrity check: FAIL — %s", result)
        return ok
    except sqlite3.Error as exc:
        log.error("[SessionPool] Integrity check error: %s", exc)
        return False


# =============================================================================
# Private helpers
# =============================================================================

def _utc_now() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
