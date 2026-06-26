"""
simulation_router.py
====================
EMMA Offline Completions Simulation & Fallback Router — Phase 2

Provides a dual-mode completions dispatcher for the EMMA Cognitive Engine:

  LIVE MODE:    Routes mutant generation requests to the real InferenceRouter
                (qwen2.5-coder via Ollama at localhost:11434).

  SIMULATION:   Returns pre-engineered, high-fidelity mock mutants instantly
                (<100ms) when EMMA_SIMULATION_MODE=1 or when the LLM endpoint
                is unreachable.

Simulation Mutant Contract per category:
  Mutant A — Clean, minimal, valid Python → WINNER   (~48.98 fitness score)
  Mutant B — Valid but verbose alternative → RUNNER   (~44.xx fitness score)
  Mutant C — Deliberate SyntaxError       → REJECTED (−100.0 fitness score)

All mutants are wrapped in <CODE_PROPOSAL>...</CODE_PROPOSAL> XML boundary
tags as required by DraftCoordinator._extract_code_proposal().

Standard library only. Zero external dependencies at module level.
Python 3.9+.
"""

import os
import re
from typing import List

# ---------------------------------------------------------------------------
# Simulation mode flag — set EMMA_SIMULATION_MODE=1 before demo execution
# ---------------------------------------------------------------------------

SIMULATION_MODE: bool = os.getenv("EMMA_SIMULATION_MODE", "0").strip() == "1"

# ---------------------------------------------------------------------------
# Task category keyword maps — used by _detect_category()
# ---------------------------------------------------------------------------

_CATEGORY_KEYWORDS: dict = {
    "oauth_repair": [
        "oauth", "bearer", "token", "authorization", "header",
        "401", "unauthorized", "http error", "urlopen", "auth",
    ],
    "sqlite_repair": [
        "sqlite", "database", "db", "locked", "operational error",
        "query", "sql", "cursor", "connection", "table",
    ],
    "file_io_repair": [
        "file", "open", "read", "write", "path", "filenotfound",
        "permission", "encoding", "utf-8", "io error", "shutil",
    ],
    "json_repair": [
        "json", "decode", "serialize", "jsondecodeerror", "parse",
        "loads", "dumps", "key error", "dict", "schema",
    ],
    "async_repair": [
        "asyncio", "async", "await", "coroutine", "event loop",
        "task", "gather", "timeout", "concurrent", "thread",
    ],
}


# =============================================================================
# High-Fidelity Simulation Patch Bank
# Each key is a category; each value contains mutant_a / mutant_b / mutant_c.
# All code blocks are wrapped in <CODE_PROPOSAL> XML boundary tags.
# =============================================================================

_DEMO_PATCHES: dict = {

    # ── OAuth 2.0 / HTTP Auth Repair ─────────────────────────────────────
    "oauth_repair": {
        "mutant_a": """\
<CODE_PROPOSAL>
def repair_token_header(headers: dict) -> dict:
    \"\"\"Repair malformed OAuth Bearer prefix to Token.\"\"\"
    if "Authorization" in headers:
        headers["Authorization"] = (
            headers["Authorization"].replace("Bearer ", "Token ")
        )
    return headers
</CODE_PROPOSAL>""",

        "mutant_b": """\
<CODE_PROPOSAL>
def repair_token_header(headers: dict) -> dict:
    \"\"\"
    Structural alternative: dict comprehension with conditional prefix rewrite.
    Handles both 'Bearer ' and 'bearer ' case variants defensively.
    \"\"\"
    def _fix(k: str, v: str) -> str:
        if k.lower() == "authorization":
            return re.sub(r"(?i)^bearer\\s+", "Token ", v)
        return v

    import re
    return {k: _fix(k, v) for k, v in headers.items()}
</CODE_PROPOSAL>""",

        "mutant_c": """\
<CODE_PROPOSAL>
def repair_token_header(headers: dict) -> dict:
    \"\"\"Wildcard mutant C — SyntaxError for rejection gate validation.\"\"\"
    if "Authorization" in headers
        headers["Authorization"] = headers["Authorization"].replace("Bearer ", "Token ")
    return headers
</CODE_PROPOSAL>""",
    },

    # ── SQLite / Database Repair ──────────────────────────────────────────
    "sqlite_repair": {
        "mutant_a": """\
<CODE_PROPOSAL>
def safe_sqlite_query(db_path: str, query: str, params: tuple = ()) -> list:
    \"\"\"Execute a parameterised SQLite query with WAL-mode resilience.\"\"\"
    import sqlite3
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute(query, params).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
</CODE_PROPOSAL>""",

        "mutant_b": """\
<CODE_PROPOSAL>
def safe_sqlite_query(db_path: str, query: str, params: tuple = ()) -> list:
    \"\"\"
    Structural alternative: context-manager pattern with explicit
    WAL checkpoint and row-factory enrichment.
    \"\"\"
    import sqlite3
    from contextlib import closing

    with closing(sqlite3.connect(db_path, timeout=30.0)) as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA busy_timeout = 30000;")
        conn.row_factory = sqlite3.Row
        with closing(conn.cursor()) as cursor:
            cursor.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
</CODE_PROPOSAL>""",

        "mutant_c": """\
<CODE_PROPOSAL>
def safe_sqlite_query(db_path: str, query: str, params: tuple = ()) -> list:
    \"\"\"Wildcard mutant C — deliberate SyntaxError for gate validation.\"\"\"
    import sqlite3
    conn = sqlite3.connect(db_path)
    if conn is not None
        return conn.execute(query, params).fetchall()
    return []
</CODE_PROPOSAL>""",
    },

    # ── File I/O Repair ───────────────────────────────────────────────────
    "file_io_repair": {
        "mutant_a": """\
<CODE_PROPOSAL>
def safe_read_file(file_path: str, encoding: str = "utf-8") -> str:
    \"\"\"Read a file with UTF-8 encoding and replace-fallback on decode errors.\"\"\"
    try:
        with open(file_path, "r", encoding=encoding) as fh:
            return fh.read()
    except UnicodeDecodeError:
        with open(file_path, "r", encoding=encoding, errors="replace") as fh:
            return fh.read()
</CODE_PROPOSAL>""",

        "mutant_b": """\
<CODE_PROPOSAL>
def safe_read_file(file_path: str, encoding: str = "utf-8") -> str:
    \"\"\"
    Structural alternative: pathlib-based read with explicit
    stat pre-check and multi-encoding fallback chain.
    \"\"\"
    from pathlib import Path

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    for enc in (encoding, "utf-8", "latin-1", "cp1252"):
        try:
            return path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue

    return path.read_text(encoding="utf-8", errors="replace")
</CODE_PROPOSAL>""",

        "mutant_c": """\
<CODE_PROPOSAL>
def safe_read_file(file_path: str, encoding: str = "utf-8") -> str:
    \"\"\"Wildcard mutant C — SyntaxError for rejection gate validation.\"\"\"
    with open(file_path, "r", encoding=encoding) as fh
        return fh.read()
</CODE_PROPOSAL>""",
    },

    # ── JSON Parsing Repair ───────────────────────────────────────────────
    "json_repair": {
        "mutant_a": """\
<CODE_PROPOSAL>
def safe_json_loads(raw: str) -> dict:
    \"\"\"Parse JSON with graceful error recovery on trailing commas/BOM.\"\"\"
    import json, re
    cleaned = raw.strip().lstrip("\\ufeff")
    cleaned = re.sub(r",\\s*([}\\]])", r"\\1", cleaned)
    return json.loads(cleaned)
</CODE_PROPOSAL>""",

        "mutant_b": """\
<CODE_PROPOSAL>
def safe_json_loads(raw: str) -> dict:
    \"\"\"
    Structural alternative: multi-stage cleaning pipeline with
    explicit error classification and partial recovery attempts.
    \"\"\"
    import json, re

    stages = [
        lambda s: s.strip().lstrip("\\ufeff"),
        lambda s: re.sub(r",\\s*([}\\]])", r"\\1", s),
        lambda s: re.sub(r"//[^\\n]*", "", s),
        lambda s: re.sub(r"/\\*.*?\\*/", "", s, flags=re.DOTALL),
    ]

    result = raw
    for stage in stages:
        result = stage(result)

    try:
        return json.loads(result)
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON repair failed after all stages: {exc}") from exc
</CODE_PROPOSAL>""",

        "mutant_c": """\
<CODE_PROPOSAL>
def safe_json_loads(raw: str) -> dict:
    \"\"\"Wildcard mutant C — SyntaxError for gate validation.\"\"\"
    import json
    if raw
        return json.loads(raw.strip())
    return {}
</CODE_PROPOSAL>""",
    },

    # ── Async / Event Loop Repair ─────────────────────────────────────────
    "async_repair": {
        "mutant_a": """\
<CODE_PROPOSAL>
import asyncio
from typing import Awaitable, TypeVar

T = TypeVar("T")

async def with_timeout(coro: Awaitable[T], timeout: float = 10.0) -> T:
    \"\"\"Wrap a coroutine with a hard timeout ceiling.\"\"\"
    return await asyncio.wait_for(coro, timeout=timeout)
</CODE_PROPOSAL>""",

        "mutant_b": """\
<CODE_PROPOSAL>
import asyncio
from typing import Any, Awaitable, Optional, TypeVar

T = TypeVar("T")

async def with_timeout(
    coro:     Awaitable[T],
    timeout:  float            = 10.0,
    fallback: Optional[Any]    = None,
) -> T:
    \"\"\"
    Structural alternative: timeout wrapper with optional fallback value
    on expiry instead of propagating TimeoutError to the caller.
    \"\"\"
    try:
        return await asyncio.wait_for(coro, timeout=timeout)
    except asyncio.TimeoutError:
        if fallback is not None:
            return fallback
        raise
</CODE_PROPOSAL>""",

        "mutant_c": """\
<CODE_PROPOSAL>
import asyncio

async def with_timeout(coro, timeout: float = 10.0):
    \"\"\"Wildcard mutant C — SyntaxError for gate validation.\"\"\"
    async for result in asyncio.wait_for(coro, timeout=timeout)
        return result
</CODE_PROPOSAL>""",
    },

    # ── Generic Fallback ──────────────────────────────────────────────────
    "generic": {
        "mutant_a": """\
<CODE_PROPOSAL>
def execute_task(*args, **kwargs):
    \"\"\"[FALLBACK-A] Minimal valid stub generated in offline simulation mode.\"\"\"
    result = None
    return result
</CODE_PROPOSAL>""",

        "mutant_b": """\
<CODE_PROPOSAL>
def execute_task(*args, **kwargs):
    \"\"\"
    [FALLBACK-B] Structural alternative simulation stub.
    More verbose to exercise the parsimony length penalty in MutantCodeSelector.
    \"\"\"
    # Step 1: initialise result container
    result = None
    # Step 2: task context reference (verbosity padding for parsimony gate)
    _task_args   = args
    _task_kwargs = kwargs
    _ = (_task_args, _task_kwargs)
    # Step 3: return result
    return result
</CODE_PROPOSAL>""",

        "mutant_c": """\
<CODE_PROPOSAL>
def execute_task(*args, **kwargs):
    \"\"\"[FALLBACK-C] Deliberate SyntaxError — rejection gate validation.\"\"\"
    if True
        pass
</CODE_PROPOSAL>""",
    },
}


# =============================================================================
# Category Detection
# =============================================================================

def _detect_category(task: str, signature: str) -> str:
    """
    Map a natural-language task description to a patch category key.

    Scans both the task string and the function signature against
    ``_CATEGORY_KEYWORDS`` using case-insensitive substring matching.
    Returns the first matching category, or ``'generic'`` if none match.

    Parameters
    ----------
    task : str
        Natural-language description of the coding objective.
    signature : str
        Target function signature string (optional, may be empty).

    Returns
    -------
    str
        Matching category key from ``_DEMO_PATCHES``.
    """
    combined = (task + " " + signature).lower()

    for category, keywords in _CATEGORY_KEYWORDS.items():
        if any(kw in combined for kw in keywords):
            return category

    return "generic"


# =============================================================================
# Simulation Mutant Retrieval
# =============================================================================

def get_simulation_mutants(task: str, signature: str = "") -> List[str]:
    """
    Return a list of exactly three pre-engineered simulation mutants for
    the detected task category.

    All mutants are wrapped in ``<CODE_PROPOSAL>`` XML boundary tags as
    required by ``DraftCoordinator._extract_code_proposal()``.

    Returns
    -------
    list[str]
        ``[mutant_a_xml, mutant_b_xml, mutant_c_xml]``
        - mutant_a: syntactically valid, minimal → expected WINNER
        - mutant_b: syntactically valid, verbose → expected RUNNER-UP
        - mutant_c: deliberate SyntaxError       → expected REJECTED (−100.0)
    """
    category = _detect_category(task, signature)
    patches  = _DEMO_PATCHES.get(category, _DEMO_PATCHES["generic"])

    return [
        patches["mutant_a"],
        patches["mutant_b"],
        patches["mutant_c"],
    ]


# =============================================================================
# Primary Dispatcher
# =============================================================================

async def generate_mutants_dispatched(
    file_path:        str,
    task:             str,
    target_signature: str = "",
) -> List[str]:
    """
    Dual-mode mutant generation dispatcher.

    Execution paths
    ---------------

    **SIMULATION MODE** (``EMMA_SIMULATION_MODE=1``):
      Returns pre-engineered simulation mutants immediately (<100ms).
      No LLM, no network, no GPU. Safe for air-gapped demo environments.

    **LIVE MODE** (``EMMA_SIMULATION_MODE=0``, default):
      Dynamically imports ``InferenceRouter`` and dispatches to the real
      Ollama LLM endpoint (qwen2.5-coder @ localhost:11434).

      On ANY exception (``URLError``, ``TimeoutError``, ``ConnectionRefusedError``,
      ``RuntimeError``, or any unexpected error), prints a structured diagnostic
      warning and **gracefully falls back** to simulation mutants — guaranteeing
      the solver loop never stalls due to network/GPU unavailability.

    Dynamic Import Strategy
    -----------------------
    ``InferenceRouter`` is imported **inside** this function (not at module level)
    to prevent circular import chains during unit-test collection and module
    initialization.

    Parameters
    ----------
    file_path : str
        Path to the target file being patched (forwarded as LLM context).
    task : str
        Natural-language coding objective.
    target_signature : str
        Optional function signature for return-constraint scoring.

    Returns
    -------
    list[str]
        Exactly three XML-wrapped code strings: [mutant_A, mutant_B, mutant_C].
    """

    # ── Path 1: Explicit simulation mode ──────────────────────────────────
    if SIMULATION_MODE:
        _log_simulation_activation(reason="EMMA_SIMULATION_MODE=1")
        return get_simulation_mutants(task, target_signature)

    # ── Path 2: Live LLM dispatch with fallback ───────────────────────────
    try:
        # Dynamic import prevents circular reference during test collection
        from app.core.inference_router import InferenceRouter  # type: ignore

        router   = InferenceRouter()
        mutants  = await router.request_mutants(
            task             = task,
            target_signature = target_signature,
            file_context     = _read_file_safe(file_path),
        )

        if not mutants or len(mutants) != 3:
            _log_fallback_activation(
                reason="InferenceRouter returned invalid/empty mutants list",
                exc=None,
            )
            return get_simulation_mutants(task, target_signature)

        return mutants

    except ImportError as exc:
        _log_fallback_activation(
            reason=f"InferenceRouter unavailable (import failed): {exc}",
            exc=exc,
        )

    except OSError as exc:
        # Covers ConnectionRefusedError, ConnectionResetError, socket.gaierror
        _log_fallback_activation(
            reason=f"Network/socket error — LLM endpoint unreachable: {exc}",
            exc=exc,
        )

    except TimeoutError as exc:
        _log_fallback_activation(
            reason=f"LLM request timed out: {exc}",
            exc=exc,
        )

    except RuntimeError as exc:
        # Raised by get_manifold_table() retry exhaustion and similar
        _log_fallback_activation(
            reason=f"Runtime failure in LLM pipeline: {exc}",
            exc=exc,
        )

    except Exception as exc:  # noqa: BLE001
        _log_fallback_activation(
            reason=f"Unexpected error during LLM dispatch: {type(exc).__name__}: {exc}",
            exc=exc,
        )

    # ── Fallback: return simulation mutants ───────────────────────────────
    return get_simulation_mutants(task, target_signature)


# =============================================================================
# Internal Helpers
# =============================================================================

def _read_file_safe(file_path: str) -> str:
    """
    Read file content for LLM context injection.
    Returns empty string if the file does not exist or cannot be read.
    """
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as fh:
            content = fh.read()
            # Truncate to 2 000 characters to stay within token budget
            return content[:2_000]
    except (OSError, IOError):
        return ""


def _log_simulation_activation(reason: str) -> None:
    """Print a structured notification when simulation mode is active."""
    try:
        from rich.console import Console as _RichConsole
        _RichConsole().print(
            f"[bold yellow]⚡ SIMULATION MODE ACTIVE[/bold yellow]  "
            f"[dim]Reason: {reason}[/dim]  "
            f"[bright_cyan]Serving pre-engineered mutants (<100ms)[/bright_cyan]"
        )
    except ImportError:
        print(
            f"\n[EMMA] ⚡ SIMULATION MODE ACTIVE"
            f"\n       Reason : {reason}"
            f"\n       Action : Serving pre-engineered mutants (<100ms)\n"
        )


def _log_fallback_activation(reason: str, exc: object) -> None:
    """Print a structured warning when live LLM falls back to simulation."""
    try:
        from rich.console import Console as _RichConsole
        _RichConsole().print(
            f"\n[bold red]⚠ LLM UNREACHABLE — SWITCHING TO SIMULATION MODE[/bold red]\n"
            f"  [dim]Reason : {reason}[/dim]\n"
            f"  [yellow]Action : Substituting high-fidelity simulation mutants[/yellow]\n"
        )
    except ImportError:
        print(
            f"\n[EMMA] ⚠  LLM UNREACHABLE — SWITCHING TO SIMULATION MODE"
            f"\n       Reason : {reason}"
            f"\n       Action : Substituting high-fidelity simulation mutants\n"
        )


# =============================================================================
# Introspection utility — list all available simulation categories
# =============================================================================

def list_simulation_categories() -> List[str]:
    """Return all registered simulation patch category keys."""
    return list(_DEMO_PATCHES.keys())


def get_category_for_task(task: str, signature: str = "") -> str:
    """
    Public wrapper around ``_detect_category`` for external inspection.
    Useful in unit tests to assert correct category routing.
    """
    return _detect_category(task, signature)


if __name__ == "__main__":
    import asyncio

    async def _run_demo() -> None:
        print("\n======================================================================")
        print("🌌 EMMA COGNITIVE ENGINE — OFFLINE SIMULATION ROUTER DEMO")
        print("======================================================================\n")

        # Force simulation mode active for testing
        os.environ["EMMA_SIMULATION_MODE"] = "1"
        global SIMULATION_MODE
        SIMULATION_MODE = True

        # Test Case 1: OAuth Task
        task_1 = "OAuth 2.0 token exchange authorization header prefix repair"
        sig_1  = "def repair_token_header(headers: dict) -> dict:"
        print(f"🔍 [TEST 1] Task : '{task_1}'")
        print(f"           Sig  : '{sig_1}'")
        cat_1 = get_category_for_task(task_1, sig_1)
        print(f"🎯 Detected Category: [bright_cyan]{cat_1}[/bright_cyan]\n")

        mutants_1 = await generate_mutants_dispatched("dummy_path.py", task_1, sig_1)
        for i, label in enumerate(["A (Minimal / Winner)", "B (Verbose / Runner)", "C (SyntaxError / Rejected)"]):
            print(f"📦 Mutant {label}:")
            print(mutants_1[i].strip())
            print("-" * 50)

        # Test Case 2: SQLite Lock Task
        task_2 = "Fix database locked operational error on SQLite write transaction"
        sig_2  = "def safe_sqlite_query(db_path: str, query: str) -> list:"
        print(f"\n🔍 [TEST 2] Task : '{task_2}'")
        cat_2 = get_category_for_task(task_2, sig_2)
        print(f"🎯 Detected Category: [bright_cyan]{cat_2}[/bright_cyan]")

    asyncio.run(_run_demo())

