# backend/app/core/code_generator.py

"""
EMMA Cognitive Core — Code Generator Module
============================================
Evolutionary Mutant Sandboxing and Safe Commit Engine

This module implements the CodeGenerator class, which serves as the gatekeeper
of the EMMA filesystem. It orchestrates the full lifecycle of AI-assisted code
generation: producing candidate patches (mutants), evaluating them through a
hardened in-memory AST-validated sandbox, scoring them via a multi-variable
fitness function, and atomically committing only the highest-scoring valid
winner to disk.

Author: EMMA Cognitive Core Engineering
"""

from __future__ import annotations

import ast
import contextlib
import io
import logging
import os
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.core.context_scheduler import MutantCodeSelector

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

#: Imports that are unconditionally forbidden inside sandboxed mutants.
BLOCKED_IMPORTS: frozenset[str] = frozenset(
    {
        "os",
        "sys",
        "subprocess",
        "shutil",
        "pathlib",
        "socket",
        "importlib",
        "ctypes",
        "multiprocessing",
        "threading",
        "signal",
        "builtins",
        "gc",
        "resource",
        "pty",
        "atexit",
    }
)

#: Built-in names that must not appear as bare Call nodes in sandboxed mutants.
BLOCKED_BUILTINS: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "open",
        "__import__",
        "compile",
        "globals",
        "locals",
        "vars",
        "dir",
        "getattr",
        "setattr",
        "delattr",
        "breakpoint",
        "input",
        "memoryview",
    }
)

#: Base score awarded to every syntactically valid, security-clean mutant.
BASE_SCORE: float = 100.0

#: Penalty applied per source character beyond the parsimony threshold.
LENGTH_PENALTY_RATE: float = 0.01

#: Parsimony threshold: mutants shorter than this are not penalised for length.
PARSIMONY_THRESHOLD: int = 500  # characters

#: Penalty per millisecond of sandbox execution latency.
LATENCY_PENALTY_RATE: float = 0.05

#: Winning score floor — mutants that score at or below this are rejected.
MIN_WINNING_SCORE: float = 0.0


# ---------------------------------------------------------------------------
# Internal data structures
# ---------------------------------------------------------------------------


@dataclass
class MutantReport:
    """Detailed diagnostic record for a single candidate mutant."""

    label: str  # "A", "B", or "C"
    code: str
    syntax_valid: bool = False
    security_clean: bool = False
    security_violations: list[str] = field(default_factory=list)
    stdout_capture: str = ""
    stderr_capture: str = ""
    exec_success: bool = False
    exec_latency_ms: float = 0.0
    length_chars: int = 0
    length_penalty: float = 0.0
    latency_penalty: float = 0.0
    score: float = -100.0
    selector_score: float = 0.0
    rejection_reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise the report to a plain dictionary for JSON output."""
        return {
            "label": self.label,
            "syntax_valid": self.syntax_valid,
            "security_clean": self.security_clean,
            "security_violations": self.security_violations,
            "exec_success": self.exec_success,
            "exec_latency_ms": round(self.exec_latency_ms, 4),
            "length_chars": self.length_chars,
            "length_penalty": round(self.length_penalty, 4),
            "latency_penalty": round(self.latency_penalty, 4),
            "selector_score": round(self.selector_score, 4),
            "final_score": round(self.score, 4),
            "stdout_capture": self.stdout_capture,
            "stderr_capture": self.stderr_capture,
            "rejection_reason": self.rejection_reason,
        }


@dataclass
class GenerationReport:
    """Top-level diagnostic report returned by generate_and_apply_patch."""

    file_path: str
    task: str
    mutants: list[MutantReport] = field(default_factory=list)
    winner_label: str | None = None
    committed: bool = False
    commit_path: str = ""
    error: str = ""

    def to_dict(self) -> dict[str, Any]:
        """Serialise the full report to a plain dictionary for JSON output."""
        return {
            "file_path": self.file_path,
            "task": self.task,
            "mutants": [m.to_dict() for m in self.mutants],
            "winner_label": self.winner_label,
            "committed": self.committed,
            "commit_path": self.commit_path,
            "error": self.error,
        }


# ---------------------------------------------------------------------------
# AST Security Auditor
# ---------------------------------------------------------------------------


class ASTSecurityAuditor(ast.NodeVisitor):
    """
    Walks the AST of a candidate mutant and records any use of blocked imports
    or dangerous built-in calls.

    Usage::

        auditor = ASTSecurityAuditor()
        auditor.visit(tree)
        if auditor.violations:
            # reject the mutant
    """

    def __init__(self) -> None:
        self.violations: list[str] = []

    # ------------------------------------------------------------------
    # Import checks
    # ------------------------------------------------------------------

    def visit_Import(self, node: ast.Import) -> None:  # noqa: N802
        for alias in node.names:
            root = alias.name.split(".")[0]
            if root in BLOCKED_IMPORTS:
                self.violations.append(
                    f"Blocked import '{alias.name}' at line {node.lineno}"
                )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:  # noqa: N802
        if node.module:
            root = node.module.split(".")[0]
            if root in BLOCKED_IMPORTS:
                self.violations.append(
                    f"Blocked from-import '{node.module}' at line {node.lineno}"
                )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Dangerous built-in call checks
    # ------------------------------------------------------------------

    def visit_Call(self, node: ast.Call) -> None:  # noqa: N802
        # Direct calls: eval(...), open(...), __import__(...)
        if isinstance(node.func, ast.Name) and node.func.id in BLOCKED_BUILTINS:
            self.violations.append(
                f"Blocked built-in call '{node.func.id}()' at line {node.lineno}"
            )
        # Attribute calls: builtins.eval(...), etc.
        elif isinstance(node.func, ast.Attribute):
            if node.func.attr in BLOCKED_BUILTINS:
                self.violations.append(
                    f"Blocked attribute call '.{node.func.attr}()' at line {node.lineno}"
                )
        self.generic_visit(node)

    # ------------------------------------------------------------------
    # Prevent dynamic attribute access used to escape sandboxes
    # ------------------------------------------------------------------

    def visit_Attribute(self, node: ast.Attribute) -> None:  # noqa: N802
        # Block dunder escapes: ().__class__.__bases__[0].__subclasses__()
        if node.attr.startswith("__") and node.attr.endswith("__"):
            # Whitelist a small set of safe dunder attributes commonly used in
            # legitimate code; block everything else.
            safe_dunders: frozenset[str] = frozenset(
                {"__init__", "__str__", "__repr__", "__len__", "__name__", "__doc__"}
            )
            if node.attr not in safe_dunders:
                self.violations.append(
                    f"Blocked dunder attribute access '{node.attr}' at line {node.lineno}"
                )
        self.generic_visit(node)


# ---------------------------------------------------------------------------
# CodeGenerator
# ---------------------------------------------------------------------------


class CodeGenerator:
    """
    Manages the generation, sandboxing, evaluation, and atomic committing of
    code patches (mutants) within the EMMA Cognitive Core.

    Lifecycle (per call to :meth:`generate_and_apply_patch`):

    1. **Generate** — :meth:`generate_mutants` produces three candidate source
       strings (Mutant A, B, C) by calling the underlying LLM/simulator.
    2. **Audit** — each mutant is parsed into an AST and inspected by
       :class:`ASTSecurityAuditor` for blocked imports and dangerous built-ins.
    3. **Sandbox** — security-clean mutants are executed in a fully isolated
       ``exec`` environment with captured stdout/stderr and measured latency.
    4. **Score** — a multi-variable fitness function combines the
       :class:`~app.core.context_scheduler.MutantCodeSelector` score with
       length and latency penalties.
    5. **Commit** — the highest-scoring mutant (score > 0) is written to a
       temporary file, verified to compile, then atomically renamed over the
       target path.
    6. **Report** — a :class:`GenerationReport` dictionary is returned
       providing full transparency over every step.

    Parameters
    ----------
    workspace_path:
        Absolute path to the EMMA workspace root. All ``file_path`` arguments
        passed to the public methods are resolved relative to this root.
    """

    def __init__(self, workspace_path: str) -> None:
        self.workspace_path: Path = Path(workspace_path).resolve()
        self.selector: MutantCodeSelector = MutantCodeSelector()
        logger.info(
            "CodeGenerator initialised with workspace_path=%s", self.workspace_path
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_mutants(self, file_path: str, task: str) -> list[str]:
        """
        Produce three alternative source-code implementations (mutants) for
        *task* applied to *file_path*.

        In production this method dispatches to the configured LLM backend and
        requests three structurally distinct completions.  For deterministic
        offline testing the :meth:`_simulate_mutants` helper is used instead.

        Parameters
        ----------
        file_path:
            Path to the target file, relative to :attr:`workspace_path`.
        task:
            Natural-language description of the desired code transformation.

        Returns
        -------
        list[str]
            A list of exactly three source-code strings: [mutant_A, mutant_B,
            mutant_C].

        Raises
        ------
        ValueError
            If fewer than three mutants could be generated.
        """
        logger.debug("Generating mutants for task=%r on file=%r", task, file_path)
        mutants: list[str] = await self._call_llm_for_mutants(file_path, task)
        if len(mutants) < 3:
            raise ValueError(
                f"Expected 3 mutants from LLM, received {len(mutants)}. "
                "Cannot proceed without exactly three candidates."
            )
        return mutants[:3]

    async def generate_and_apply_patch(
        self, file_path: str, task: str
    ) -> dict[str, Any]:
        """
        Coordinate the complete mutant generation, evaluation, and commit
        lifecycle for a single code-generation task.

        Parameters
        ----------
        file_path:
            Path to the target file, relative to :attr:`workspace_path`.
        task:
            Natural-language description of the desired code transformation.

        Returns
        -------
        dict[str, Any]
            A serialisable :class:`GenerationReport` dictionary containing per-
            mutant diagnostics, the winner label, and commit metadata.  The
            ``"committed"`` key is ``True`` only when a valid, high-scoring
            mutant was atomically written to *file_path*.
        """
        resolved_path = self._resolve_path(file_path)
        report = GenerationReport(file_path=str(resolved_path), task=task)

        try:
            raw_mutants: list[str] = await self.generate_mutants(file_path, task)
        except Exception as exc:  # pragma: no cover
            report.error = f"Mutant generation failed: {exc}"
            logger.error(report.error)
            return report.to_dict()

        labels = ["A", "B", "C"]
        mutant_reports: list[MutantReport] = []

        for label, code in zip(labels, raw_mutants):
            mr = self._evaluate_mutant(label=label, code=code)
            mutant_reports.append(mr)
            logger.debug(
                "Mutant %s — score=%.2f  valid=%s  secure=%s",
                label,
                mr.score,
                mr.syntax_valid,
                mr.security_clean,
            )

        report.mutants = mutant_reports

        # Select winner: highest score strictly above MIN_WINNING_SCORE
        eligible = [m for m in mutant_reports if m.score > MIN_WINNING_SCORE]
        if not eligible:
            report.error = (
                "All mutants were rejected (no candidate exceeded the minimum "
                f"score threshold of {MIN_WINNING_SCORE})."
            )
            logger.warning(report.error)
            return report.to_dict()

        winner: MutantReport = max(eligible, key=lambda m: m.score)
        report.winner_label = winner.label
        logger.info(
            "Winner: Mutant %s with score=%.2f", winner.label, winner.score
        )

        committed, commit_path, commit_error = self._atomic_commit(
            target=resolved_path, code=winner.code
        )
        report.committed = committed
        report.commit_path = commit_path
        if not committed:
            report.error = commit_error

        return report.to_dict()

    # ------------------------------------------------------------------
    # Sandbox execution
    # ------------------------------------------------------------------

    def run_sandbox(self, code: str) -> tuple[bool, str, str, float]:
        """
        Execute *code* inside a fully isolated subprocess sandbox.

        Delegates entirely to sandbox.run_in_sandbox() which:
          - Applies the Sudarshana AST Gas Metering Shield
          - Enforces 256 MB RAM ceiling (OS-level, platform-specific)
          - Enforces 30s timeout via subprocess.Popen.communicate(timeout=)
          - Communicates via structured JSON pipe protocol
          - Returns a SandboxResult with normalised exit classification
        """
        from app.safety.sandbox import run_in_sandbox
        result = run_in_sandbox(
            code=code,
            timeout_s=30.0,
            memory_mb=256,
            gas_limit=50_000,
            safe_builtins=True,
            inject_gas=True,
        )
        return result.success, result.stdout, result.stderr, result.latency_ms

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _evaluate_mutant(self, label: str, code: str) -> MutantReport:
        """
        Run the full evaluation pipeline for a single candidate mutant and
        return a populated :class:`MutantReport`.

        Pipeline stages:

        1. AST parse (syntax check).
        2. AST security audit (blocked imports / builtins).
        3. Sandboxed execution with stdout/stderr capture.
        4. Selector scoring via :class:`MutantCodeSelector`.
        5. Multi-variable fitness calculation.

        Parameters
        ----------
        label:
            Human-readable label for this mutant ("A", "B", or "C").
        code:
            The candidate source-code string.

        Returns
        -------
        MutantReport
            Fully populated diagnostic record for this mutant.
        """
        mr = MutantReport(label=label, code=code, length_chars=len(code))

        # --- Stage 1: Syntax validation ---
        try:
            tree = ast.parse(code)
            mr.syntax_valid = True
        except SyntaxError as exc:
            mr.rejection_reason = f"SyntaxError: {exc}"
            mr.score = -100.0
            logger.debug("Mutant %s rejected — syntax error: %s", label, exc)
            return mr

        # --- Stage 2: AST security audit ---
        auditor = ASTSecurityAuditor()
        auditor.visit(tree)
        mr.security_violations = auditor.violations
        if auditor.violations:
            mr.security_clean = False
            mr.rejection_reason = (
                f"Security violations detected: {'; '.join(auditor.violations)}"
            )
            mr.score = -100.0
            logger.warning(
                "Mutant %s rejected — security violations: %s",
                label,
                auditor.violations,
            )
            return mr
        mr.security_clean = True

        # --- Stage 3: Sandboxed execution ---
        success, stdout, stderr, latency_ms = self.run_sandbox(code)
        mr.exec_success = success
        mr.stdout_capture = stdout
        mr.stderr_capture = stderr
        mr.exec_latency_ms = latency_ms

        if not success:
            mr.rejection_reason = f"Runtime error in sandbox: {stderr.strip()}"
            mr.score = -100.0
            logger.debug("Mutant %s rejected — sandbox execution failed.", label)
            return mr

        # --- Stage 4: Selector scoring ---
        try:
            selector_score: float = float(
                self.selector.score(code=code, task="")
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "MutantCodeSelector raised an exception for mutant %s: %s",
                label,
                exc,
            )
            selector_score = 0.0
        mr.selector_score = selector_score

        # --- Stage 5: Multi-variable fitness ---
        length_over_threshold = max(0, len(code) - PARSIMONY_THRESHOLD)
        length_penalty = length_over_threshold * LENGTH_PENALTY_RATE
        latency_penalty = latency_ms * LATENCY_PENALTY_RATE

        mr.length_penalty = length_penalty
        mr.latency_penalty = latency_penalty
        mr.score = (BASE_SCORE + selector_score) - length_penalty - latency_penalty

        logger.debug(
            "Mutant %s — base=%.2f selector=%.2f len_pen=%.2f lat_pen=%.2f => score=%.2f",
            label,
            BASE_SCORE,
            selector_score,
            length_penalty,
            latency_penalty,
            mr.score,
        )
        return mr

    def _atomic_commit(
        self, target: Path, code: str
    ) -> tuple[bool, str, str]:
        """
        Write *code* to *target* via an atomic rename to guarantee that the
        target file is never left in a partially written state.

        The procedure is:

        1. Write *code* to a temporary file in the same directory as *target*
           (ensuring the rename is on the same filesystem).
        2. Compile the temporary file's source to verify it produces valid
           bytecode.
        3. Call :func:`os.replace` to atomically overwrite *target*.

        Parameters
        ----------
        target:
            Absolute resolved path of the file to update.
        code:
            Winning mutant source code to commit.

        Returns
        -------
        tuple[bool, str, str]
            ``(success, committed_path, error_message)`` where *committed_path*
            is the final path of the committed file (same as *target* on
            success) and *error_message* is non-empty only on failure.
        """
        target_dir = target.parent
        target_dir.mkdir(parents=True, exist_ok=True)

        tmp_fd, tmp_path = tempfile.mkstemp(
            suffix=".py.tmp", dir=target_dir, prefix=".emma_commit_"
        )
        try:
            # Write source to temp file
            with os.fdopen(tmp_fd, "w", encoding="utf-8") as fh:
                fh.write(code)

            # Verify the written file compiles cleanly before replacing target
            with open(tmp_path, "r", encoding="utf-8") as fh:
                source = fh.read()
            compile(source, str(target), "exec")

            # Atomic replacement — on POSIX this is guaranteed atomic
            os.replace(tmp_path, target)
            logger.info("Atomic commit successful: %s", target)
            return True, str(target), ""

        except Exception as exc:
            error_msg = (
                f"Atomic commit failed for {target}: {type(exc).__name__}: {exc}"
            )
            logger.error(error_msg)
            # Best-effort cleanup of the temp file
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            return False, "", error_msg

    def _resolve_path(self, file_path: str) -> Path:
        """
        Resolve *file_path* relative to :attr:`workspace_path` and ensure the
        result is still within the workspace (path-traversal guard).

        Parameters
        ----------
        file_path:
            Relative or absolute file path provided by the caller.

        Returns
        -------
        Path
            Resolved absolute path.

        Raises
        ------
        ValueError
            If the resolved path escapes the workspace root.
        """
        resolved = (self.workspace_path / file_path).resolve()
        try:
            resolved.relative_to(self.workspace_path)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: '{file_path}' resolves to '{resolved}', "
                f"which is outside workspace '{self.workspace_path}'."
            )
        return resolved

    async def _call_llm_for_mutants(
        self, file_path: str, task: str
    ) -> list[str]:
        """
        Dispatch to the LLM backend to obtain three candidate mutants.

        In the production environment this method calls the configured LLM
        provider via the EMMA inference router.  During integration tests or
        when the LLM is unavailable, :meth:`_simulate_mutants` is used as a
        deterministic fallback, controlled by the ``EMMA_SIMULATE_LLM``
        environment variable.

        Parameters
        ----------
        file_path:
            Target file path (informational, forwarded to the LLM prompt).
        task:
            Natural-language task description forwarded to the LLM.

        Returns
        -------
        list[str]
            List of three source-code strings.
        """
        if os.environ.get("EMMA_SIMULATE_LLM", "false").lower() == "true":
            logger.info(
                "EMMA_SIMULATE_LLM=true — using deterministic mutant simulator."
            )
            return self._simulate_mutants(task)

        # Production path: delegate to the EMMA inference router.
        # This import is intentionally deferred so that the module remains
        # importable in test environments that mock the inference layer.
        try:
            from app.core.inference_router import InferenceRouter  # type: ignore[import]

            router = InferenceRouter()
            mutants: list[str] = await router.request_mutants(
                file_path=file_path,
                task=task,
                num_mutants=3,
            )
            return mutants
        except ImportError:
            logger.warning(
                "InferenceRouter not available — falling back to mutant simulator."
            )
            return self._simulate_mutants(task)

    @staticmethod
    def _simulate_mutants(task: str) -> list[str]:
        """
        Generate three deterministic synthetic mutants for offline testing.

        * **Mutant A** — Clean, idiomatic, intentionally the best candidate.
        * **Mutant B** — Valid Python but artificially verbose (high length
          penalty).
        * **Mutant C** — Contains a deliberate syntax error to exercise the
          rejection path.

        Parameters
        ----------
        task:
            The task description, embedded in the docstring of each mutant for
            traceability.

        Returns
        -------
        list[str]
            Exactly three source-code strings.
        """
        mutant_a = (
            f'"""\nGenerated mutant A for task: {task}\n"""\n\n'
            "def solution(data):\n"
            '    """Compute the result for the given data."""\n'
            "    return [item * 2 for item in data if isinstance(item, (int, float))]\n"
        )

        mutant_b = (
            f'"""\nGenerated mutant B for task: {task}\n"""\n\n'
            "def solution(data):\n"
            '    """Compute the result for the given data (verbose implementation)."""\n'
            "    result = []\n"
            "    for index in range(len(data)):\n"
            "        item = data[index]\n"
            "        if isinstance(item, int) or isinstance(item, float):\n"
            "            value = item * 2\n"
            "            result.append(value)\n"
            "    return result\n"
            + "# padding\n" * 60  # Inflate length to trigger the parsimony penalty
        )

        # Deliberate SyntaxError: missing colon after def
        mutant_c = (
            f'"""\nGenerated mutant C for task: {task}\n"""\n\n'
            "def solution(data)\n"  # <-- intentional SyntaxError
            '    return data\n'
        )

        return [mutant_a, mutant_b, mutant_c]
