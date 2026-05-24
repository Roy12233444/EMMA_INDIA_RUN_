# Technical Implementation Plan: EMMA Modular Cognitive Core (Hybrid Design)
## JIT Context Rotation, Novikov Safeguards, AST Mutation, & Page Curve Evaporation

This document defines the highly structured, 5-file modular architecture for upgrading EMMA's local execution engine. To maintain maximum elegance, all math-heavy parsing, scoring, and compaction classes are packed into a single utilities file (`context_scheduler.py`), while execution loops, sandboxes, and databases remain isolated in their respective layers.

---

## 🏛️ 1. Modular Architecture Map

The cognitive components are cleanly distributed across five dedicated files:

```
backend/app/
├── core/
│   ├── orchestrator.py            <-- [MODIFY] Integrates solver loop with CausalConvergenceMonitor checks
│   ├── context_scheduler.py       <-- [NEW] Consolidates ASTContextRotator, MutantCodeSelector, & PageCurveEvaporator
│   └── code_generator.py          <-- [NEW] Executes LLM runs and invokes MutantCodeSelector from context_scheduler
└── utils/
    ├── ast_parser.py              <-- [NEW] Provides structural syntax checking helper routines
    └── session_manager.py         <-- [MODIFY] Wraps database IO with automated log evaporation
```

---

## 🛰️ 2. Detailed Technical Specifications

### File 1 [NEW]: `backend/app/core/context_scheduler.py`
*Houses all core math, token-compression, and candidate-evaluation classes.*

*   **`ASTContextRotator` Class:**
    *   Compiles Abstract Syntax Tree coordinates of working python files using native `ast.parse`.
    *   Hides sibling method bodies, displaying only their method signatures to keep the prompt under **1,500 tokens**.
    *   Injects the active node segment wrapped in `<TRANSIENT_CONTEXT id="..." type="ast_node">` tags.
*   **`MutantCodeSelector` Class:**
    *   Grading sandbox that runs AST checks in-memory on candidate code variations.
    *   Grades candidate fitness: awards $+50$ points for clean compilation, penalizes code length, and penalizes $-30$ points if return values are missing. The best candidate is selected.
*   **`PageCurveEvaporator` Class:**
    *   Monitors terminal execution log standard output sizes.
    *   If logs exceed 20 lines, automatically parses out exit codes, error lines, and warning counts, replacing raw data with a 1-line metadata summary string.

---

### File 2 [MODIFY]: `backend/app/core/orchestrator.py`
*Houses the core cognitive solver loop and handles loop safety checks.*

*   **`CausalConvergenceMonitor` Class:**
    *   Tracks diagnostic and execution logs over solver turns.
    *   Computes convergence residuals based on Levenshtein distances between consecutive compile logs.
    *   Enforce a zero-trust break if the error residual fails to decay over 3 consecutive execution loops.
    *   Execute automated `git rollback` commands (`git checkout -- .`) to safely restore stable session code.

---

### File 3 [NEW]: `backend/app/core/code_generator.py`
*Manages candidate patch generations and invokes grading.*

*   **`MutantCodeSelector` Integration:**
    *   Generates 3 parallel mutant patch suggestions in-memory from LLM thoughts.
    *   Imports and queries `MutantCodeSelector` from `context_scheduler.py` to select the highest-fitness mutant before writing to the filesystem.

---

### File 4 [NEW]: `backend/app/utils/ast_parser.py`
*Provides decoupled Abstract Syntax Tree checking scripts.*

*   **Helper Functions:**
    *   `def parse_syntax(code: str) -> bool`: Safe in-memory code compilation syntax check.
    *   `def extract_signatures(code: str) -> list[str]`: Utility for finding method signatures.

---

### File 5 [MODIFY]: `backend/app/utils/session_manager.py`
*Manages database storage and state serialization.*

*   **Database Wrapper:**
    *   Automatically runs `PageCurveEvaporator` on active log entries right before writing session states to `sessions.json`, ensuring the database remains ultra-light.

---

## 📅 3. Actionable Step-by-Step Task List

### **Phase 1: Advanced Core Utilities**
*   **Target File:** `backend/app/core/context_scheduler.py`
*   **Tasks:** Build `ASTContextRotator`, `MutantCodeSelector`, and `PageCurveEvaporator` together in this single utility file.

### **Phase 2: Loop Safety Monitor**
*   **Target File:** `backend/app/core/orchestrator.py`
*   **Tasks:** Implement `CausalConvergenceMonitor` and integrate its delta checks inside the solver loop.

### **Phase 3: Sandbox Selector & Helper**
*   **Target Files:** `backend/app/core/code_generator.py` & `backend/app/utils/ast_parser.py`
*   **Tasks:** Scaffold LLM generator calls in `code_generator.py` and call `MutantCodeSelector` from `context_scheduler.py` for sandbox evaluations.

### **Phase 4: Persistence Link**
*   **Target File:** `backend/app/utils/session_manager.py`
*   **Tasks:** Wrap session load/save methods with automated evaporation before writing to `sessions.json`.

---

## 🛡️ 4. Verification & Testing

### Automated Unit Tests (`backend/app/tests/test_advanced_core.py`)
1. **Rotator Check:** Assert that `ASTContextRotator` stubs inactive sibling methods in mock files.
2. **Selector Check:** Assert that `MutantCodeSelector` correctly detects and discards invalid python syntax in memory.
3. **Evaporator Check:** Assert that `PageCurveEvaporator` successfully reduces a 50-line stdout print to a 1-line metadata summary.
4. **Monitor Check:** Assert that `CausalConvergenceMonitor` returns `False` (break condition) when progress stalls over 3 cycles.
