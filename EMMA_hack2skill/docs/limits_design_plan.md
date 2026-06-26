# EMM-05-A3: limits.py Detailed Design Plan
## Architectural Specification for Sandbox Limits Configuration & Presets
### Document Version: 1.0 (Production-Grade)

This document outlines the design, interface specification, and exact mathematical scaling rules for `backend/app/safety/limits.py` as part of the **EMM-05-A3 Adaptive Sandbox Limits** implementation.

---

## 1. Objectives & Context

The sandbox execution pipeline (`sandbox.py`) operates as a resource-constrained subprocess executor. Currently, the limits are static constants. To enable adaptive scaling:
1. We must encapsulate all resource constraints (timeout, memory, gas, retry strategies) into a single immutable configuration token: `SandboxLimits`.
2. We must provide standardized, calibrated presets (`LimitPreset`) for different computational workloads.
3. We must define mathematical clamping boundaries (`HARD_CEILING`) to protect the host system during auto-scaling and retry loops.

---

## 2. Component Design & Class Hierarchy

```
┌────────────────────────────────────────────────────────────────────────┐
│                        limits.py Module                                │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                    class SandboxLimits                         │   │
│   ├────────────────────────────────────────────────────────────────┤   │
│   │  - timeout_s: float (Wall-clock timeout)                       │   │
│   │  - memory_mb: int (Virtual memory limit)                       │   │
│   │  - gas_limit: int (AST gas instruction ceiling)                │   │
│   │  - max_retries: int (Tuning attempt budget)                    │   │
│   │  - retry_scale: float (Multiplicative growth factor)           │   │
│   ├────────────────────────────────────────────────────────────────┤   │
│   │  + scale(factor: float) -> SandboxLimits                       │   │
│   │  + cap(ceiling: SandboxLimits) -> SandboxLimits                │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                     class LimitPreset                          │   │
│   ├────────────────────────────────────────────────────────────────┤   │
│   │  - MICRO: SandboxLimits                                        │   │
│   │  - STANDARD: SandboxLimits                                     │   │
│   │  - MEDIUM: SandboxLimits                                       │   │
│   │  - HEAVY: SandboxLimits                                        │   │
│   │  - RESEARCH: SandboxLimits                                     │   │
│   └────────────────────────────────────────────────────────────────┘   │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │              constant HARD_CEILING: SandboxLimits              │   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 2.1 The `SandboxLimits` Dataclass
A dataclass holding the resource limits for a single sandbox run.

* **Attributes:**
  * `timeout_s` (`float`): Subprocess execution timeout in seconds.
  * `memory_mb` (`int`): Virtual memory cap in Megabytes.
  * `gas_limit` (`int`): Maximum instruction count before gas metering halts execution.
  * `max_retries` (`int`): Number of allowed retries on timeout/gas limit exhaustion.
  * `retry_scale` (`float`): Multiplier applied to `timeout_s` and `gas_limit` on each retry.

* **Methods:**
  * `scale(factor: float) -> SandboxLimits`:
    * Multiplies `timeout_s` by `factor`.
    * Multiplies `gas_limit` by `factor` (cast to `int`).
    * Preserves `memory_mb` unchanged (memory allocations should not scale dynamically due to leak risks).
    * Decrements `max_retries` by `1` (capped at minimum `0`).
    * Returns a new `SandboxLimits` instance.
  * `cap(ceiling: SandboxLimits) -> SandboxLimits`:
    * Returns a new `SandboxLimits` instance with values clamped to the minimum of current values and corresponding `ceiling` values.

### 2.2 `LimitPreset` Configurations
Calibrated defaults for different classes of computational workloads:

* **`MICRO`**:
  * For light operations (e.g., string manipulation, small utility calculations).
  * `timeout_s = 5.0`, `memory_mb = 64`, `gas_limit = 10_000`, `max_retries = 0`.
* **`STANDARD`**:
  * For baseline solver operations.
  * `timeout_s = 30.0`, `memory_mb = 256`, `gas_limit = 50_000`, `max_retries = 1`.
* **`MEDIUM`**:
  * For algorithms utilizing single nested loops or basic standard library operations.
  * `timeout_s = 60.0`, `memory_mb = 512`, `gas_limit = 500_000`, `max_retries = 1`.
* **`HEAVY`**:
  * For heavier computations involving mathematical libraries (`numpy`, `scipy`) or double/triple nested loops.
  * `timeout_s = 120.0`, `memory_mb = 1024`, `gas_limit = 5_000_000`, `max_retries = 2`.
* **`RESEARCH`**:
  * For research-grade complex math models, optimization frameworks, or highly recursive algorithms.
  * `timeout_s = 300.0`, `memory_mb = 2048`, `gas_limit = 50_000_000`, `max_retries = 3`.

### 2.3 `HARD_CEILING` Constant
A global threshold clamp to protect the host against resource exhaustion:
```python
HARD_CEILING = SandboxLimits(
    timeout_s=600.0,
    memory_mb=4096,
    gas_limit=100_000_000,
    max_retries=0,
    retry_scale=1.0
)
```

---

## 3. Mathematical Execution Logic

When scaling limits during retries:

$$\text{timeout\_s}_{new} = \min(\text{timeout\_s}_{old} \times \text{retry\_scale}, \text{HARD\_CEILING.timeout\_s})$$

$$\text{gas\_limit}_{new} = \min(\lfloor\text{gas\_limit}_{old} \times \text{retry\_scale}\rfloor, \text{HARD\_CEILING.gas\_limit})$$

$$\text{memory\_mb}_{new} = \text{memory\_mb}_{old}$$

This design guarantees that memory allocation remains predictable, avoiding wild escalations if memory leaks occur, while allowing CPU-bound tasks (which typically fail via timeouts or gas exhausted) to successfully heal.

---

## 4. Verification & Testing Anchors

The class will be verified inside `test_adaptive_sandbox.py` using:
1. **Serialization Checks:** Ensuring dataclass fields are correctly castable to standard dictionary shapes for passing directly into `run_in_sandbox(**dataclasses.asdict(limits))`.
2. **Immutability Check:** Asserting that calling `.scale()` or `.cap()` returns new instances and does not modify the source presets.
3. **Clamp Verification:** Ensuring that applying `.cap(HARD_CEILING)` to extreme values clamps them to the exact limits of the ceiling.
