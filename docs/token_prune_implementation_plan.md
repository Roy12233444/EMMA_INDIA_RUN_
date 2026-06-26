# Technical Implementation Plan: EMM-02-A5 — Context Compaction & Token Pruner (`token_prune.py`)

## Executive Summary
This document provides the technical blueprint for **`EMM-02-A5`**, detailing the design, implementation, and integration of the core token manager (`backend/app/utils/token_prune.py`) for EMMA's solver pipeline. The module acts as an active cognitive memory compressor that:
1. **Counts tokens locally** with byte-level accuracy using `tiktoken` (utilizing a standard library mathematical approximation as a zero-dependency fallback).
2. **Evaluates active prompt usage** against a strict **70% context capacity threshold**.
3. **Prunes and condenses logs** dynamically when triggered, translating heavy conversational files/logs into dense, structured **Execution State Vectors (ESVs)**.

---

## 1. Module Structure and Class Design
We will implement the `ContextVectorPruner` class inside `backend/app/utils/token_prune.py`.

```python
class ContextVectorPruner:
    """
    Cognitive memory pruner for EMMA.
    Counts tokens accurately and condenses conversational logs at 70% threshold.
    """
    def __init__(self, max_tokens: int = 8000, encoding_name: str = "cl100k_base"):
        self.max_tokens = max_tokens
        self.threshold = int(0.70 * max_tokens)
        self.encoding_name = encoding_name
```

### Key Methods:
- `count_tokens(self, text: str) -> int`: Measures token count. If `tiktoken` is importable, calls `tiktoken.get_encoding(self.encoding_name).encode()`. If `tiktoken` is unavailable, counts length of characters and divides by standard multiplier (approx. 4.0 chars/token).
- `evaluate_threshold(self, text: str) -> bool`: Returns `True` if `count_tokens(text) >= self.threshold` (70% of `max_tokens`), signaling that compaction must be run immediately.
- `compact_history(self, turn_logs: list[dict[str, Any]]) -> list[dict[str, Any]]`: Compresses heavy turn logs into lightweight, high-density ESVs.
- `_extract_error_signature(self, output: str) -> str`: A heuristic parser that inspects stderr/stdout to isolate key tracebacks, exception types (e.g., `AssertionError`, `TypeError`, `SyntaxError`), and failing files/lines.

---

## 2. Advanced Algorithmic Heuristics for ESVs
To compress raw logs from thousands of tokens down to under 100, `token_prune.py` will use targeted heuristic parsing:
- **Python Stderr Traceback Scraper:** Searches for `Traceback (most recent call last):` up to the final exception line, capturing only the target file, line number, failing expression, and the exception message.
- **Pytest Failure Condenser:** Detects standard `pytest` failure hunks (lines starting with `> ` or `E `) and extracts the failing assertion expression and diff details, discarding verbose surrounding environment telemetry.
- **Log Stream Stripper:** Removes timestamp headers, debug trace lines, and standard boilerplate terminal warnings.

---

## 3. Integration Points inside `orchestrator.py`
In `orchestrator.py`, inside the `solve()` loop, we will hook `ContextVectorPruner` as follows:

```python
# During solver turn initialization:
from app.utils.token_prune import ContextVectorPruner

pruner = ContextVectorPruner(max_tokens=8000)

# Inside the turn loop, prior to code generation:
current_history_str = ... # (serialize the current list of turns/messages)
if pruner.evaluate_threshold(current_history_str):
    print("[ORCHESTRATOR] Context 70% threshold reached. Compacting logs...")
    turn_log = pruner.compact_history(turn_log)
```

---

## 4. Verification and Automated Testing Plan
We will add a suite of test cases to `backend/app/tests/test_advanced_core.py` (or a dedicated `test_token_prune.py`):
1. **Token Counting Accuracy:** Compare fallback mathematical estimations to exact `tiktoken` outcomes to ensure the ratio holds within an acceptable margin of error.
2. **Threshold Evaluation:** Feed short and long prompts to verify the 70% flag triggers precisely when expected.
3. **Log Compaction Fidelity:** Pass a simulated heavy `pytest` error output into `compact_history()` and assert that the output contains the specific filename, line number, and error type while dropping >90% of the token payload size.
