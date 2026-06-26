# Implementation Plan: EMM-05-A3 — Adaptive Sandbox Limits
## Dynamic Resource Scaling, Self-Healing Retry Engine & AST Complexity Pre-Analysis
### Production-Grade Engineering Specification v1.0

> **Ticket:** EMM-05-A3 · **Priority:** P1 · **Sprint:** 06
> **Predecessor:** EMM-05-A2 (Jailed Python Sandbox Subprocess — ✅ Complete)
> **Author:** Nexus AI Research Lab — SUDARSHANA Safety Division
> **Date:** June 2026

---

## Table of Contents

1. [Goal Description](#1-goal-description)
2. [Architectural Layering — Why This Belongs in the Scheduler, Not the Sandbox](#2-architectural-layering)
3. [Concept 1 — Dynamic Limits (Configurable)](#3-concept-1--dynamic-limits-configurable)
4. [Concept 2 — Adaptive Limits (Self-Healing Retry Engine)](#4-concept-2--adaptive-limits-self-healing-retry-engine)
5. [Concept 3 — AST Complexity Pre-Analysis](#5-concept-3--ast-complexity-pre-analysis)
6. [Unified Execution Pipeline — How All Three Work Together](#6-unified-execution-pipeline)
7. [Target File Mapping](#7-target-file-mapping)
8. [Data Structures & Type Definitions](#8-data-structures--type-definitions)
9. [Full Code Skeletons](#9-full-code-skeletons)
10. [Calibration Reference Table](#10-calibration-reference-table)
11. [Verification Plan](#11-verification-plan)

---

## 1. Goal Description

### Problem Statement

The `EMM-05-A2` sandbox (`sandbox.py`) correctly enforces **hard limits**:
- **30-second timeout** — subprocess killed by OS
- **50,000 gas instructions** — infinite loop caught by AST Gas Meter
- **256 MB RAM ceiling** — process killed by Windows Job Object / Unix RLIMIT_AS

However, these limits are **static and universal**. They work well for small helper functions, but they create a critical problem for the EMMA solver:

> **An AI-generated code mutant that solves a complex mathematical optimization problem (e.g., matrix diagonalization, eigenvalue computation, recursive dynamic programming) may be 100% correct, 100% safe — but legitimately require 90 seconds and 3,000,000 gas instructions.**

Under the `v2.0` sandbox, this correct solution would be **incorrectly rejected** with a `TIMEOUT` or `GAS_LIMIT_EXCEEDED` status — causing the solver to discard a potentially optimal mutant.

### Solution

Introduce three complementary mechanisms **in the Scheduler Layer** (above the sandbox):

| Mechanism | Layer | Purpose |
|---|---|---|
| **Dynamic Limits** | `run_in_sandbox()` call-site | Caller specifies task-appropriate limits per invocation |
| **AST Complexity Pre-Analysis** | `ComplexityAnalyzer` (new class) | Automatically scale limits *before* execution based on code structure |
| **Self-Healing Retry Engine** | `AdaptiveSandboxRunner` (new class) | Automatically retry with relaxed limits on `TIMEOUT` / `GAS_LIMIT_EXCEEDED` |

```
                    ┌─────────────────────────────────────┐
                    │         code_generator.py            │
                    │   (Evolutionary Mutation Scheduler)   │
                    └──────────────┬──────────────────────┘
                                   │ code_str
                                   ▼
                    ┌─────────────────────────────────────┐
                    │    ComplexityAnalyzer (NEW)          │
                    │  • AST node counting                 │
                    │  • Nesting depth detection           │
                    │  • Math signature pattern matching   │
                    │  → Returns: SandboxLimits (scaled)  │
                    └──────────────┬──────────────────────┘
                                   │ SandboxLimits
                                   ▼
                    ┌─────────────────────────────────────┐
                    │  AdaptiveSandboxRunner (NEW)         │
                    │  • Attempt 1: run with scaled limits │
                    │  • On TIMEOUT/GAS: scale × RETRY_MUL│
                    │  • Attempt 2: retry with 2× limits   │
                    │  • Final: return result or REJECTED  │
                    └──────────────┬──────────────────────┘
                                   │ SandboxResult
                                   ▼
                    ┌─────────────────────────────────────┐
                    │   sandbox.run_in_sandbox() (EMM-A2) │
                    │   (Passive subprocess executor)      │
                    └─────────────────────────────────────┘
```

---

## 2. Architectural Layering

### Why This Logic Lives in the Scheduler — NOT in `sandbox.py`

This is a critical design decision. The three adaptive mechanisms must NOT be placed inside `sandbox.py`. The reasons are:

#### 2.1 Single Responsibility Principle

```
sandbox.py     → "Execute code. Enforce limits. Report result. Done."
                  (Passive, stateless, does not make decisions)

scheduler.py   → "Analyze code. Choose limits. Run. Retry if needed."
                  (Active, stateful, makes orchestration decisions)
```

The sandbox is a **pure execution primitive** — it is the equivalent of a kernel system call. It should not contain business logic about *when* to retry or *how* to scale.

#### 2.2 Testability

| Concern | If in `sandbox.py` | If in `scheduler.py` |
|---|---|---|
| Test `TIMEOUT` behavior | ❌ Self-heals itself — test cannot assert cutoff | ✅ Sandbox always cuts off, scheduler retries |
| Test retry logic | ❌ Impossible to inject mock results | ✅ Mock `run_in_sandbox()` → test retry decisions |
| Test complexity analysis | ❌ Coupled to subprocess lifecycle | ✅ Pure function — test with code strings only |

#### 2.3 Reusability

The `ComplexityAnalyzer` and `AdaptiveSandboxRunner` can be independently used by:
- `code_generator.py` — for mutant evaluation
- `run_real_solver.py` — for full solver runs
- Future REST API endpoints — for arbitrary user-submitted code evaluation

---

## 3. Concept 1 — Dynamic Limits (Configurable)

### 3.1 Core Idea

Replace all hardcoded limit constants with a **`SandboxLimits` dataclass** that is constructed at the call-site and passed through the entire execution pipeline.

```python
@dataclasses.dataclass
class SandboxLimits:
    timeout_s:    float = 30.0       # Wall-clock timeout for subprocess (seconds)
    memory_mb:    int   = 256        # RAM ceiling (MB) enforced by OS/Job Object
    gas_limit:    int   = 50_000     # Max AST instruction count (Gas Meter)
    max_retries:  int   = 1          # Self-healing retry attempts (0 = disabled)
    retry_scale:  float = 2.0        # Multiplier applied on each retry
```

### 3.2 Task-Tier Limit Presets

Rather than requiring every caller to manually specify limits, we define named **task-tier presets** that map to known computation profiles:

```python
class LimitPreset:
    """
    Named presets for common EMMA solver task profiles.
    Callers select a preset; the ComplexityAnalyzer may override upward.
    """

    # Tiny utility functions: formatters, validators, type converters
    MICRO = SandboxLimits(timeout_s=5.0,   memory_mb=64,  gas_limit=10_000,  max_retries=0)

    # Standard function mutation (default for most solver turns)
    STANDARD = SandboxLimits(timeout_s=30.0,  memory_mb=256, gas_limit=50_000,  max_retries=1)

    # Medium complexity: sorting algorithms, tree traversals, graph search
    MEDIUM = SandboxLimits(timeout_s=60.0,  memory_mb=512, gas_limit=500_000, max_retries=1)

    # Heavy mathematical tasks: matrix operations, numerical solvers, FFT
    HEAVY = SandboxLimits(timeout_s=120.0, memory_mb=1024, gas_limit=5_000_000, max_retries=2)

    # Research-grade: eigenvalues, large-scale optimization, symbolic math
    RESEARCH = SandboxLimits(timeout_s=300.0, memory_mb=2048, gas_limit=50_000_000, max_retries=3)
```

### 3.3 Usage at Call Sites

```python
# In code_generator.py — standard evolutionary mutation:
result = adaptive_runner.run(code=mutant_code, preset=LimitPreset.STANDARD)

# In run_real_solver.py — known heavy math task:
result = adaptive_runner.run(code=solver_code, preset=LimitPreset.HEAVY)

# Explicit override (ComplexityAnalyzer result):
limits = SandboxLimits(timeout_s=90.0, gas_limit=2_000_000, memory_mb=512)
result = adaptive_runner.run(code=code, limits=limits)
```

---

## 4. Concept 2 — Adaptive Limits (Self-Healing Retry Engine)

### 4.1 Core Concept

The `AdaptiveSandboxRunner` wraps `run_in_sandbox()` with a **retry loop**. If a code candidate fails *only* because of resource exhaustion (not because of a logical error or security violation), it receives a **second chance** with scaled-up limits.

```
Attempt 1 (initial limits)
    │
    ├── SUCCESS            → Return result immediately ✅
    ├── SYNTAX_ERROR       → Reject immediately ❌ (retry won't fix syntax)
    ├── RUNTIME_ERROR      → Reject immediately ❌ (retry won't fix logic error)
    ├── PROCESS_CRASH      → Reject immediately ❌ (retry won't fix segfault)
    │
    ├── TIMEOUT            → Scale limits × retry_scale → Attempt 2 ↩️
    └── GAS_LIMIT_EXCEEDED → Scale limits × retry_scale → Attempt 2 ↩️
                                        │
                                Attempt 2 (scaled limits)
                                        │
                                        ├── SUCCESS         → Return result ✅
                                        ├── TIMEOUT again   → FINAL REJECTION ❌
                                        └── GAS again       → FINAL REJECTION ❌
```

### 4.2 Retry Eligibility Gate

Only two failure modes trigger a retry. This is the **Eligibility Gate** — a strict filter preventing the system from wasting compute on fundamentally broken code:

```python
RETRY_ELIGIBLE_STATUSES = frozenset({
    "TIMEOUT",           # Code was safe but ran out of wall-clock time
    "GAS_LIMIT_EXCEEDED" # Code was safe but exceeded AST instruction budget
})

# These NEVER retry — the code is broken, not just slow:
HARD_REJECT_STATUSES = frozenset({
    "SYNTAX_ERROR",      # Fix the syntax first
    "RUNTIME_ERROR",     # Logic bug — retry won't help
    "PROCESS_CRASH",     # Segfault/memory corruption — dangerous
    "OOM_KILLED",        # Already got more memory — not a limit tuning issue
    "UNKNOWN_ERROR",     # Unknown — conservative rejection
})
```

### 4.3 Adaptive Scaling Formula

On each retry attempt `n`:

```
new_timeout_s  = original_timeout_s  × (retry_scale ^ n)
new_gas_limit  = original_gas_limit  × (retry_scale ^ n)
new_memory_mb  = original_memory_mb  (memory is NOT scaled — OOM = logic bug)
```

**Examples with `retry_scale=2.0`:**

| Attempt | Timeout | Gas Limit | Memory |
|---|---|---|---|
| 1 (initial) | 30s | 50,000 | 256 MB |
| 2 (1st retry) | 60s | 100,000 | 256 MB |
| 3 (2nd retry) | 120s | 200,000 | 256 MB |

> **Note:** Memory is never auto-scaled. If code requires more than 256 MB, the caller must explicitly set a higher limit. An OOM kill suggests the code is allocating irresponsibly, not that the limit is wrong.

### 4.4 Safety Ceiling — Hard Max Limits

To prevent the retry engine from granting unlimited resources, we enforce **hard ceilings** that can never be exceeded regardless of retry count or preset:

```python
HARD_CEILING = SandboxLimits(
    timeout_s  = 600.0,        # Never more than 10 minutes total
    memory_mb  = 4096,         # Never more than 4 GB RAM
    gas_limit  = 100_000_000,  # Never more than 100M gas instructions
)
```

---

## 5. Concept 3 — AST Complexity Pre-Analysis

### 5.1 Core Concept

Before spawning a subprocess, the `ComplexityAnalyzer` performs a **static analysis pass** on the generated code's AST. It computes a **Complexity Score** and uses a lookup table to derive an appropriately scaled `SandboxLimits` object.

This prevents the common failure pattern:
1. Spawn subprocess with 30s limit
2. Complex code runs for 31s
3. Subprocess killed → `TIMEOUT`
4. Retry engine kicks in with 60s
5. Code runs to completion on retry (wasting one full subprocess spawn)

With pre-analysis, step 1 already uses 60s — **zero wasted executions**.

### 5.2 Complexity Metrics Collected

```python
@dataclasses.dataclass
class ASTComplexityProfile:
    total_nodes:        int   # Total AST node count
    loop_count:         int   # Number of For + While loops
    max_loop_depth:     int   # Maximum loop nesting depth (1=flat, 3=triple nested)
    function_count:     int   # Number of function definitions (incl. recursive)
    has_recursion:      bool  # True if any function calls itself
    has_numpy:          bool  # True if 'import numpy' or 'np.' is found
    has_scipy:          bool  # True if 'import scipy' or 'scipy.' is found
    has_sympy:          bool  # True if 'import sympy' or 'sympy.' is found
    comprehension_count: int  # Number of list/dict/set comprehensions
    estimated_complexity: str # O(1), O(N), O(N²), O(N³), O(2^N), O(N!)
```

### 5.3 Loop Nesting Depth — The Key Metric

Loop nesting depth is the single most predictive metric for runtime complexity. It is computed by a recursive AST walk:

```
Flat loop (depth=1):          O(N)   → STANDARD limits
  for i in range(N):
      process(i)

Double nested (depth=2):      O(N²)  → MEDIUM limits
  for i in range(N):
      for j in range(N):
          process(i, j)

Triple nested (depth=3):      O(N³)  → HEAVY limits
  for i in range(N):
      for j in range(N):
          for k in range(N):
              process(i, j, k)
```

### 5.4 Math Library Signature Detection

If the code imports known heavy-compute libraries, the limits are automatically elevated:

```python
MATH_LIBRARY_SIGNATURES = {
    # Pattern         → Minimum Preset
    "numpy":          LimitPreset.MEDIUM,
    "scipy":          LimitPreset.HEAVY,
    "sympy":          LimitPreset.HEAVY,
    "sklearn":        LimitPreset.HEAVY,
    "tensorflow":     LimitPreset.RESEARCH,
    "torch":          LimitPreset.RESEARCH,
    "cvxpy":          LimitPreset.HEAVY,     # Convex optimization
    "numba":          LimitPreset.HEAVY,     # JIT compiled math
}
```

### 5.5 Complexity → Limits Mapping Table

| Condition | Complexity Class | Auto-Selected Preset |
|---|---|---|
| `total_nodes < 50`, `loop_depth ≤ 1` | O(1) / O(N) | `MICRO` |
| `total_nodes < 200`, `loop_depth ≤ 1` | O(N) | `STANDARD` |
| `loop_depth == 2` OR `has_numpy` | O(N²) | `MEDIUM` |
| `loop_depth == 3` OR `has_scipy` OR `has_sympy` | O(N³) | `HEAVY` |
| `loop_depth ≥ 4` OR `has_recursion` + `has_numpy` | O(N^k) / O(2^N) | `RESEARCH` |
| `has_tensorflow` OR `has_torch` | Deep learning | `RESEARCH` |

---

## 6. Unified Execution Pipeline

The three concepts compose into a single linear pipeline:

```
Generated Code String (mutant_code)
         │
         ▼
┌────────────────────────────────────────────────────────┐
│  STEP 1: ComplexityAnalyzer.analyze(code)              │
│                                                        │
│  • Parse AST (SyntaxError → immediate rejection)       │
│  • Count nodes, loops, nesting depth                   │
│  • Detect math library imports                         │
│  • Detect recursion patterns                           │
│  • Return: ASTComplexityProfile                        │
│  • Derive: SandboxLimits (auto-scaled preset)          │
└────────────────────────┬───────────────────────────────┘
                         │ SandboxLimits (scaled)
                         ▼
┌────────────────────────────────────────────────────────┐
│  STEP 2: AdaptiveSandboxRunner.run(code, limits)       │
│                                                        │
│  Attempt 1:                                            │
│    run_in_sandbox(code, limits)  ──►  SandboxResult    │
│         │                                              │
│    ELIGIBILITY GATE:                                   │
│    ├── SUCCESS / SYNTAX_ERROR / RUNTIME_ERROR          │
│    │       → Return immediately (no retry)             │
│    └── TIMEOUT / GAS_LIMIT_EXCEEDED                    │
│            → Scale: limits × retry_scale               │
│            → Cap:   min(scaled, HARD_CEILING)          │
│                                                        │
│  Attempt 2 (if eligible):                              │
│    run_in_sandbox(code, scaled_limits) → SandboxResult │
│         │                                              │
│    Return result (success or final failure)            │
└────────────────────────┬───────────────────────────────┘
                         │ Final SandboxResult
                         ▼
┌────────────────────────────────────────────────────────┐
│  STEP 3: code_generator.py — Score & Rank              │
│                                                        │
│  • result.success=True  → Score the output             │
│  • result.success=False → Assign penalty (−100.0)      │
│  • result.retry_count   → Log for diagnostics          │
│  • result.limits_used   → Log for calibration          │
└────────────────────────────────────────────────────────┘
```

---

## 7. Target File Mapping

| File | Role | Action |
|---|---|---|
| `backend/app/safety/complexity_analyzer.py` | AST Complexity Pre-Analysis engine | **NEW FILE** |
| `backend/app/safety/adaptive_runner.py` | Self-Healing Retry Engine + Dynamic Limits | **NEW FILE** |
| `backend/app/safety/limits.py` | `SandboxLimits` dataclass + `LimitPreset` + `HARD_CEILING` | **NEW FILE** |
| `backend/app/core/code_generator.py` | Swap `run_sandbox()` to use `AdaptiveSandboxRunner` | **MODIFY** |
| `backend/app/safety/__init__.py` | Re-export public API for clean imports | **MODIFY** |
| `backend/tests/test_adaptive_sandbox.py` | Full test suite for all three mechanisms | **NEW FILE** |

---

## 8. Data Structures & Type Definitions

### 8.1 `SandboxLimits` — `backend/app/safety/limits.py`

```python
import dataclasses
import typing

@dataclasses.dataclass
class SandboxLimits:
    """
    Resource limit envelope passed to run_in_sandbox() and AdaptiveSandboxRunner.

    All fields have safe defaults that match the EMM-05-A2 sandbox baseline.
    """
    timeout_s:    float = 30.0      # Wall-clock timeout (seconds)
    memory_mb:    int   = 256       # RAM ceiling (megabytes)
    gas_limit:    int   = 50_000    # Max AST gas meter instruction count
    max_retries:  int   = 1         # 0 = no retry, 1 = one retry, etc.
    retry_scale:  float = 2.0       # Multiplier for limits on each retry

    def scale(self, factor: float) -> "SandboxLimits":
        """Return a new SandboxLimits with timeout and gas scaled by factor."""
        return SandboxLimits(
            timeout_s   = self.timeout_s  * factor,
            memory_mb   = self.memory_mb,             # Memory NOT scaled
            gas_limit   = int(self.gas_limit * factor),
            max_retries = max(0, self.max_retries - 1),
            retry_scale = self.retry_scale,
        )

    def cap(self, ceiling: "SandboxLimits") -> "SandboxLimits":
        """Return a new SandboxLimits clamped to ceiling values."""
        return SandboxLimits(
            timeout_s   = min(self.timeout_s,  ceiling.timeout_s),
            memory_mb   = min(self.memory_mb,  ceiling.memory_mb),
            gas_limit   = min(self.gas_limit,  ceiling.gas_limit),
            max_retries = self.max_retries,
            retry_scale = self.retry_scale,
        )
```

### 8.2 `AdaptiveSandboxResult` — Extended Result

```python
@dataclasses.dataclass
class AdaptiveSandboxResult:
    """
    Wraps SandboxResult with adaptive execution metadata.
    Adds retry accounting and limits audit trail.
    """
    # Core result (from sandbox.py)
    success:       bool
    stdout:        str
    stderr:        str
    status:        str           # SUCCESS / TIMEOUT / GAS_LIMIT_EXCEEDED / etc.
    error_type:    typing.Optional[str]
    error_message: typing.Optional[str]
    error_line:    typing.Optional[int]
    gas_consumed:  int

    # Adaptive execution metadata
    attempt_count:       int              # How many attempts were made (1 or 2)
    limits_used:         SandboxLimits    # The limits used on the FINAL attempt
    complexity_profile:  typing.Optional["ASTComplexityProfile"] = None
    was_auto_scaled:     bool = False     # True if ComplexityAnalyzer increased limits
    was_retried:         bool = False     # True if Self-Healing retry was triggered
```

---

## 9. Full Code Skeletons

### 9.1 `complexity_analyzer.py` — Full Skeleton

```python
"""
backend/app/safety/complexity_analyzer.py
EMMA SUDARSHANA Safety Division — AST Complexity Pre-Analysis Engine

Performs static AST analysis of generated code to derive appropriate
SandboxLimits before subprocess execution. Prevents false timeout
rejections by proactively scaling limits based on code structure.
"""

import ast
import dataclasses
import typing
from .limits import SandboxLimits, LimitPreset


@dataclasses.dataclass
class ASTComplexityProfile:
    total_nodes:         int
    loop_count:          int
    max_loop_depth:      int
    function_count:      int
    has_recursion:       bool
    has_numpy:           bool
    has_scipy:           bool
    has_sympy:           bool
    comprehension_count: int
    estimated_complexity: str
    detected_libraries:  list[str]


class LoopDepthVisitor(ast.NodeVisitor):
    """Walks the AST to compute maximum loop nesting depth."""

    def __init__(self) -> None:
        self.max_depth: int   = 0
        self.loop_count: int  = 0
        self._current_depth: int = 0

    def _visit_loop(self, node: ast.AST) -> None:
        self.loop_count += 1
        self._current_depth += 1
        self.max_depth = max(self.max_depth, self._current_depth)
        self.generic_visit(node)
        self._current_depth -= 1

    visit_For   = _visit_loop   # type: ignore[assignment]
    visit_While = _visit_loop   # type: ignore[assignment]


class RecursionDetector(ast.NodeVisitor):
    """Detects direct self-recursive function calls."""

    def __init__(self) -> None:
        self._function_names: set[str] = set()
        self.has_recursion: bool = False

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._function_names.add(node.name)
        self.generic_visit(node)

    def visit_Call(self, node: ast.Call) -> None:
        if isinstance(node.func, ast.Name):
            if node.func.id in self._function_names:
                self.has_recursion = True
        self.generic_visit(node)


class ComplexityAnalyzer:
    """
    Analyzes generated code complexity and returns a scaled SandboxLimits.

    Usage:
        analyzer = ComplexityAnalyzer()
        profile, limits = analyzer.analyze(code_string)
        result = run_in_sandbox(code_string, **dataclasses.asdict(limits))
    """

    MATH_LIBRARY_SIGNATURES: dict[str, SandboxLimits] = {
        "numpy":      LimitPreset.MEDIUM,
        "scipy":      LimitPreset.HEAVY,
        "sympy":      LimitPreset.HEAVY,
        "sklearn":    LimitPreset.HEAVY,
        "tensorflow": LimitPreset.RESEARCH,
        "torch":      LimitPreset.RESEARCH,
        "cvxpy":      LimitPreset.HEAVY,
        "numba":      LimitPreset.HEAVY,
    }

    def analyze(
        self,
        code: str,
        base_preset: SandboxLimits | None = None,
    ) -> tuple[ASTComplexityProfile, SandboxLimits]:
        """
        Parse code, compute complexity metrics, derive SandboxLimits.

        Args:
            code:        Raw Python source code string.
            base_preset: Minimum preset to start from. If None, starts at MICRO.

        Returns:
            (ASTComplexityProfile, SandboxLimits) — profile for logging,
            limits for sandbox invocation.

        Raises:
            SyntaxError: If code cannot be parsed. Caller should handle this
                         as an immediate rejection (no sandbox spawn needed).
        """
        tree = ast.parse(code)   # Raises SyntaxError — intentional

        # --- Node count ---
        total_nodes = sum(1 for _ in ast.walk(tree))

        # --- Loop depth + count ---
        loop_visitor = LoopDepthVisitor()
        loop_visitor.visit(tree)

        # --- Function / recursion detection ---
        recursion_detector = RecursionDetector()
        recursion_detector.visit(tree)

        # --- Library detection ---
        detected_libraries: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.name.split(".")[0]
                    if name in self.MATH_LIBRARY_SIGNATURES:
                        detected_libraries.append(name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    name = node.module.split(".")[0]
                    if name in self.MATH_LIBRARY_SIGNATURES:
                        detected_libraries.append(name)

        # --- Comprehension count ---
        comprehension_count = sum(
            1 for node in ast.walk(tree)
            if isinstance(node, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp))
        )

        # --- Complexity class estimation ---
        depth = loop_visitor.max_depth
        if depth == 0:
            complexity = "O(1)"
        elif depth == 1:
            complexity = "O(N)"
        elif depth == 2:
            complexity = "O(N²)"
        elif depth == 3:
            complexity = "O(N³)"
        else:
            complexity = f"O(N^{depth})"
        if recursion_detector.has_recursion:
            complexity = f"O(2^N) or worse (recursion detected)"

        profile = ASTComplexityProfile(
            total_nodes          = total_nodes,
            loop_count           = loop_visitor.loop_count,
            max_loop_depth       = depth,
            function_count       = recursion_detector._function_names.__len__(),
            has_recursion        = recursion_detector.has_recursion,
            has_numpy            = "numpy" in detected_libraries,
            has_scipy            = "scipy" in detected_libraries,
            has_sympy            = "sympy" in detected_libraries,
            comprehension_count  = comprehension_count,
            estimated_complexity = complexity,
            detected_libraries   = list(set(detected_libraries)),
        )

        # --- Derive limits ---
        limits = self._derive_limits(profile, base_preset or LimitPreset.MICRO)
        return profile, limits

    def _derive_limits(
        self,
        profile: ASTComplexityProfile,
        base: SandboxLimits,
    ) -> SandboxLimits:
        """
        Apply complexity rules to select the appropriate preset.
        Always returns the MAXIMUM of the base and the computed preset.
        """
        computed = base

        # Loop nesting depth rules
        if profile.max_loop_depth >= 4 or profile.has_recursion:
            computed = LimitPreset.RESEARCH
        elif profile.max_loop_depth == 3:
            computed = LimitPreset.HEAVY
        elif profile.max_loop_depth == 2:
            computed = max(computed, LimitPreset.MEDIUM, key=lambda l: l.timeout_s)
        elif profile.total_nodes > 200:
            computed = max(computed, LimitPreset.STANDARD, key=lambda l: l.timeout_s)

        # Library signature rules (take highest of depth-rule and library-rule)
        for lib in profile.detected_libraries:
            lib_preset = self.MATH_LIBRARY_SIGNATURES.get(lib, LimitPreset.MICRO)
            if lib_preset.timeout_s > computed.timeout_s:
                computed = lib_preset

        return computed
```

### 9.2 `adaptive_runner.py` — Full Skeleton

```python
"""
backend/app/safety/adaptive_runner.py
EMMA SUDARSHANA Safety Division — Self-Healing Sandbox Retry Engine

Wraps sandbox.run_in_sandbox() with:
  1. ComplexityAnalyzer pre-analysis for limit auto-scaling
  2. Retry loop for TIMEOUT / GAS_LIMIT_EXCEEDED failures
  3. Hard ceiling enforcement on all scaled limits
"""

import logging
from .limits import SandboxLimits, LimitPreset, HARD_CEILING
from .sandbox import run_in_sandbox, SandboxResult
from .complexity_analyzer import ComplexityAnalyzer, ASTComplexityProfile
from .adaptive_result import AdaptiveSandboxResult

logger = logging.getLogger(__name__)

# Failure modes that qualify for a retry
RETRY_ELIGIBLE = frozenset({"TIMEOUT", "GAS_LIMIT_EXCEEDED"})

# Failure modes that are immediately rejected — no retry
HARD_REJECT = frozenset({"SYNTAX_ERROR", "RUNTIME_ERROR", "PROCESS_CRASH",
                          "OOM_KILLED", "UNKNOWN_ERROR"})


class AdaptiveSandboxRunner:
    """
    Orchestrates complexity pre-analysis and self-healing retry logic
    around the passive sandbox.run_in_sandbox() primitive.

    Usage:
        runner = AdaptiveSandboxRunner()
        result = runner.run(code=mutant_code, preset=LimitPreset.STANDARD)
    """

    def __init__(self, analyzer: ComplexityAnalyzer | None = None) -> None:
        self._analyzer = analyzer or ComplexityAnalyzer()

    def run(
        self,
        code:    str,
        preset:  SandboxLimits = LimitPreset.STANDARD,
        limits:  SandboxLimits | None = None,
        skip_analysis: bool = False,
    ) -> AdaptiveSandboxResult:
        """
        Execute code with adaptive limits and optional self-healing retry.

        Args:
            code:          Python source code to execute.
            preset:        Base limit preset (default: STANDARD).
            limits:        Explicit limits override. If provided, bypasses preset.
            skip_analysis: If True, skip AST complexity analysis.

        Returns:
            AdaptiveSandboxResult with execution result and metadata.
        """
        # --- Phase 1: AST Complexity Pre-Analysis ---
        profile: ASTComplexityProfile | None = None
        was_auto_scaled = False

        if not skip_analysis:
            try:
                profile, analyzed_limits = self._analyzer.analyze(
                    code, base_preset=limits or preset
                )
                effective_limits = analyzed_limits
                was_auto_scaled = (
                    effective_limits.timeout_s > (limits or preset).timeout_s
                )
                if was_auto_scaled:
                    logger.info(
                        "[AdaptiveSandboxRunner] Complexity=%s — "
                        "Auto-scaled limits: timeout=%.1fs gas=%d",
                        profile.estimated_complexity,
                        effective_limits.timeout_s,
                        effective_limits.gas_limit,
                    )
            except SyntaxError as exc:
                # SyntaxError during pre-analysis → immediate rejection
                return AdaptiveSandboxResult(
                    success=False, stdout="", stderr="",
                    status="SYNTAX_ERROR",
                    error_type="SyntaxError",
                    error_message=str(exc),
                    error_line=getattr(exc, "lineno", None),
                    gas_consumed=0,
                    attempt_count=0,
                    limits_used=limits or preset,
                    complexity_profile=None,
                    was_auto_scaled=False,
                    was_retried=False,
                )
        else:
            effective_limits = limits or preset

        # --- Phase 2: Subprocess Execution + Retry Loop ---
        current_limits = effective_limits
        attempt = 0
        was_retried = False

        while True:
            attempt += 1
            logger.debug(
                "[AdaptiveSandboxRunner] Attempt %d — timeout=%.1fs gas=%d mem=%dMB",
                attempt, current_limits.timeout_s,
                current_limits.gas_limit, current_limits.memory_mb,
            )

            raw: SandboxResult = run_in_sandbox(
                code          = code,
                timeout_s     = current_limits.timeout_s,
                memory_mb     = current_limits.memory_mb,
                gas_limit     = current_limits.gas_limit,
                safe_builtins = True,
                inject_gas    = True,
            )

            status = raw.status   # e.g. "SUCCESS", "TIMEOUT", "GAS_LIMIT_EXCEEDED"

            # Check if retry is eligible and budget remains
            if (
                status in RETRY_ELIGIBLE
                and current_limits.max_retries > 0
                and attempt <= 3   # Safety: never more than 3 attempts total
            ):
                scaled = current_limits.scale(current_limits.retry_scale)
                capped  = scaled.cap(HARD_CEILING)
                logger.warning(
                    "[AdaptiveSandboxRunner] %s on attempt %d — "
                    "Retrying with timeout=%.1fs gas=%d",
                    status, attempt,
                    capped.timeout_s, capped.gas_limit,
                )
                current_limits = capped
                was_retried = True
                continue   # Go to next attempt

            # No retry (success, hard reject, or retries exhausted)
            break

        return AdaptiveSandboxResult(
            success       = raw.success,
            stdout        = raw.stdout,
            stderr        = raw.stderr,
            status        = status,
            error_type    = raw.error_type,
            error_message = raw.error_message,
            error_line    = raw.error_line,
            gas_consumed  = raw.gas_consumed,
            attempt_count       = attempt,
            limits_used         = current_limits,
            complexity_profile  = profile,
            was_auto_scaled     = was_auto_scaled,
            was_retried         = was_retried,
        )
```

### 9.3 Modified `code_generator.py` Integration

```python
# BEFORE (in code_generator.py):
from app.safety.sandbox import run_in_sandbox

def run_sandbox(self, code: str) -> SandboxResult:
    return run_in_sandbox(code, timeout_s=30.0, memory_mb=256, gas_limit=50_000)


# AFTER:
from app.safety.adaptive_runner import AdaptiveSandboxRunner
from app.safety.limits import LimitPreset

_adaptive_runner = AdaptiveSandboxRunner()   # Module-level singleton

def run_sandbox(self, code: str) -> AdaptiveSandboxResult:
    """
    Execute generated mutant code via the Adaptive Sandbox pipeline:
      1. ComplexityAnalyzer scales limits based on AST structure
      2. AdaptiveSandboxRunner runs with those limits
      3. If TIMEOUT/GAS: auto-retry with 2× limits (one time)
    """
    return _adaptive_runner.run(
        code   = code,
        preset = LimitPreset.STANDARD,   # Base preset; analyzer may scale up
    )
```

---

## 10. Calibration Reference Table

| Scenario | `estimated_complexity` | `timeout_s` | `gas_limit` | `memory_mb` | `max_retries` |
|---|---|---|---|---|---|
| `def add(a, b): return a+b` | O(1) | 5s | 10,000 | 64 MB | 0 |
| `for i in range(N): process(i)` | O(N) | 30s | 50,000 | 256 MB | 1 |
| `[[...] for i in range(N) for j in range(N)]` | O(N²) | 60s | 500,000 | 512 MB | 1 |
| `import numpy; np.linalg.eig(M)` | O(N²)+ (numpy) | 60s | 500,000 | 512 MB | 1 |
| `import scipy; scipy.optimize.minimize(...)` | O(N³) (scipy) | 120s | 5,000,000 | 1024 MB | 2 |
| Triple nested loop + scipy | O(N³) | 120s | 5,000,000 | 1024 MB | 2 |
| Recursive DFS + numpy | O(2^N) | 300s | 50,000,000 | 2048 MB | 3 |
| `import torch; model.train(...)` | Deep learning | 300s | 50,000,000 | 2048 MB | 3 |

---

## 11. Verification Plan

### 11.1 Unit Tests — `tests/test_adaptive_sandbox.py`

| # | Test Name | Input | Expected Behavior |
|---|---|---|---|
| 1 | `test_simple_code_uses_micro_preset` | `def add(a,b): return a+b` | `limits_used.timeout_s == 5.0`, `attempt_count == 1` |
| 2 | `test_double_loop_auto_scales_to_medium` | Two nested for loops | `was_auto_scaled=True`, `timeout_s == 60` |
| 3 | `test_triple_loop_auto_scales_to_heavy` | Three nested for loops | `was_auto_scaled=True`, `timeout_s == 120` |
| 4 | `test_numpy_import_scales_to_medium` | `import numpy` | `was_auto_scaled=True`, `limits_used.timeout_s >= 60` |
| 5 | `test_scipy_import_scales_to_heavy` | `import scipy` | `was_auto_scaled=True`, `limits_used.timeout_s >= 120` |
| 6 | `test_syntax_error_skips_sandbox` | `def f( pass` | `status=SYNTAX_ERROR`, `attempt_count=0`, no subprocess spawned |
| 7 | `test_timeout_triggers_retry` | Mock `run_in_sandbox` → TIMEOUT then SUCCESS | `was_retried=True`, `attempt_count=2`, final `success=True` |
| 8 | `test_gas_exceeded_triggers_retry` | Mock → GAS_LIMIT_EXCEEDED then SUCCESS | `was_retried=True`, `attempt_count=2`, final `success=True` |
| 9 | `test_runtime_error_no_retry` | `1/0` | `was_retried=False`, `attempt_count=1`, `status=RUNTIME_ERROR` |
| 10 | `test_oom_killed_no_retry` | Mock → OOM_KILLED | `was_retried=False`, `attempt_count=1` |
| 11 | `test_hard_ceiling_enforced` | `limits.scale(10.0)` then `.cap(HARD_CEILING)` | `timeout_s <= 600.0` |
| 12 | `test_retry_exhaust_returns_failure` | Mock → TIMEOUT on all attempts | `was_retried=True`, final `success=False` |
| 13 | `test_memory_not_scaled_on_retry` | Mock → TIMEOUT → retry | `limits_used.memory_mb == original_memory_mb` |
| 14 | `test_recursion_detected` | Fibonacci recursive | `has_recursion=True`, `estimated_complexity` contains "2^N" |
| 15 | `test_gas_consumed_logged` | Simple compute | `gas_consumed > 0` in result |

### 11.2 Integration Test

```python
# End-to-end: complex code that WOULD timeout at 30s but passes at 60s
def test_heavy_code_passes_with_adaptive_limits():
    code = """
import time
# Simulates a moderately heavy computation
result = sum(i**2 for i in range(1_000_000))
print(result)
"""
    runner = AdaptiveSandboxRunner()
    result = runner.run(code, preset=LimitPreset.STANDARD)
    assert result.success is True
    assert "333333833333500000" in result.stdout
```

---

*End of Plan — EMM-05-A3 v1.0*
*Adaptive Sandbox Limits — Dynamic Scaling, Self-Healing Retry, AST Pre-Analysis*
*Nexus AI Research Lab — SUDARSHANA Safety Division*
*Next: EMM-05-A4 — Live Dashboard Integration & Sandbox Telemetry*
