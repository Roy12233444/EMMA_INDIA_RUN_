"""
adaptive_result.py
Adaptive sandbox execution results and telemetry structure.
Part of EMM-05-A3 Adaptive Sandbox Limits.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from backend.app.safety.limits import SandboxLimits
from backend.app.safety.sandbox import SandboxResult


@dataclass(frozen=True)
class AdaptiveSandboxResult:
    """
    Telemetry result class returned by AdaptiveSandboxRunner.
    Wraps standard SandboxResult with multi-attempt execution details.
    """
    success: bool
    stdout: str
    stderr: str
    exit_code: Optional[int]
    gas_consumed: int
    error_type: Optional[str]
    error_message: Optional[str]
    error_line: Optional[int]
    latency_ms: float               # Cumulative wall-clock latency across all attempts
    exit_class: str
    retries_attempted: int          # 0 for single attempt, >=1 if retries ran
    final_limits: SandboxLimits     # The limits used in the final attempt
    history: List[SandboxResult] = field(default_factory=list) # Full log of individual runs
