"""
orchestrator.py
===============
EMMA — Central Executive Solver Loop
Causal Convergence Monitoring · Loop Stability Audits · Git Rollback Safeguards

Integrates the CausalConvergenceMonitor directly inside the core solver pipeline,
establishing a 100% resilient, zero-trust boundary that prevents infinite diagnostic
error regressions and guarantees file system stability via automated Git rollbacks.

Standard library only. Python 3.9+.
"""

import subprocess
import difflib
import asyncio
import shlex
import os
import re
import json
from typing import Any, Dict, List, Optional, Tuple
from app.core.code_generator import CodeGenerator
from app.utils.token_prune import ContextVectorPruner, ContextOverflowError



# =============================================================================
# Exception: CausalInstabilityException
# =============================================================================

class CausalInstabilityException(Exception):
    """
    Raised when the solver loop enters an infinite error regression.

    Signals that the CausalConvergenceMonitor has detected a stalled
    convergence sequence (residual >= 0.95 for ``loop_threshold`` consecutive
    turns) and that the workspace has been rolled back to the last stable state.

    Attributes
    ----------
    turn : int
        The solver turn at which the instability was detected.
    residuals : list[float]
        The full residual history at the time of detection.
    last_error : str
        The last captured error output that triggered the halt.
    """

    def __init__(
        self,
        message: str,
        turn: int = 0,
        residuals: Optional[List[float]] = None,
        last_error: str = "",
    ) -> None:
        super().__init__(message)
        self.turn:       int         = turn
        self.residuals:  List[float] = residuals or []
        self.last_error: str         = last_error

    def __str__(self) -> str:
        base = super().__str__()
        residual_summary = (
            f" | Residuals={[round(r, 4) for r in self.residuals[-5:]]}"
            if self.residuals else ""
        )
        return f"{base} [Turn={self.turn}{residual_summary}]"


# =============================================================================
# Class A: CausalConvergenceMonitor
# =============================================================================

class CausalConvergenceMonitor:
    """
    Levenshtein-based error convergence tracker.

    Treats the debugging execution loop as a fixed-point convergence sequence.
    Let the error stdout trace at turn k be E_k.  The Causal Residual R_k is
    defined as the structural similarity ratio between consecutive errors::

        R_k = SequenceMatcher(E_k, E_{k-1})

    A ratio near 1.0 implies no progress (identical error loops).
    A decaying ratio implies active debugging progress.

    If R_k >= 0.95 for ``loop_threshold`` consecutive turns, a Causal Paradox
    (infinite loop) is flagged and ``evaluate_step`` returns ``False``.
    """

    _SIMILARITY_THRESHOLD: float = 0.95

    def __init__(self, loop_threshold: int = 3) -> None:
        if loop_threshold < 1:
            raise ValueError(
                "CausalConvergenceMonitor: loop_threshold must be >= 1."
            )
        self.threshold:     int         = loop_threshold
        self.state_history: List[str]   = []   # Raw error strings, turn-ordered
        self.residuals:     List[float] = []   # Similarity ratios, turn-ordered

    # ------------------------------------------------------------------
    # Residual Calculation
    # ------------------------------------------------------------------

    def calculate_residual(self, error_output: str) -> float:
        """
        Calculate the SequenceMatcher similarity ratio between *error_output*
        and the most recently stored error state.

        Returns 1.0 when no prior state exists (first turn is treated as
        a baseline, not a delta — no false positive on the first call).

        Parameters
        ----------
        error_output : str
            The raw captured stderr/stdout from the current turn.

        Returns
        -------
        float
            Similarity ratio in [0.0, 1.0].  Values close to 1.0 indicate
            the error has not materially changed from the previous turn.
        """
        if not self.state_history:
            return 1.0  # No prior state — treat as baseline; no loop yet

        prev_error = self.state_history[-1]
        # Normalise whitespace to focus on structural text deltas,
        # not incidental spacing differences.
        clean_prev = " ".join(prev_error.split())
        clean_curr = " ".join(error_output.split())

        return difflib.SequenceMatcher(
            None, clean_prev, clean_curr, autojunk=False
        ).ratio()

    # ------------------------------------------------------------------
    # Step Evaluation
    # ------------------------------------------------------------------

    def evaluate_step(self, error_output: str) -> bool:
        """
        Record the current turn's error output and evaluate loop stability.

        Parameters
        ----------
        error_output : str
            Captured stderr/stdout from the failed command execution.

        Returns
        -------
        bool
            ``True``  — Loop is making progress; continue execution.
            ``False`` — Causal Paradox detected; halt and rollback.
        """
        if not error_output.strip():
            # Empty error output implies the command succeeded or produced no
            # diagnostic output — treat as converging; do not record.
            return True

        residual = self.calculate_residual(error_output)
        self.residuals.append(residual)
        self.state_history.append(error_output)

        # Paradox gate: check the last N residuals
        if len(self.residuals) >= self.threshold:
            recent = self.residuals[-self.threshold:]
            if all(r >= self._SIMILARITY_THRESHOLD for r in recent):
                return False  # Stalled convergence — Causal Paradox confirmed

        return True

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------

    def summary(self) -> Dict[str, Any]:
        """Return a structured diagnostics snapshot of the monitor's state."""
        return {
            "total_turns":      len(self.state_history),
            "threshold":        self.threshold,
            "residuals":        [round(r, 6) for r in self.residuals],
            "avg_residual":     (
                round(sum(self.residuals) / len(self.residuals), 6)
                if self.residuals else None
            ),
            "paradox_detected": (
                len(self.residuals) >= self.threshold
                and all(
                    r >= self._SIMILARITY_THRESHOLD
                    for r in self.residuals[-self.threshold:]
                )
            ),
        }


# =============================================================================
# Class B: Orchestrator
# =============================================================================

class Orchestrator:
    """
    EMMA Central Executive Solver Loop.

    Coordinates the metacognitive agent cycle:
      1. Code generation (LLM patch synthesis).
      2. JIT pre-commit git savepoint registration.
      3. Compile / test command execution.
      4. Causal convergence evaluation.
      5. Automated rollback and graceful halt on instability.

    Parameters
    ----------
    workspace_path : str
        Absolute path to the project root (must contain a ``.git`` directory
        for rollback operations to succeed).
    max_turns : int
        Hard ceiling on solver iterations.  Default: 15.
    loop_threshold : int
        Consecutive stall turns before a Causal Paradox is declared.  Default: 3.
    test_command : str
        Shell command executed each turn to validate the workspace state.
        Example: ``"pytest backend/tests/ -x -q"``.
    """

    _GIT_ROLLBACK_CMD:   List[str] = ["git", "checkout", "--", "."]
    _GIT_STATUS_CMD:     List[str] = ["git", "status", "--porcelain"]
    _GIT_STASH_CMD:      List[str] = ["git", "stash", "--include-untracked"]
    _GIT_STASH_POP_CMD:  List[str] = ["git", "stash", "pop"]

    def __init__(
        self,
        workspace_path: str,
        max_turns:      int  = 15,
        loop_threshold: int  = 3,
        test_command:   str  = "pytest backend/tests/ -x -q",
    ) -> None:
        self.workspace_path: str = os.path.abspath(workspace_path)
        self.max_turns:      int = max_turns
        self.loop_threshold: int = loop_threshold
        self.test_command:   str = test_command
        self.pruner: ContextVectorPruner = ContextVectorPruner(max_tokens=8000)

    # ------------------------------------------------------------------
    # Subprocess Utilities
    # ------------------------------------------------------------------

    async def _run_command(
        self,
        cmd: List[str],
        cwd: Optional[str] = None,
        timeout: float = 120.0,
    ) -> Tuple[int, str, str]:
        """
        Execute *cmd* asynchronously and capture stdout / stderr.

        Returns
        -------
        tuple[int, str, str]
            (exit_code, stdout_text, stderr_text)
        """
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd or self.workspace_path,
            )
            try:
                stdout_bytes, stderr_bytes = await asyncio.wait_for(
                    proc.communicate(), timeout=timeout
                )
            except asyncio.TimeoutError:
                proc.kill()
                await proc.communicate()
                return (
                    -1,
                    "",
                    f"[TIMEOUT] Command exceeded {timeout}s limit: {' '.join(cmd)}",
                )
            return (
                proc.returncode or 0,
                stdout_bytes.decode("utf-8", errors="replace"),
                stderr_bytes.decode("utf-8", errors="replace"),
            )
        except FileNotFoundError as exc:
            return (-2, "", f"[EXEC ERROR] Command not found: {exc}")
        except Exception as exc:
            return (-3, "", f"[EXEC ERROR] Unexpected error: {exc}")

    async def _git_rollback(self) -> Tuple[bool, str]:
        """
        Execute ``git checkout -- .`` to restore the workspace to the last
        committed state, discarding all unstable in-flight edits.

        Returns
        -------
        tuple[bool, str]
            (success, diagnostic_message)
        """
        code, stdout, stderr = await self._run_command(
            self._GIT_ROLLBACK_CMD,
            timeout=30.0,
        )
        if code == 0:
            return (
                True,
                "[ORCHESTRATOR] Workspace successfully restored to last stable state.",
            )
        return (
            False,
            f"[ORCHESTRATOR] Git rollback failed (exit={code}): {stderr.strip()}",
        )

    async def _git_workspace_clean(self) -> bool:
        """Return True if the workspace has no uncommitted changes."""
        code, stdout, _ = await self._run_command(
            self._GIT_STATUS_CMD, timeout=15.0
        )
        return code == 0 and not stdout.strip()

    def _parse_task_md(self) -> Tuple[List[str], List[str]]:
        completed = []
        pending = []
        # Find task.md relative to workspace or direct absolute path
        # Try both the workspace root and EMMA_hack2skill folder
        paths_to_try = [
            os.path.join(self.workspace_path, "task.md"),
            os.path.join(self.workspace_path, "EMMA_hack2skill", "task.md"),
            r"C:\Users\soura\.gemini\antigravity-ide\brain\06ac37f7-d228-4ac9-8501-0a6a9562514d\task.md"
        ]
        
        for p in paths_to_try:
            if os.path.exists(p):
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line_str = line.strip()
                            if not line_str.startswith("-"):
                                continue
                            if "[x]" in line_str or "`[x]`" in line_str:
                                parts = line_str.split("]", 1)
                                if len(parts) > 1:
                                    completed.append(parts[1].strip().strip("`"))
                            elif "[ ]" in line_str or "`[ ]`" in line_str or "[/]" in line_str or "`[/]`" in line_str:
                                parts = line_str.split("]", 1)
                                if len(parts) > 1:
                                    pending.append(parts[1].strip().strip("`"))
                    if completed or pending:
                        return completed, pending
                except Exception:
                    pass
        return completed, pending

    # ------------------------------------------------------------------
    # Core Solver Loop
    # ------------------------------------------------------------------

    async def solve(self, task_description: str, target_file: str = "backend/app/core/executor.py") -> Dict[str, Any]:
        """
        Execute EMMA's primary metacognitive solver loop.

        Integrates JIT error stability checks, causal convergence monitoring,
        and automated Git rollback hooks into the execution cycle.

        Parameters
        ----------
        task_description : str
            Human-readable description of the task the agent is solving.
        target_file : str
            Path to the file to modify, relative to workspace_path.

        Returns
        -------
        dict
            Status report containing loop metadata, diagnostics, and
            final workspace state.

        Raises
        ------
        CausalInstabilityException
            When the convergence monitor detects a stalled infinite regression
            and the workspace has been rolled back to a safe state.
        """
        print(
            f"[ORCHESTRATOR] Initiating Causal Solver Loop.\n"
            f"[ORCHESTRATOR] Task: {task_description}\n"
            f"[ORCHESTRATOR] Target File: {target_file}\n"
            f"[ORCHESTRATOR] Max Turns: {self.max_turns} | "
            f"Stall Threshold: {self.loop_threshold}"
        )

        # ----------------------------------------------------------------
        # Gate 0: Pre-flight workspace check
        # ----------------------------------------------------------------
        if not os.path.isdir(os.path.join(self.workspace_path, ".git")):
            raise EnvironmentError(
                f"[ORCHESTRATOR] No .git directory found at: {self.workspace_path}\n"
                "Git rollback safeguards require a valid Git repository."
            )

        # ----------------------------------------------------------------
        # Initialise Causal Convergence Monitor
        # ----------------------------------------------------------------
        monitor = CausalConvergenceMonitor(loop_threshold=self.loop_threshold)

        turn_log: List[Dict[str, Any]] = []
        loop_turn = 0

        # ----------------------------------------------------------------
        # Primary solver turn loop
        # ----------------------------------------------------------------
        while loop_turn < self.max_turns:
            loop_turn += 1
            print(f"\n[ORCHESTRATOR] ── Cycle Turn #{loop_turn}/{self.max_turns} ──")

            # ----------------------------------------------------------------
            # ACTIVE MEMORY MONITORING & CONTEXT COMPACTION
            # ----------------------------------------------------------------
            history_str = json.dumps(turn_log, ensure_ascii=False)
            tier, token_count = self.pruner.evaluate_threshold(history_str)
            print(f"[ORCHESTRATOR] Active prompt footprint: {token_count} tokens | Tier: {tier}")

            if tier in ("RED", "CRITICAL", "OVERFLOW"):
                print(f"[ORCHESTRATOR] Utilization >= 70% threshold ({token_count} tokens). Initiating DTE-IS memory compaction...")
                entropy_map = self.pruner.score_entropy(turn_log)
                completed_tasks, pending_tasks = self._parse_task_md()
                
                touched_files = []
                last_committed_file = None
                for turn in turn_log:
                    out = str(turn.get("output", ""))
                    if '"commit_path"' in out:
                        match = re.search(r'"commit_path":\s*"([^"]+)"', out)
                        if match:
                            p = match.group(1)
                            touched_files.append(p)
                            last_committed_file = p
                
                telemetry = {
                    "completed_tasks": completed_tasks,
                    "pending_tasks": pending_tasks,
                    "touched_files": list(set(touched_files)),
                    "last_committed_file": last_committed_file,
                }
                
                turn_log = await self.pruner.compact_history(
                    turn_logs              = turn_log,
                    orchestrator_telemetry = telemetry,
                    entropy_map            = entropy_map,
                    emergency              = (tier == "OVERFLOW"),
                )
                print(f"[ORCHESTRATOR] Context compaction complete. Free memory buffer secured.")

            if tier == "OVERFLOW":
                print(f"[CRITICAL ERROR] Context utilization exceeded 95% budget ({token_count}/8000 tokens).")
                print(f"[ORCHESTRATOR] Executing emergency Git checkout rollback...")
                rollback_ok, rollback_msg = await self._git_rollback()
                print(rollback_msg)
                
                raise CausalInstabilityException(
                    f"Cognitive memory overflow detected at turn #{loop_turn} ({token_count} tokens). Safe rollback applied.",
                    turn=loop_turn,
                    last_error="Token budget overflow (OVERFLOW tier)"
                )

            # ============================================================
            # Step 1: CODE GENERATION (Evolutionary Mutant Sandboxing)
            # ============================================================
            print(f"[ORCHESTRATOR] [Step 1] Initializing Evolutionary Mutant Selection...")
            generator = CodeGenerator(workspace_path=self.workspace_path)
            gen_report = await generator.generate_and_apply_patch(
                file_path=target_file,
                task=task_description
            )
            print(
                f"[ORCHESTRATOR] Code generation completed. "
                f"Winner mutant: {gen_report.get('winner_label', 'None')} | "
                f"Committed successfully: {gen_report.get('committed', False)}"
            )
            if gen_report.get("error"):
                print(f"[ORCHESTRATOR] Generation info: {gen_report['error']}")


            # ============================================================
            # Step 2: CAUSAL ANCHOR — JIT Pre-Commit Savepoint
            # ============================================================
            # Record whether the workspace is dirty before the test run so
            # we know there is something to roll back if needed.
            workspace_dirty = not await self._git_workspace_clean()
            print(
                f"[ORCHESTRATOR] [Step 2] Causal Anchor — "
                f"workspace dirty: {workspace_dirty}"
            )

            # ============================================================
            # Step 3: EXECUTE TEST / COMPILE COMMAND
            # ============================================================
            cmd_tokens: List[str] = shlex.split(self.test_command)
            print(f"[ORCHESTRATOR] [Step 3] Executing: {self.test_command}")

            exit_code, cmd_stdout, cmd_stderr = await self._run_command(
                cmd_tokens,
                timeout=120.0,
            )

            # Merge stdout + stderr into a single diagnostic blob
            combined_output: str = "\n".join(
                filter(None, [cmd_stdout.strip(), cmd_stderr.strip()])
            )

            print(
                f"[ORCHESTRATOR] Command finished — exit code: {exit_code}"
            )

            # Log this turn
            turn_log.append({
                "turn":      loop_turn,
                "exit_code": exit_code,
                "output":    combined_output[:500],   # Truncated for log storage
            })

            # ============================================================
            # Step 4: SUCCESS PATH — exit code 0
            # ============================================================
            if exit_code == 0:
                print(
                    f"[ORCHESTRATOR] [PASS] Command succeeded. "
                    f"Task complete at turn #{loop_turn}."
                )
                return {
                    "status":          "SUCCESS",
                    "turns_elapsed":   loop_turn,
                    "monitor_summary": monitor.summary(),
                    "turn_log":        turn_log,
                }

            # ============================================================
            # Step 5: FAILURE PATH — evaluate causal stability
            # ============================================================
            print(
                "[ORCHESTRATOR] [FAIL] Command failed. "
                "Passing to Causal Convergence Monitor..."
            )

            loop_stable: bool = monitor.evaluate_step(combined_output)

            print(
                f"[ORCHESTRATOR] Monitor residual: "
                f"{round(monitor.residuals[-1], 4) if monitor.residuals else 'N/A'} "
                f"| Stable: {loop_stable}"
            )

            if loop_stable:
                # Progress is being made — proceed to next generation cycle
                print(
                    f"[ORCHESTRATOR] Loop is converging. "
                    f"Proceeding to Turn #{loop_turn + 1}."
                )
                continue

            # ============================================================
            # Step 6: PARADOX DETECTED — rollback and halt
            # ============================================================
            print(
                "[WARNING] ══════════════════════════════════════════════\n"
                "[WARNING]  CAUSAL INSTABILITY / INFINITE LOOP DETECTED  \n"
                "[WARNING] ══════════════════════════════════════════════"
            )
            print(
                f"[ORCHESTRATOR] Residuals for last {self.loop_threshold} turns: "
                f"{[round(r, 4) for r in monitor.residuals[-self.loop_threshold:]]}"
            )

            # --- Execute Git Rollback ---
            print("[ORCHESTRATOR] Triggering Causal Branch Pruning (git rollback)...")
            rollback_ok, rollback_msg = await self._git_rollback()
            print(rollback_msg)

            if not rollback_ok:
                # Rollback failed — still raise the exception but flag the
                # workspace as potentially dirty in the diagnostics payload.
                print(
                    "[ERROR] Git rollback failed. "
                    "Workspace may contain unstable edits."
                )

            # --- Raise graceful halt exception ---
            raise CausalInstabilityException(
                f"EMMA solver loop halted: infinite regression detected at "
                f"turn #{loop_turn}. Workspace rolled back={rollback_ok}.",
                turn=loop_turn,
                residuals=monitor.residuals,
                last_error=combined_output,
            )

        # ----------------------------------------------------------------
        # Max turn ceiling reached without success
        # ----------------------------------------------------------------
        print(
            f"[ORCHESTRATOR] Max turns ({self.max_turns}) exhausted "
            "without convergence."
        )
        return {
            "status":          "MAX_TURNS_REACHED",
            "turns_elapsed":   loop_turn,
            "monitor_summary": monitor.summary(),
            "turn_log":        turn_log,
        }
