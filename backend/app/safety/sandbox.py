"""
backend/app/safety/sandbox.py
==============================
EMMA SUDARSHANA Safety Division — Jailed Local Python Sandbox Subprocess
Ticket: EMM-05-A2 · Phase 2

Provides a platform-agnostic jailed subprocess execution environment for
running AI-generated mutant code safely. Implements two interlocking
security mechanisms:

  1. OS-Level Resource Isolation
     ─────────────────────────────
     Windows: Windows Job Objects (kernel32/ctypes)
       - Enforces per-process virtual memory ceiling (default 256 MB).
       - JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE guarantees zombie-free cleanup
         even if the parent process dies unexpectedly.
       - Child spawned with CREATE_BREAKAWAY_FROM_JOB so it can be cleanly
         enrolled in the new constrained Job after creation.

     Unix/macOS: resource.setrlimit
       - RLIMIT_AS caps the virtual address space of the child process.
       - RLIMIT_NPROC = (0, 0) prevents any fork-bomb inside the sandbox.

  2. Structured JSON Pipe Protocol
     ──────────────────────────────
     Parent → Child stdin:  JSON execution envelope with code + options.
     Child  → Parent stdout: JSON result envelope with telemetry + errors.
     This eliminates raw code string injection vectors and produces a
     fully structured, machine-readable execution report.

  The child worker script applies the Sudarshana AST Gas Metering Shield
  (gas_meter.instrument_code) before executing, catching infinite loops
  orders of magnitude faster than the OS wall-clock timeout.

Standard library only (subprocess, tempfile, json, ctypes, resource,
dataclasses, functools). Zero external dependencies.
"""

from __future__ import annotations

import functools
import json
import os
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from typing import Optional


# ─────────────────────────────────────────────────────────────────────────────
# Platform-conditional imports (top-level, not inside functions)
# ─────────────────────────────────────────────────────────────────────────────

if sys.platform == "win32":
    import ctypes
    import ctypes.wintypes as wt
else:
    import resource  # type: ignore[import]  # Unix/macOS only


# ─────────────────────────────────────────────────────────────────────────────
# Result Dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SandboxResult:
    """Structured execution telemetry returned by run_in_sandbox().

    Fields
    ------
    success:       True iff execution completed without raising an exception.
    stdout:        Captured standard output produced by the sandboxed code.
    stderr:        Captured standard error or diagnostic messages.
    exit_code:     Raw subprocess return code (0 = clean, None = unknown).
    gas_consumed:  Total AST gas units consumed (from WeightedGasMeterTransformer).
    error_type:    Exception class name string (e.g. "ZeroDivisionError"), or
                   a classified crash category: "OOMKilled", "TimeoutExpired",
                   "GasMeterException", "SegmentationFault", "ProcessAborted".
    error_message: Human-readable error description.
    error_line:    Line number inside <sandbox> where the exception was raised.
    latency_ms:    Wall-clock elapsed time for the full sandbox call (ms).
    exit_class:    Normalised semantic classification string, one of:
                   SUCCESS | SYNTAX_ERROR | RUNTIME_ERROR | GAS_LIMIT_EXCEEDED
                   | TIMEOUT | OOM_KILLED | PROCESS_CRASH | UNKNOWN_ERROR
    """
    success: bool
    stdout: str
    stderr: str
    exit_code: Optional[int]
    gas_consumed: int
    error_type: Optional[str]
    error_message: Optional[str]
    error_line: Optional[int]
    latency_ms: float
    exit_class: str = field(default="UNKNOWN_ERROR")


# ─────────────────────────────────────────────────────────────────────────────
# Windows Job Object Structures & Constants (ctypes / kernel32)
# ─────────────────────────────────────────────────────────────────────────────

if sys.platform == "win32":

    class IO_COUNTERS(ctypes.Structure):
        """Maps to the Win32 IO_COUNTERS structure (winnt.h)."""
        _fields_ = [
            ("ReadOperationCount",  ctypes.c_uint64),
            ("WriteOperationCount", ctypes.c_uint64),
            ("OtherOperationCount", ctypes.c_uint64),
            ("ReadTransferCount",   ctypes.c_uint64),
            ("WriteTransferCount",  ctypes.c_uint64),
            ("OtherTransferCount",  ctypes.c_uint64),
        ]

    class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
        """Maps to JOBOBJECT_BASIC_LIMIT_INFORMATION (winnt.h)."""
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),    # 100-ns intervals
            ("PerJobUserTimeLimit",     ctypes.c_int64),
            ("LimitFlags",              ctypes.c_uint32),   # JOB_OBJECT_LIMIT_* bitmask
            ("MinimumWorkingSetSize",   ctypes.c_size_t),
            ("MaximumWorkingSetSize",   ctypes.c_size_t),
            ("ActiveProcessLimit",      ctypes.c_uint32),
            ("Affinity",                ctypes.c_size_t),
            ("PriorityClass",           ctypes.c_uint32),
            ("SchedulingClass",         ctypes.c_uint32),
        ]

    class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
        """Maps to JOBOBJECT_EXTENDED_LIMIT_INFORMATION (winnt.h)."""
        _fields_ = [
            ("BasicLimitInformation",  JOBOBJECT_BASIC_LIMIT_INFORMATION),
            ("IoInfo",                 IO_COUNTERS),
            ("ProcessMemoryLimit",     ctypes.c_size_t),  # Per-process virtual memory cap
            ("JobMemoryLimit",         ctypes.c_size_t),  # Total job virtual memory cap
            ("PeakProcessMemoryUsed",  ctypes.c_size_t),
            ("PeakJobMemoryUsed",      ctypes.c_size_t),
        ]

    # ── kernel32 DLL — declare restype/argtypes before any call ───────────────
    _k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    _k32.CreateJobObjectW.restype = wt.HANDLE
    _k32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]

    _k32.SetInformationJobObject.restype = wt.BOOL
    _k32.SetInformationJobObject.argtypes = [
        wt.HANDLE, ctypes.c_int, ctypes.c_void_p, wt.DWORD
    ]

    _k32.OpenProcess.restype = wt.HANDLE
    _k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]

    _k32.AssignProcessToJobObject.restype = wt.BOOL
    _k32.AssignProcessToJobObject.argtypes = [wt.HANDLE, wt.HANDLE]

    _k32.CloseHandle.restype = wt.BOOL
    _k32.CloseHandle.argtypes = [wt.HANDLE]

    # ── LimitFlags constants (winnt.h) ────────────────────────────────────────
    _JOB_OBJECT_LIMIT_PROCESS_MEMORY    = 0x00000100
    _JOB_OBJECT_LIMIT_JOB_MEMORY        = 0x00000200
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000
    _JobObjectExtendedLimitInformation  = 9        # JOBOBJECTINFOCLASS enum value

    # ── OpenProcess access rights ─────────────────────────────────────────────
    _PROCESS_ALL_ACCESS = 0x001FFFFF

    # ── Popen creationflags ───────────────────────────────────────────────────
    # CREATE_NEW_PROCESS_GROUP (0x200) ensures a dedicated process group.
    # CREATE_BREAKAWAY_FROM_JOB (0x1000000) lets the child leave the parent's
    # Job Object so it can be enrolled in the new constrained Job.
    _WIN_CREATION_FLAGS = 0x00000200 | 0x01000000

    # ── NTSTATUS exit code constants (kernel returns these as unsigned 32-bit) ─
    _NTSTATUS_ACCESS_VIOLATION    = 0xC0000005
    _NTSTATUS_STACK_OVERFLOW      = 0xC00000FD
    _NTSTATUS_NO_MEMORY           = 0xC0000017
    _NTSTATUS_COMMITMENT_LIMIT    = 0xC000012D
    _NTSTATUS_BREAKPOINT          = 0x80000003  # Assertion failures / debug breaks


# ─────────────────────────────────────────────────────────────────────────────
# Windows Memory Cap — _apply_windows_memory_cap()
# ─────────────────────────────────────────────────────────────────────────────

def _apply_windows_memory_cap(pid: int, limit_bytes: int) -> int:
    """Enrol a running child process in a Job Object with a virtual-memory cap.

    IMPORTANT: Returns the open job_handle. The CALLER must call
    kernel32.CloseHandle(job_handle) AFTER the child process has exited.
    Closing job_handle early triggers KILL_ON_JOB_CLOSE, killing the child
    immediately before it can produce any output.

    The six-step procedure mirrors Section 4.3 of the mathematical safety
    sandbox design document (EMM_05_A2_mathematical_safety_sandbox_plan_v2.md):

      1. CreateJobObjectW        -- create an anonymous kernel Job Object.
      2. Build limit structure   -- configure ProcessMemoryLimit + LimitFlags.
      3. SetInformationJobObject -- apply limits to the Job.
      4. OpenProcess             -- acquire a handle to the child by PID.
      5. AssignProcessToJobObject -- bind child to the constrained Job.
      6. CloseHandle(proc_handle) -- release only the process handle.
         (job_handle is returned to caller for deferred close)

    Args:
        pid:         Windows PID of the already-running child process.
        limit_bytes: Virtual memory ceiling in bytes (e.g. 256 * 1024 * 1024).

    Returns:
        job_handle: The open kernel Job Object handle. Caller must CloseHandle()
                    it after the child process has finished.

    Raises:
        OSError: If any kernel call fails. Includes the Win32 last-error code.
    """
    if sys.platform != "win32":
        return 0  # Unreachable on Unix

    # Step 1 -- Create anonymous Job Object
    job_handle = _k32.CreateJobObjectW(None, None)
    if not job_handle:
        raise OSError(
            f"CreateJobObjectW failed: Win32 error {ctypes.get_last_error()}"
        )

    proc_handle: Optional[int] = None
    try:
        # Step 2 -- Populate extended limit structure
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            _JOB_OBJECT_LIMIT_PROCESS_MEMORY       # Enforce per-process virtual memory limit
            | _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE  # Kill all processes when job handle closes
        )
        info.ProcessMemoryLimit = limit_bytes

        # Step 3 -- Apply extended limits to Job Object
        ok = _k32.SetInformationJobObject(
            job_handle,
            _JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            raise OSError(
                f"SetInformationJobObject failed: Win32 error {ctypes.get_last_error()}"
            )

        # Step 4 -- Open a handle to the child process
        proc_handle = _k32.OpenProcess(_PROCESS_ALL_ACCESS, False, pid)
        if not proc_handle:
            raise OSError(
                f"OpenProcess(pid={pid}) failed: Win32 error {ctypes.get_last_error()}"
            )

        # Step 5 -- Assign the child to the constrained Job
        ok = _k32.AssignProcessToJobObject(job_handle, proc_handle)
        if not ok:
            raise OSError(
                f"AssignProcessToJobObject failed: Win32 error {ctypes.get_last_error()}"
            )

    except Exception:
        # On failure, close both handles before re-raising
        if proc_handle:
            _k32.CloseHandle(proc_handle)
        _k32.CloseHandle(job_handle)
        raise

    finally:
        # Step 6 -- Always release the process handle (not needed beyond this point)
        if proc_handle:
            _k32.CloseHandle(proc_handle)

    # Return job_handle to caller -- DO NOT close here.
    # KILL_ON_JOB_CLOSE will fire when the caller calls CloseHandle(job_handle)
    # after proc.communicate() completes, cleaning up naturally.
    return job_handle



# ─────────────────────────────────────────────────────────────────────────────
# Unix preexec — _unix_preexec_fn()
# ─────────────────────────────────────────────────────────────────────────────

def _unix_preexec_fn(memory_bytes: int) -> None:
    """Pre-exec hook executed *inside the child process* on Unix/macOS.

    Called by the OS after fork() but before exec(). Sets hard resource
    ceilings that the child cannot exceed or remove.

    RLIMIT_AS:    Caps the total virtual address space.  Stronger than
                  RLIMIT_DATA because it also caps mmap / numpy allocations.
    RLIMIT_NPROC: Prevents the sandboxed code from spawning further processes
                  (fork bombs, subprocess.Popen chains, multiprocessing).

    Both soft and hard limits are set to the same value so that the child
    cannot raise them back up using setrlimit().

    Args:
        memory_bytes: Virtual memory ceiling in bytes.
    """
    # RLIMIT_AS — total virtual address space (soft, hard)
    resource.setrlimit(resource.RLIMIT_AS, (memory_bytes, memory_bytes))

    # RLIMIT_NPROC — zero means "no new processes allowed"
    try:
        resource.setrlimit(resource.RLIMIT_NPROC, (0, 0))
    except ValueError:
        # macOS may raise ValueError for RLIMIT_NPROC on some versions — non-fatal
        pass


# ─────────────────────────────────────────────────────────────────────────────
# Exit Code Classification — _classify_exit()
# ─────────────────────────────────────────────────────────────────────────────

def _classify_exit(
    exit_code: Optional[int],
    timed_out: bool,
) -> tuple[str, str, str]:
    """Translate a raw subprocess return code into a human-readable classification.

    Returns
    -------
    tuple (exit_class, error_type, error_message)
        exit_class:    One of the canonical status strings used in SandboxResult.
        error_type:    Short exception/signal name string.
        error_message: Verbose human-readable description.
    """
    if timed_out:
        return (
            "TIMEOUT",
            "TimeoutExpired",
            "Execution timed out — sandbox process was forcibly killed.",
        )

    if exit_code is None:
        return (
            "UNKNOWN_ERROR",
            "UnknownExit",
            "Subprocess return code is None (unexpected termination).",
        )

    if exit_code == 0:
        return ("SUCCESS", None, None)

    if exit_code == 1:
        return (
            "RUNTIME_ERROR",
            "RuntimeError",
            "Sandboxed code raised an unhandled exception.",
        )

    if exit_code == 2:
        return (
            "SYNTAX_ERROR",
            "SyntaxError",
            "SyntaxError during AST parsing/compilation.",
        )

    if exit_code == 42:
        return (
            "GAS_LIMIT_EXCEEDED",
            "GasMeterException",
            "Sudarshana Gas Meter halted execution — gas limit exceeded.",
        )

    # ── Windows NTSTATUS crash codes ──────────────────────────────────────────
    if sys.platform == "win32":
        unsigned = exit_code & 0xFFFFFFFF  # Convert signed int to unsigned 32-bit

        if unsigned in (_NTSTATUS_NO_MEMORY, _NTSTATUS_COMMITMENT_LIMIT):
            return (
                "OOM_KILLED",
                "OOMKilled",
                f"Process killed by OS: virtual memory limit exceeded "
                f"(NTSTATUS 0x{unsigned:08X}).",
            )
        if unsigned == _NTSTATUS_ACCESS_VIOLATION:
            return (
                "PROCESS_CRASH",
                "AccessViolation",
                "Process crashed: access violation / segmentation fault "
                f"(NTSTATUS 0x{unsigned:08X}).",
            )
        if unsigned == _NTSTATUS_STACK_OVERFLOW:
            return (
                "PROCESS_CRASH",
                "StackOverflow",
                "Process crashed: stack overflow "
                f"(NTSTATUS 0x{unsigned:08X}).",
            )
        if unsigned == _NTSTATUS_BREAKPOINT:
            return (
                "PROCESS_CRASH",
                "DebugBreakpoint",
                "Process crashed: unhandled debug breakpoint "
                f"(NTSTATUS 0x{unsigned:08X}).",
            )
        # Generic Windows abnormal termination
        if unsigned >= 0x80000000:
            return (
                "PROCESS_CRASH",
                "AbnormalTermination",
                f"Process crashed with NTSTATUS 0x{unsigned:08X}.",
            )

    else:
        # ── Unix negative exit codes (signals) ────────────────────────────────
        if exit_code == -9:    # SIGKILL — typically OOM from kernel
            return (
                "OOM_KILLED",
                "OOMKilled",
                "Process killed by SIGKILL — likely virtual memory exhaustion.",
            )
        if exit_code == -11:   # SIGSEGV
            return (
                "PROCESS_CRASH",
                "SegmentationFault",
                "Process crashed: segmentation fault (SIGSEGV -11).",
            )
        if exit_code == -6:    # SIGABRT
            return (
                "PROCESS_CRASH",
                "ProcessAborted",
                "Process aborted (SIGABRT -6) — assertion failure or C abort().",
            )
        if exit_code == -8:    # SIGFPE
            return (
                "PROCESS_CRASH",
                "FloatingPointException",
                "Process crashed: floating-point exception (SIGFPE -8).",
            )
        if exit_code < 0:
            return (
                "PROCESS_CRASH",
                "SignalTerminated",
                f"Process killed by signal {-exit_code}.",
            )

    # Fallback for unrecognised non-zero exit codes
    return (
        "UNKNOWN_ERROR",
        "UnknownExitCode",
        f"Process exited with unrecognised code {exit_code}.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Sandbox Worker Script (embedded string — runs inside child subprocess)
# ─────────────────────────────────────────────────────────────────────────────

_WORKER_SCRIPT = """\
# -*- coding: utf-8 -*-
\"\"\"
emma_sandbox_worker -- EMMA SUDARSHANA Subprocess Execution Worker
Reads a JSON envelope from stdin, instruments code with the Sudarshana AST
Gas Metering Shield (if requested), executes it inside a restricted builtins
namespace, and writes a JSON result envelope to stdout.

This script is NEVER imported as a module. It is always run as __main__.
\"\"\"
import sys
import os
import json
import io
import traceback
import contextlib


# -- Safe built-ins whitelist (mirrors _SAFE_BUILTINS in gas_meter.py) --------

def _build_safe_builtins():
    import builtins as _b
    SAFE = {
        # Numeric / type builtins
        "abs", "all", "any", "ascii", "bin", "bool", "bytearray", "bytes",
        "callable", "chr", "complex", "dict", "divmod", "enumerate", "filter",
        "float", "format", "frozenset", "hash", "hasattr", "hex", "id", "int",
        "isinstance", "issubclass", "iter", "len", "list", "map", "max", "min",
        "next", "object", "oct", "ord", "pow", "print", "property", "range",
        "repr", "reversed", "round", "set", "slice", "sorted", "staticmethod",
        "str", "sum", "super", "tuple", "type", "zip",
        # Constants
        "True", "False", "None",
        # Class construction internal
        "__build_class__", "__name__",
        # Exception classes commonly used in user code
        "Exception", "BaseException", "ValueError", "TypeError", "KeyError",
        "IndexError", "AttributeError", "StopIteration", "RuntimeError",
        "NameError", "ImportError", "ZeroDivisionError", "SyntaxError",
        "OSError", "IOError", "MemoryError", "OverflowError", "RecursionError",
        "NotImplementedError", "AssertionError", "ArithmeticError",
        "LookupError", "UnicodeError",
    }
    return {k: getattr(_b, k) for k in SAFE if hasattr(_b, k)}


# -- JSON response helpers ----------------------------------------------------

def _emit(payload: dict) -> None:
    \"\"\"Write the JSON result envelope to stdout as UTF-8 bytes and flush.\"\"\"
    data = json.dumps(payload, ensure_ascii=True).encode("utf-8")
    sys.stdout.buffer.write(data)
    sys.stdout.buffer.flush()


def _emit_error(
    exit_code: int,
    error_type: str,
    error_message: str,
    stdout: str = "",
    stderr: str = "",
    error_line=None,
    gas_consumed: int = 0,
) -> None:
    \"\"\"Convenience wrapper to emit a failed execution result.\"\"\"
    _emit({
        "success":       False,
        "stdout":        stdout,
        "stderr":        stderr,
        "exit_code":     exit_code,
        "gas_consumed":  gas_consumed,
        "error_type":    error_type,
        "error_message": error_message,
        "error_line":    error_line,
    })


# -- Main execution entry point ------------------------------------------------

def main() -> None:
    # 1. Read and parse the JSON envelope from parent process via stdin.
    try:
        raw_input = sys.stdin.read()
        payload = json.loads(raw_input)
    except Exception as exc:
        _emit_error(
            exit_code=3,
            error_type=type(exc).__name__,
            error_message=f"Failed to deserialise stdin payload: {exc}",
        )
        sys.exit(3)

    code          = payload.get("code", "")
    gas_limit     = int(payload.get("gas_limit", 50000))
    inject_gas    = bool(payload.get("inject_gas", True))
    safe_builtins = bool(payload.get("safe_builtins", True))

    compiled_code  = None
    sealed_globals = None

    # 2. Instrument code with the Sudarshana AST Gas Metering Shield (if requested).
    if inject_gas:
        try:
            from app.safety.gas_meter import instrument_code, GasMeterException  # noqa
            compiled_code, sealed_globals = instrument_code(
                code, gas_limit=gas_limit, weighted=True
            )
        except SyntaxError as exc:
            _emit_error(
                exit_code=2,
                error_type="SyntaxError",
                error_message=str(exc),
                error_line=getattr(exc, "lineno", None),
            )
            sys.exit(2)
        except Exception as exc:
            _emit_error(
                exit_code=3,
                error_type=type(exc).__name__,
                error_message=f"Gas instrumentation error: {exc}",
            )
            sys.exit(3)
    else:
        # No gas metering -- compile directly into a plain safe namespace
        try:
            compiled_code = compile(code, "<sandbox>", "exec")
        except SyntaxError as exc:
            _emit_error(
                exit_code=2,
                error_type="SyntaxError",
                error_message=str(exc),
                error_line=getattr(exc, "lineno", None),
            )
            sys.exit(2)
        builtins_dict = _build_safe_builtins() if safe_builtins else __builtins__
        sealed_globals = {"__builtins__": builtins_dict, "__name__": "__sandbox__"}

    # 3. Execute the compiled code object inside captured stdout/stderr streams.
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()
    err_type   = None
    err_msg    = None
    err_line   = None
    exit_code  = 0
    success    = False

    try:
        with (
            contextlib.redirect_stdout(stdout_buf),
            contextlib.redirect_stderr(stderr_buf),
        ):
            exec(compiled_code, sealed_globals)  # noqa: S102
        success = True

    except Exception as exc:
        err_type = type(exc).__name__
        err_msg  = str(exc)
        exit_code = 42 if err_type == "GasMeterException" else 1

        # Extract the innermost <sandbox> frame line number for precise error reporting
        raw_tb = traceback.extract_tb(sys.exc_info()[2])
        sandbox_frames = [f for f in raw_tb if f.filename == "<sandbox>"]
        if sandbox_frames:
            err_line = sandbox_frames[-1].lineno
        elif raw_tb:
            err_line = raw_tb[-1].lineno

    # 4. Read the final gas counter from the sealed namespace inspector
    gas_consumed = 0
    if sealed_globals and callable(sealed_globals.get("_get_gas_consumed")):
        try:
            gas_consumed = sealed_globals["_get_gas_consumed"]()
        except Exception:
            pass

    # 5. Emit final JSON result envelope
    _emit({
        "success":       success,
        "stdout":        stdout_buf.getvalue(),
        "stderr":        stderr_buf.getvalue(),
        "exit_code":     exit_code,
        "gas_consumed":  gas_consumed,
        "error_type":    err_type,
        "error_message": err_msg,
        "error_line":    err_line,
    })

    if exit_code not in (0, 1):
        # Exit with the worker's exit code so the parent can classify it
        sys.exit(exit_code)


if __name__ == "__main__":
    main()
"""


# ─────────────────────────────────────────────────────────────────────────────
# Public API — run_in_sandbox()
# ─────────────────────────────────────────────────────────────────────────────

def run_in_sandbox(
    code: str,
    timeout_s: float = 30.0,
    memory_mb: int = 256,
    gas_limit: int = 50_000,
    safe_builtins: bool = True,
    inject_gas: bool = True,
) -> SandboxResult:
    """Execute candidate Python code inside a platform-agnostic jailed subprocess.

    Platform strategy:
      - Windows: Job Objects via ctypes (256 MB virtual memory cap).
      - Unix:    resource.setrlimit RLIMIT_AS + RLIMIT_NPROC via preexec_fn.

    The child process runs the embedded ``_WORKER_SCRIPT`` which:
      1. Parses the JSON envelope from stdin.
      2. Applies the Sudarshana AST Gas Metering Shield (if inject_gas=True).
      3. Executes the instrumented code in a restricted namespace.
      4. Returns a structured JSON result on stdout.

    This function never raises an exception to the caller. All error
    conditions are captured and returned as ``SandboxResult`` fields.

    Args:
        code:          Raw Python source string to execute.
        timeout_s:     Wall-clock timeout in seconds (default 30).
        memory_mb:     Virtual memory ceiling in megabytes (default 256).
        gas_limit:     AST gas unit budget before GasMeterException (default 50 000).
        safe_builtins: If True, restrict __builtins__ to the safe whitelist.
        inject_gas:    If True, apply WeightedGasMeterTransformer before exec().

    Returns:
        SandboxResult with all execution telemetry populated.
    """
    t_start = time.perf_counter()
    limit_bytes = memory_mb * 1024 * 1024
    _win_job_handle: int = 0

    # ── Build child environment: add backend/ to PYTHONPATH so worker can import app.safety.gas_meter ───
    env = os.environ.copy()
    cwd = os.getcwd()
    # Compute backend/ directory relative to THIS file's location:
    # sandbox.py lives at: backend/app/safety/sandbox.py
    # _this_file_dir = backend/app/safety/
    # 1 level up (..)   = backend/app/
    # 2 levels up (.,..)= backend/          <-- correct import root for app.*
    _this_file_dir = os.path.dirname(os.path.abspath(__file__))
    backend_dir = os.path.normpath(os.path.join(_this_file_dir, "..", ".."))
    existing_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = backend_dir + os.pathsep + cwd + (os.pathsep + existing_pythonpath if existing_pythonpath else "")


    # ── Write worker script to a temp file (auto-cleaned in finally block) ────
    fd, worker_path = tempfile.mkstemp(suffix=".py", prefix="emma_sandbox_worker_")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as fh:
            fh.write(_WORKER_SCRIPT)

        # ── Build JSON payload for child stdin ─────────────────────────────────
        payload_bytes = json.dumps({
            "code":          code,
            "gas_limit":     gas_limit,
            "inject_gas":    inject_gas,
            "safe_builtins": safe_builtins,
        }).encode("utf-8")

        # ── Platform-specific Popen kwargs ─────────────────────────────────────
        popen_kwargs: dict = {
            "stdin":  subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.PIPE,
            "env":    env,
            "cwd":    cwd,
        }

        if sys.platform == "win32":
            # CREATE_BREAKAWAY_FROM_JOB + CREATE_NEW_PROCESS_GROUP
            popen_kwargs["creationflags"] = _WIN_CREATION_FLAGS
        else:
            # On Unix, set resource limits in the child before exec()
            popen_kwargs["preexec_fn"] = functools.partial(_unix_preexec_fn, limit_bytes)

        # ── Spawn the isolated child process ───────────────────────────────────
        try:
            proc = subprocess.Popen(
                [sys.executable, worker_path],
                **popen_kwargs,
            )
        except PermissionError:
            # If CREATE_BREAKAWAY_FROM_JOB is denied (e.g. parent is in a Job Object
            # that doesn't permit breakaway), fall back to spawning without breakaway.
            if sys.platform == "win32" and popen_kwargs.get("creationflags") == _WIN_CREATION_FLAGS:
                popen_kwargs["creationflags"] = 0x00000200  # CREATE_NEW_PROCESS_GROUP only
                proc = subprocess.Popen(
                    [sys.executable, worker_path],
                    **popen_kwargs,
                )
            else:
                raise

        # ── Windows: enrol the child in a constrained Job Object ──────────────
        if sys.platform == "win32":
            try:
                _win_job_handle = _apply_windows_memory_cap(proc.pid, limit_bytes)
            except OSError:
                # Non-fatal: The child may already be enrolled in the parent IDE's
                # Job Object (e.g. VS Code, Windows Terminal, CI runners).
                # In that case AssignProcessToJobObject fails with ERROR_ACCESS_DENIED.
                # We continue — the wall-clock timeout is still active as a safety net.
                pass

        # ── Communicate with child: enforce wall-clock timeout ─────────────────
        timed_out = False
        stdout_bytes = b""
        stderr_bytes = b""

        try:
            stdout_bytes, stderr_bytes = proc.communicate(
                input=payload_bytes, timeout=timeout_s
            )
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            # Drain after kill to release pipe buffers and reap the zombie
            stdout_bytes, stderr_bytes = proc.communicate()

        latency_ms = (time.perf_counter() - t_start) * 1000.0
        raw_exit = proc.returncode

        stdout_str = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_str = stderr_bytes.decode("utf-8", errors="replace").strip()

        # ── Classify exit status ──────────────────────────────────────────────
        exit_class, err_type, err_msg = _classify_exit(raw_exit, timed_out)

        # ── If timed out or crash (no valid JSON from worker), build result directly
        if timed_out or exit_class in ("OOM_KILLED", "PROCESS_CRASH"):
            return SandboxResult(
                success=False,
                stdout=stdout_str,
                stderr=stderr_str or err_msg,
                exit_code=raw_exit,
                gas_consumed=0,
                error_type=err_type,
                error_message=err_msg,
                error_line=None,
                latency_ms=latency_ms,
                exit_class=exit_class,
            )

        # ── Attempt to deserialise the worker JSON result ─────────────────────
        try:
            result = json.loads(stdout_str)
        except json.JSONDecodeError:
            # Worker output was not valid JSON (e.g. crashed before emitting).
            # Fall back to exit-code classification.
            if exit_class == "UNKNOWN_ERROR":
                exit_class, err_type, err_msg = _classify_exit(raw_exit, False)

            return SandboxResult(
                success=False,
                stdout="",
                stderr=stderr_str or f"Worker stdout (unparsed): {stdout_str[:500]}",
                exit_code=raw_exit,
                gas_consumed=0,
                error_type=err_type or "WorkerOutputError",
                error_message=err_msg or "Worker did not produce valid JSON output.",
                error_line=None,
                latency_ms=latency_ms,
                exit_class=exit_class,
            )

        # ── Build SandboxResult from the structured worker response ───────────
        worker_success = bool(result.get("success", False))

        # Derive exit_class from worker's error_type if the OS-level classification
        # was too coarse (e.g. a GasMeterException inside a normal exit_code=42)
        if result.get("error_type") == "GasMeterException":
            exit_class = "GAS_LIMIT_EXCEEDED"
        elif worker_success:
            exit_class = "SUCCESS"
        elif result.get("exit_code") == 2:
            exit_class = "SYNTAX_ERROR"
        elif result.get("error_type") and not worker_success:
            # Worker caught a runtime exception (exit_code=1 or 0 with error_type set)
            exit_class = "RUNTIME_ERROR"
        elif exit_class == "UNKNOWN_ERROR":
            exit_class = "RUNTIME_ERROR"

        return SandboxResult(
            success=worker_success,
            stdout=result.get("stdout", ""),
            stderr=result.get("stderr", "") or stderr_str,
            exit_code=result.get("exit_code", raw_exit),
            gas_consumed=int(result.get("gas_consumed", 0)),
            error_type=result.get("error_type"),
            error_message=result.get("error_message"),
            error_line=result.get("error_line"),
            latency_ms=latency_ms,
            exit_class=exit_class,
        )

    except Exception as unexpected:
        # Catch-all: ensure run_in_sandbox() never propagates exceptions to caller
        latency_ms = (time.perf_counter() - t_start) * 1000.0
        return SandboxResult(
            success=False,
            stdout="",
            stderr=str(unexpected),
            exit_code=None,
            gas_consumed=0,
            error_type=type(unexpected).__name__,
            error_message=f"Unexpected sandbox orchestration error: {unexpected}",
            error_line=None,
            latency_ms=latency_ms,
            exit_class="UNKNOWN_ERROR",
        )

    finally:
        # Guarantee temp worker script deletion under all code paths
        try:
            os.unlink(worker_path)
        except OSError:
            pass
        if sys.platform == "win32" and _win_job_handle:
            try:
                _k32.CloseHandle(_win_job_handle)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# Module public API surface
# ─────────────────────────────────────────────────────────────────────────────

__all__: list[str] = [
    "SandboxResult",
    "run_in_sandbox",
    # Internal helpers exposed for testing
    "_apply_windows_memory_cap",
    "_unix_preexec_fn",
    "_classify_exit",
]
