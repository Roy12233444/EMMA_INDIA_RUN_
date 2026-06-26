# EMMA: Enterprise Metacognitive Multi-Agent Fleet
## Project Directory Structure & Component Specification

This document maps the complete production-grade directory layout and component architecture for the **EMMA** system, spanning the FastAPI backend, React/Vite frontend console, sandbox execution framework, and local experience manifold.

---

```
EMMA_INDIA_RUN/
├── .github/                   # CI/CD Workflows & Issue Templates
│   └── workflows/
│       └── python-tests.yml   # Auto-run local sandbox & regression test suites
├── backend/                   # FastAPI Backend Service
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py            # FastAPI Entry Point (WebSocket + REST endpoints)
│   │   ├── config.py          # Environment variable loaders (Local Model URLs, DB Paths)
│   │   ├── core/              # Core Agentic & Cognitive Engine
│   │   │   ├── __init__.py
│   │   │   ├── orchestrator.py# Main loop, dynamic checklist tracker, JIT context manager
│   │   │   ├── planner.py     # Decomposes user goals into ordered task graphs
│   │   │   ├── executor.py    # Generates code drafts & coordinates tool actions
│   │   │   └── critic.py      # Stateless AST-level structural diff reviewer & patch generator
│   │   ├── database/          # Local Experience Manifold & Analytics Store
│   │   │   ├── __init__.py
│   │   │   ├── session.py     # DB Engine session handlers (SQLite3 + pgvector mapping)
│   │   │   ├── models.py      # SQL schemas (Trajectories, Diffs, GDI Logs, Compactions)
│   │   │   └── manifold.py    # Experience Manifold semantic search & indexing wrapper
│   │   ├── routers/           # REST API Route Definitions
│   │   │   ├── __init__.py
│   │   │   ├── ws_terminal.py # WebSocket router for live high-frequency thought stream
│   │   │   ├── execution.py   # Runs, rollbacks, overrides, and checkpoint triggers
│   │   │   └── manifold.py    # Manifold search queries, analytics, and metrics
│   │   ├── safety/            # Alignment & Constraint Verification (SAHOO)
│   │   │   ├── __init__.py
│   │   │   ├── gdi.py         # Goal Drift Index mathematical calculator (α·Δsem + β·Δstruct)
│   │   │   ├── sandbox.py     # Jailed Python subprocess runner (memory limiters, timeouts)
│   │   │   └── sahoo_gates.py # The 6-gate safety verifier & hierarchical rollback controller
│   │   └── utils/             # Core System Helpers
│   │       ├── __init__.py
│   │       ├── ast_utils.py   # Pinpoints failing code nodes via Python's AST parser
│   │       └── token_prune.py # Measures context usage, compiles Execution State Vectors
│   ├── requirements.txt       # Python dependencies (fastapi, uvicorn, lancedb, sentence-transformers, ast, pydantic)
│   └── Dockerfile.backend     # FastAPI container config (pre-installed Python environment)
│
├── frontend/                  # React 18 / Vite Frontend Console
│   ├── public/                # Static public assets (icons, brand marks)
│   ├── src/
│   │   ├── main.jsx           # React Entry Point
│   │   ├── App.jsx            # Core UI layout wrapper
│   │   ├── index.css          # Premium theme styling tokens, global resets, radial glows
│   │   ├── assets/            # UI images, svgs, fonts
│   │   ├── components/        # Reusable dashboard widgets
│   │   │   ├── Header.jsx     # Navigation, active workspace switcher, safety override toggle
│   │   │   ├── Terminal.jsx   # Live WebSocket-streamed terminal thought stream
│   │   │   ├── DiffViewer.jsx # Side-by-side Monaco split editor (initial draft vs. self-critique)
│   │   │   ├── DriftDial.jsx  # Interactive SVG speedometer rendering current GDI level
│   │   │   └── SandboxPanel.jsx# Sandbox terminal showing execution stdout/stderr and tests
│   │   ├── hooks/             # Custom React Hooks
│   │   │   ├── useWebSocket.js# Handles real-time terminal stream connection
│   │   │   └── useGDI.js      # Animates GDI dial transitions & snaps to checkpoints
│   │   └── utils/
│   │       └── theme.js       # Color tokens (Teal, Emerald, Amber, Slate, Coral)
│   ├── package.json           # NodeJS dependencies (react, vite, monaco-editor, tailwind/css, lucide-react)
│   ├── vite.config.js         # Vite configuration (path aliases, dev server port)
│   └── Dockerfile.frontend    # Frontend production build container (Nginx based)
│
├── scripts/                   # Local Utility & Setup Scripts
│   ├── setup_local_env.bat    # Windows script to check for Ollama/LM Studio local servers
│   ├── init_manifold_db.py    # Initializes the SQLite database & seeds baseline trajectories
│   └── run_regression_tests.py# Local test script simulating AST self-healing loops
│
├── docs/                      # Documentation & Pitch Artifacts
│   ├── emma_pitch_deck.md     # The Marp slide deck markdown source
│   ├── emma_title_slide.png   # Widescreen PPT Slide 1 image background
│   ├── emma_slide2_crisis.png # Widescreen PPT Slide 2 image background
│   ├── emma_slide3_reimagined.png # Widescreen PPT Slide 3 image background
│   └── emma_context_compaction_plan.md # Advanced Context Management specification
│
├── .gitignore
├── README.md                  # System overview, quickstart setup, CLI usage
└── docker-compose.yml         # Local container orchestrator (launches backend, DB, frontend)
```

---

## Component Specifications

### 1. `backend/app/core/orchestrator.py`
The nervous system of EMMA. It drives the main execution lifecycle:
1. Receives the user goal and starts the token monitor.
2. Invokes `planner.py` to draft the dynamic checklist.
3. Coordinates loop passes between `executor.py` (writes draft code), `sandbox.py` (executes code), and `critic.py` (audits failures).
4. Prunes context history via `token_prune.py` when threshold reaches 70%, resetting the agent state using the structured **Execution State Vector**.

### 2. `backend/app/safety/gdi.py`
The mathematical alignment safeguard. It computes a real-time scalar to prevent **Alignment Drift**:
*   **Semantic Drift ($\Delta_{\text{sem}}$):** Measures cosine distance between the embedding of the current planned task and the embedding of the original user prompt.
*   **Structural Drift ($\Delta_{\text{struct}}$):** Measures deviations in JSON schemas or AST node outputs from designer expectations.
*   **GDI Scalar:** $\text{GDI} = \alpha \cdot \Delta_{\text{sem}} + \beta \cdot \Delta_{\text{struct}}$. If $\text{GDI} > 0.35$, alerts are sent to the console; if $\text{GDI} > 0.60$, a hard rollback is sent to the Orchestrator to restore the last safe checkpoint.

### 3. `backend/app/safety/sandbox.py`
The execution isolation cell. Operates on standard Python `subprocess` configurations:
*   Limits execution RAM using Windows/Linux OS-level job limits.
*   Clamps network sockets and restricts filesystem writes strictly to a dedicated local `/sandbox_jail` directory.
*   Enforces a hard timeout limit of 30 seconds to catch infinite loops or runaway compute calls.

### 4. `frontend/src/components/DiffViewer.jsx`
The transparency engine. Built on a Microsoft **Monaco Editor Split Diff** component:
*   Left pane: Shows the initial code or config draft written by the Executor.
*   Right pane: Shows the self-critiqued, sandboxed-corrected code after a rollback iteration.
*   Highlights changed nodes and renders inline hover explanations detailing exactly *why* the Critic agent made specific code modifications.
