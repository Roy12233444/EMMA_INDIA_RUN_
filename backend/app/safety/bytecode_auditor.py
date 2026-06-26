"""
bytecode_auditor.py
===================
EMMA AST Bytecode Auditor & Path Security Whitelist Guards — Phase 4

Provides three interlocking static analysis layers for EMMA's code-generation
pipeline, executed on every winning mutant BEFORE ``os.replace()`` atomic
commit:

  Layer 1 — Path Safety Gate:
    Validates that the target commit path is strictly inside the workspace
    boundary and does not write to protected system directories unless the
    ``force_system`` override flag is set.

  Layer 2 — CommitSafetyVisitor (AST NodeVisitor):
    Walks the full Abstract Syntax Tree to detect:
      • Destructive API calls  (os.remove, shutil.rmtree, sys.exit, ...)
      • Dangerous direct calls (eval, exec, __import__, compile)
      • Forbidden import statements (ctypes, subprocess, signal, ...)
      • Unconditional infinite loops (while True: with no break/return)
      • Dunder escape patterns (__class__.__subclasses__, __globals__, ...)

  Layer 3 — AST Roundtrip Validator:
    Applies ``ast.unparse()`` to the parsed tree and re-parses the result,
    verifying full roundtrip fidelity. Detects malformed AST constructs
    that survive initial parsing but fail during code generation.

Standard library only (ast, pathlib, sys). Python 3.9+.
Zero external dependencies.
"""

import ast
import sys
from pathlib import Path
from typing import FrozenSet, List, Optional, Tuple


# =============================================================================
# Security Constants
# =============================================================================

#: Filesystem directories that require force_system=True to write.
_PROTECTED_PREFIXES: Tuple[str, ...] = (
    "backend/app/core/",
    "backend/app/database/",
    "backend/app/routers/",
    "backend/app/safety/",
    "scripts/",
)

#: Direct builtin names blocked unconditionally.
_BLOCKED_BUILTIN_NAMES: FrozenSet[str] = frozenset({
    "eval",
    "exec",
    "__import__",
    "compile",
    "input",
    "breakpoint",
    "memoryview",
})

#: (module, attribute) pairs for dangerous attribute-style calls.
_BLOCKED_ATTRIBUTE_CALLS: FrozenSet[Tuple[str, str]] = frozenset({
    # os module
    ("os",       "system"),
    ("os",       "remove"),
    ("os",       "rmdir"),
    ("os",       "unlink"),
    ("os",       "popen"),
    ("os",       "execv"),
    ("os",       "execve"),
    ("os",       "execvpe"),
    ("os",       "spawnl"),
    ("os",       "spawnle"),
    ("os",       "fork"),
    ("os",       "kill"),
    # shutil module
    ("shutil",   "rmtree"),
    ("shutil",   "move"),
    ("shutil",   "disk_usage"),
    # sys module
    ("sys",      "exit"),
    ("sys",      "_getframe"),
    # subprocess module
    ("subprocess", "run"),
    ("subprocess", "Popen"),
    ("subprocess", "call"),
    ("subprocess", "check_call"),
    ("subprocess", "check_output"),
    ("subprocess", "getoutput"),
    # pathlib
    ("Path",     "unlink"),
    ("Path",     "rmdir"),
    # ctypes
    ("ctypes",   "CDLL"),
    ("ctypes",   "WinDLL"),
    ("ctypes",   "windll"),
})

#: Top-level module names whose import is blocked.
_BLOCKED_IMPORT_MODULES: FrozenSet[str] = frozenset({
    "subprocess", "ctypes", "signal", "multiprocessing",
    "threading",  "socket",  "ssl",    "ftplib",
    "http",       "urllib",  "email",  "smtplib",
    "pty",        "termios", "fcntl",  "resource",
    "winreg",     "winsound","mmap",   "gc",
    "weakref",    "inspect", "dis",    "importlib",
})

#: Dangerous dunder attribute names indicating sandbox escape attempts.
_BLOCKED_DUNDER_ATTRS: FrozenSet[str] = frozenset({
    "__subclasses__",
    "__bases__",
    "__mro__",
    "__globals__",
    "__builtins__",
    "__code__",
    "__closure__",
    "__reduce__",
    "__reduce_ex__",
    "__getattribute__",
    "__import__",
    "__loader__",
    "__spec__",
})


# =============================================================================
# CommitSafetyVisitor — AST Node Visitor
# =============================================================================

class CommitSafetyVisitor(ast.NodeVisitor):
    """
    Deep AST traversal auditor for generated code mutants.

    Walks every node in the parsed syntax tree and appends a structured
    violation string for every security policy breach detected.

    Usage
    -----
    ::

        visitor = CommitSafetyVisitor()
        visitor.visit(ast.parse(code))
        print(visitor.violations)  # [] = clean, [str, ...] = violations found

    Violation format:
    -----------------
    ``[CATEGORY] Description at line N``

    Categories: ``DESTRUCTIVE_CALL``, ``BLOCKED_BUILTIN``, ``FORBIDDEN_IMPORT``,
    ``DUNDER_ESCAPE``, ``INFINITE_LOOP``, ``DYNAMIC_IMPORT``.
    """

    def __init__(self) -> None:
        self.violations: List[str] = []

    # ── Call node inspection ───────────────────────────────────────────────

    def visit_Call(self, node: ast.Call) -> None:
        """Detect dangerous direct calls and attribute-style API calls."""
        func = node.func
        lineno = getattr(node, "lineno", "?")

        # Direct builtin calls: eval(...), exec(...), __import__(...), etc.
        if isinstance(func, ast.Name):
            if func.id in _BLOCKED_BUILTIN_NAMES:
                self.violations.append(
                    f"[BLOCKED_BUILTIN] '{func.id}()' called directly "
                    f"at line {lineno}. Dynamic execution is forbidden."
                )

        # Attribute-style calls: os.system(), shutil.rmtree(), sys.exit(), ...
        elif isinstance(func, ast.Attribute):
            attr_lineno = getattr(func, "lineno", lineno)

            # Dunder escape pattern: obj.__subclasses__(), obj.__globals__(), ...
            if func.attr in _BLOCKED_DUNDER_ATTRS:
                self.violations.append(
                    f"[DUNDER_ESCAPE] '.{func.attr}()' called "
                    f"at line {attr_lineno}. "
                    "Sandbox escape via dunder attribute detected."
                )

            # Module.method() pattern
            if isinstance(func.value, ast.Name):
                pair = (func.value.id, func.attr)
                if pair in _BLOCKED_ATTRIBUTE_CALLS:
                    self.violations.append(
                        f"[DESTRUCTIVE_CALL] '{func.value.id}.{func.attr}()' "
                        f"at line {attr_lineno}. "
                        "Destructive or privileged API call blocked."
                    )

            # Chained call: pathlib.Path(x).unlink(), Path(x).rmdir(), ...
            elif isinstance(func.value, ast.Call):
                inner_func = func.value.func
                if isinstance(inner_func, ast.Name):
                    pair = (inner_func.id, func.attr)
                    if pair in _BLOCKED_ATTRIBUTE_CALLS:
                        self.violations.append(
                            f"[DESTRUCTIVE_CALL] '{inner_func.id}(...).{func.attr}()' "
                            f"at line {attr_lineno}. "
                            "Chained destructive call blocked."
                        )

        self.generic_visit(node)

    # ── Attribute access inspection (non-call dunders) ────────────────────

    def visit_Attribute(self, node: ast.Attribute) -> None:
        """Detect dangerous dunder attribute access (not necessarily called)."""
        if node.attr in _BLOCKED_DUNDER_ATTRS:
            lineno = getattr(node, "lineno", "?")
            self.violations.append(
                f"[DUNDER_ESCAPE] Attribute access '.{node.attr}' "
                f"at line {lineno}. "
                "Sandbox escape via dunder attribute reference detected."
            )
        self.generic_visit(node)

    # ── Import inspection ─────────────────────────────────────────────────

    def visit_Import(self, node: ast.Import) -> None:
        """Block direct imports of forbidden modules."""
        lineno = getattr(node, "lineno", "?")
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in _BLOCKED_IMPORT_MODULES:
                self.violations.append(
                    f"[FORBIDDEN_IMPORT] 'import {alias.name}' "
                    f"at line {lineno}. "
                    f"Module '{root}' is blocked in generated code."
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Block 'from X import ...' statements for forbidden modules."""
        lineno = getattr(node, "lineno", "?")
        if node.module:
            root = node.module.split(".")[0]
            if root in _BLOCKED_IMPORT_MODULES:
                self.violations.append(
                    f"[FORBIDDEN_IMPORT] 'from {node.module} import ...' "
                    f"at line {lineno}. "
                    f"Module '{root}' is blocked in generated code."
                )
        self.generic_visit(node)

    # ── Infinite loop detection ───────────────────────────────────────────

    def visit_While(self, node: ast.While) -> None:
        """
        Detect unconditional infinite loops without exit paths.

        A loop is flagged when:
          1. The test expression is a literal ``True`` constant.
          2. The entire loop body subtree contains no ``ast.Break``
             or ``ast.Return`` node.

        A ``while True`` with a ``break`` or ``return`` is a valid
        sentinel loop pattern and is NOT flagged.
        """
        lineno = getattr(node, "lineno", "?")

        is_unconditional = (
            isinstance(node.test, ast.Constant)
            and node.test.value is True
        )

        if is_unconditional:
            # Walk the entire loop body subtree for exit nodes
            has_exit = any(
                isinstance(child, (ast.Break, ast.Return))
                for child in ast.walk(node)
            )
            if not has_exit:
                self.violations.append(
                    f"[INFINITE_LOOP] Unconditional 'while True:' with no "
                    f"'break' or 'return' detected at line {lineno}. "
                    "This construct would hang the executor indefinitely."
                )

        self.generic_visit(node)

    # ── Dynamic import via __import__ or importlib ────────────────────────

    def visit_Expr(self, node: ast.Expr) -> None:
        """Catch standalone __import__('module') expression statements."""
        if isinstance(node.value, ast.Call):
            func = node.value.func
            lineno = getattr(node, "lineno", "?")
            if isinstance(func, ast.Name) and func.id == "__import__":
                self.violations.append(
                    f"[DYNAMIC_IMPORT] '__import__(...)' called as standalone "
                    f"expression at line {lineno}."
                )
        self.generic_visit(node)


# =============================================================================
# Layer 1 — Path Safety Gate
# =============================================================================

def validate_target_path(
    target_path:    str,
    workspace_root: str,
    force_system:   bool = False,
) -> None:
    """
    Validate that a commit target path is safe to write.

    Security Checks
    ---------------
    1. **Workspace boundary** — ``target_path`` must be a descendant of
       ``workspace_root`` after resolving all symlinks and ``../`` escapes
       via ``Path.resolve()``.

    2. **Protected directory gate** — ``target_path`` must not fall inside
       any of the protected system prefixes unless ``force_system=True``.

    Parameters
    ----------
    target_path : str
        Relative or absolute path of the file to be committed.
    workspace_root : str
        Absolute path of the EMMA workspace root directory.
    force_system : bool
        If ``True``, bypass the protected directory check.
        Never set this in automated CI/CD pipelines.

    Raises
    ------
    ValueError
        With a structured ``PATH_ESCAPE`` or ``PROTECTED_PATH`` prefix on
        any policy violation.
    """
    abs_root   = Path(workspace_root).resolve()
    abs_target = Path(target_path).resolve()

    # ── Check 1: Workspace boundary ───────────────────────────────────────
    try:
        rel = abs_target.relative_to(abs_root)
    except ValueError:
        raise ValueError(
            f"PATH_ESCAPE: Target '{target_path}' resolves to '{abs_target}', "
            f"which is outside the workspace boundary '{abs_root}'. "
            "Commit blocked. Potential directory traversal attack."
        )

    # ── Check 2: Protected system directories ─────────────────────────────
    if not force_system:
        rel_str = str(rel).replace("\\", "/")
        for prefix in _PROTECTED_PREFIXES:
            if rel_str.startswith(prefix) or rel_str == prefix.rstrip("/"):
                raise ValueError(
                    f"PROTECTED_PATH: Cannot write to protected system directory "
                    f"'{prefix}' without --force-system flag.\n"
                    f"  Resolved target : {abs_target}\n"
                    f"  Relative path   : {rel_str}\n"
                    f"  To override     : pass force_system=True explicitly."
                )


# =============================================================================
# Layer 3 — AST Roundtrip Validator
# =============================================================================

def _ast_roundtrip_validate(tree: ast.AST, code: str) -> List[str]:
    """
    Verify AST roundtrip fidelity via ``ast.unparse()`` → re-parse.

    Detects malformed AST constructs that survive initial parsing but
    generate invalid Python when unparsed — a class of error that can
    arise from adversarially-crafted code or non-standard AST mutations.

    Parameters
    ----------
    tree : ast.AST
        Pre-parsed AST of the candidate code.
    code : str
        Original source string (used in violation messages only).

    Returns
    -------
    list[str]
        Violation strings (empty = roundtrip clean).
    """
    violations: List[str] = []

    try:
        unparsed: str = ast.unparse(tree)
    except AttributeError:
        # ast.unparse requires Python 3.9+
        violations.append(
            "[AST_ROUNDTRIP] ast.unparse() unavailable. "
            "Python 3.9+ is required for roundtrip validation."
        )
        return violations
    except Exception as exc:
        violations.append(
            f"[AST_ROUNDTRIP_FAIL] ast.unparse() raised an exception: {exc}. "
            "The AST may contain non-standard node types."
        )
        return violations

    if not unparsed.strip():
        violations.append(
            "[AST_ROUNDTRIP_FAIL] ast.unparse() produced an empty string "
            "from a non-empty source. AST may be malformed."
        )
        return violations

    try:
        ast.parse(unparsed)
    except SyntaxError as exc:
        violations.append(
            f"[AST_ROUNDTRIP_FAIL] Re-parsing the unparsed AST raised "
            f"SyntaxError at line {exc.lineno}: {exc.msg}. "
            "The code is not losslessly representable."
        )

    return violations


# =============================================================================
# Primary Public API — deep_ast_validate
# =============================================================================

def deep_ast_validate(
    code:           str,
    target_path:    str,
    workspace_root: str,
    force_system:   bool = False,
) -> List[str]:
    """
    Execute the full three-layer safety audit on a candidate code mutant.

    Pipeline
    --------
    1. **Path Safety Gate** (Layer 1) — validates ``target_path`` is inside
       the workspace and not a protected system directory.
    2. **Syntax Check** — parses ``code`` via ``ast.parse()``.
       A ``SyntaxError`` here short-circuits all further checks.
    3. **CommitSafetyVisitor** (Layer 2) — traverses the full AST for
       destructive calls, forbidden imports, dunder escapes, and infinite loops.
    4. **Roundtrip Validation** (Layer 3) — verifies ``ast.unparse()`` fidelity.

    Parameters
    ----------
    code : str
        Source code string of the candidate mutant to audit.
    target_path : str
        Intended filesystem target of the atomic commit.
    workspace_root : str
        Absolute workspace root path (used for path boundary checks).
    force_system : bool
        If ``True``, bypass the protected directory check in Layer 1.

    Returns
    -------
    list[str]
        Complete list of all detected violations across all layers.
        An **empty list** signifies the code is fully safe to commit.
        A **non-empty list** means the code must be rejected.

    Examples
    --------
    ::

        violations = deep_ast_validate(code, "backend/app/target.py", "/workspace")
        if violations:
            print("REJECTED:", violations)
        else:
            os.replace(tmp_path, target_path)  # Safe to commit
    """
    all_violations: List[str] = []

    # ── Layer 1: Path safety gate ──────────────────────────────────────────
    try:
        validate_target_path(target_path, workspace_root, force_system)
    except ValueError as exc:
        all_violations.append(str(exc))
        # Path violation is a hard block — skip further checks
        return all_violations

    # ── Layer 2a: Syntax check (parse gate) ───────────────────────────────
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        all_violations.append(
            f"[SYNTAX_ERROR] ast.parse() failed at line {exc.lineno}: "
            f"{exc.msg}. Code cannot be committed."
        )
        # No tree to traverse — stop here
        return all_violations
    except Exception as exc:
        all_violations.append(
            f"[PARSE_ERROR] Unexpected error during ast.parse(): {exc}"
        )
        return all_violations

    # ── Layer 2b: CommitSafetyVisitor traversal ───────────────────────────
    visitor = CommitSafetyVisitor()
    try:
        visitor.visit(tree)
    except Exception as exc:
        all_violations.append(
            f"[VISITOR_ERROR] CommitSafetyVisitor raised an exception: {exc}"
        )
    all_violations.extend(visitor.violations)

    # ── Layer 3: AST roundtrip validation ─────────────────────────────────
    roundtrip_violations = _ast_roundtrip_validate(tree, code)
    all_violations.extend(roundtrip_violations)

    return all_violations


# =============================================================================
# Convenience wrapper for single-result commit decision
# =============================================================================

def is_safe_to_commit(
    code:           str,
    target_path:    str,
    workspace_root: str,
    force_system:   bool = False,
) -> Tuple[bool, List[str]]:
    """
    Convenience wrapper — returns a (safe, violations) tuple.

    Parameters
    ----------
    code : str
        Candidate mutant source code.
    target_path : str
        Intended commit target path.
    workspace_root : str
        Workspace root for path boundary checks.
    force_system : bool
        Bypass protected directory check if True.

    Returns
    -------
    tuple[bool, list[str]]
        ``(True, [])``  — safe to commit, no violations.
        ``(False, [...])`` — unsafe, violations list non-empty.
    """
    violations = deep_ast_validate(code, target_path, workspace_root, force_system)
    return (len(violations) == 0, violations)


# =============================================================================
# Standalone Demo — python backend/app/safety/bytecode_auditor.py
# =============================================================================

if __name__ == "__main__":

    _WORKSPACE = "/workspace/emma"
    _TARGET    = "/workspace/emma/backend/app/tasks/oauth_repair.py"

    _DIVIDER = "─" * 72

    def _report(label: str, violations: List[str]) -> None:
        print(f"\n{_DIVIDER}")
        print(f"  TEST: {label}")
        print(_DIVIDER)
        if violations:
            print(f"  ❌  REJECTED  ({len(violations)} violation(s)):\n")
            for v in violations:
                print(f"    • {v}")
        else:
            print("  ✅  CLEAN — safe to commit.\n")

    # ── Demo 1: Clean, minimal safe code ─────────────────────────────────
    _SAFE_CODE = '''
def repair_token_header(headers: dict) -> dict:
    """Repair malformed OAuth Bearer prefix."""
    if "Authorization" in headers:
        headers["Authorization"] = (
            headers["Authorization"].replace("Bearer ", "Token ")
        )
    return headers
'''
    _report(
        "SAFE CODE — minimal valid function",
        deep_ast_validate(_SAFE_CODE, _TARGET, _WORKSPACE),
    )

    # ── Demo 2: Destructive call — os.remove() ────────────────────────────
    _DESTRUCTIVE_CODE = '''
import os

def malicious_patch():
    os.remove("/etc/passwd")
    os.system("rm -rf /")
    return True
'''
    _report(
        "UNSAFE CODE — os.remove + os.system",
        deep_ast_validate(_DESTRUCTIVE_CODE, _TARGET, _WORKSPACE),
    )

    # ── Demo 3: eval() + exec() builtins ─────────────────────────────────
    _EVAL_CODE = '''
def sneaky_eval(user_input: str):
    result = eval(user_input)
    exec("import os; os.system('whoami')")
    return result
'''
    _report(
        "UNSAFE CODE — eval() + exec()",
        deep_ast_validate(_EVAL_CODE, _TARGET, _WORKSPACE),
    )

    # ── Demo 4: Forbidden import ──────────────────────────────────────────
    _IMPORT_CODE = '''
import subprocess
from ctypes import CDLL

def run_shell(cmd: str) -> str:
    return subprocess.check_output(cmd, shell=True).decode()
'''
    _report(
        "UNSAFE CODE — forbidden imports (subprocess, ctypes)",
        deep_ast_validate(_IMPORT_CODE, _TARGET, _WORKSPACE),
    )

    # ── Demo 5: Infinite loop — while True: no break ──────────────────────
    _INFINITE_CODE = '''
def hang_forever():
    while True:
        print("spinning...")
'''
    _report(
        "UNSAFE CODE — unconditional infinite loop (no break/return)",
        deep_ast_validate(_INFINITE_CODE, _TARGET, _WORKSPACE),
    )

    # ── Demo 6: while True with break — SHOULD PASS ──────────────────────
    _SENTINEL_CODE = '''
def poll_until_ready(queue):
    while True:
        item = queue.get()
        if item is None:
            break
        yield item
'''
    _report(
        "SAFE CODE — while True with break (sentinel loop pattern)",
        deep_ast_validate(_SENTINEL_CODE, _TARGET, _WORKSPACE),
    )

    # ── Demo 7: Path escape attack ────────────────────────────────────────
    _ESCAPE_TARGET = "/workspace/emma/../../../etc/crontab"
    _report(
        "PATH ESCAPE — target resolves outside workspace",
        deep_ast_validate(_SAFE_CODE, _ESCAPE_TARGET, _WORKSPACE),
    )

    # ── Demo 8: Protected system path ────────────────────────────────────
    _SYS_TARGET = "/workspace/emma/backend/app/core/orchestrator.py"
    _report(
        "PROTECTED PATH — write to backend/app/core/ without force_system",
        deep_ast_validate(_SAFE_CODE, _SYS_TARGET, _WORKSPACE),
    )

    # ── Demo 9: Protected path with force_system override ────────────────
    _report(
        "PROTECTED PATH — same path with force_system=True (override)",
        deep_ast_validate(_SAFE_CODE, _SYS_TARGET, _WORKSPACE, force_system=True),
    )

    # ── Demo 10: Dunder escape ────────────────────────────────────────────
    _DUNDER_CODE = '''
def escape_sandbox(obj):
    klass = obj.__class__
    subs  = klass.__subclasses__()
    return subs[0].__globals__["__builtins__"]
'''
    _report(
        "UNSAFE CODE — dunder escape chain (__class__, __subclasses__, __globals__)",
        deep_ast_validate(_DUNDER_CODE, _TARGET, _WORKSPACE),
    )

    print(f"\n{_DIVIDER}")
    print("  BytecodeAuditor demo complete.")
    print(_DIVIDER + "\n")
