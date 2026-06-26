# Implementation Plan: EMM-05-A2 — Mathematical Safety: Jailed Python Sandbox Subprocess
## Production-Grade Engineering Specification v2.0

> **Ticket:** EMM-05-A2 · **Priority:** P0 · **Sprint:** 05
> **Predecessor:** EMM-05-A1 (run_real_solver.py Masterclass — ✅ Complete)

---

## Table of Contents

1. [Goal Description](#1-goal-description)
2. [Threat Model & Failure Modes](#2-threat-model--failure-modes)
3. [Target Component & File Mapping](#3-target-component--file-mapping)
4. [Windows Job Object Memory Cap (ctypes/kernel32)](#4-windows-job-object-memory-cap-ctypeskernel32)
5. [Unix Resource Limit (resource module)](#5-unix-resource-limit-resource-module)
6. [Subprocess JSON Pipe Protocol](#6-subprocess-json-pipe-protocol)
7. [Exit Status Code Mapping Matrix](#7-exit-status-code-mapping-matrix)
8. [🔱 SUDARSHANA AST Gas Metering Shield](#8-sudarshana-ast-gas-metering-shield)
9. [Integration Hook — code_generator.py](#9-integration-hook--code_generatorpy)
10. [Verification Plan](#10-verification-plan)

---

## 1. Goal Description

The existing `CodeGenerator.run_sandbox()` implementation uses in-memory
`exec()` with a restricted `__builtins__` dict. This approach has three
critical unresolved vulnerabilities:

| Vulnerability | Severity | Current Status |
|---|---|---|
| **CPU lockup** — `while True: pass` blocks the calling thread indefinitely | CRITICAL | Mitigated only by `ThreadPoolExecutor` timeout (cannot forcibly kill thread) |
| **RAM exhaustion** — `x = [0] * 500_000_000` will OOM the host process | CRITICAL | Unmitigated |
| **Process crash escape** — a C-extension segfault in user code kills the host | HIGH | Unmitigated |

**Solution:** Spawn generated code in a **dedicated child subprocess** using
`subprocess.Popen`, enforce hard OS-level resource ceilings (256 MB RAM,
30-second CPU timeout), communicate via a structured JSON pipe protocol,
and inject a novel **AST Gas Metering Shield** to catch infinite loops at
the VM instruction level — faster and more deterministic than OS timeouts.

---

## 2. Threat Model & Failure Modes

```
                     ATTACK SURFACE OF exec()-BASED SANDBOX
                     ═══════════════════════════════════════

  Generated Code         In-Memory exec()          Host Process
  ─────────────          ────────────────          ────────────
  while True: pass  →  ThreadPoolExecutor   →    Thread hangs forever
                        (cannot kill)               Memory leaks

  [0]*500_000_000   →  No memory ceiling    →    Host OOM / crash

  import ctypes         Blocked by builtins  →   Partial protection only
  ctypes.cdll...        (but __class__             (dunder escape possible)
                         chains may bypass)

  Segfault in C ext →   Crashes host Python  →    Entire backend dies
```

**New subprocess architecture eliminates all four vectors:**

- CPU lockup → subprocess killed by OS after 30s timeout
- RAM exhaustion → subprocess killed by OS/kernel at 256 MB ceiling
- Process crash → child dies, parent handles `Popen.returncode` cleanly
- Escape attempts → child has no handles to parent's memory space

---

## 3. Target Component & File Mapping

| File | Role | Action |
|---|---|---|
| `backend/app/safety/sandbox.py` | Platform-agnostic subprocess sandbox | **NEW FILE** |
| `backend/app/safety/gas_meter.py` | Sudarshana AST Gas Metering Shield | **NEW FILE** |
| `backend/app/core/code_generator.py` | Evolutionary mutation engine | **MODIFY** `run_sandbox()` |

---

## 4. Windows Job Object Memory Cap (ctypes/kernel32)

Windows does not expose `resource.setrlimit`. Memory ceilings must be
applied to child processes via **Windows Job Objects** — kernel-level
containers that enforce resource quotas on sets of processes.

### 4.1 Required ctypes Structure Definitions

```python
import ctypes
import ctypes.wintypes as wt

# ── IO_COUNTERS ─────────────────────────────────────────────────────────────

class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount",  ctypes.c_uint64),
        ("WriteOperationCount", ctypes.c_uint64),
        ("OtherOperationCount", ctypes.c_uint64),
        ("ReadTransferCount",   ctypes.c_uint64),
        ("WriteTransferCount",  ctypes.c_uint64),
        ("OtherTransferCount",  ctypes.c_uint64),
    ]


# ── JOBOBJECT_BASIC_LIMIT_INFORMATION ───────────────────────────────────────

class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_int64),   # 100-ns intervals
        ("PerJobUserTimeLimit",     ctypes.c_int64),
        ("LimitFlags",              ctypes.c_uint32),  # Bitmask of JOB_OBJECT_LIMIT_*
        ("MinimumWorkingSetSize",   ctypes.c_size_t),
        ("MaximumWorkingSetSize",   ctypes.c_size_t),
        ("ActiveProcessLimit",      ctypes.c_uint32),
        ("Affinity",                ctypes.c_size_t),
        ("PriorityClass",           ctypes.c_uint32),
        ("SchedulingClass",         ctypes.c_uint32),
    ]


# ── JOBOBJECT_EXTENDED_LIMIT_INFORMATION ────────────────────────────────────

class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation",  JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo",                 IO_COUNTERS),
        ("ProcessMemoryLimit",     ctypes.c_size_t),   # Per-process virtual memory limit
        ("JobMemoryLimit",         ctypes.c_size_t),   # Total job virtual memory limit
        ("PeakProcessMemoryUsed",  ctypes.c_size_t),
        ("PeakJobMemoryUsed",      ctypes.c_size_t),
    ]


# ── Kernel32 API handles ─────────────────────────────────────────────────────

kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

# Return types
kernel32.CreateJobObjectW.restype    = wt.HANDLE
kernel32.AssignProcessToJobObject.restype = wt.BOOL
kernel32.SetInformationJobObject.restype  = wt.BOOL
kernel32.OpenProcess.restype         = wt.HANDLE
kernel32.CloseHandle.restype         = wt.BOOL
```

### 4.2 Job Object Limit Flag Constants

```python
# LimitFlags bitmask values (from winnt.h)
JOB_OBJECT_LIMIT_PROCESS_MEMORY    = 0x00000100  # Enforce per-process virtual memory limit
JOB_OBJECT_LIMIT_JOB_MEMORY        = 0x00000200  # Enforce total job memory limit
JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x00002000  # Kill all processes when job handle closes
JOB_OBJECT_LIMIT_DIE_ON_UNHANDLED_EXCEPTION = 0x00000400

# SetInformationJobObject information class selector
JobObjectExtendedLimitInformation   = 9   # JOBOBJECTINFOCLASS enum value

# OpenProcess access rights
PROCESS_ALL_ACCESS = 0x001FFFFF
```

### 4.3 Windows Job Object Appliance Procedure

```python
def _apply_windows_memory_cap(pid: int, limit_bytes: int) -> None:
    """
    Assign a running child process (by PID) to a Job Object with a
    256 MB virtual memory ceiling and KILL_ON_JOB_CLOSE enforcement.

    Steps:
      1. CreateJobObjectW       — create anonymous kernel Job Object
      2. Build limit structure  — set ProcessMemoryLimit + LimitFlags
      3. SetInformationJobObject — apply limits to the Job Object
      4. OpenProcess            — acquire handle to child by PID
      5. AssignProcessToJobObject — bind child to constrained Job
      6. CloseHandle            — release process handle (Job outlives it)

    Notes:
      - KILL_ON_JOB_CLOSE ensures child is killed if parent Python process
        dies unexpectedly (e.g., SIGKILL), preventing zombie processes.
      - On Windows 8+, processes launched by a Job-member parent are
        automatically assigned to the parent's job; use
        CREATE_BREAKAWAY_FROM_JOB flag in Popen if needed.
    """
    # Step 1: Create Job Object
    job_handle = kernel32.CreateJobObjectW(None, None)
    if not job_handle:
        raise OSError(f"CreateJobObjectW failed: error={ctypes.get_last_error()}")

    try:
        # Step 2: Build extended limit structure
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = (
            JOB_OBJECT_LIMIT_PROCESS_MEMORY |
            JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        )
        info.ProcessMemoryLimit = limit_bytes   # e.g. 256 * 1024 * 1024

        # Step 3: Apply limits to Job Object
        ok = kernel32.SetInformationJobObject(
            job_handle,
            JobObjectExtendedLimitInformation,
            ctypes.byref(info),
            ctypes.sizeof(info),
        )
        if not ok:
            raise OSError(f"SetInformationJobObject failed: error={ctypes.get_last_error()}")

        # Step 4: Open child process handle
        proc_handle = kernel32.OpenProcess(PROCESS_ALL_ACCESS, False, pid)
        if not proc_handle:
            raise OSError(f"OpenProcess({pid}) failed: error={ctypes.get_last_error()}")

        try:
            # Step 5: Assign process to job
            ok = kernel32.AssignProcessToJobObject(job_handle, proc_handle)
            if not ok:
                raise OSError(
                    f"AssignProcessToJobObject failed: error={ctypes.get_last_error()}"
                )
        finally:
            kernel32.CloseHandle(proc_handle)   # Step 6

    finally:
        kernel32.CloseHandle(job_handle)
        # Note: Job is destroyed when all handles close. KILL_ON_JOB_CLOSE
        # ensures the child is killed when the parent closes this handle.
```

> **[!WARNING]**
> On Windows 8 and later, a new process spawned by a Job-member parent is
> automatically assigned to the parent job. Use `PROCESS_CREATION_FLAGS =
> subprocess.CREATE_NEW_PROCESS_GROUP | 0x01000000` (CREATE_BREAKAWAY_FROM_JOB)
> in `Popen` kwargs to allow clean Job Object re-assignment.

---

## 5. Unix Resource Limit (resource module)

On Linux/macOS, the `resource` standard library module wraps `setrlimit(2)`
syscalls. Resource limits are set in the child process via `preexec_fn`.

```python
def _unix_preexec_fn(memory_bytes: int) -> None:
    """
    Executed in the forked child process BEFORE exec().
    Sets RLIMIT_AS (virtual address space) to enforce the memory ceiling.

    RLIMIT_AS vs RLIMIT_DATA:
      - RLIMIT_DATA limits heap + BSS only (does not cap mmap allocations).
      - RLIMIT_AS limits the entire virtual address space — a stronger
        guarantee that catches numpy/mmap-based allocation attacks.
    """
    import resource as _resource
    _resource.setrlimit(
        _resource.RLIMIT_AS,
        (memory_bytes, memory_bytes),   # (soft, hard) — both set to ceiling
    )
    # Also cap number of child processes to prevent fork bombs
    _resource.setrlimit(
        _resource.RLIMIT_NPROC,
        (0, 0),   # No forking allowed inside sandbox
    )

import functools

def _make_unix_preexec(memory_bytes: int):
    return functools.partial(_unix_preexec_fn, memory_bytes)
```

---

## 6. Subprocess JSON Pipe Protocol

### 6.1 Motivation

Passing raw Python source code directly to a subprocess via `stdin` or a
temp file creates namespace leakage risks (e.g., the subprocess can read
its own `sys.argv`, inspect its environment, or import from the parent's
working directory). A structured JSON envelope with explicit execution
parameters eliminates this attack surface.

### 6.2 Parent → Child Payload (stdin)

```json
{
  "code":         "def f(x): return x * 2\nprint(f(21))",
  "safe_builtins": true,
  "timeout_guard": 28,
  "gas_limit":    50000,
  "inject_gas_meter": true
}
```

| Field | Type | Description |
|---|---|---|
| `code` | `str` | Raw Python source code to execute |
| `safe_builtins` | `bool` | If True, restrict `__builtins__` to safe subset |
| `timeout_guard` | `int` | Seconds: inner `signal.alarm` guard (Unix only) |
| `gas_limit` | `int` | Max AST instruction count before GasMeterException |
| `inject_gas_meter` | `bool` | If True, apply Sudarshana AST Gas Metering Shield |

### 6.3 Child → Parent Response (stdout)

```json
{
  "success":       true,
  "stdout":        "42\n",
  "stderr":        "",
  "exit_code":     0,
  "gas_consumed":  127,
  "error_type":    null,
  "error_message": null,
  "error_line":    null
}
```

| Field | Type | Description |
|---|---|---|
| `success` | `bool` | True if execution completed without exception |
| `stdout` | `str` | Captured standard output |
| `stderr` | `str` | Captured standard error |
| `exit_code` | `int` | Process exit code (0 = clean) |
| `gas_consumed` | `int` | Total AST instructions executed (Gas Meter count) |
| `error_type` | `str\|null` | Exception class name if failed |
| `error_message` | `str\|null` | Exception message string |
| `error_line` | `int\|null` | Line number of exception |

### 6.4 Child Worker Script (`_sandbox_worker.py`)

This script is the isolated execution wrapper running inside the subprocess.
It is written to a `tempfile` and invoked as `python _sandbox_worker.py`.

```python
"""
_sandbox_worker.py  —  EMMA Subprocess Sandbox Worker
Reads a JSON execution payload from stdin, runs the code in a
restricted environment, and writes a JSON result to stdout.
Never imported as a module — always executed as __main__.
"""

import sys, os, json, io, traceback, contextlib

def _safe_builtins_dict():
    """Minimal safe builtin subset: no eval, exec, open, __import__, etc."""
    import builtins as _b
    SAFE = {
        "abs","all","any","ascii","bin","bool","bytearray","bytes",
        "callable","chr","complex","dict","divmod","enumerate","filter",
        "float","format","frozenset","hash","hasattr","hex","id","int",
        "isinstance","issubclass","iter","len","list","map","max","min",
        "next","object","oct","ord","pow","print","property","range",
        "repr","reversed","round","set","slice","sorted","staticmethod",
        "str","sum","super","tuple","type","zip",
        "True","False","None","__build_class__","__name__",
    }
    return {k: getattr(_b, k) for k in SAFE if hasattr(_b, k)}

def main():
    payload = json.loads(sys.stdin.read())
    code    = payload["code"]

    # Optional: inject AST Gas Metering before execution
    if payload.get("inject_gas_meter") and payload.get("gas_limit"):
        try:
            from gas_meter import GasMeterTransformer, GasMeterException
            import ast
            tree = ast.parse(code)
            tree = GasMeterTransformer(payload["gas_limit"]).visit(tree)
            ast.fix_missing_locations(tree)
            code_obj = compile(tree, "<sandbox>", "exec")
        except SyntaxError as exc:
            _emit_error(exc, "SyntaxError")
            return
    else:
        try:
            code_obj = compile(code, "<sandbox>", "exec")
        except SyntaxError as exc:
            _emit_error(exc, "SyntaxError")
            return

    g = {
        "__builtins__": _safe_builtins_dict() if payload.get("safe_builtins") else __builtins__,
        "__name__":     "__sandbox__",
    }
    stdout_buf = io.StringIO()
    stderr_buf = io.StringIO()

    try:
        with contextlib.redirect_stdout(stdout_buf), \
             contextlib.redirect_stderr(stderr_buf):
            exec(code_obj, g)    # noqa: S102

        gas = g.get("__gas_counter__", {}).get("count", 0)
        json.dump({
            "success": True, "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(), "exit_code": 0,
            "gas_consumed": gas, "error_type": None,
            "error_message": None, "error_line": None,
        }, sys.stdout)

    except Exception as exc:
        tb = traceback.extract_tb(exc.__traceback__)
        lineno = tb[-1].lineno if tb else None
        json.dump({
            "success": False, "stdout": stdout_buf.getvalue(),
            "stderr": stderr_buf.getvalue(), "exit_code": 1,
            "gas_consumed": g.get("__gas_counter__", {}).get("count", 0),
            "error_type": type(exc).__name__,
            "error_message": str(exc), "error_line": lineno,
        }, sys.stdout)

def _emit_error(exc, error_type: str):
    json.dump({
        "success": False, "stdout": "", "stderr": "",
        "exit_code": 2, "gas_consumed": 0,
        "error_type": error_type,
        "error_message": str(exc),
        "error_line": getattr(exc, "lineno", None),
    }, sys.stdout)

if __name__ == "__main__":
    main()
```

---

## 7. Exit Status Code Mapping Matrix

### 7.1 Cross-Platform Exit Code Semantics

| Exit Code | Platform | Cause | EMMA Classification | Action |
|---|---|---|---|---|
| `0` | All | Execution completed cleanly | `SUCCESS` | Accept output |
| `1` | All | Runtime exception in user code | `RUNTIME_ERROR` | Extract `error_message` |
| `2` | All | SyntaxError during compile | `SYNTAX_ERROR` | Score −100.0 |
| `−1` | Windows | `subprocess.TimeoutExpired` (SIGTERM via `proc.kill()`) | `TIMEOUT` | Score −100.0 |
| `−1` | Unix | `subprocess.TimeoutExpired` (SIGTERM) | `TIMEOUT` | Score −100.0 |
| `−9` | Unix | SIGKILL from OS (OOM killer) | `OOM_KILLED` | Score −100.0 |
| `−6` | Unix | SIGABRT (abort in C extension) | `PROCESS_CRASH` | Score −100.0 |
| `−11` | Unix | SIGSEGV (segmentation fault) | `PROCESS_CRASH` | Score −100.0 |
| `3221225477` | Windows | `STATUS_ACCESS_VIOLATION (0xC0000005)` | `PROCESS_CRASH` | Score −100.0 |
| `3221225786` | Windows | `STATUS_STACK_OVERFLOW (0xC00000FD)` | `PROCESS_CRASH` | Score −100.0 |
| `None` | All | `proc.returncode is None` after timeout | `TIMEOUT` | `proc.kill()` then score −100.0 |
| `42` | All | `GasMeterException` (custom exit) | `GAS_LIMIT_EXCEEDED` | Score −100.0 + log |

### 7.2 OOM Detection on Windows

Windows does **not** send a signal on memory limit breach. The subprocess
is silently terminated by the Job Object. Detection algorithm:

```python
def _classify_windows_exit(returncode: int, timed_out: bool) -> str:
    if timed_out:
        return "TIMEOUT"
    if returncode == 0:
        return "SUCCESS"
    if returncode == 1:
        return "RUNTIME_ERROR"
    if returncode == 2:
        return "SYNTAX_ERROR"
    if returncode == 42:
        return "GAS_LIMIT_EXCEEDED"
    # Windows NTSTATUS codes (unsigned 32-bit wraparound)
    unsigned = returncode & 0xFFFFFFFF
    STATUS_ACCESS_VIOLATION    = 0xC0000005
    STATUS_STACK_OVERFLOW      = 0xC00000FD
    STATUS_NO_MEMORY           = 0xC0000017
    STATUS_COMMITMENT_LIMIT    = 0xC000012D
    if unsigned in (STATUS_NO_MEMORY, STATUS_COMMITMENT_LIMIT):
        return "OOM_KILLED"
    if unsigned in (STATUS_ACCESS_VIOLATION, STATUS_STACK_OVERFLOW):
        return "PROCESS_CRASH"
    return "UNKNOWN_ERROR"
```

---

## 8. 🔱 SUDARSHANA AST Gas Metering Shield

### 8.1 Concept — Why OS Timeouts Are Not Enough

A 30-second OS timeout is the **last line of defence**. It has two
fundamental weaknesses:

1. **Latency:** A tight infinite loop (e.g., `while True: pass`) burns
   30 seconds of CPU before detection. For a hackathon demo with 15 solver
   turns, this is catastrophic.

2. **Determinism:** OS timeout precision varies by scheduler load.
   Measured time ≠ CPU cycles consumed.

**The Sudarshana AST Gas Metering Shield** solves both problems by operating
at the **Python VM instruction level**, below the OS scheduler.

### 8.2 Core Concept — AST Rewriting

The generated code is parsed into an AST. A custom `ast.NodeTransformer`
walks every `For`, `While`, and recursive `Call` node and **injects a gas
check statement** at the loop body entry point. If the accumulated counter
exceeds `GAS_LIMIT`, a `GasMeterException` is raised immediately — without
waiting for the OS.

```
ORIGINAL CODE                    INSTRUMENTED CODE
─────────────                    ─────────────────
while condition:         →       while condition:
    body_statement()                 __gas_check__(50000)
                                     body_statement()

for item in iterable:    →       for item in iterable:
    process(item)                    __gas_check__(50000)
                                     process(item)
```

### 8.3 GasMeterTransformer — Exact Implementation Blueprint

```python
import ast
import textwrap

# ── Custom exception raised when gas limit is exceeded ────────────────────

class GasMeterException(Exception):
    """Raised when the Sudarshana gas counter exceeds GAS_LIMIT."""
    def __init__(self, limit: int, consumed: int) -> None:
        super().__init__(
            f"[SUDARSHANA] Gas limit exceeded: {consumed} > {limit}. "
            "Infinite loop or excessive computation detected. Execution halted."
        )
        self.limit    = limit
        self.consumed = consumed


# ── Gas counter preamble injected at module scope ─────────────────────────

_GAS_PREAMBLE = textwrap.dedent("""
__gas_counter__ = {"count": 0}

def __gas_check__(limit):
    __gas_counter__["count"] += 1
    if __gas_counter__["count"] > limit:
        raise GasMeterException(limit, __gas_counter__["count"])
""")


# ── AST NodeTransformer — injects __gas_check__ at loop/call sites ────────

class GasMeterTransformer(ast.NodeTransformer):
    """
    Rewrites the AST of generated code to inject gas-check statements
    at the entry of every For and While loop body.

    Injection point selection rationale:
      - Inserting at loop BODY ENTRY (not header) ensures the check runs
        on each iteration, not just at loop creation.
      - Recursive function calls are instrumented via a separate
        visit_Call injection that prepends a check before the call site.
      - Comprehensions ([x for x in ...]) are NOT instrumented because
        they have no AST body node — they are bounded by the iterable size.

    Gas limit propagation:
      - `gas_limit` is captured as a closure constant in the injected
        `__gas_check__` call argument, not as a global variable.
        This prevents user code from modifying the limit by overwriting
        a global name.
    """

    def __init__(self, gas_limit: int) -> None:
        self.gas_limit: int = gas_limit

    def _make_gas_check_stmt(self) -> ast.Expr:
        """
        Build the AST node for:  __gas_check__(gas_limit)

        Uses ast.Constant for the limit so it cannot be tampered with
        via global namespace manipulation.
        """
        return ast.Expr(
            value=ast.Call(
                func=ast.Name(id="__gas_check__", ctx=ast.Load()),
                args=[ast.Constant(value=self.gas_limit)],
                keywords=[],
            )
        )

    def visit_For(self, node: ast.For) -> ast.For:
        """Instrument For loop bodies."""
        check = self._make_gas_check_stmt()
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_While(self, node: ast.While) -> ast.While:
        """Instrument While loop bodies."""
        check = self._make_gas_check_stmt()
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_FunctionDef(self, node: ast.FunctionDef) -> ast.FunctionDef:
        """
        Instrument function bodies to catch deep recursion before
        Python's RecursionError ceiling (which is less descriptive).
        """
        check = self._make_gas_check_stmt()
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node

    def visit_AsyncFunctionDef(
        self, node: ast.AsyncFunctionDef
    ) -> ast.AsyncFunctionDef:
        """Instrument async function bodies (same as sync)."""
        check = self._make_gas_check_stmt()
        ast.copy_location(check, node)
        node.body.insert(0, check)
        self.generic_visit(node)
        return node
```

### 8.4 Gas Limit Calibration Table

| Code Pattern | Expected Instructions | Recommended Gas Limit |
|---|---|---|
| Simple arithmetic function | `< 100` | 50,000 |
| List processing (100 items) | `~500` | 50,000 |
| Nested loops (100×100) | `~10,000` | 50,000 |
| Recursive Fibonacci (n=30) | `~2.7M` | 5,000,000 |
| Infinite `while True` | `→ ∞` | Caught at limit |
| `[x for x in range(1M)]` | `~1M` (not metered) | N/A (bounded by range) |

**Default recommended gas limit:** `50,000` for EMMA mutant evaluation.
Adjust upward for complex algorithmic tasks.

### 8.5 Gas Meter Application Flow

```
Generated Code String
        │
        ▼
ast.parse(code)           — SyntaxError → REJECTED immediately
        │
        ▼
GasMeterTransformer       — Injects __gas_check__(50000) at all
  .visit(tree)              For/While/FunctionDef entry points
        │
        ▼
ast.fix_missing_locations — Repair line numbers for error reporting
        │
        ▼
compile(tree, "<sandbox>", "exec")  — Produces instrumented bytecode
        │
        ▼
exec(code_obj, safe_globals)
        │
        ├── Normal completion  → SUCCESS
        ├── GasMeterException  → GAS_LIMIT_EXCEEDED (exit 42)
        ├── RuntimeError       → RUNTIME_ERROR      (exit 1)
        └── Any other          → PROCESS_CRASH      (exit 1)
```

---

## 9. Integration Hook — code_generator.py

### 9.1 Replace `run_sandbox()` — Exact Modification

The existing method:

```python
# BEFORE (in-memory exec — INSECURE)
def run_sandbox(self, code: str) -> SandboxResult:
    ...
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(CodeGenerator._exec_target, ...)
        try:
            exc = future.result(timeout=self.sandbox_timeout)
```

Must be replaced with:

```python
# AFTER (subprocess isolation — PRODUCTION GRADE)
from app.safety.sandbox import run_in_sandbox, SandboxResult

def run_sandbox(self, code: str) -> SandboxResult:
    """
    Execute candidate code in an isolated subprocess sandbox.

    Delegates entirely to sandbox.run_in_sandbox() which:
      - Applies the Sudarshana AST Gas Metering Shield
      - Enforces 256 MB RAM ceiling (OS-level, platform-specific)
      - Enforces 30s timeout via subprocess.Popen.communicate(timeout=)
      - Communicates via structured JSON pipe protocol
      - Returns a SandboxResult with normalised exit classification
    """
    return run_in_sandbox(
        code           = code,
        timeout_s      = self.sandbox_timeout,
        memory_mb      = 256,
        gas_limit      = 50_000,
        safe_builtins  = True,
        inject_gas     = True,
    )
```

### 9.2 `sandbox.run_in_sandbox()` Public Interface

```python
def run_in_sandbox(
    code:          str,
    timeout_s:     float = 30.0,
    memory_mb:     int   = 256,
    gas_limit:     int   = 50_000,
    safe_builtins: bool  = True,
    inject_gas:    bool  = True,
) -> SandboxResult:
    """
    Platform-agnostic subprocess execution sandbox.

    Selects the correct memory-limiting strategy automatically:
      - sys.platform == 'win32'  → Windows Job Object via ctypes
      - sys.platform != 'win32'  → Unix RLIMIT_AS via resource.setrlimit

    Returns a SandboxResult dataclass with all execution metrics.
    Never raises an exception to the caller.
    """
```

---

## 10. Verification Plan

### 10.1 Unit Tests — `tests/test_sandbox.py`

| # | Test Name | Input | Expected Result |
|---|---|---|---|
| 1 | `test_clean_execution` | `print(21 * 2)` | `success=True`, `stdout="42\n"` |
| 2 | `test_syntax_error` | `def f( pass` | `success=False`, `error_type="SyntaxError"` |
| 3 | `test_runtime_error` | `1 / 0` | `success=False`, `error_type="ZeroDivisionError"` |
| 4 | `test_cpu_infinite_loop` | `while True: pass` | `success=False`, `error_type="GasMeterException"` in < 1s |
| 5 | `test_gas_meter_fires` | `for i in range(10**9): pass` | `GAS_LIMIT_EXCEEDED` |
| 6 | `test_memory_bomb` | `x = [0]*100_000_000` | `success=False`, `OOM_KILLED` |
| 7 | `test_blocked_import` | `import subprocess` | `success=False`, `ImportError` |
| 8 | `test_blocked_eval` | `eval("1+1")` | `success=False`, `NameError` (eval not in builtins) |
| 9 | `test_timeout_fires` | `import time; time.sleep(60)` | `success=False`, `TIMEOUT` within `timeout_s + 2` |
| 10 | `test_return_value_capture` | `x = 5 * 5; print(x)` | `stdout="25\n"`, `gas_consumed < 50000` |

### 10.2 Platform Matrix

| Feature | Windows 10/11 | Ubuntu 20.04+ | macOS 12+ |
|---|---|---|---|
| Memory ceiling | Job Object (ctypes) | RLIMIT_AS | RLIMIT_AS |
| CPU timeout | `proc.kill()` after 30s | `proc.kill()` after 30s | `proc.kill()` after 30s |
| Gas Meter | ✅ AST-level (all platforms) | ✅ | ✅ |
| OOM detection | NTSTATUS 0xC000012D | returncode −9 (SIGKILL) | returncode −9 |
| Fork bomb prevention | Job Object `ActiveProcessLimit` | RLIMIT_NPROC = 0 | RLIMIT_NPROC = 0 |

---

*End of Implementation Plan — EMM-05-A2 v2.0*
*SUDARSHANA AST Gas Metering Shield — Novel Feature, Nexus AI Research Lab*
*Next: EMM-05-A3 — Sudarshana Live Dashboard Panel Integration & Sandbox Dry-Runs*
