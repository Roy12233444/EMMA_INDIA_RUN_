import sys
import os
import pytest
import time
from app.safety.sandbox import run_in_sandbox

def test_clean_execution():
    """Test that valid Python code executes successfully and returns output."""
    result = run_in_sandbox("print('Hello World')")
    assert result.success is True
    assert result.stdout.strip() == "Hello World"
    assert result.exit_class == "SUCCESS"
    assert result.exit_code == 0


def test_syntax_error():
    """Test that invalid Python code triggers a SyntaxError."""
    result = run_in_sandbox("def faulty_syntax(")
    assert result.success is False
    assert result.exit_class == "SYNTAX_ERROR"
    assert result.error_type == "SyntaxError"


def test_runtime_error():
    """Test that runtime exceptions are correctly caught and reported."""
    result = run_in_sandbox("1 / 0")
    assert result.success is False
    assert result.exit_class == "RUNTIME_ERROR"
    assert result.error_type == "ZeroDivisionError"


def test_cpu_infinite_loop():
    """Test that infinite loops are caught by the gas meter."""
    result = run_in_sandbox("while True: pass", gas_limit=500)
    assert result.success is False
    assert result.exit_class == "GAS_LIMIT_EXCEEDED"
    assert result.error_type == "GasMeterException"


def test_memory_bomb():
    """Test that memory limits or standard allocator ceilings prevent RAM exhaustion."""
    # Allocating 300MB when ceiling is 256MB
    result = run_in_sandbox("x = b'a' * (300 * 1024 * 1024)", memory_mb=256)
    assert result.success is False
    # Memory exhaustion is either caught by the worker as MemoryError
    # or terminated by the OS (OOM_KILLED). Both are safe.
    assert result.exit_class in ("RUNTIME_ERROR", "OOM_KILLED")
    assert result.error_type in ("MemoryError", "OOMKilled")


def test_built_in_isolation():
    """Test that blocked built-in functions are not accessible in the sandbox."""
    # eval is not in the restricted _SAFE_BUILTINS whitelist
    result = run_in_sandbox("eval('1 + 1')")
    assert result.success is False
    assert result.exit_class == "RUNTIME_ERROR"
    assert result.error_type == "NameError"


def test_timeout():
    """Test that processes sleeping/looping beyond the timeout are terminated (without gas injection)."""
    result = run_in_sandbox("while True: pass", inject_gas=False, timeout_s=1.0)
    assert result.success is False
    assert result.exit_class == "TIMEOUT"
    assert result.error_type == "TimeoutExpired"
