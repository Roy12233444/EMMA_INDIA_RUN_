"""
limits.py
Resource limits configuration, presets, and scaling/capping utilities.
Part of EMM-05-A3 Adaptive Sandbox Limits.
"""

import dataclasses

@dataclasses.dataclass(frozen=True)
class SandboxLimits:
    """Dataclass holding resource limits for a single sandbox execution."""
    timeout_s: float
    memory_mb: int
    gas_limit: int
    max_retries: int
    retry_scale: float

    def scale(self, factor: float) -> "SandboxLimits":
        """
        Creates a new SandboxLimits instance with timeout and gas_limit scaled.
        Note that memory_mb remains unscaled to prevent OOM/leak risks,
        and max_retries is decremented by 1 (clamped at 0).
        """
        new_timeout = self.timeout_s * factor
        new_gas = int(self.gas_limit * factor)
        new_retries = max(0, self.max_retries - 1)
        
        return SandboxLimits(
            timeout_s=new_timeout,
            memory_mb=self.memory_mb,
            gas_limit=new_gas,
            max_retries=new_retries,
            retry_scale=self.retry_scale
        )

    def cap(self, ceiling: "SandboxLimits") -> "SandboxLimits":
        """
        Clamps all numeric limits to the values specified in the ceiling.
        Returns a new SandboxLimits instance.
        """
        return SandboxLimits(
            timeout_s=min(self.timeout_s, ceiling.timeout_s),
            memory_mb=min(self.memory_mb, ceiling.memory_mb),
            gas_limit=min(self.gas_limit, ceiling.gas_limit),
            max_retries=min(self.max_retries, ceiling.max_retries),
            retry_scale=self.retry_scale
        )


# Hard limits ceiling to prevent system-wide resource starvation
HARD_CEILING = SandboxLimits(
    timeout_s=600.0,
    memory_mb=4096,
    gas_limit=100_000_000,
    max_retries=0,
    retry_scale=1.0
)


class LimitPreset:
    """Standard resource envelopes calibrated for different computational workloads."""
    MICRO = SandboxLimits(
        timeout_s=5.0,
        memory_mb=64,
        gas_limit=10_000,
        max_retries=0,
        retry_scale=1.5
    )
    
    STANDARD = SandboxLimits(
        timeout_s=30.0,
        memory_mb=256,
        gas_limit=50_000,
        max_retries=1,
        retry_scale=2.0
    )
    
    MEDIUM = SandboxLimits(
        timeout_s=60.0,
        memory_mb=512,
        gas_limit=500_000,
        max_retries=1,
        retry_scale=2.0
    )
    
    HEAVY = SandboxLimits(
        timeout_s=120.0,
        memory_mb=1024,
        gas_limit=5_000_000,
        max_retries=2,
        retry_scale=2.0
    )
    
    RESEARCH = SandboxLimits(
        timeout_s=300.0,
        memory_mb=2048,
        gas_limit=50_000_000,
        max_retries=3,
        retry_scale=2.0
    )
