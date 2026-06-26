# Implementation Plan: EMM-05-A2 — Mathematical Safety: Jailed Python Sandbox Subprocess

This implementation plan covers Phase 2 and Phase 3 of the `EMM-05-A2` task: building a platform-agnostic jailed Python subprocess sandbox to execute candidate code safely without CPU lockup, RAM exhaustion, or process escape vulnerabilities.

## User Review Required

> [!WARNING]
> To enforce memory limits on Windows, we utilize Windows Job Objects via `ctypes` bindings. If the parent process crashes or terminates abruptly, the `JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE` flag ensures the sandboxed child is forcibly killed by the OS kernel, preventing zombie processes.
> 
> On Linux/macOS, we utilize `resource.setrlimit` with `RLIMIT_AS` (virtual address space) and `RLIMIT_NPROC` (0 for child, blocking further forks).

> [!IMPORTANT]
> The sandbox uses standard library components only (`subprocess`, `tempfile`, `json`, `ctypes`, `resource`). No external dependencies are added.

## Open Questions

None at this stage. The blueprint is fully defined and aligns with the mathematical safety specifications.

## Proposed Changes

---

### Component: Safety Isolation (app/safety)

#### [NEW] [sandbox.py](file:///e:/EMMA_INDIA_RUN/EMMA_hack2skill/backend/app/safety/sandbox.py)
This file will contain the core subprocess sandbox execution logic:
- `SandboxResult`: Dataclass containing execution metrics: `success`, `stdout`, `stderr`, `exit_code`, `gas_consumed`, `error_type`, `error_message`, `error_line`.
- `_apply_windows_memory_cap(pid, limit_bytes)`: Uses `ctypes` to create a Job Object, configure virtual memory limits, and bind the child subprocess.
- `_unix_preexec_fn(memory_bytes)`: Uses the standard `resource` module to set `RLIMIT_AS` and set `RLIMIT_NPROC` to 0.
- `run_in_sandbox(...)`:
  - Serializes options and code to a JSON envelope.
  - Spawns a Python child process running a temporary worker script (`_sandbox_worker.py`).
  - Passes the execution request via stdin, and reads the execution result from stdout.
  - Enforces time limits using `subprocess.Popen.communicate(timeout)`.
  - Classifies the exit status code (e.g. mapping Windows NTSTATUS values like `0xC0000005` or `0xC000012d` and Unix signals like `SIGKILL`, `SIGSEGV` to `OOM_KILLED` or `PROCESS_CRASH`).

#### [MODIFY] [__init__.py](file:///e:/EMMA_INDIA_RUN/EMMA_hack2skill/backend/app/safety/__init__.py)
Exposes the main entry point:
```python
from app.safety.sandbox import run_in_sandbox, SandboxResult
from app.safety.gas_meter import GasMeterException

__all__ = ["run_in_sandbox", "SandboxResult", "GasMeterException"]
```

---

### Component: Cognitive Core Integration (app/core)

#### [MODIFY] [code_generator.py](file:///e:/EMMA_INDIA_RUN/EMMA_hack2skill/backend/app/core/code_generator.py)
Modify `run_sandbox(self, code: str) -> tuple[bool, str, str, float]` to delegate to `run_in_sandbox`:
```python
from app.safety.sandbox import run_in_sandbox

def run_sandbox(self, code: str) -> tuple[bool, str, str, float]:
    result = run_in_sandbox(
        code=code,
        timeout_s=self.sandbox_timeout,
        memory_mb=256,
        gas_limit=50_000,
        safe_builtins=True,
        inject_gas=True,
    )
    # Return 4-tuple for backward compatibility with the existing CodeGenerator evaluate pipeline
    return result.success, result.stdout, result.stderr, result.latency_ms
```

---

## Verification Plan

### Automated Tests
We will create a comprehensive test suite in [test_sandbox.py](file:///e:/EMMA_INDIA_RUN/EMMA_hack2skill/backend/app/tests/test_sandbox.py) to assert:
1. **Normal Execution**: A clean program outputs expected values, returns `success=True`.
2. **Syntax Error**: Invalid Python raises `SyntaxError`.
3. **Runtime Error**: Standard runtime exceptions (e.g., `ZeroDivisionError`) are handled.
4. **Infinite CPU Loop (Gas Meter)**: Deep recursive loops or infinite loops are halted rapidly by `GasMeterException`.
5. **Memory Bomb**: Memory exhaustion is intercepted and classified as `OOM_KILLED` by OS resource limits (Job Objects/RLIMIT_AS).
6. **Built-in Isolation**: Dynamic evaluation/dangerous attributes are blocked.
7. **Timeout**: Code that hangs or sleeps is killed by OS timeouts and classified as `TIMEOUT`.

We will run the verification tests using the pytest runner:
```powershell
py -3 -m pytest backend/app/tests/test_sandbox.py -v
```
And check that all other core tests pass:
```powershell
.\run_tests.bat
```

### Manual Verification
Review logs from `run_sandbox` execution inside a simulated run to ensure no leakage or errors occur.
