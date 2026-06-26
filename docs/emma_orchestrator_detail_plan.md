# Advanced Implementation Plan: `orchestrator.py` Modification Spec
## Deep Causal Convergence Monitoring, Loop Stability Audits, & Git Rollback Safeguards

This document defines the highly detailed, production-grade technical specification and code blueprint for modifying **`backend/app/core/orchestrator.py`**. 

This component acts as EMMA's central executive loop. It integrates the **Causal Convergence Monitor** and **Novikov Loop Safeguard** directly inside the core solver pipeline, establishing a $100\%$ resilient, zero-trust boundary that prevents infinite diagnostic error regressions and guarantees file system stability.

---

## 🏛️ 1. File Metadata & Component Map

*   **Target File Path:** `backend/app/core/orchestrator.py`
*   **Target Classes/Methods to Add:**
    1.  `CausalConvergenceMonitor` (Class: Calculates Levenshtein-based error residuals).
    2.  `CausalInstabilityException` (Class: Custom loop breakout exception).
*   **Target Loops to Modify:**
    *   `Orchestrator.solve(...)` or the primary solver execution turn loop (injecting JIT pre-save states, evaluation gates, and shell rollback commands).
*   **Required Imports:** `difflib`, `subprocess`, `asyncio`, `typing`

---

## 🛰️ 2. Comprehensive Class & Integration Specifications

### Class A: `CausalConvergenceMonitor`
*   **Algorithmic Concept: Levenshtein Convergence & Paradox Gap Estimation**
    *   *Mathematical Intuition:* Treat the debugging execution loop as a fixed-point convergence sequence. Let the error stdout trace at turn $k$ be $E_k$. We define the **Causal Residual** $R_k$ as the structural similarity ratio between consecutive errors:
        
        $$R_k = \text{SequenceMatcher}(E_k, E_{k-1})$$
        
    *   *Mechanism:*
        *   **Similarity Tracking:** Compares $E_k$ with $E_{k-1}$ using `difflib.SequenceMatcher`. A ratio near $1.0$ implies no progress (identical error loops), while a decaying ratio implies active debugging progress.
        *   **Stability Threshold:** If the residual remains $\ge 0.95$ for $3$ consecutive turns (`loop_threshold`), the monitor flags a "Causal Paradox" (infinite loop).

#### **Core Methods:**
1.  `__init__(self, loop_threshold: int = 3)`:
    *   Initializes the limit threshold (default to 3 steps).
    *   Sets up lists for error state hashes and calculated residuals.
2.  `calculate_residual(self, error_output: str) -> float`:
    *   Cleans and strips white-spaces from the current error output.
    *   Calculates the structural ratio similarity against the last stored error state.
3.  `evaluate_step(self, error_output: str) -> bool`:
    *   Appends the error and calculated residual to the history trackers.
    *   Returns `False` (trigger break) if the last 3 consecutive residuals are $\ge 0.95$, indicating a stalled convergence loop. Otherwise, returns `True` (stable).

---

### Class B: `CausalInstabilityException`
*   **Purpose:** Custom exception thrown by the orchestrator loop when the convergence monitor triggers a break. It halts execution gracefully, prevents token drain, and returns detailed debug logs to the UI.

---

### Solver Loop Integration (`Orchestrator.solve`)
*   **Goal:** Protect the file system and ensure that the agent loops are evaluated for stability at every turn.
*   **Core Logic Steps:**
    1.  **The Causal Anchor (Pre-Commit Savepoint):**
        *   Right before EMMA writes an LLM-suggested patch to the codebase, the orchestrator registers a git savepoint.
    2.  **The Command Gate:**
        *   EMMA runs the compiler or test command (e.g. `pytest` or `npm run build`).
        *   The orchestrator captures standard output and standard error.
    3.  **The Safety Gate Evaluation:**
        *   If the command fails (exit code > 0), the orchestrator extracts the error traceback.
        *   It runs `monitor.evaluate_step(error_log)`.
        *   If the monitor returns `True`, execution continues to the next cycle.
        *   If the monitor returns `False` (Paradox Detected), the orchestrator triggers:
            *   **The Rollback Command:** Calls a subprocess command:
                ```powershell
                git checkout -- .
                ```
                *(This instantly wipes all unstable edits, restoring the project back to the last clean state).*
            *   **Graceful Termination:** Raises `CausalInstabilityException` to break the solver thread and report the logs to the console dashboard.

---

## 💻 3. Production Code Blueprint Skeleton

This is the exact skeleton of `orchestrator.py` modifications that Claude Code will implement:

```python
import subprocess
import difflib
from typing import List, Optional, Dict, Any

class CausalInstabilityException(Exception):
    """Exception thrown when the solver loop enters an infinite error regression."""
    pass


class CausalConvergenceMonitor:
    """
    Tracks execution error logs and calculates convergence residuals.
    Returns False if debugging progress has stalled over consecutive cycles.
    """
    def __init__(self, loop_threshold: int = 3) -> None:
        self.threshold: int = loop_threshold
        self.state_history: List[str] = []
        self.residuals: List[float] = []

    def calculate_residual(self, error_output: str) -> float:
        """Calculates SequenceMatcher similarity ratio against the last error state."""
        if not self.state_history:
            return 1.0
        
        prev_error = self.state_history[-1]
        # Clean white spaces to focus only on structural text deltas
        clean_prev = " ".join(prev_error.split())
        clean_curr = " ".join(error_output.split())
        
        ratio = difflib.SequenceMatcher(None, clean_prev, clean_curr).ratio()
        return ratio

    def evaluate_step(self, error_output: str) -> bool:
        """Returns False if loop progress is stalled, indicating a causal loop."""
        if not error_output.strip():
            return True  # No error output = converging/clean

        residual = self.calculate_residual(error_output)
        self.residuals.append(residual)
        self.state_history.append(error_output)

        if len(self.residuals) >= self.threshold:
            recent_residuals = self.residuals[-self.threshold:]
            # If all recent turns show sequence similarity ratio >= 0.95
            if all(r >= 0.95 for r in recent_residuals):
                return False
        return True


# =============================================================================
# Solver Loop Integration Spec (Orchestrator Class)
# =============================================================================

class Orchestrator:
    # Existing initialization code...
    
    async def solve(self, task_description: str) -> Dict[str, Any]:
        """
        Executes EMMA's primary metacognitive solver loop.
        Integrates JIT error stability checks and automated Git rollbacks.
        """
        print(f"[ORCHESTRATOR] Initiating Causal Solver Loop for task: {task_description}")
        
        # 1. Initialize our convergence monitor
        monitor = CausalConvergenceMonitor(loop_threshold=3)
        loop_turn = 0
        max_turns = 15

        while loop_turn < max_turns:
            loop_turn += 1
            print(f"[ORCHESTRATOR] Starting Cycle Turn #{loop_turn}")
            
            # --- CODE GEN & JIT PRE-COMMIT ---
            # Right before writing LLM suggestions, verify workspace status
            
            # --- EXECUTE TEST / COMPILE COMMAND ---
            # Run test using subprocess (e.g. pytest app/tests/)
            command_output = "mock error stack trace"  # Replace with actual captured stdout/stderr
            command_exit_code = 1  # Replace with actual process exit code
            
            if command_exit_code > 0:
                print("[ORCHESTRATOR] Execution failed. Passing to Causal Monitor...")
                
                # Evaluate step stability
                if not monitor.evaluate_step(command_output):
                    print("[WARNING] Causal Instability / Infinite loop detected!")
                    
                    # --- EXECUTE GIT ROLLBACK ---
                    print("[ORCHESTRATOR] Triggering Causal Branch Pruning (Rollback)...")
                    try:
                        subprocess.run(
                            ["git", "checkout", "--", "."],
                            check=True,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE
                        )
                        print("[ORCHESTRATOR] [OK] Workspace successfully restored to last stable state.")
                    except subprocess.SubprocessError as e:
                        print(f"[ERROR] Rollback failed: {e}")
                    
                    # Raise break exception to halt the loop gracefully
                    raise CausalInstabilityException(
                        f"EMMA solver loop halted: infinite regression detected at turn #{loop_turn}."
                    )
            
            # Proceed to next turn...
            
        return {"status": "SUCCESS"}
```

---

## 🛡️ 4. Verification Checkpoints

*   **Checkpoint 1:** Confirm `CausalConvergenceMonitor` is imported or declared cleanly at the top of the file with no parsing errors.
*   **Checkpoint 2:** Simulate a compilation failure where a mock subprocess returns the same `SyntaxError` string three times in a row. Verify that the loop terminates, the checkout command is triggered, and `CausalInstabilityException` is correctly raised.
*   **Checkpoint 3:** Confirm that when a test command succeeds (exit code = 0), the monitor is bypassed, and the loop proceeds cleanly to completion.
