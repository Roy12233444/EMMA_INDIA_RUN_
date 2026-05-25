# Implementation Plan: EMMA Code Generator Module (`code_generator.py`)
## Evolutionary Mutant Sandboxing and Safe Commit Engine

This document outlines the detailed architectural design and implementation plan for the new `code_generator.py` module. This module serves as the **gatekeeper** of the EMMA filesystem, ensuring that no syntactically invalid or sub-optimal AI-generated code is ever written to disk.

---

## 🎯 Objective
Create a robust, sandboxed code-generation interface that receives edit requests, generates/simulates multiple candidate patches (mutants), evaluates them in an isolated in-memory AST compiler, selects the optimal candidate based on fitness and parsimony, and commits it safely.

---

## 🏗️ Detailed Architecture

### 1. File Location
* **Path:** `backend/app/core/code_generator.py`

### 2. Core Dependencies
* `app.core.context_scheduler.MutantCodeSelector`: Used to score, validate, and select the best mutant.
* `ast`: Standard library module for checking syntax correctness.
* `os` / `shutil`: File operations.

### 3. Class Design: `CodeGenerator`
The class will expose the following interface:

```python
class CodeGenerator:
    """
    Manages the generation, sandboxing, evaluation, and committing
    of code patches (mutants) within the EMMA Cognitive Core.
    """
    def __init__(self, workspace_path: str):
        self.workspace_path = workspace_path
        # Import the mutant selector from the core scheduler
        self.selector = MutantCodeSelector()

    async def generate_mutants(self, file_path: str, task: str) -> list[str]:
        """
        Simulates or calls the LLM to generate 3 alternative implementations
        (mutants) for the given task.
        """
        pass

    async def generate_and_apply_patch(self, file_path: str, task: str) -> dict:
        """
        Coordinates the complete lifecycle:
          1. Generates 3 mutant patches.
          2. Passes mutants to the MutantCodeSelector.
          3. Evaluates and scores mutants in-memory (AST syntax + parsimony).
          4. Automatically identifies the winner.
          5. Commits only the winning, verified mutant to 'file_path'.
        """
        pass
```

---

## 🔄 The In-Memory Sandboxing Flow

When a code-generation task is initiated, the code flows through the following pipeline:

```
[User Task] ──► [LLM/Simulator] ──► Generates 3 Mutants (A, B, C) in-memory
                                             │
                                             ▼
                               ┌───────────────────────────┐
                               │     MutantCodeSelector    │
                               │  In-Memory AST Validation │
                               └─────────────┬─────────────┘
                                             │
                                             ├─► Mutant B (Syntax Error) ──► REJECTED (Score -100)
                                             ├─► Mutant C (Bloated)      ──► PENALIZED (Score 45)
                                             └─► Mutant A (Clean, Valid) ──► WINNER    (Score 95)
                                             │
                                             ▼
                                 [Safe Filesystem Commit]
                                 Only Mutant A is written to disk!
```

---

## 📝 Implementation Checklist

- [ ] **Step 1: Create the Module**
  * Create `backend/app/core/code_generator.py` with proper imports (`ast`, `os`, and `MutantCodeSelector`).
- [ ] **Step 2: Implement Mutant Generation & Simulation**
  * Write the `generate_mutants` method to simulate/produce three variations of code.
- [ ] **Step 3: Implement Sandboxing and Evaluation**
  * Write `generate_and_apply_patch` to integrate with `MutantCodeSelector` and perform the scoring and selection.
- [ ] **Step 4: Implement Safe Disk Commits**
  * Add the filesystem writing logic to overwrite the target file *only* when a valid, high-scoring mutant is selected.
- [ ] **Step 5: Orchestrator Integration**
  * Update `orchestrator-v2.py` to replace the "Step 1: Code Generation" placeholder with a live call to `CodeGenerator`.

---

## 🧪 Verification Plan

### 1. Unit Testing
We will verify this module with the following test cases in `backend/app/tests/test_advanced_core.py`:
* **Syntax Guard Test:** Verify that if the generator produces a mutant with a syntax error (e.g., missing colon), the generator rejects it and the file remains unchanged.
* **Parsimony Selection Test:** Verify that given two syntactically correct mutants, the shorter, cleaner, and more efficient mutant is selected.
* **Successful Commit Test:** Verify that a valid, winning mutant is successfully written to the target file.
