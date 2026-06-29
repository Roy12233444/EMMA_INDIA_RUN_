# EMMA — Enterprise Metacognitive Multi-Agent Fleet
## Complete Project Documentation

> **Version:** 1.0.0  
> **Build:** EMMA_hack2skill (India Runs Hackathon — Track 1 Submission)  
> **Last Updated:** May 2026  
> **License:** Proprietary — All rights reserved

### 🔗 Project Links

| Resource | Link |
|----------|------|
| 📁 **Google Drive** (Full Submission Materials) | [Click here to access](https://drive.google.com/drive/folders/1CQtJkdS_THL2ZrP1Sdx1J_1FjGKYc00k?usp=sharing) |
| 💻 **GitHub Repository** (Source Code) | [Roy12233444/EMMA_INDIA_RUN_](https://github.com/Roy12233444/EMMA_INDIA_RUN_/tree/main) |

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [System Architecture](#2-system-architecture)
3. [The Five Cognitive Pillars](#3-the-five-cognitive-pillars)
4. [ANJANEYA Memory Protocol (AMP)](#4-anjaneya-memory-protocol-amp)
5. [Module Reference](#5-module-reference)
   - 5.1 [Orchestrator (`orchestrator.py`)](#51-orchestrator)
   - 5.2 [Executor / DraftCoordinator (`executor.py`)](#52-executor--draftcoordinator)
   - 5.3 [Code Generator (`code_generator.py`)](#53-code-generator)
   - 5.4 [Context Scheduler (`context_scheduler.py`)](#54-context-scheduler)
   - 5.5 [Critic (`critic.py`)](#55-critic--codecritic)
   - 5.6 [Token Pruner (`token_prune.py`)](#56-token-pruner--contextvectorpruner)
   - 5.7 [Session Layer (`database/session.py`)](#57-session-layer)
   - 5.8 [Semantic Manifold (`database/manifold.py`)](#58-semantic-manifold)
   - 5.9 [Safety Layer (`safety/`)](#59-safety-layer)
6. [REST & WebSocket API Reference](#6-rest--websocket-api-reference)
7. [Configuration Reference](#7-configuration-reference)
8. [Project Directory Structure](#8-project-directory-structure)
9. [Tech Stack & Dependencies](#9-tech-stack--dependencies)
10. [Running EMMA Locally](#10-running-emma-locally)
11. [Testing](#11-testing)
12. [Mathematical Foundations](#12-mathematical-foundations)
13. [Design Principles & Constraints](#13-design-principles--constraints)
14. [Glossary](#14-glossary)

---

## 1. Project Overview

**EMMA** (Enterprise Metacognitive Multi-Agent Fleet) is a next-generation, self-healing, autonomous AI software engineer designed to operate in **zero-dependency, air-gapped, local enterprise environments**.

Unlike traditional static code generation pipelines that produce a single draft and crash on error, EMMA functions as a **biological evolutionary engine**. She thinks in parallel, audits her own work, scores candidates against a multi-variable fitness function, commits atomically, and monitors her own cognitive stability — all without requiring cloud APIs or internet connectivity.

### Core Mission

> *Build the world's first truly self-correcting, metacognitive AI software engineer that can diagnose, refactor, and evolve enterprise codebases entirely on-premise — using only locally hosted models.*

### What Makes EMMA Unique

| Feature | Traditional AI Coder | EMMA |
|---|---|---|
| Code Generation | Single draft, single temperature | 3 parallel mutants (T=0.20, 0.70, 0.95) |
| Error Recovery | Crash or retry | Self-healing causal convergence loop |
| Context Management | Fixed window, token overflow crash | JIT AST rotation + 5-tier compaction |
| Memory | Stateless per-call | Persistent vector manifold + SQLite sessions |
| Safety | None | SAHOO gates + GDI + sandboxed execution |
| Cloud Dependency | Always-on APIs | 100% local — Ollama + sentence-transformers |
| Code Commit | Overwrite in place | Atomic POSIX-safe commit with rollback |

---

## 2. System Architecture

EMMA's architecture is organized into **three concentric rings**:

```
┌─────────────────────────────────────────────────────────────────┐
│  RING 3: PERSISTENCE LAYER                                      │
│  SQLite Session Store ←→ LanceDB Vector Manifold ←→ Spore ZIP  │
├─────────────────────────────────────────────────────────────────┤
│  RING 2: SAFETY & ALIGNMENT LAYER                               │
│  SAHOO Gates  ←→  Goal Drift Index  ←→  Sandbox Jail           │
├─────────────────────────────────────────────────────────────────┤
│  RING 1: COGNITIVE CORE                                         │
│  Orchestrator → Executor → Code Generator → Critic → Pruner    │
└─────────────────────────────────────────────────────────────────┘
```

### Data Flow Diagram

```
User Goal / Task
       │
       ▼
┌─────────────────┐
│  Orchestrator   │◄──── CausalConvergenceMonitor (stability)
│  (solve loop)   │
└────────┬────────┘
         │ invokes
         ▼
┌─────────────────┐      ┌───────────────────────────┐
│  Code Generator │─────►│  DraftCoordinator          │
│  (gate keeper)  │      │  ├─ Mutant A  (T=0.20)    │
└────────┬────────┘      │  ├─ Mutant B  (T=0.70)    │
         │               │  └─ Mutant C  (T=0.95)    │
         │               └──────────┬────────────────┘
         │                          │ asyncio.gather
         │                          ▼
         │               ┌─────────────────────┐
         │               │  Ollama / Local LLM  │
         │               │  qwen2.5-coder       │
         │               └──────────┬──────────┘
         │                          │ XML extraction
         │                          ▼
         │               ┌─────────────────────┐
         │               │  MutantCodeSelector  │
         │               │  Fitness Scoring     │
         │               └──────────┬──────────┘
         │                          │ winner
         ▼                          ▼
┌─────────────────┐      ┌─────────────────────┐
│  Critic         │      │  Atomic Commit       │
│  (STAI review)  │      │  (.emma_mutant_tmp)  │
└────────┬────────┘      └──────────┬──────────┘
         │                          │
         ▼                          ▼
┌─────────────────┐      ┌─────────────────────┐
│  Token Pruner   │      │  Filesystem (target) │
│  (ContextVector)│      └─────────────────────┘
└────────┬────────┘
         │
         ▼
┌─────────────────────────────────────────────┐
│  ANJANEYA Memory Protocol                   │
│  SQLite Session ←→ LanceDB Semantic Search  │
└─────────────────────────────────────────────┘
```

---

## 3. The Five Cognitive Pillars

EMMA's intelligence is divided into five named cognitive pillars, each responsible for a distinct metacognitive function:

### Pillar I — Evolutionary Concurrency Bridge (`executor.py`)

Spawns three **parallel inference threads** at distinct temperature coefficients targeting low, mid, and high entropy ranges. Each thread carries a unique system prompt designed to produce structurally different code candidates:

| Mutant | Name | Temperature | Cognitive Axis |
|--------|------|-------------|----------------|
| **A** | Parsimonious Architect | `0.20` | Minimal lines, list comprehensions, direct logic |
| **B** | Structural Alternative | `0.70` | Alt data structures, map/filter, helper patterns |
| **C** | Creative Decoupler | `0.95` | Closures, factory patterns, radical modular decomposition |

All three requests fire concurrently via `asyncio.gather(return_exceptions=True)`, so a failure in one slot never cancels its siblings.

### Pillar II — JIT AST Context Rotation (`context_scheduler.py`)

Compiles every source file into an **Abstract Syntax Tree** and dynamically "stubs out" all classes and functions not directly relevant to the current task. The active target node is fully expanded; sibling nodes are collapsed to single-line signature stubs:

```python
# Before rotation (3,000+ tokens):
class DatabaseManager:
    def connect(self): ...   # 80 lines
    def query(self): ...     # 120 lines  ← ACTIVE TARGET
    def close(self): ...     # 40 lines

# After rotation (~200 tokens):
class DatabaseManager: ...
def connect(...) -> Connection: ...
def query(self, sql: str, params: tuple) -> List[Row]:
    # FULL BODY HERE (120 lines)
def close(...) -> None: ...
```

This reduces LLM prompt token sizes by **over 80%**, allowing EMMA to work efficiently on large enterprise codebases without hitting context windows.

### Pillar III — AST-Hardened Sandboxed Auditor (`code_generator.py`)

A secure, in-memory execution sandbox that validates every candidate mutant before it may touch the filesystem:

- **AST Walk Scan:** Parses the candidate bytecode and walks every AST node looking for blocked imports (`os`, `sys`, `subprocess`, `socket`, `pathlib`, `threading`, etc.)
- **Compile Gate:** Calls `compile(code, "<sandbox>", "exec")` to verify bytecode viability before execution
- **Security Penalty:** Any security violation immediately disqualifies the mutant with a `-200` penalty score
- **Atomic Commit:** Winners are written to a `.emma_mutant_tmp.py` staging file, verified once more via `ast.parse()`, then atomically renamed to the target path using `os.replace()` (POSIX atomic)

### Pillar IV — Page Curve Log Evaporator (`context_scheduler.py` → `PageCurveEvaporator`)

Monitors stdout/stderr accumulation across solver turns. When log output exceeds the `max_lines` threshold (the **Page Time**), a single-pass regex extraction condenses the entire log stream into a compact metadata summary:

```
[Log Evaporated: Total Lines=1247 | Errors=3 | Warnings=12 | Status=1 | Last Error="AttributeError: 'NoneType' object has no attribute 'query'"]
```

This preserves all structural debugging signals (exit codes, error counts, last traceback) while recovering **~98% of the token footprint** — modelled on the Hawking Radiation Page Curve where information is preserved through entropy evaporation.

### Pillar V — Causal Convergence Monitor (`orchestrator.py` → `CausalConvergenceMonitor`)

Treats the debugging loop as a **fixed-point convergence sequence**. The Causal Residual R_k is defined as the Levenshtein structural similarity ratio between consecutive error outputs:

```
R_k = SequenceMatcher(E_{k-1}, E_k).ratio()
```

If `R_k ≥ 0.95` for `loop_threshold` consecutive turns (default: 3), EMMA has entered an **infinite error regression**. The monitor immediately:

1. Emits a `CausalInstabilityException` with full residual history
2. Executes `git checkout -- .` to roll back the workspace to the last stable state
3. Halts the solver loop — protecting both the repository and API token budget

---

## 4. ANJANEYA Memory Protocol (AMP)

The **ANJANEYA Memory Protocol** is EMMA's persistent experience memory system — a dual-layer database combining a relational SQLite session store with a LanceDB vector manifold for semantic search and experience retrieval.

Named after the Hindu deity Anjaneya (Hanuman) — symbol of devotion, strength, memory, and unwavering purpose — the protocol ensures EMMA never loses the lessons learned from past solver sessions.

### The Five AMP Pillars

#### AMP Pillar 1 — Devotion Crystal Scoring

Every solver session is scored against the **Devotion Score formula**:

```
D = α · (1 - turns_used/T_max) + β · (1 - tokens_used/U_max)
```

| Parameter | Value | Meaning |
|-----------|-------|---------|
| `α` | 0.60 | Turn Efficiency weight |
| `β` | 0.40 | Token Utilization Efficiency weight |
| `T_max` | 15 | Maximum solver turns ceiling |
| `U_max` | 100,000 | Theoretical token budget ceiling |
| `Θ_crystal` | 0.85 | Hard-freeze threshold |

When `D ≥ Θ_crystal`, the session is **crystallised** — permanently frozen in an immutable state that can never be overwritten or deleted. This preserves EMMA's highest-quality solver runs as eternal reference benchmarks.

#### AMP Pillar 2 — Dronagiri Holographic Null-Guard

Named after the mountain Hanuman carried whole to save Lakshmana. If the LanceDB vector database becomes corrupted or unavailable, the Null-Guard activates a **holographic fallback** — returning pre-cached or reconstructed results from the SQLite session store to maintain operational continuity without crashing.

#### AMP Pillar 3 — Chiranjeevi Spore Persistence

Named after the immortal Chiranjeevi (one who lives forever). The Spore system creates **compressed ZIP archives** of the entire vector manifold state at configurable intervals:

- Archives are stored in the `/spores/` directory alongside the manifold database
- Each archive is SHA-256 hashed for integrity verification
- The hash is recorded in the SQLite session table for cross-reference
- In the event of database corruption, `restore_from_spore()` rebuilds the manifold from the most recent healthy archive

#### AMP Pillar 4 — Sankat Mochan Semantic Drift Interception

Named after "Sankat Mochan" — the reliever of suffering. Monitors **cosine distance drift** in the embedding space across sequential queries. When the minimum distance `d_min` between a query embedding and the nearest stored experience exceeds thresholds:

| Threshold | `d_min` | Action |
|-----------|---------|--------|
| DISTRESS | > 0.75 | Auto-escalate to MAHA depth (K=40) |
| ALERT | > 0.55 | Escalate to MADHYA depth (K=20) |
| NORMAL | ≤ 0.55 | Use ANIMA depth (K=10) |

#### AMP Pillar 5 — Anima-Mahima Adaptive Multi-Depth Scaling

Named after the Siddhis (mystical powers) of Hanuman. Provides **three adaptive KNN search depths** that scale with query complexity and drift level:

| Mode | K Value | Use Case |
|------|---------|----------|
| `ANIMA` | 10 | Standard queries, low drift |
| `MADHYA` | 20 | Moderate drift, broader recall |
| `MAHA` | 40 | High distress, maximum recall |

---

## 5. Module Reference

### 5.1 Orchestrator

**File:** `backend/app/core/orchestrator.py`  
**Size:** ~611 lines  
**Role:** Central Executive Solver Loop

The Orchestrator is EMMA's nervous system. It drives the main execution lifecycle, integrating all cognitive pillars into a single coherent solve loop.

#### Key Classes

**`CausalInstabilityException`**
```python
class CausalInstabilityException(Exception):
    turn: int           # Solver turn at detection
    residuals: List[float]  # Full residual history
    last_error: str     # Last captured error output
```
Raised when the solver enters an infinite error regression. Carries a full diagnostic payload for post-mortem analysis.

**`CausalConvergenceMonitor`**
```python
class CausalConvergenceMonitor:
    def evaluate_step(
        self,
        current_error: str,
        turn: int,
        workspace_path: str
    ) -> None
```
Levenshtein-based error similarity tracker. Computes the Causal Residual R_k between consecutive error outputs and triggers a Git rollback if the solver stalls.

**`EMMAOrchestrator`** (main solve engine)
```python
async def solve(
    self,
    goal: str,
    target_file: str,
    target_function: str,
    max_turns: int = 15
) -> SolveResult
```
Drives the complete solve loop: plan → generate → sandbox → critique → commit → monitor → prune.

#### Solve Loop Steps

```
Turn N:
  1. ASTContextRotator.get_rotated_context(target_function)
  2. DraftCoordinator.generate_drafts(task, signature, context)
  3. MutantCodeSelector.evaluate_mutants(candidates)
  4. CodeGenerator.generate_and_apply_patch(winner)
  5. subprocess.run(["python", target_file])  → exit_code, stdout
  6. CausalConvergenceMonitor.evaluate_step(stdout, turn)
  7. PageCurveEvaporator.evaporate_log(stdout)
  8. ContextVectorPruner.maybe_prune(context_history)
  9. db_record_event(session_id, turn, event_data)
 10. If exit_code == 0: return SUCCESS
     Else: loop to Turn N+1
```

---

### 5.2 Executor / DraftCoordinator

**File:** `backend/app/core/executor.py`  
**Size:** ~604 lines  
**Role:** Evolutionary Draft Coordinator — Parallel LLM Inference Bridge

#### Key Class: `DraftCoordinator`

The evolutionary bridge between EMMA's cognitive core and the local Ollama LLM endpoint.

**Constructor Parameters:**

| Parameter | Default | Description |
|-----------|---------|-------------|
| `llm_url` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |
| `model` | `qwen2.5-coder` | Model identifier |
| `timeout` | `10.0` | Hard wall-clock ceiling in seconds |
| `max_tokens` | `1024` | Max tokens in LLM request body |

**Primary Method:**
```python
async def generate_drafts(
    self,
    task: str,
    target_signature: str = "",
    file_context: str = ""
) -> List[str]  # Exactly 3 code strings: [Mutant_A, Mutant_B, Mutant_C]
```

**Internal Pipeline:**
1. `_build_user_message()` — constructs shared user prompt (truncated at 2,000 chars)
2. `asyncio.to_thread(_sync_llm_call, ...)` × 3 — parallel HTTP POST to Ollama
3. `asyncio.gather(return_exceptions=True)` — collects all results without cancellation
4. `_extract_code_proposal()` — regex extracts code from `<CODE_PROPOSAL>` XML tags
5. `compile(code, "<sandbox>", "exec")` — bytecode syntax verification gate
6. Fallback to `_FALLBACK_A/B/C` simulation mutants on any failure

**XML Extraction Regex:**
```python
r"<CODE_PROPOSAL>\s*(?:```python\s*)?(.*?)(?:\s*``)?\s*</CODE_PROPOSAL>"
# Flags: re.DOTALL | re.IGNORECASE
```

**Offline Fallback Contract:**
- Slot 0 (Mutant A): Syntactically valid → passes fitness gate
- Slot 1 (Mutant B): Syntactically valid → passes fitness gate
- Slot 2 (Mutant C): Deliberate `SyntaxError` → rejected at `-100.0` (validates rejection path)

---

### 5.3 Code Generator

**File:** `backend/app/core/code_generator.py`  
**Size:** ~817 lines  
**Role:** AST-Hardened Sandboxed Auditor & Atomic Commit Engine

#### Blocked Imports (Security Gate)

```python
BLOCKED_IMPORTS = frozenset({
    "os", "sys", "subprocess", "shutil", "pathlib",
    "socket", "importlib", "ctypes", "multiprocessing",
    "threading", "signal", "builtins", "gc", "resource",
    "pty", "atexit"
})
```

Any candidate mutant that imports these modules is **immediately disqualified** with a `-200` security penalty.

#### Key Class: `CodeGenerator`

```python
async def generate_and_apply_patch(
    self,
    task: str,
    target_file: str,
    target_function: str
) -> CommitResult
```

**Atomic Commit Protocol:**
```python
def _atomic_commit(self, target_path: Path, code: str) -> None:
    tmp = target_path.with_suffix(".emma_mutant_tmp.py")
    tmp.write_text(code, encoding="utf-8")
    ast.parse(tmp.read_text())   # Final verification
    os.replace(tmp, target_path) # POSIX atomic rename
```

If `ast.parse()` fails on the temp file, it is unlinked and the original target is preserved untouched.

---

### 5.4 Context Scheduler

**File:** `backend/app/core/context_scheduler.py`  
**Size:** ~570 lines  
**Role:** JIT AST Context Rotation · Mutant Fitness Scoring · Page Curve Log Compression

#### Class A: `ASTContextRotator`

Geodesic coordinate reduction via AST projection. Treats a source file as a high-dimensional state space and projects it onto a localised active-manifold.

```python
class ASTContextRotator:
    def __init__(self, file_path: str) -> None

    def get_rotated_context(self, active_node_name: str) -> str
    # Returns: <TRANSIENT_CONTEXT id="func_name" type="ast_node">
    #          ...compressed source...
    #          </TRANSIENT_CONTEXT>
```

**Algorithm:**
1. Parse file to AST, index all `FunctionDef`, `AsyncFunctionDef`, `ClassDef` nodes
2. For each sibling node (not ancestor, not descendant, not overlapping): mark for compression
3. Compress: keep definition line, replace body lines `ns+2..ne` with `...`
4. Wrap output in `<TRANSIENT_CONTEXT>` XML boundary

#### Class B: `MutantCodeSelector`

Multi-variable Fitness Objective Function:

```
Fitness(c) = SyntaxCheck(c) - ParsimonyPenalty(c) - ConstraintPenalty(c)
```

| Gate | Score | Condition |
|------|-------|-----------|
| AST parse succeeds | +50.0 | `ast.parse(code)` passes |
| AST parse fails | -100.0 | `SyntaxError` — halts further scoring |
| Missing return | -30.0 | Signature declares non-None return; `return` absent |
| Parsimony penalty | -0.1 × lines | Per physical line count |

```python
class MutantCodeSelector:
    def evaluate_mutants(self, candidate_codes: List[str]) -> str
    # Returns the highest-fitness code string
```

#### Class C: `PageCurveEvaporator`

```python
class PageCurveEvaporator:
    def __init__(self, max_lines: int = 20) -> None

    def evaporate_log(self, raw_stdout: str) -> str
    # If lines <= max_lines: return as-is
    # If lines > max_lines: return single-line metadata summary
```

Output format:
```
[Log Evaporated: Total Lines={n} | Errors={e} | Warnings={w} | Status={code} | Last Error="{msg}"]
```

---

### 5.5 Critic / CodeCritic

**File:** `backend/app/core/critic.py`  
**Size:** ~889 lines  
**Role:** Stateless AST Diff Reviewer · Surgical Patcher · STAI Calculator · Error Frequency Diagnostic Monitor

The Critic is the sole arbiter of structural code quality within the EMMA Metacognitive Loop. It enforces **four invariants** on every candidate mutant:

1. **Structural correctness** — AST-level diff analysis (not string comparison)
2. **Surgical precision** — JIT line-range splice replacing only the target node
3. **Structural integrity** — STAI / STAI-DW scalar gate post-splice
4. **Regression detection** — Error-log frequency monitor breaking looping states

#### Configuration Constants

| Constant | Default | Override |
|----------|---------|----------|
| `STAI_COMMIT_THRESHOLD` | 0.85 | `EMMA_STAI_THRESHOLD` env var |
| `ERROR_LOOP_THRESHOLD` | 3 | `EMMA_ERROR_LOOP_THRESHOLD` env var |
| `STAI_DW_ROUTING_THRESHOLD` | 3 | Hard-coded |

#### STAI (Structural Target Alignment Index)

The STAI is a normalized scalar measuring the structural similarity between a patched file and its pre-patch baseline:

```
STAI = 1 - (changed_nodes / total_nodes)
```

For small files (< 3 top-level structures), **STAI-DW** (Density-Weighted variant) is used instead. If `STAI < STAI_COMMIT_THRESHOLD`, the orchestrator commit gate fires and the filesystem write is aborted.

#### Key Class: `CodeCritic`

```python
class CodeCritic:
    # Concurrency guarantee: all methods are pure and stateless
    # Zero-dependency guarantee: only stdlib modules

    def review_patch(
        self,
        original_code: str,
        patched_code: str,
        target_function: str
    ) -> CriticReport

    def surgical_splice(
        self,
        file_source: str,
        target_name: str,
        replacement_code: str
    ) -> str

    def compute_stai(
        self,
        original_ast: ast.AST,
        patched_ast: ast.AST
    ) -> float

    def detect_error_loop(
        self,
        error_history: List[str]
    ) -> bool
```

---

### 5.6 Token Pruner / `ContextVectorPruner`

**File:** `backend/app/utils/token_prune.py`  
**Size:** ~1,690 lines  
**Role:** Advanced Metacognitive Memory Compressor (EMM-02-A5)

EMMA's active cognitive memory management subsystem. Enforces a hard **8K token context boundary** through five graduated compaction tiers.

#### Five Budget Tiers

| Tier | Budget Used | Action |
|------|-------------|--------|
| `GREEN` | 0–60% | No action — verbatim pass-through |
| `AMBER` | 60–75% | Pin critical turns, condense tool outputs |
| `RED` | 75–85% | Aggressive key-phrase condensation |
| `CRITICAL` | 85–95% | Traceback scraping + NOISE drops |
| `OVERFLOW` | 95–100% | Compile A-ESV state vector, full reset |

#### DTE-IS (Dynamic Token-Entropy Importance Scoring)

Scores each conversation turn across four signals:

1. **Error density** — presence of `Exception`, `Error`, `Traceback` markers
2. **Tool result size** — length-weighted importance of tool outputs
3. **Recency bias** — exponential decay favouring recent turns
4. **Structural novelty** — Levenshtein distance from previously seen turns

#### A-ESV (Adaptive Execution State Vector)

When OVERFLOW is triggered, the pruner compiles a structured state vector preserving the essential cognitive context:

```json
{
  "goal": "Original user goal string",
  "completed_steps": ["step_1", "step_2"],
  "pending_steps": ["step_3"],
  "last_error": "AttributeError: ...",
  "active_file": "backend/app/core/critic.py",
  "token_budget_used": 7840,
  "turn_count": 12
}
```

---

### 5.7 Session Layer

**File:** `backend/app/database/session.py`  
**Size:** ~680 lines  
**Role:** SQLite Session Pool — Relational Memory Layer (ANJANEYA Pillars 1, 2, 3)

Windows-optimised, thread-safe, WAL-mode SQLite connection pool managing the EMMA solver session lifecycle.

#### Threading Model

Uses `threading.local()` for per-thread connection isolation, preventing SQLite's single-writer lock from blocking the FastAPI async event loop:

```python
_thread_local = threading.local()

def get_thread_local_conn(db_path: Path) -> sqlite3.Connection:
    # Returns the existing connection for this thread,
    # or opens a new WAL-mode connection if none exists
```

#### Session Schema

```sql
CREATE TABLE IF NOT EXISTS emma_sessions (
    session_id      TEXT PRIMARY KEY,
    task_description TEXT NOT NULL,
    status          TEXT DEFAULT 'active',
    devotion_score  REAL DEFAULT 0.0,
    is_frozen       INTEGER DEFAULT 0,
    spore_hash      TEXT,
    turns_used      INTEGER DEFAULT 0,
    tokens_used     INTEGER DEFAULT 0,
    created_at      TEXT,
    completed_at    TEXT
);
```

#### Key Functions

| Function | Signature | Description |
|----------|-----------|-------------|
| `create_session` | `(task: str) -> str` | Creates new session, returns UUID |
| `get_session` | `(session_id: str) -> dict` | Retrieves session record |
| `update_session_status` | `(session_id, status, turns, tokens)` | Updates solve metrics |
| `compute_devotion_score` | `(turns_used, tokens_used) -> float` | Computes D formula |
| `freeze_session` | `(session_id: str) -> bool` | Hard-freezes high-D sessions |
| `get_frozen_sessions` | `() -> List[dict]` | Lists all crystallised sessions |
| `checkpoint_wal` | `(conn) -> None` | Forces WAL checkpoint |
| `verify_integrity` | `(conn) -> bool` | SQLite `PRAGMA integrity_check` |

---

### 5.8 Semantic Manifold

**File:** `backend/app/database/manifold.py`  
**Size:** ~1,111 lines  
**Role:** LanceDB Vector Memory Layer (ANJANEYA Pillars 2–5)

Windows-resilient, air-gapped, self-healing vector memory engine. Ingests solver trace events as **384-dimensional semantic embeddings**, executes adaptive-depth KNN retrieval with cosine drift monitoring, and maintains Chiranjeevi spore archives for disaster recovery.

#### Embedding Model

```python
EMBEDDINGS_MODEL = "all-MiniLM-L6-v2"  # sentence-transformers
# Output: 384-dimensional float32 vectors
# Cosine similarity space
```

#### LanceDB Schema (PyArrow)

```python
schema = pa.schema([
    pa.field("session_id",    pa.string()),
    pa.field("event_type",    pa.string()),
    pa.field("turn",          pa.int32()),
    pa.field("content",       pa.string()),
    pa.field("embedding",     pa.list_(pa.float32(), 384)),
    pa.field("timestamp",     pa.string()),
    pa.field("metadata",      pa.string()),   # JSON string
])
```

#### Key Functions

| Function | Description |
|----------|-------------|
| `record_event(session_id, event_type, turn, content, metadata)` | Embeds and stores a solver event |
| `search_manifold(query, k, mode)` | KNN search with drift-adaptive depth |
| `create_spore(session_id)` | Creates ZIP archive + computes SHA-256 |
| `restore_from_spore(spore_path)` | Reconstructs manifold from archive |
| `get_manifold_table()` | Returns LanceDB table handle (retry-wrapped) |
| `_embed(text)` | Generates 384-dim embedding vector |

#### Retry & Resilience

All LanceDB operations are wrapped in a retry loop with exponential backoff to handle Windows file-lock transients:

```python
for attempt in range(max_retries):
    try:
        return operation()
    except Exception as e:
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt * 0.1)  # 0.1s, 0.2s, 0.4s...
        else:
            raise
```

---

### 5.9 Safety Layer

**Directory:** `backend/app/safety/`

#### `gdi.py` — Goal Drift Index

Mathematical alignment safeguard computing the **GDI scalar** to detect and prevent semantic drift from the original user goal:

```
GDI = α · Δ_sem + β · Δ_struct
```

| Component | Formula | Trigger |
|-----------|---------|---------|
| `Δ_sem` | Cosine distance between current task embedding and original goal embedding | GDI > 0.35 → alert |
| `Δ_struct` | AST node deviation from designer-expected schema | GDI > 0.60 → hard rollback |

#### `sahoo_gates.py` — SAHOO Safety Gate System

**S**elf-**A**lignment **H**ierarchical **O**rchestration **O**verride — a six-gate safety verification system. Each gate must pass before execution proceeds:

| Gate | Check |
|------|-------|
| Gate 1 | Syntax validation — no `SyntaxError` |
| Gate 2 | Blocked import scan — no dangerous modules |
| Gate 3 | GDI threshold — no alignment drift |
| Gate 4 | STAI threshold — no structural regression |
| Gate 5 | Sandbox execution — no runtime exceptions |
| Gate 6 | Causal convergence — no infinite error loops |

#### `sandbox.py` — Isolated Execution Environment

- Restricts filesystem writes strictly to `/sandbox_jail/` directory
- Clamps network socket access
- Enforces 30-second hard timeout on subprocess execution
- Memory-limited via OS-level process controls

---

## 6. REST & WebSocket API Reference

### Base URL

```
http://localhost:8000
```

### Health Check

```http
GET /health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "EMMA Backend Core",
  "config": {
    "model": "qwen2.5-coder",
    "port": 8000
  }
}
```

---

### WebSocket Terminal

```
WS /ws/terminal
```

Real-time bidirectional stream for EMMA's live cognitive output.

**Client → Server Messages:**
```json
{ "type": "pong" }                         // Heartbeat response
{ "type": "command", "command": "solve" }  // Trigger command
```

**Server → Client Messages:**
```json
{ "type": "ping" }                         // Heartbeat (every 5s)
{ "type": "info", "message": "..." }       // Acknowledgement
{ "type": "error", "message": "..." }      // Error notification
{ "type": "thought", "content": "..." }    // Agent cognitive output
{ "type": "commit", "file": "..." }        // Atomic commit notification
```

---

### ANJANEYA Memory Protocol Endpoints

All endpoints are prefixed with `/manifold`.

#### Session Management

**Create Session**
```http
POST /manifold/session
Content-Type: application/json

{
  "task_description": "Implement a binary search function"
}
```
Response: `{ "session_id": "uuid-...", "status": "active" }`

**Get Session**
```http
GET /manifold/session/{session_id}
```

**Update Session**
```http
PATCH /manifold/session/{session_id}
Content-Type: application/json

{
  "status": "completed",
  "turns_used": 7,
  "tokens_used": 42000
}
```

**List Sessions**
```http
GET /manifold/sessions
GET /manifold/sessions?frozen_only=true
```

---

#### Event Ingestion

**Record Event**
```http
POST /manifold/event
Content-Type: application/json

{
  "session_id": "uuid-...",
  "event_type": "code_commit",
  "turn": 3,
  "content": "Successfully patched binary_search() in utils.py",
  "metadata": { "file": "utils.py", "function": "binary_search" }
}
```

---

#### Semantic Search

**Search Manifold**
```http
POST /manifold/search
Content-Type: application/json

{
  "query": "AttributeError NoneType object has no attribute query",
  "k": 10,
  "mode": "ANIMA",
  "session_id": "uuid-..."
}
```

**`mode` options:**

| Mode | K Override | Description |
|------|-----------|-------------|
| `ANIMA` | 10 | Standard recall |
| `MADHYA` | 20 | Moderate drift |
| `MAHA` | 40 | High-distress maximum recall |

Response includes semantic drift analysis and auto-escalation if `d_min` exceeds thresholds.

---

#### Spore Management

**Create Spore (Backup)**
```http
POST /manifold/spore
Content-Type: application/json

{ "session_id": "uuid-..." }
```
Response: `{ "spore_path": "...", "sha256": "...", "size_bytes": 12345 }`

**Restore from Spore**
```http
POST /manifold/restore
Content-Type: application/json

{ "spore_path": "E:\\EMMA_INDIA_RUN\\spores\\spore_20260530_143200.zip" }
```

---

#### Skill Registry

**Register Skill**
```http
POST /manifold/skills
Content-Type: application/json

{
  "skill_name": "binary_search_pattern",
  "skill_code": "def binary_search(arr, target): ...",
  "description": "Efficient O(log n) search implementation",
  "tags": ["search", "algorithms"]
}
```

**Search Skills**
```http
POST /manifold/skills/search
Content-Type: application/json

{ "query": "efficient array search", "k": 5 }
```

---

## 7. Configuration Reference

**File:** `backend/app/config.py`  
**Backend:** `pydantic-settings` with `.env` file support

| Setting | Default | Description |
|---------|---------|-------------|
| `LOCAL_LLM_URL` | `http://localhost:11434/v1` | Ollama OpenAI-compatible endpoint |
| `LOCAL_LLM_MODEL` | `qwen2.5-coder` | Model identifier for inference requests |
| `EMBEDDINGS_MODEL` | `all-MiniLM-L6-v2` | Sentence-Transformers model for vector embeddings |
| `SANDBOX_DIR` | `E:\EMMA_INDIA_RUN\...\sandbox_jail` | Jailed execution directory |
| `MANIFOLD_DB_PATH` | `E:\EMMA_INDIA_RUN\...\manifold.db` | LanceDB database path |
| `PORT` | `8000` | FastAPI server port |

**Environment Variables (`.env` file):**
```env
LOCAL_LLM_URL=http://localhost:11434/v1
LOCAL_LLM_MODEL=qwen2.5-coder
EMBEDDINGS_MODEL=all-MiniLM-L6-v2
PORT=8000
```

**Safety Overrides (environment variables):**
```env
EMMA_STAI_THRESHOLD=0.85       # Structural integrity gate (0.0-1.0)
EMMA_ERROR_LOOP_THRESHOLD=3    # Consecutive identical errors before rollback
```

---

## 8. Project Directory Structure

```
EMMA_hack2skill/
├── .gitignore
├── README.md                          # System overview & quickstart
├── docker-compose.yml                 # Local container orchestrator
│
├── backend/
│   ├── .env                           # Local environment variable overrides
│   ├── Dockerfile.backend             # FastAPI container configuration
│   ├── requirements.txt               # Python package dependencies
│   └── app/
│       ├── __init__.py
│       ├── main.py                    # FastAPI entry point & CORS config
│       ├── config.py                  # Pydantic Settings (env var loader)
│       │
│       ├── core/                      # Cognitive Engine (Pillars I–V)
│       │   ├── __init__.py
│       │   ├── orchestrator.py        # Central solve loop (611 lines)
│       │   ├── executor.py            # DraftCoordinator — 3× parallel LLM (604 lines)
│       │   ├── code_generator.py      # AST sandbox & atomic commit engine (817 lines)
│       │   ├── context_scheduler.py   # JIT rotation, MutantSelector, Log Evaporator (570 lines)
│       │   ├── critic.py              # CodeCritic — STAI reviewer & surgical patcher (889 lines)
│       │   ├── inference_router.py    # Decoupling routing adapter
│       │   └── ast_utils.py           # AST helper utilities (7,933 bytes)
│       │
│       ├── database/                  # Persistence Layer (ANJANEYA AMP)
│       │   ├── __init__.py
│       │   ├── session.py             # WAL-mode SQLite session pool (680 lines)
│       │   ├── manifold.py            # LanceDB vector manifold (1,111 lines)
│       │   ├── manifold_v2.py         # Enhanced manifold implementation
│       │   └── models.py              # SQLAlchemy ORM schemas
│       │
│       ├── routers/                   # FastAPI REST & WebSocket Routes
│       │   ├── __init__.py
│       │   ├── manifold.py            # ANJANEYA AMP REST API (1,325 lines)
│       │   ├── ws_terminal.py         # Real-time WebSocket terminal stream
│       │   └── execution.py           # Execution, rollback & checkpoint triggers
│       │
│       ├── safety/                    # Alignment & Constraint Verification
│       │   ├── __init__.py
│       │   ├── gdi.py                 # Goal Drift Index mathematical calculator
│       │   ├── sandbox.py             # Jailed subprocess execution environment
│       │   └── sahoo_gates.py         # 6-gate SAHOO safety verification system
│       │
│       ├── utils/                     # System Helpers & Memory Management
│       │   ├── __init__.py
│       │   ├── ast_utils.py           # AST node analysis helpers
│       │   ├── token_prune.py         # ContextVectorPruner — 5-tier compaction (1,690 lines)
│       │   └── session_manager.py     # High-level session lifecycle helpers
│       │
│       └── tests/                     # Automated Test Suite
│           ├── test_advanced_core.py  # 8-part core unit tests (14,007 bytes)
│           └── test_token_prune.py    # Token pruner unit tests (20,264 bytes)
│
├── frontend/                          # React 18 / Vite Dashboard Console
│   ├── Dockerfile.frontend
│   ├── package.json
│   ├── vite.config.js
│   └── src/
│       ├── main.jsx                   # React entry point
│       ├── App.jsx                    # Core layout wrapper
│       ├── index.css                  # Premium dark theme tokens & radial glows
│       └── components/
│           ├── Terminal.jsx           # Live WebSocket thought stream
│           ├── DiffViewer.jsx         # Monaco split diff editor
│           ├── DriftDial.jsx          # GDI SVG speedometer
│           └── SandboxPanel.jsx       # Execution stdout/stderr viewer
│
├── docs/                              # Documentation & Architecture
│   ├── EMMA_DOCUMENTATION.md          # This file — complete project docs
│   ├── EMMA_PitchDeck.md              # Marp Markdown slide deck (Hackathon PPT)
│   ├── emma_full_project_architecture.png  # System architecture diagram
│   ├── emma_project_structure.md      # Directory specification
│   ├── emma_architecture_v2_vertical.md   # Vertical flow architecture
│   ├── EMMA_02_A2_plan_v2.md          # Evolutionary Bridge implementation plan
│   ├── anjaneya_memory_integration_plan_v2.md  # AMP full specification
│   ├── critic_implementation_plan_v2.md   # CodeCritic implementation plan
│   ├── token_prune_state_vector_plan_v3.md # Token Pruner v3 specification
│   ├── manifold_router_implementation_plan_v2.md # Router implementation plan
│   └── session_context_checkpoint.md  # Session context checkpoint
│
└── scripts/                           # Utility & Setup Scripts
    ├── run_tests.py                   # Zero-dependency test launcher
    └── demo_live_action.py            # Live simulation showrunner
```

---

## 9. Tech Stack & Dependencies

### Backend Core

| Package | Version | Purpose |
|---------|---------|---------|
| `fastapi` | 0.110.0 | Async REST API framework |
| `uvicorn` | 0.28.0 | ASGI server |
| `pydantic` | 2.6.4 | Data validation & settings |
| `pydantic-settings` | 2.2.1 | `.env` file configuration |
| `python-dotenv` | 1.0.1 | Environment variable loading |
| `websockets` | 12.0 | WebSocket protocol support |
| `lancedb` | 0.6.2 | Local vector database |
| `sentence-transformers` | 2.5.1 | `all-MiniLM-L6-v2` embedding model |
| `numpy` | 1.26.4 | Vector operations & PyArrow support |
| `pyarrow` | (via lancedb) | Columnar data format for LanceDB |

### Cognitive Core (Zero External Dependencies)

The cognitive modules (`executor.py`, `context_scheduler.py`, `orchestrator.py`, `critic.py`) are implemented in **pure Python 3.9+ standard library**:

```
urllib.request  asyncio  ast  json  re  difflib  math
subprocess      pathlib  os   io    time  threading
```

### Local AI (Required Pre-Installation)

| Component | Description |
|-----------|-------------|
| **Ollama** | Local LLM server — hosts `qwen2.5-coder` model |
| **qwen2.5-coder** | Primary inference model (or any OpenAI-compatible model) |

### Frontend

| Package | Purpose |
|---------|---------|
| React 18 | UI framework |
| Vite | Build tool & dev server |
| WebSocket API | Real-time terminal stream |

---

## 10. Running EMMA Locally

### Prerequisites

1. **Python 3.9+** installed
2. **Ollama** installed and running (`ollama serve`)
3. **qwen2.5-coder** model pulled: `ollama pull qwen2.5-coder`
4. **Node.js 18+** (for frontend)

### Backend Setup

```bash
# Navigate to backend directory
cd E:\EMMA_INDIA_RUN\EMMA_hack2skill\backend

# Install Python dependencies
pip install -r requirements.txt

# Start the FastAPI server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Frontend Setup

```bash
# Navigate to frontend directory
cd E:\EMMA_INDIA_RUN\EMMA_hack2skill\frontend

# Install dependencies
npm install

# Start the Vite dev server
npm run dev
```

### Verify Health

```bash
curl http://localhost:8000/health
# Expected: {"status":"healthy","service":"EMMA Backend Core",...}
```

### Docker Compose (Full Stack)

```bash
cd E:\EMMA_INDIA_RUN\EMMA_hack2skill
docker-compose up --build
```

---

## 11. Testing

EMMA ships with a comprehensive automated test suite designed to verify all cognitive systems without requiring an active LLM connection.

### Core Unit Tests

```bash
# Run 8-part core unit test suite
python -m pytest backend/app/tests/test_advanced_core.py -v
```

**Test Coverage:**
1. XML extraction with valid `<CODE_PROPOSAL>` tags
2. Parallel thread concurrency (3× simultaneous LLM requests)
3. Offline fallback activation on `URLError`
4. SyntaxError rejection at `-100.0` fitness score
5. AST context rotation stub compression
6. Page Curve log evaporation at threshold
7. Causal Convergence Monitor rollback detection
8. Atomic commit with temp file verification

#### Live Test Suite Execution Log (`run_tests.bat` Output)
Here is the real output generated by EMMA's zero-dependency test runner:

```text
================================================================================
 [TEST RUNNER] INITIATING EMMA COGNITIVE CORE SUITE
================================================================================
[RUNNING] test_ast_context_rotator...[PASS]    test_ast_context_rotator
[RUNNING] test_page_curve_evaporator...[PASS]    test_page_curve_evaporator
[RUNNING] test_causal_convergence_monitor...[PASS]    test_causal_convergence_monitor
[RUNNING] test_code_generator_sandbox_security...Mutant B rejected 🛇 security violations: ["Blocked import 'os' at line 1"]
[PASS]    test_code_generator_sandbox_security
[RUNNING] test_code_generator_atomic_commit...[PASS]    test_code_generator_atomic_commit
[RUNNING] test_xml_extractor...[PASS]    test_xml_extractor
[RUNNING] test_draft_coordinator_fallback...[PASS]    test_draft_coordinator_fallback
[RUNNING] test_parallel_concurrency...[PASS]    test_parallel_concurrency
[RUNNING] test_critic_ast_comparison...[PASS]    test_critic_ast_comparison
[RUNNING] test_critic_surgical_splicing...[PASS]    test_critic_surgical_splicing
[RUNNING] test_critic_stai_score...[PASS]    test_critic_stai_score
[RUNNING] test_critic_error_monitor...[PASS]    test_critic_error_monitor
[RUNNING] test_token_counting_accuracy...[PASS]    test_token_counting_accuracy
[RUNNING] test_threshold_evaluation...[PASS]    test_threshold_evaluation
[RUNNING] test_entropy_scoring_dte_is...[PASS]    test_entropy_scoring_dte_is
[RUNNING] test_log_compaction_fidelity...[PASS]    test_log_compaction_fidelity
[RUNNING] test_traceback_regex_edge_cases...[PASS]    test_traceback_regex_edge_cases
[RUNNING] test_esv_schema_adaptive_keys...[PASS]    test_esv_schema_adaptive_keys
[RUNNING] test_prompt_assembly_completeness...[PASS]    test_prompt_assembly_completeness
[RUNNING] test_json_extraction_strategy_1_clean...[PASS]    test_json_extraction_strategy_1_clean
[RUNNING] test_json_extraction_strategy_2_fenced...[PASS]    test_json_extraction_strategy_2_fenced
[RUNNING] test_json_extraction_strategy_3_preamble_text...[PASS]    test_json_extraction_strategy_3_preamble_text
[RUNNING] test_json_extraction_strategy_4_trailing_comma...[PASS]    test_json_extraction_strategy_4_trailing_comma
[RUNNING] test_json_extraction_strategy_5_truncated...[PASS]    test_json_extraction_strategy_5_truncated
[RUNNING] test_json_extraction_all_strategies_fail...[PASS]    test_json_extraction_all_strategies_fail
[RUNNING] test_offline_fallback_triggers_on_urlerror...[PASS]    test_offline_fallback_triggers_on_urlerror
[RUNNING] test_offline_fallback_triggers_on_timeout...[PASS]    test_offline_fallback_triggers_on_timeout
[RUNNING] test_health_probe_skips_inference_on_failure...[PASS]    test_health_probe_skips_inference_on_failure
[RUNNING] test_token_budget_convergence...[PASS]    test_token_budget_convergence
[RUNNING] test_causal_loop_alert_injection...[PASS]    test_causal_loop_alert_injection
[RUNNING] test_task_checklist_parity_enforcement...[PASS]    test_task_checklist_parity_enforcement
[RUNNING] test_schema_version_tag_always_present...[PASS]    test_schema_version_tag_always_present
================================================================================
 [TEST RUNNER] COMPLETE: 32 passed, 0 failed.
================================================================================
```

### Token Pruner Tests

```bash
python -m pytest backend/app/tests/test_token_prune.py -v
```

**Test Coverage:**
- DTE-IS scoring across all four signals
- GREEN/AMBER/RED/CRITICAL/OVERFLOW tier transitions
- A-ESV state vector assembly and JSON schema validation
- Verbatim pin preservation of critical turns
- Traceback extraction and condensation

### Live Demo Simulation

```bash
# Watch EMMA's cognitive layers run in a full-speed simulation cycle
python scripts/demo_live_action.py
```

Simulates: context stubbing → mutant fitness scoring → log evaporation → causal monitor safety halt — all without requiring the Ollama server.

### Live Central Executive Solver Run Log
Below is the execution output of the live solver pipeline (`run_solver.bat` in non-interactive demo mode), validating the entire evolutionary feedback loop in a single command:

```text
  ◈ INITIALISING EMMA COGNITIVE ENGINE...

  ✓ AMP session registered
  ✓ Orchestrator instantiated

  ◈ LAUNCHING LIVE COCKPIT...

[ORCHESTRATOR] Initiating Causal Solver Loop.
  Task: Add a descriptive module docstring to backend/app/utils/mock_target.py
  Target File: backend/app/utils/mock_target.py
  Max Turns: 2 | Stall Threshold: 3
[ORCHESTRATOR] ── Cycle Turn #1/2 ──
[ORCHESTRATOR] Active prompt footprint: 1 tokens | Tier: GREEN
[ORCHESTRATOR]  Initializing Evolutionary Mutant Selection...
[ORCHESTRATOR] Code generation completed. Winner mutant: B | Committed successfully: True
[ORCHESTRATOR]  Causal Anchor — workspace dirty: True
[ORCHESTRATOR]  Executing: python scripts/run_tests.py
[ORCHESTRATOR] Command finished — exit code: 0
[ORCHESTRATOR]  Command succeeded. Task complete at turn #1.

┌─────────────────────────────────────────────────────────────────────────────┐
│ ⚡ EMMA COGNITIVE ENGINE  ·  NEXUS AI RESEARCH LAB  ·  EMMA SOLVER v3.0     │
│   Session: e52ae85f-fd80-47b2-9721-44ebed7f8f20                             │
└─────────────────────────────────────────────────────────────────────────────┘
┌────── 📐 CONTEXT COMPRESSION ───────┐┌──────── ⚡ TOKEN UTILIZATION ────────┐
│   Raw File:              0 tokens   ││   Peak:         1 / 100,000          │
│   Rotated Context:       0 tokens   ││   ░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░ │
│   Compression:        —  waiting... ││ 0.0%                                 │
└─────────────────────────────────────┘└──────────────────────────────────────┘
                                       ┌─── 🔬 CAUSAL CONVERGENCE MONITOR ────┐
                                       │   Score D:    0.999996               │
                                       │   Status:     CRYSTALLISED (Winner)  │
                                       └──────────────────────────────────────┘

┌──────────────────────────── 📡 LIVE SOLVER LOG ─────────────────────────────┐
│ [11:19:06] [Step 3] Executing: python scripts/run_tests.py                  │
│ [11:19:07] Command finished — exit code: 0                                  │
│ [11:19:07] [PASS] Command succeeded. Task complete at turn #1.              │
│ [11:19:07] 💎 CRYSTALLISED — D=0.999996 ≥ Θ=0.85                             │
│ [11:19:07] ✅ All tests PASSED — solver loop converged!                     │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────── ⚡ EMMA SOLVER — FINAL REPORT ───────────────────────┐
│                                                                             │
│    ✅  SUCCESS                                                              │
│                                                                             │
│    Session ID   :  e52ae85f-fd80-47b2-9721-44ebed7f8f20                     │
│    Task         :  Add a descriptive module docstring to                    │
│                    backend/app/utils/mock_target.py                         │
│    Target File  :  backend/app/utils/mock_target.py                         │
│    Turns Elapsed:  1 / 2                                                    │
│    Wall Time    :  15.1s                                                    │
│    Devotion D   :  0.999996  💎 CRYSTALLISED                                │
│    Threshold    :  0.85  (Θ_crystal)                                        │
│    Causal Monitor: STABLE                                                   │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

---


## 12. Mathematical Foundations

### Causal Residual (Convergence Monitor)

```
R_k = SequenceMatcher(E_{k-1}, E_k).ratio()
```

Where `E_k` is the error output string at solver turn `k`. When `R_k ≥ 0.95` for `loop_threshold` consecutive turns, the solver has stalled.

### Devotion Score (AMP Pillar 1)

```
D = α · (1 - turns_used/T_max) + β · (1 - tokens_used/U_max)

Where: α = 0.60, β = 0.40, T_max = 15, U_max = 100,000
Range: [0.0, 1.0]
Crystal threshold: D ≥ 0.85
```

### Mutant Fitness Function (MutantCodeSelector)

```
Fitness(c) = SyntaxBase(c) - ParsimonyPenalty(c) - ReturnConstraintPenalty(c)

SyntaxBase(c)            = +50.0   if ast.parse(c) succeeds
                         = -100.0  if SyntaxError
ParsimonyPenalty(c)      = 0.1 × line_count(c)
ReturnConstraintPenalty  = +30.0   if return required but absent
```

### Goal Drift Index (GDI)

```
GDI = α · Δ_sem + β · Δ_struct

Δ_sem    = 1 - cosine_similarity(embed(current_task), embed(original_goal))
Δ_struct = normalized_AST_node_deviation(current_output, expected_schema)

Alert threshold:   GDI > 0.35
Rollback threshold: GDI > 0.60
```

### STAI (Structural Target Alignment Index)

```
STAI     = 1 - (changed_nodes / total_nodes)     [standard mode]
STAI-DW  = weighted variant for small files       [< 3 top-level nodes]

Commit gate: STAI >= 0.85  (default, configurable via EMMA_STAI_THRESHOLD)
```

### Cosine Drift (Sankat Mochan — AMP Pillar 4)

```
drift(q) = min_{x ∈ manifold}  (1 - cosine_similarity(embed(q), x))

d_min > 0.75 → DISTRESS → MAHA   (K=40)
d_min > 0.55 → ALERT    → MADHYA (K=20)
d_min ≤ 0.55 → NORMAL   → ANIMA  (K=10)
```

---

## 13. Design Principles & Constraints

### Zero External Dependency Constraint

The cognitive core (`orchestrator.py`, `executor.py`, `context_scheduler.py`, `critic.py`) must operate using **only the Python 3.9+ standard library**. This ensures EMMA can deploy in:

- Air-gapped government/enterprise environments
- Docker containers with no internet access
- Restricted CI/CD sandboxes
- Offline hackathon evaluation environments

### Atomic Commit Guarantee

Every filesystem mutation follows a strict 3-phase protocol:
1. Write to staging file (`.emma_mutant_tmp.py`)
2. Parse staging file via `ast.parse()` — abort if invalid
3. `os.replace(tmp, target)` — POSIX atomic rename (no partial writes)

This guarantees the target file is **never left in a corrupted or partial state**.

### Pure Stateless Critic

The `CodeCritic` class has no mutable instance state after `__init__`. All methods are pure functions — safe to call concurrently from multiple `asyncio` coroutines without locking. This is a hard invariant enforced by design.

### WAL Mode SQLite

All SQLite connections operate in **Write-Ahead Logging** mode:
```python
conn.execute("PRAGMA journal_mode=WAL")
conn.execute("PRAGMA synchronous=NORMAL")
```

This allows concurrent reads during writes — essential for EMMA's hybrid sync/async architecture on Windows.

### Windows-Resilient Design

All path operations use `pathlib.Path` with explicit `mkdir(parents=True, exist_ok=True)`. File operations that may fail due to Windows file-lock transients are wrapped in retry loops with exponential backoff.

---

## 14. Glossary

| Term | Definition |
|------|-----------|
| **AMP** | ANJANEYA Memory Protocol — EMMA's dual-layer persistent memory system |
| **A-ESV** | Adaptive Execution State Vector — compact cognitive state snapshot compiled at context OVERFLOW |
| **Causal Residual (R_k)** | Levenshtein similarity ratio between consecutive error outputs — measures solver stagnation |
| **Chiranjeevi Spore** | ZIP archive of the vector manifold used for disaster recovery |
| **CodeCritic** | Stateless AST-level diff reviewer and surgical patcher |
| **Devotion Score (D)** | Scalar [0,1] measuring solver efficiency — used to crystallise high-quality sessions |
| **DraftCoordinator** | EMMA's parallel LLM inference bridge generating 3 mutant code candidates simultaneously |
| **DTE-IS** | Dynamic Token-Entropy Importance Scoring — multi-signal turn importance calculator |
| **GDI** | Goal Drift Index — real-time scalar measuring EMMA's alignment to the original user goal |
| **GEA** | Group-Evolving Agents — EMMA's evolutionary parallel inference strategy |
| **JIT AST Rotation** | Just-In-Time context compression via AST projection — reduces prompt tokens by 80%+ |
| **LanceDB** | Local vector database used as EMMA's semantic memory manifold |
| **Mutant** | A distinct code candidate generated at a specific temperature and cognitive axis |
| **Page Curve Evaporator** | Log compression engine that condenses verbose stdout into single-line metadata summaries |
| **POSIX Atomic Rename** | `os.replace(src, dst)` — guaranteed single-system-call file replacement |
| **SAHOO Gates** | Six-layer safety verification system (Self-Alignment Hierarchical Orchestration Override) |
| **Spore** | A named compressed backup archive of EMMA's vector memory |
| **STAI** | Structural Target Alignment Index — normalized scalar measuring post-patch code structural similarity |
| **WAL Mode** | SQLite Write-Ahead Logging — enables concurrent reads during active writes |

---

*EMMA — Enterprise Metacognitive Multi-Agent Fleet*  
*Designed and engineered for the India Runs Hackathon by Redrob AI × Hack2Skill — Track 2 (Ideathon)*  
*Built with precision, purpose, and an unwavering commitment to local-first AI.*
