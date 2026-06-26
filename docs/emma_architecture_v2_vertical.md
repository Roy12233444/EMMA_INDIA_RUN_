# 🌌 EMMA COGNITIVE CORE — UPGRADED VERTICAL SIGNAL FLOW
### Classification: Production-Grade Architectural Specification v2.0
### File: E:\EMMA_INDIA_RUN\emma_architecture_v2_vertical.md

This document contains the complete, upgraded vertical system signal flow diagram for Task **EMM-02-A2**. It is optimized for vertical scrolling and full-screen readability.

---

## 🗺️ System Signal Flow Diagram

```mermaid
flowchart TD
    subgraph ORCHESTRATOR["🔁 Orchestrator Solve Cycle"]
        direction TB
        O1["orchestrator.py\nsolve loop turn N"]
        O2{"Exit Code > 0?"}
        O3["CausalConvergenceMonitor\nevaluate_step"]
        O4{"Paradox\nDetected?"}
        O5["git checkout -- .\nRollback Workspace"]
        O6["Raise CausalInstabilityException"]
        
        O1 --> O2
        O2 -->|Yes| O3
        O2 -->|No - PASS| SUCCESS(["✅ Return SUCCESS"])
        O3 --> O4
        O4 -->|Stable| O1
        O4 -->|Stalled R≥0.95 x3| O5
        O5 --> O6
    end

    subgraph CODEGEN["⚙️ Code Generator — executor.py"]
        direction TB
        C1["CodeGenerator\ngenerate_and_apply_patch"]
        C2["InferenceRouter\nrequest_mutants"]
        C3["DraftCoordinator\ngenerate_drafts"]
        C1 --> C2 --> C3
    end

    subgraph PARALLEL["⚡ asyncio.gather — Parallel Inference"]
        direction TB
        T1["asyncio.to_thread\n_sync_llm_call\nMutant A\ntemp=0.20"]
        T2["asyncio.to_thread\n_sync_llm_call\nMutant B\ntemp=0.70"]
        T3["asyncio.to_thread\n_sync_llm_call\nMutant C\ntemp=0.95"]
        C3 --> T1
        C3 --> T2
        C3 --> T3
    end

    subgraph LLM["🧠 Local AI — Ollama qwen2.5-coder"]
        direction TB
        L1["http://localhost:11434\n/v1/chat/completions"]
        T1 & T2 & T3 -->|urllib.request POST| L1
    end

    subgraph PROMPTS["✍️ Evolutionary Prompt Engineering"]
        direction TB
        P1["Mutant A\nParsimonious Architect\nMinimise lines\nDirect logic"]
        P2["Mutant B\nStructural Alternative\nAlt data structures\nHelper patterns"]
        P3["Mutant C\nCreative Decoupler\nHigh-entropy\nModular abstraction"]
        L1 -->|Raw response A| P1
        L1 -->|Raw response B| P2
        L1 -->|Raw response C| P3
    end

    subgraph XML["🛡️ XML Extraction Gate"]
        direction TB
        X1["XMLExtractor\n_extract_code_proposal\nregex: CODE_PROPOSAL"]
        X2{"Tags\nFound?"}
        X3["compile code exec\nSyntax Verification"]
        X4{"Syntax\nValid?"}
        XF["Fallback Mutant\nSimulation Mode\n+ Diagnostic Log"]
        P1 & P2 & P3 --> X1
        X1 --> X2
        X2 -->|No tags| XF
        X2 -->|Tags found| X3
        X3 --> X4
        X4 -->|SyntaxError| XF
        X4 -->|Clean| CLEAN(["Clean Python\nstring extracted"])
    end

    subgraph OFFLINE["🔌 Offline Fallback Mode"]
        direction TB
        OF1{"URLError /\nTimeoutError?"}
        OF2["Log: FALLBACK Mutant X\nReason: LLM unreachable\nSubstituting simulation"]
        OF3["Simulation Mutant\nA=valid B=valid C=invalid"]
        T1 & T2 & T3 -->|Exception?| OF1
        OF1 -->|Yes| OF2 --> OF3
        OF3 --> X1
    end

    subgraph SANDBOX["🔬 MutantCodeSelector — Fitness Scoring"]
        direction TB
        S1["Mutant A — Score computation\nBase +50 or -100\n- Length Penalty 0.1/line\n- Latency Penalty 5.0/sec\n+ Security Penalty -200/violation"]
        S2["Mutant B — Score computation"]
        S3["Mutant C — Score computation"]
        SW{"Winner\nSelection\nmax score > 0"}
        SR["REJECTED\nscore ≤ 0 or\nviolations"]
        CLEAN --> S1 & S2 & S3
        S1 & S2 & S3 --> SW
        SW -->|Loser| SR
    end

    subgraph COMMIT["💾 Atomic Filesystem Commit"]
        direction TB
        A1["_atomic_commit\nWrite to .emma_mutant_tmp.py"]
        A2["ast.parse verify\ntemp file"]
        A3{"Compile\nOK?"}
        A4["os.replace\ntarget_path ← tmp\nPOSIX atomic"]
        A5["CommitError raised\ntemp file unlinked\noriginal preserved"]
        SW -->|Winner| A1
        A1 --> A2 --> A3
        A3 -->|Yes| A4
        A3 -->|No| A5
        A4 --> O1
    end

    %% Flow link between main components
    O1 --> C1

    %% Sleek Cyber Style Palette
    style ORCHESTRATOR fill:#0f1b2d,stroke:#06b6d4,color:#f1f5f9
    style CODEGEN fill:#0f1b2d,stroke:#10b981,color:#f1f5f9
    style PARALLEL fill:#0f1b2d,stroke:#f59e0b,color:#f1f5f9
    style LLM fill:#0f1b2d,stroke:#8b5cf6,color:#f1f5f9
    style PROMPTS fill:#0f1b2d,stroke:#8b5cf6,color:#f1f5f9
    style XML fill:#0f1b2d,stroke:#06b6d4,color:#f1f5f9
    style OFFLINE fill:#0f1b2d,stroke:#f43f5e,color:#f1f5f9
    style SANDBOX fill:#0f1b2d,stroke:#10b981,color:#f1f5f9
    style COMMIT fill:#0f1b2d,stroke:#f59e0b,color:#f1f5f9
```

---

## 🔍 Subgraph Summaries

* **ORCHESTRATOR:** Monitors the run cycle and forces workspace rollback if paradox loops are encountered.
* **CODEGEN:** Gateway adapting raw generation queries into structured drafts.
* **PARALLEL & LLM:** Thread-safe parallel execution pipelines making concurrent requests to local Ollama endpoints.
* **PROMPTS:** Specific system templates mapped to low, medium, and high temperature variations.
* **XML & OFFLINE:** Extraction, parser, and error safety nets guaranteeing robust offline simulations.
* **SANDBOX:** Real-time scoring computations validating mutant viability.
* **COMMIT:** Atomic IO execution avoiding directory corruption.
