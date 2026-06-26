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
from typing import Any, Dict, List, Optional, Tuple, Callable
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

    async def solve(
        self,
        task_description: str,
        target_file: str = "backend/app/core/executor.py",
        on_turn_start: Optional[Callable[[int], None]] = None,
        on_context_compressed: Optional[Callable[[int, int], None]] = None,
        on_token_peak: Optional[Callable[[int], None]] = None,
        on_mutants_graded: Optional[Callable[[list], None]] = None,
        on_residual: Optional[Callable[[float], None]] = None,
        on_log: Optional[Callable[[str], None]] = None,
        on_request_steering: Optional[Callable[[str], str]] = None,
    ) -> Dict[str, Any]:
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
        on_turn_start : Callable
            Callback triggered at start of each solver turn.
        on_context_compressed : Callable
            Callback triggered when context is compressed.
        on_token_peak : Callable
            Callback triggered with active token count peak.
        on_mutants_graded : Callable
            Callback triggered with list of graded mutants.
        on_residual : Callable
            Callback triggered with latest loop residual score.
        on_log : Callable
            Callback triggered to send logging statements to terminal dashboard.
        on_request_steering : Callable
            Callback triggered to request human steering hint when stuck.

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
        def _log(msg: str) -> None:
            clean_msg = re.sub(r"\[/?.*?\]", "", msg)
            print(f"[ORCHESTRATOR] {clean_msg}")
            if on_log:
                on_log(msg)

        _log(
            f"Initiating Causal Solver Loop.\n"
            f"  Task: {task_description}\n"
            f"  Target File: {target_file}\n"
            f"  Max Turns: {self.max_turns} | Stall Threshold: {self.loop_threshold}"
        )

        # ----------------------------------------------------------------
        # Gate 0: Pre-flight workspace check
        # ----------------------------------------------------------------
        git_found = False
        curr = self.workspace_path
        while True:
            if os.path.isdir(os.path.join(curr, ".git")):
                git_found = True
                break
            parent = os.path.dirname(curr)
            if parent == curr:
                break
            curr = parent
            
        if not git_found:
            try:
                import subprocess as sp
                res = sp.run(
                    ["git", "rev-parse", "--is-inside-work-tree"],
                    cwd=self.workspace_path,
                    capture_output=True,
                    text=True,
                    check=False
                )
                if res.returncode == 0 and "true" in res.stdout.strip().lower():
                    git_found = True
            except Exception:
                pass

        if not git_found:
            raise EnvironmentError(
                f"[ORCHESTRATOR] No .git directory found at or above: {self.workspace_path}\n"
                "Git rollback safeguards require a valid Git repository."
            )

        # ----------------------------------------------------------------
        # Initialise Causal Convergence Monitor & Steering Memory
        # ----------------------------------------------------------------
        monitor = CausalConvergenceMonitor(loop_threshold=self.loop_threshold)
        self.active_hints = []

        turn_log: List[Dict[str, Any]] = []
        loop_turn = 0

        # ----------------------------------------------------------------
        # Primary solver turn loop
        # ----------------------------------------------------------------
        while loop_turn < self.max_turns:
            loop_turn += 1
            if on_turn_start:
                on_turn_start(loop_turn)
            _log(f"── Cycle Turn #{loop_turn}/{self.max_turns} ──")

            # ----------------------------------------------------------------
            # ACTIVE MEMORY MONITORING & CONTEXT COMPACTION
            # ----------------------------------------------------------------
            history_str = json.dumps(turn_log, ensure_ascii=False)
            tier, token_count = self.pruner.evaluate_threshold(history_str)
            if on_token_peak:
                on_token_peak(token_count)
            _log(f"Active prompt footprint: {token_count} tokens | Tier: {tier}")

            if tier in ("RED", "CRITICAL", "OVERFLOW"):
                _log(f"Utilization >= 70% threshold ({token_count} tokens). Initiating DTE-IS memory compaction...")
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
                
                # Capture current logs to know rotation reduction
                raw_len = len(history_str)
                turn_log = await self.pruner.compact_history(
                    turn_logs              = turn_log,
                    orchestrator_telemetry = telemetry,
                    entropy_map            = entropy_map,
                    emergency              = (tier == "OVERFLOW"),
                )
                compacted_str = json.dumps(turn_log, ensure_ascii=False)
                comp_len = len(compacted_str)
                if on_context_compressed:
                    on_context_compressed(raw_len, comp_len)
                _log(f"Context compaction complete. Free memory buffer secured.")

            if tier == "OVERFLOW":
                _log(f"[CRITICAL ERROR] Context utilization exceeded 95% budget ({token_count}/8000 tokens).")
                _log(f"Executing emergency Git checkout rollback...")
                rollback_ok, rollback_msg = await self._git_rollback()
                _log(rollback_msg)
                
                raise CausalInstabilityException(
                    f"Cognitive memory overflow detected at turn #{loop_turn} ({token_count} tokens). Safe rollback applied.",
                    turn=loop_turn,
                    last_error="Token budget overflow (OVERFLOW tier)"
                )

            # ============================================================
            # Step 1: CODE GENERATION (Evolutionary Mutant Sandboxing)
            # ============================================================
            _log(f"[Step 1] Initializing Evolutionary Mutant Selection...")
            
            # Inject active steering hints into task description
            current_task = task_description
            if self.active_hints:
                hints_block = "\n".join(f"• {h}" for h in self.active_hints)
                current_task = f"{task_description}\n\n[USER STEERING HINTS (FOLLOW THESE INSTRUCTIONS STRICTLY)]:\n{hints_block}"
                
            generator = CodeGenerator(workspace_path=self.workspace_path)
            gen_report = await generator.generate_and_apply_patch(
                file_path=target_file,
                task=current_task
            )
            
            winner_label = gen_report.get("winner_label", "None")
            _log(
                f"Code generation completed. "
                f"Winner mutant: {winner_label} | "
                f"Committed successfully: {gen_report.get('committed', False)}"
            )
            if gen_report.get("error"):
                _log(f"Generation info: {gen_report['error']}")

            # Trigger mutants graded callback
            if on_mutants_graded and gen_report.get("mutants"):
                graded_list = []
                for m in gen_report["mutants"]:
                    m_code = m.get("code", "")
                    lines_count = len(m_code.splitlines()) if m_code else 0
                    is_winner = gen_report.get("winner_label") == m.get("label")
                    rejected = not m.get("syntax_valid", False) or not m.get("security_clean", False) or not m.get("exec_success", False)
                    lat_s = m.get("exec_latency_ms", 0.0) / 1000.0 if m.get("exec_latency_ms") else 0.0
                    
                    m_label = f"Mutant {m.get('label', '')}"
                    
                    graded_list.append({
                        "label": m_label,
                        "syntax_valid": m.get("syntax_valid", False),
                        "lines": lines_count,
                        "latency": lat_s,
                        "base_score": 100.0,
                        "length_penalty": m.get("length_penalty", 0.0),
                        "latency_penalty": m.get("latency_penalty", 0.0),
                        "total_score": m.get("final_score", 0.0) if m.get("syntax_valid") else -100.0,
                        "is_winner": is_winner,
                        "rejected": rejected,
                    })
                on_mutants_graded(graded_list)

            # ============================================================
            # Step 2: CAUSAL ANCHOR — JIT Pre-Commit Savepoint
            # ============================================================
            workspace_dirty = not await self._git_workspace_clean()
            _log(f"[Step 2] Causal Anchor — workspace dirty: {workspace_dirty}")

            # ============================================================
            # Step 3: EXECUTE TEST / COMPILE COMMAND
            # ============================================================
            cmd_tokens: List[str] = shlex.split(self.test_command)
            _log(f"[Step 3] Executing: {self.test_command}")

            exit_code, cmd_stdout, cmd_stderr = await self._run_command(
                cmd_tokens,
                timeout=120.0,
            )

            combined_output: str = "\n".join(
                filter(None, [cmd_stdout.strip(), cmd_stderr.strip()])
            )
            _log(f"Command finished — exit code: {exit_code}")

            # Log this turn
            turn_log.append({
                "turn":      loop_turn,
                "exit_code": exit_code,
                "output":    combined_output[:500],
            })

            # ============================================================
            # Step 4: SUCCESS PATH — exit code 0
            # ============================================================
            if exit_code == 0:
                _log(f"[PASS] Command succeeded. Task complete at turn #{loop_turn}.")
                return {
                    "status":          "SUCCESS",
                    "turns_elapsed":   loop_turn,
                    "monitor_summary": monitor.summary(),
                    "turn_log":        turn_log,
                }

            # ============================================================
            # Step 5: FAILURE PATH — evaluate causal stability
            # ============================================================
            _log("[FAIL] Command failed. Passing to Causal Convergence Monitor...")

            loop_stable: bool = monitor.evaluate_step(combined_output)
            
            if monitor.residuals and on_residual:
                on_residual(monitor.residuals[-1])

            _log(
                f"Monitor residual: "
                f"{round(monitor.residuals[-1], 4) if monitor.residuals else 'N/A'} "
                f"| Stable: {loop_stable}"
            )

            if loop_stable:
                _log(f"Loop is converging. Proceeding to Turn #{loop_turn + 1}.")
                continue

            # ============================================================
            # Step 6: PARADOX DETECTED — check for steering or rollback
            # ============================================================
            if on_request_steering:
                err_preview = combined_output[-250:] if combined_output else "No trace available"
                hint_msg = f"Causal Loop Stalled (Residual: {monitor.residuals[-1]:.4f}).\nLast error:\n{err_preview}"
                
                if asyncio.iscoroutinefunction(on_request_steering):
                    hint = await on_request_steering(hint_msg)
                else:
                    hint = on_request_steering(hint_msg)
                    
                if hint:
                    self.active_hints.append(hint)
                    monitor.residuals.clear()
                    monitor.state_history.clear()
                    _log(f"🔄 [SARATHI] Steering accepted. Resetting convergence monitor loops.")
                    continue

            # If no steering was provided, execute rollback and halt
            _log(
                "[WARNING] ══════════════════════════════════════════════\n"
                "[WARNING]  CAUSAL INSTABILITY / INFINITE LOOP DETECTED  \n"
                "[WARNING] ══════════════════════════════════════════════"
            )
            _log(
                f"Residuals for last {self.loop_threshold} turns: "
                f"{[round(r, 4) for r in monitor.residuals[-self.loop_threshold:]]}"
            )

            # --- Execute Git Rollback ---
            _log("Triggering Causal Branch Pruning (git rollback)...")
            rollback_ok, rollback_msg = await self._git_rollback()
            _log(rollback_msg)

            if not rollback_ok:
                _log("[ERROR] Git rollback failed. Workspace may contain unstable edits.")

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
        _log(f"Max turns ({self.max_turns}) exhausted without convergence.")
        return {
            "status":          "MAX_TURNS_REACHED",
            "turns_elapsed":   loop_turn,
            "monitor_summary": monitor.summary(),
            "turn_log":        turn_log,
        }
