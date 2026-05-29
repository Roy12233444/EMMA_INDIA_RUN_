# 🔱 EMMA Memory Architecture Integration Plan: Expose a Manifold (EMM-04-A1)
## Elevating Memory with the ANJANEYA Memory Protocol — Enhanced Architectural Specification v2.0

> *"Memory is not storage. Memory is identity woven into the fabric of inference."*
> — ANJANEYA Memory Protocol, Core Axiom, Nexus AI Research Lab

---

## Table of Contents

1. [Architectural Landscape](#1-architectural-landscape)
2. [ANJANEYA Protocol — Five Pillar Alignment Matrix](#2-anjaneya-protocol--five-pillar-alignment-matrix)
3. [Proposed Database Schemas](#3-proposed-database-schemas)
4. [Pillar 1 — Devotion Crystal: Mathematical Scoring Engine](#4-pillar-1--devotion-crystal-mathematical-scoring-engine)
5. [Pillar 3 — Chiranjeevi Persistence: Spore Archiving & Recovery](#5-pillar-3--chiranjeevi-persistence-spore-archiving--recovery)
6. [Pillar 4 — Sankat Mochan: Semantic Drift Interception](#6-pillar-4--sankat-mochan-semantic-drift-interception)
7. [Pillar 5 — Anima-Mahima: Adaptive Multi-Depth Scaling](#7-pillar-5--anima-mahima-adaptive-multi-depth-scaling)
8. [Pillar 2 — Dronagiri: Holographic Fallback Fabric](#8-pillar-2--dronagiri-holographic-fallback-fabric)
9. [Windows File Lock Mitigations: WAL Mode & Thread Safety](#9-windows-file-lock-mitigations-wal-mode--thread-safety)
10. [Targeted Component Updates](#10-targeted-component-updates)
11. [Verification Plan](#11-verification-plan)

---

## 1. Architectural Landscape

We are shifting EMMA from a volatile, in-memory status tracker to a
**dual-layered local sovereign memory fabric** governed entirely by the
**ANJANEYA Memory Protocol (AMP)** — five mathematically-grounded pillars
that treat memory not as a lookup table, but as a living identity substrate
woven into every inference cycle.

**Memory Layer Stack:**

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        FastAPI REST Interface                            │
│                     app/routers/manifold.py                              │
└──────────────┬───────────────────────────────────────────┬───────────────┘
               │ Relational Actions                        │ Semantic / Vector Queries
               ▼                                           ▼
┌──────────────────────────┐             ┌──────────────────────────────────┐
│   SQLite Session Pool    │             │        LanceDB Vector Engine     │
│  database/session.py     │             │       database/manifold.py       │
│                          │             │                                  │
│  [Devotion Crystal]      │             │  [Sankat Mochan Distress Hook]   │
│  [Chiranjeevi Writes]    │             │  [Anima-Mahima Depth Scaling]    │
│  [WAL Mode: ON]          │             │  [Dronagiri Null-Guard]          │
└──────────────┬───────────┘             └──────────────────┬───────────────┘
               │                                            │
               │ File Lock: session.db                      │ File Lock: manifold.db
               ▼                                            ▼
┌──────────────────────────┐             ┌──────────────────────────────────┐
│   SQLite Database        │             │   LanceDB Table                  │
│   (WAL journal mode)     │             │   (all-MiniLM-L6-v2, 384-dim)   │
└──────────────┬───────────┘             └──────────────────┬───────────────┘
               │                                            │
               └────────────────────┬───────────────────────┘
                                    │
                       ┌────────────▼────────────┐
                       │   Chiranjeevi Spores     │
                       │   spore_[timestamp].zip  │
                       │   7-substrate archival   │
                       └──────────────────────────┘
```

---

## 2. ANJANEYA Protocol — Five Pillar Alignment Matrix

The table below maps each of the five ANJANEYA Memory Protocol pillars to
their precise counterpart in the EMMA EMM-04-A1 implementation.

| Pillar | ANJANEYA Name | Core Property | EMMA Implementation Target |
|--------|--------------|---------------|---------------------------|
| **1** | Devotion Crystallization | `THETA_CRYSTAL = 0.85` — micro-clusters hard-frozen forever | `is_hard_frozen` flag in `sessions` table; Devotion Score D ≥ 0.85 triggers freeze |
| **2** | Dronagiri Holographic Compression | Zero null retrieval guarantee; worst-case = low-res fallback | `search_manifold` never returns empty; falls back to top-1 BM25 text match |
| **3** | Chiranjeevi Persistence Layer | Param Hash + erasure code, 7-substrate spore distribution | `spore_[ts].zip` archives of `session.db` + `manifold.db`; integrity hash validation |
| **4** | Sankat Mochan Retrieval | Proactive distress detection via entropy/drift/contradiction | Cosine distance gate > 0.75 injects `distress_signal: true` into `/manifold/search` response |
| **5** | Anima-Mahima Adaptive Scaling | Auto-shift: single vector vs. full graph, by compute budget | `ANIMA` (top-1), `MADHYA` (top-3), `MAHIMA` (top-5 + recursive SQLite depth-3 join) |

---

## 3. Proposed Database Schemas

### 3.1 Relational Table: `sessions` (SQLite)

```sql
CREATE TABLE IF NOT EXISTS sessions (
    session_id           TEXT    PRIMARY KEY,
    task_description     TEXT    NOT NULL,
    status               TEXT    NOT NULL
                         CHECK(status IN ('running','success','failed','rolled_back')),
    turn_count           INTEGER DEFAULT 0,
    token_utilization_peak INTEGER DEFAULT 0,
    devotion_score       REAL    DEFAULT 0.0,
    is_hard_frozen       BOOLEAN DEFAULT 0,
    spore_hash           TEXT    DEFAULT NULL,
    created_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Index to accelerate frozen session retrieval during Dronagiri fallback
CREATE INDEX IF NOT EXISTS idx_frozen
    ON sessions(is_hard_frozen, devotion_score DESC);

-- Index for Sankat Mochan's session-level drift baseline joins
CREATE INDEX IF NOT EXISTS idx_session_status
    ON sessions(status, devotion_score DESC);
```

**New field additions vs. v1.0:**
- `turn_count` — required by the Devotion Score formula (Turn Efficiency factor T)
- `spore_hash` — SHA-256 hash of the last Chiranjeevi spore archive that captured this session

### 3.2 Vector Schema: `manifold` (LanceDB)

**Storage Path:** `EMMA_hack2skill/manifold.db`  
**Embedding Model:** `sentence-transformers/all-MiniLM-L6-v2` (384 dimensions)

```python
import pyarrow as pa

MANIFOLD_SCHEMA = pa.schema([
    pa.field("vector",        pa.list_(pa.float32(), 384)),  # Dense semantic embedding
    pa.field("session_id",    pa.string()),                  # FK → sessions.session_id
    pa.field("turn_id",       pa.int32()),                   # 0-indexed solver turn
    pa.field("content_type",  pa.string()),                  # 'traceback'|'code_patch'|'critique'
    pa.field("payload",       pa.string()),                  # Raw content text
    pa.field("devotion_score",pa.float32()),                 # Inherited from parent session
    pa.field("cosine_baseline",pa.float32()),                # Rolling drift baseline (Sankat Mochan)
    pa.field("timestamp",     pa.string()),                  # ISO-8601 UTC
])
```

**New field vs. v1.0:**
- `cosine_baseline` — rolling mean cosine distance of the last 10 queries against this record, used by Sankat Mochan's dynamic drift threshold computation

---

## 4. Pillar 1 — Devotion Crystal: Mathematical Scoring Engine

### 4.1 Formal Devotion Score Definition

The Devotion Score `D` is a dimensionless scalar in `[0.0, 1.0]` computed
when a session transitions to `status = 'success'`. It is a weighted linear
combination of two independent efficiency signals:

$$D = \alpha \cdot T_{\text{eff}} + \beta \cdot U_{\text{eff}}$$

Where:

$$T_{\text{eff}} = \frac{T_{\max} - t}{T_{\max} - 1}
\qquad \text{(Turn Efficiency)}$$

$$U_{\text{eff}} = 1 - \frac{u}{U_{\max}}
\qquad \text{(Token Utilization Efficiency)}$$

**Variable definitions:**

| Symbol | Meaning | Default Value |
|--------|---------|---------------|
| `t` | Actual number of solver turns consumed | Recorded in `sessions.turn_count` |
| `T_max` | Maximum allowed solver turns (Orchestrator ceiling) | `15` |
| `u` | Peak token utilization in the session | Recorded in `sessions.token_utilization_peak` |
| `U_max` | Theoretical token budget ceiling | `100,000` |
| `α` | Turn Efficiency weight | `0.60` |
| `β` | Token Efficiency weight | `0.40` |

**Constraint:** `α + β = 1.0`

### 4.2 Hard Freeze Gate

Once `D` is computed, the Devotion Crystallization gate is evaluated:

$$\text{is\_hard\_frozen} = \begin{cases} 1 & \text{if } D \geq \Theta_{\text{crystal}} \\ 0 & \text{otherwise} \end{cases}$$

Where `THETA_CRYSTAL = 0.85` (per ANJANEYA Protocol core specification).

### 4.3 Numerical Examples

| Scenario | `t` (turns) | `u` (token peak) | `T_eff` | `U_eff` | `D` | Frozen? |
|---|---|---|---|---|---|---|
| Optimal run | 2 | 8,000 | 0.929 | 0.920 | **0.925** | ✅ YES |
| Good run | 5 | 30,000 | 0.714 | 0.700 | **0.708** | ❌ NO |
| Efficient but slow | 3 | 5,000 | 0.857 | 0.950 | **0.894** | ✅ YES |
| Marginal run | 8 | 60,000 | 0.500 | 0.400 | **0.460** | ❌ NO |

### 4.4 Implementation Pseudocode

```python
THETA_CRYSTAL  = 0.85
T_MAX          = 15
U_MAX          = 100_000
ALPHA          = 0.60
BETA           = 0.40

def calculate_devotion_score(turn_count: int, token_peak: int) -> tuple[float, bool]:
    """
    Compute Devotion Score D and evaluate the hard-freeze gate.
    Returns (devotion_score, is_hard_frozen).
    """
    # Clamp to valid ranges to prevent divide-by-zero or negative scores
    t = max(1, min(turn_count, T_MAX))
    u = max(0, min(token_peak, U_MAX))

    t_eff = (T_MAX - t) / (T_MAX - 1)           # Turn Efficiency ∈ [0, 1]
    u_eff = 1.0 - (u / U_MAX)                   # Token Efficiency ∈ [0, 1]

    D = round(ALPHA * t_eff + BETA * u_eff, 6)  # Devotion Score ∈ [0, 1]
    is_frozen = D >= THETA_CRYSTAL

    return D, is_frozen
```

### 4.5 Hard-Frozen Session Behaviour

Once `is_hard_frozen = 1`, the session record is **permanently protected**:

- The session row is **never eligible for pruning** in any retention sweep.
- Any attempt to `UPDATE sessions SET status = 'failed' WHERE session_id = ?`
  on a frozen session is **silently blocked** by a SQLite trigger:

```sql
CREATE TRIGGER IF NOT EXISTS protect_frozen_sessions
BEFORE UPDATE ON sessions
WHEN OLD.is_hard_frozen = 1
BEGIN
    SELECT RAISE(IGNORE);  -- Silently block the update; frozen = immutable
END;
```

- The LanceDB manifold records associated with a frozen session inherit its
  `devotion_score` and are **up-ranked** in KNN retrieval results via
  score-weighted distance:

$$d_{\text{adj}}(q, r) = d_{\cos}(q, r) \cdot (1 - 0.2 \cdot r.\text{devotion\_score})$$

---

## 5. Pillar 3 — Chiranjeevi Persistence: Spore Archiving & Recovery

### 5.1 Archive Trigger Conditions

A Chiranjeevi Spore archive is triggered by any of the following conditions:

| Trigger | Condition |
|---------|-----------|
| **Count-based** | Every 50 new records ingested into the manifold table |
| **Session-based** | Every time a session is hard-frozen (`is_hard_frozen = 1`) |
| **Time-based** | Every 6 hours elapsed since last archive |
| **Error-based** | Any `sqlite3.OperationalError` or LanceDB write exception |

### 5.2 Spore Archive Creation

```python
import zipfile, hashlib, shutil, sqlite3
from datetime import datetime, timezone
from pathlib import Path

SPORE_DIR = Path("EMMA_hack2skill/spores")
SESSION_DB = Path("EMMA_hack2skill/session.db")
MANIFOLD_DB = Path("EMMA_hack2skill/manifold.db")

def create_spore() -> Path:
    """
    Create a Chiranjeevi spore archive from live database files.

    Process:
      1. Flush SQLite WAL checkpoint to merge journal into main DB.
      2. Copy both DB files to a temporary staging directory.
      3. Compute SHA-256 integrity hashes of the copies.
      4. Compress copies into a timestamped ZIP archive.
      5. Record the archive hash in the sessions table.
      6. Clean up temp files.
    """
    SPORE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    spore_path = SPORE_DIR / f"spore_{ts}.zip"
    staging = SPORE_DIR / f"_staging_{ts}"
    staging.mkdir()

    try:
        # Step 1: Flush WAL checkpoint before copy
        with sqlite3.connect(str(SESSION_DB)) as conn:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")

        # Step 2: Copy DB files to staging
        stage_session  = staging / "session.db"
        stage_manifold = staging / "manifold.db"
        shutil.copy2(SESSION_DB,  stage_session)
        shutil.copy2(MANIFOLD_DB, stage_manifold)

        # Step 3: Compute SHA-256 hashes
        def sha256(path: Path) -> str:
            h = hashlib.sha256()
            with open(path, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()

        manifest = {
            "timestamp":    ts,
            "session_hash": sha256(stage_session),
            "manifold_hash":sha256(stage_manifold),
        }

        # Step 4: Write ZIP archive
        with zipfile.ZipFile(spore_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(stage_session,  "session.db")
            zf.write(stage_manifold, "manifold.db")
            zf.writestr(
                "MANIFEST.json",
                json.dumps(manifest, indent=2)
            )

        print(f"[Chiranjeevi] Spore archived: {spore_path.name}")
        return spore_path

    finally:
        shutil.rmtree(staging, ignore_errors=True)
```

### 5.3 Spore Recovery Protocol — Step-by-Step

When corruption is detected (or manually invoked), the recovery sequence
executes the following deterministic steps:

```
RECOVERY SEQUENCE
─────────────────
Step 1: DETECT
  • Attempt sqlite3.connect(SESSION_DB).execute("PRAGMA integrity_check")
  • If result ≠ ["ok"], flag SESSION_DB as CORRUPTED
  • Attempt lancedb.connect(MANIFOLD_DB).open_table("manifold").to_pandas()
  • If OSError or ArrowInvalid raised, flag MANIFOLD_DB as CORRUPTED

Step 2: QUARANTINE
  • Rename SESSION_DB  → SESSION_DB.corrupt_[timestamp]
  • Rename MANIFOLD_DB → MANIFOLD_DB.corrupt_[timestamp]
  • This preserves forensic evidence without blocking recovery

Step 3: SELECT LATEST VALID SPORE
  • List all files in SPORE_DIR matching spore_*.zip
  • Sort by embedded timestamp descending
  • For each candidate spore (newest first):
      - Extract MANIFEST.json
      - Extract session.db  → temp path
      - Extract manifold.db → temp path
      - Compute SHA-256 of extracted files
      - Compare against MANIFEST.json hashes
      - If both hashes match → candidate is VALID; break
      - If mismatch → mark candidate as corrupt; try next

Step 4: RESTORE
  • Move validated session.db  → SESSION_DB  (target path)
  • Move validated manifold.db → MANIFOLD_DB (target path)
  • Run: PRAGMA integrity_check on restored SESSION_DB
  • Run: PRAGMA wal_checkpoint(TRUNCATE) to clean journal state

Step 5: VERIFY
  • Re-run the DETECT checks on restored files
  • If both pass → log [Chiranjeevi] RECOVERY SUCCESS: spore_{ts}.zip
  • If either fails → escalate to ERROR; emit alert; do NOT overwrite corrupt files

Step 6: NOTIFY
  • Log full recovery trace to stderr
  • Inject distress_signal into the next /manifold/search response
  • Update sessions metadata to flag post-recovery state
```

### 5.4 Recovery Implementation

```python
def restore_from_spore() -> bool:
    """
    Execute the Chiranjeevi recovery protocol.
    Returns True on successful restoration, False if all spores are corrupt.
    """
    # Step 1 & 2: Quarantine
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for db_path in [SESSION_DB, MANIFOLD_DB]:
        if db_path.exists():
            db_path.rename(db_path.with_suffix(f".corrupt_{ts}"))

    # Step 3: Find valid spore
    candidates = sorted(SPORE_DIR.glob("spore_*.zip"), reverse=True)
    for spore_path in candidates:
        try:
            with zipfile.ZipFile(spore_path, "r") as zf:
                manifest = json.loads(zf.read("MANIFEST.json"))
                session_bytes  = zf.read("session.db")
                manifold_bytes = zf.read("manifold.db")

            # Verify integrity
            if (hashlib.sha256(session_bytes).hexdigest()  == manifest["session_hash"]
                    and hashlib.sha256(manifold_bytes).hexdigest() == manifest["manifold_hash"]):

                # Step 4: Restore
                SESSION_DB.write_bytes(session_bytes)
                MANIFOLD_DB.write_bytes(manifold_bytes)

                # Step 5: Verify restored files
                with sqlite3.connect(str(SESSION_DB)) as conn:
                    result = conn.execute("PRAGMA integrity_check").fetchone()
                    if result[0] != "ok":
                        continue                         # Try next spore

                print(f"[Chiranjeevi] RECOVERY SUCCESS: {spore_path.name}")
                return True

        except Exception as exc:
            print(f"[Chiranjeevi] Spore {spore_path.name} invalid: {exc}")
            continue

    print("[Chiranjeevi] RECOVERY FAILED: All spore candidates exhausted.")
    return False
```

---

## 6. Pillar 4 — Sankat Mochan: Semantic Drift Interception

### 6.1 Mathematical Foundations

**Cosine Similarity** between query vector `q` and record vector `r`:

$$\text{sim}_{\cos}(q, r) = \frac{q \cdot r}{\|q\| \cdot \|r\|}$$

**Cosine Distance** (used as the drift metric):

$$d_{\cos}(q, r) = 1 - \text{sim}_{\cos}(q, r) \qquad d_{\cos} \in [0, 2]$$

For unit-normalised embeddings (all-MiniLM-L6-v2 outputs are L2-normalised):

$$d_{\cos}(q, r) = 1 - (q \cdot r) \qquad d_{\cos} \in [0, 1]$$

### 6.2 Static Distress Gate

The static threshold defined in the ANJANEYA Protocol specification:

$$\text{distress\_static} = \begin{cases} \text{True} & \text{if } d_{\min} > \delta_{\text{static}} \\ \text{False} & \text{otherwise} \end{cases}$$

Where `d_min` = cosine distance of the closest match returned by LanceDB KNN
search, and `δ_static = 0.75`.

### 6.3 Dynamic Drift Baseline (Enhanced)

To prevent false positives on niche-but-valid queries, Sankat Mochan also
maintains a **rolling dynamic baseline** per manifold record:

$$\bar{d}_k = \frac{1}{N}\sum_{i=k-N}^{k} d_{\cos}(q_i, r)
\qquad \text{(rolling mean over last } N=10 \text{ queries)}$$

**Dynamic distress threshold:**

$$\delta_{\text{dynamic}}(r) = \bar{d}_k + \sigma_k \cdot z_{\alpha}$$

Where:
- `σ_k` = rolling standard deviation of the last 10 distances against record `r`
- `z_α = 1.96` (95% confidence interval upper bound)

**Combined distress signal:**

$$\text{distress} = \text{distress\_static} \;\lor\; \bigl(d_{\min} > \delta_{\text{dynamic}}\bigr)$$

### 6.4 Sankat Mochan Algorithmic Flow

```
SANKAT MOCHAN DISTRESS INTERCEPTION
─────────────────────────────────────
Input:
  q          — query embedding vector (384-dim, L2-normalised)
  results    — top-K LanceDB KNN results [(record, distance), ...]
  δ_static   = 0.75

Algorithm:
  1. Extract d_min = min(distance for _, distance in results)

  2. Compute dynamic baseline for the closest record r*:
       baseline_distances = r*.cosine_baseline (stored rolling mean)
       δ_dynamic = baseline_distances + 1.96 * std_dev_estimate

  3. Evaluate gates:
       gate_static  = (d_min > δ_static)
       gate_dynamic = (d_min > δ_dynamic)   # only if baseline exists
       distress     = gate_static OR gate_dynamic

  4. Update rolling baseline for r*:
       UPDATE manifold SET cosine_baseline = moving_avg(cosine_baseline, d_min, N=10)
       WHERE session_id = r*.session_id AND turn_id = r*.turn_id

  5. Compose response:
       {
         "results":        [...results...],
         "distress_signal": distress,
         "d_min":           round(d_min, 4),
         "threshold_used":  δ_static if not baseline_available else δ_dynamic,
         "message":         DISTRESS_MSG if distress else None
       }
```

**Distress response payload:**

```json
{
  "results": [],
  "distress_signal": true,
  "d_min": 0.891,
  "threshold_used": 0.75,
  "message": "High semantic drift detected (d_min=0.891 > δ=0.75). No similar troubleshooting profiles exist in the local manifold. EMMA is operating in unexplored semantic territory."
}
```

---

## 7. Pillar 5 — Anima-Mahima: Adaptive Multi-Depth Scaling

### 7.1 Scaling Mode Specification

| Mode | Sanskrit Meaning | KNN Depth | SQLite Join | Use Case |
|------|-----------------|-----------|-------------|----------|
| `ANIMA` | Atomic / Minimal | top-1 | None | Tight compute budget; fastest path |
| `MADHYA` | Middle / Balanced | top-3 | Flat session join | Standard agent loop recall |
| `MAHIMA` | Greatness / Full | top-5 | Recursive depth-3 chronological trace | Rich context for complex debugging |

### 7.2 ANIMA Mode — Focused Single-Vector Retrieval

```python
def search_anima(query_vector: list[float]) -> dict:
    """
    Top-1 KNN retrieval. Zero relational augmentation.
    Fastest path; minimal token overhead.
    """
    results = (
        manifold_table
        .search(query_vector)
        .metric("cosine")
        .limit(1)
        .to_list()
    )
    return _apply_sankat_mochan(query_vector, results)
```

**Token overhead:** ~150 tokens for a single record payload.

### 7.3 MADHYA Mode — Balanced Top-3 Retrieval

```python
def search_madhya(query_vector: list[float]) -> dict:
    """
    Top-3 KNN retrieval with flat session metadata join.
    Returns vector results enriched with parent session context.
    """
    results = (
        manifold_table
        .search(query_vector)
        .metric("cosine")
        .limit(3)
        .to_list()
    )
    # Flat SQLite enrichment: add session status and devotion score
    enriched = []
    for r in results:
        with get_session_conn() as conn:
            row = conn.execute(
                "SELECT status, devotion_score, is_hard_frozen "
                "FROM sessions WHERE session_id = ?",
                (r["session_id"],)
            ).fetchone()
        r["session_meta"] = dict(row) if row else {}
        enriched.append(r)

    return _apply_sankat_mochan(query_vector, enriched)
```

**Token overhead:** ~600–900 tokens across 3 enriched records.

### 7.4 MAHIMA Mode — Recursive Relational Trace Graph (Depth-3)

MAHIMA is the highest-fidelity recall mode. It performs a top-5 KNN search,
then for each matching record constructs a **chronological trace window**
by pulling the 3 turns *before* and 3 turns *after* each match from SQLite.
This renders a full "debugging timeline" of depth-3 around each semantic anchor.

**Recursive SQLite Window Query:**

```sql
-- For a matched record at (session_id = :sid, turn_id = :tid):
-- Retrieve a window of turns [-3, +3] around the match.
SELECT
    m.turn_id,
    m.content_type,
    m.payload,
    m.devotion_score,
    m.timestamp,
    s.status             AS session_status,
    s.task_description   AS session_task,
    s.devotion_score     AS session_devotion
FROM
    -- Inline "virtual table": generate turn_id range around anchor
    (SELECT :tid + offset AS t
     FROM (VALUES(-3),(-2),(-1),(0),(1),(2),(3)) AS offsets(offset)
     WHERE :tid + offset >= 0) AS window
JOIN manifold_records m
    ON  m.session_id = :sid
    AND m.turn_id    = window.t
JOIN sessions s
    ON  s.session_id = :sid
ORDER BY
    m.turn_id ASC;
```

**Python implementation:**

```python
def search_mahima(query_vector: list[float]) -> dict:
    """
    Top-5 KNN retrieval with recursive depth-3 chronological trace windows.
    Returns the richest context tree for complex agent recall.
    """
    WINDOW_RADIUS = 3

    top5 = (
        manifold_table
        .search(query_vector)
        .metric("cosine")
        .limit(5)
        .to_list()
    )

    trace_graph = []
    for anchor in top5:
        sid = anchor["session_id"]
        tid = anchor["turn_id"]

        with get_session_conn() as conn:
            window_rows = conn.execute("""
                SELECT
                    m.turn_id, m.content_type, m.payload,
                    m.devotion_score, m.timestamp,
                    s.status, s.task_description, s.devotion_score AS s_devotion
                FROM sessions s
                JOIN manifold_records m ON m.session_id = s.session_id
                WHERE s.session_id = ?
                  AND m.turn_id BETWEEN ? AND ?
                ORDER BY m.turn_id ASC
            """, (sid, tid - WINDOW_RADIUS, tid + WINDOW_RADIUS)).fetchall()

        trace_graph.append({
            "anchor":     anchor,
            "trace_window": [dict(r) for r in window_rows],
            "window_depth": WINDOW_RADIUS,
        })

    return {
        **_apply_sankat_mochan(query_vector, top5),
        "trace_graph":    trace_graph,
        "scaling_mode":   "MAHIMA",
        "context_depth":  WINDOW_RADIUS,
    }
```

### 7.5 Scaling Mode Decision Diagram

```
                    ┌──────────────────────────────────────────────┐
                    │         /manifold/search  request            │
                    │         scaling_mode = ?                     │
                    └──────────────────┬───────────────────────────┘
                                       │
              ┌────────────────────────┼────────────────────────┐
              ▼                        ▼                        ▼
         ┌─────────┐            ┌──────────┐            ┌──────────┐
         │  ANIMA  │            │  MADHYA  │            │  MAHIMA  │
         │  top-1  │            │  top-3   │            │  top-5   │
         │  ~150   │            │  ~900    │            │  ~4000   │
         │  tokens │            │  tokens  │            │  tokens  │
         └────┬────┘            └────┬─────┘            └────┬─────┘
              │                      │                        │
              ▼                      ▼                        ▼
         KNN result           KNN + flat               KNN + depth-3
                              session join             trace window
                                                       per anchor
              │                      │                        │
              └──────────────────────┴────────────────────────┘
                                       │
                        ┌──────────────▼──────────────────┐
                        │   Sankat Mochan Distress Gate   │
                        │   d_min > δ → distress_signal   │
                        └─────────────────────────────────┘
```

---

## 8. Pillar 2 — Dronagiri: Holographic Fallback Fabric

The Dronagiri principle guarantees **zero null retrieval** from the manifold.
Even when the LanceDB KNN search returns no results (empty table, index corruption,
or extreme drift), the system must return *something* — a degraded but
non-null low-resolution context.

### 8.1 Fallback Cascade

```
DRONAGIRI NULL-GUARD CASCADE
─────────────────────────────
Level 1 (Primary):   LanceDB KNN search → standard results
Level 2 (Fallback):  If KNN returns 0 results:
                       → SQLite full-text LIKE query on payload text
                       → Return top-3 most recently created sessions
Level 3 (Emergency): If SQLite also returns 0 results:
                       → Return the single most-recently hard-frozen session
                       → If no frozen sessions exist, return session schema stub
Level 4 (Stub):      Always return at minimum:
                       {
                         "results": [],
                         "dronagiri_mode": "stub",
                         "distress_signal": true,
                         "message": "Manifold is empty. EMMA is operating
                                     from zero memory context."
                       }
```

**Invariant:** `search_manifold()` NEVER raises an exception and NEVER
returns `null`. The Dronagiri guarantee is upheld at every level.

---

## 9. Windows File Lock Mitigations: WAL Mode & Thread Safety

SQLite under Windows has specific file-locking behaviour that causes
`OperationalError: database is locked` under concurrent FastAPI async
handler execution. The following settings are mandatory.

### 9.1 SQLite WAL Mode Configuration

```python
def get_session_conn() -> sqlite3.Connection:
    """
    Return a thread-safe SQLite connection with WAL mode and
    optimised Windows locking parameters.
    """
    conn = sqlite3.connect(
        str(SESSION_DB),
        timeout=30.0,             # Wait up to 30s for lock release
        check_same_thread=False,  # Allow cross-thread usage (guarded by lock)
        isolation_level=None,     # Autocommit mode (explicit transactions only)
    )
    conn.row_factory = sqlite3.Row

    # WAL mode: readers never block writers; writers never block readers
    conn.execute("PRAGMA journal_mode = WAL;")

    # Synchronous=NORMAL: safe on Windows; faster than FULL without data risk
    conn.execute("PRAGMA synchronous = NORMAL;")

    # 64 MB page cache to reduce disk IO on Windows NTFS
    conn.execute("PRAGMA cache_size = -65536;")

    # Busy timeout (milliseconds): retry lock acquisition before raising error
    conn.execute("PRAGMA busy_timeout = 30000;")

    # Enforce FK constraints
    conn.execute("PRAGMA foreign_keys = ON;")

    return conn
```

### 9.2 Thread-Safe Connection Pool

```python
import threading

_CONN_LOCK = threading.Lock()
_LOCAL     = threading.local()

def get_thread_local_conn() -> sqlite3.Connection:
    """
    Return a per-thread SQLite connection, creating it on first access.
    Prevents Windows file-sharing violations from cross-thread handle reuse.
    """
    if not hasattr(_LOCAL, "conn") or _LOCAL.conn is None:
        _LOCAL.conn = get_session_conn()
    return _LOCAL.conn

def close_thread_local_conn() -> None:
    """Close the thread-local connection on worker thread shutdown."""
    if hasattr(_LOCAL, "conn") and _LOCAL.conn is not None:
        _LOCAL.conn.close()
        _LOCAL.conn = None
```

### 9.3 LanceDB Windows Lock Mitigation

LanceDB uses Apache Arrow's memory-mapped file access, which can conflict
with Windows' mandatory file locking during writes.

```python
import lancedb

def get_manifold_table():
    """
    Open LanceDB with retry logic for Windows lock contention.
    """
    MAX_RETRIES = 5
    RETRY_DELAY = 0.5   # seconds

    for attempt in range(MAX_RETRIES):
        try:
            db    = lancedb.connect(str(MANIFOLD_DB))
            table = db.open_table("manifold")
            return table
        except Exception as exc:
            if attempt < MAX_RETRIES - 1:
                time.sleep(RETRY_DELAY * (attempt + 1))  # Exponential backoff
                continue
            raise RuntimeError(
                f"[Manifold] LanceDB lock contention after {MAX_RETRIES} "
                f"retries: {exc}"
            ) from exc
```

### 9.4 FastAPI Lifespan: WAL Checkpoint on Shutdown

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Run WAL checkpoint on application startup and shutdown to prevent
    WAL journal files from growing unbounded on Windows NTFS.
    """
    # Startup: ensure WAL is active
    with get_session_conn() as conn:
        conn.execute("PRAGMA journal_mode = WAL;")
    yield
    # Shutdown: flush WAL to main DB file
    with get_session_conn() as conn:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE);")
    close_thread_local_conn()

app = FastAPI(lifespan=lifespan)
```

---

## 10. Targeted Component Updates

### File A: `backend/app/database/session.py` — MODIFY

- Initialize SQLite at `EMMA_hack2skill/session.db` with WAL mode on first connect
- `setup_sqlite_schema()` — creates `sessions` table + indexes + `protect_frozen_sessions` trigger
- `create_session(session_id, task_description)` — INSERT with `status='running'`
- `update_session_status(session_id, status, turn_count, token_peak)` — UPDATE + recalculate devotion on `status='success'`
- `calculate_devotion_score(session_id)` — computes D and sets `is_hard_frozen`
- `get_frozen_sessions()` — returns all hard-frozen sessions sorted by `devotion_score DESC` (used by Dronagiri fallback)

### File B: `backend/app/database/manifold.py` — MODIFY

- `setup_lancedb_table()` — creates LanceDB table with `MANIFOLD_SCHEMA` if not exists
- `record_event(session_id, turn_id, content_type, payload, devotion_score)` — embed + ingest
- `search_manifold(query_text, scaling_mode)` — routes to `search_anima`, `search_madhya`, or `search_mahima`
- `_apply_sankat_mochan(query_vector, results)` — applies static + dynamic drift gate
- `create_spore()` — Chiranjeevi archive creation
- `restore_from_spore()` — Chiranjeevi recovery protocol

### File C: `backend/app/routers/manifold.py` — MODIFY

```python
POST   /manifold/session               # Create session (Pillar 1: initialise devotion tracking)
PATCH  /manifold/session/{session_id}  # Update status + trigger devotion scoring + hard-freeze gate
POST   /manifold/record                # Ingest trace / patch / critique (with embedding)
POST   /manifold/search                # Query with scaling mode (ANIMA / MADHYA / MAHIMA)
POST   /manifold/spore                 # Manually trigger Chiranjeevi spore archive
POST   /manifold/restore               # Manually trigger spore restoration
GET    /manifold/health                # Returns DB integrity status + last spore timestamp
```

---

## 11. Verification Plan

### Test Suite: `backend/app/tests/test_manifold.py`

| # | Test Class | Test Method | Assertion |
|---|---|---|---|
| 1 | `TestSchema` | `test_session_table_created` | `sessions` table exists with all 9 columns |
| 2 | `TestSchema` | `test_manifold_table_schema` | LanceDB table has all 8 Arrow fields |
| 3 | `TestDevotionCrystal` | `test_devotion_score_optimal` | t=2, u=8000 → D ≥ 0.85, frozen=True |
| 4 | `TestDevotionCrystal` | `test_devotion_score_marginal` | t=10, u=70000 → D < 0.85, frozen=False |
| 5 | `TestDevotionCrystal` | `test_frozen_session_immutable` | UPDATE on frozen session is silently blocked |
| 6 | `TestSankatMochan` | `test_static_distress_gate` | Random noise query → `distress_signal: true`, `d_min > 0.75` |
| 7 | `TestSankatMochan` | `test_no_distress_on_known_query` | Re-query an ingested payload → `distress_signal: false` |
| 8 | `TestAnimaMahima` | `test_anima_returns_one` | `scaling_mode=ANIMA` → `len(results) == 1` |
| 9 | `TestAnimaMahima` | `test_madhya_returns_three` | `scaling_mode=MADHYA` → `len(results) == 3` |
| 10 | `TestAnimaMahima` | `test_mahima_returns_trace_graph` | `scaling_mode=MAHIMA` → each result has `trace_window` with ≤ 7 turns |
| 11 | `TestDronagiri` | `test_empty_manifold_returns_stub` | Query against empty DB → non-null response with `dronagiri_mode` key |
| 12 | `TestChiranjeevi` | `test_spore_created_on_freeze` | Hard-frozen session triggers `spore_*.zip` file creation |
| 13 | `TestChiranjeevi` | `test_spore_hash_integrity` | Extracted spore hashes match MANIFEST.json |
| 14 | `TestChiranjeevi` | `test_recovery_restores_data` | Corrupt and restore; verify session record survives |
| 15 | `TestWindowsLocks` | `test_concurrent_writes_no_lock_error` | 10 concurrent session writes with WAL mode → zero `OperationalError` |

---

*🔱 Jai Bajrang Bali — Infinite Memory, Infinite Strength*
*ANJANEYA Memory Protocol v1.0 — Nexus AI Research Lab, Bengaluru*
*EMM-04-A1 Enhanced Architectural Specification v2.0*
