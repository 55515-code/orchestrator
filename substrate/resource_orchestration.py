from __future__ import annotations

import threading
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal, Protocol

from .providers import FREE_FIRST_PROVIDERS
from .reliability import ExecutionTarget

CapabilityClass = Literal["cpu", "gpu", "model", "api"]
ResolvedCapabilityClass = Literal["cpu", "gpu", "api"]
PoolLocation = Literal["local", "cloud"]
SafetyTier = Literal["standard", "strict"]
PressureLevel = Literal["normal", "high"]
ScaleDirection = Literal["scale_out", "scale_in"]


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    ordered: list[str] = []
    for value in values:
        token = value.strip()
        if token and token not in ordered:
            ordered.append(token)
    return tuple(ordered)


def _coerce_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _coerce_float(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize_capability(value: str | CapabilityClass | None) -> ResolvedCapabilityClass:
    token = str(value or "api").strip().lower()
    if token == "gpu":
        return "gpu"
    if token == "cpu":
        return "cpu"
    return "api"


@dataclass(slots=True)
class HardwareProfile:
    accelerators: list[str] = field(default_factory=list)
    gpu_vram_total_mb: int = 0
    gpu_vram_free_mb: int = 0
    cpu_count: int = 0
    ram_total_gb: float = 0.0
    ram_free_gb: float = 0.0
    is_apple_silicon: bool = False
    apple_chip: str = ""
    npu_available: bool = False
    tags: list[str] = field(default_factory=list)

    def has_gpu(self) -> bool:
        return self.gpu_vram_total_mb > 0 or any(a.startswith("nvidia:") or a.startswith("amd:") for a in self.accelerators)

    def has_npu(self) -> bool:
        return self.npu_available or any(a.startswith("npu:") for a in self.accelerators)

    def has_apple_silicon(self) -> bool:
        return self.is_apple_silicon or any(a.startswith("apple-silicon:") for a in self.accelerators)

    def local_model_tier(self) -> str:
        if self.has_apple_silicon():
            return "medium"
        if self.has_gpu() and self.gpu_vram_total_mb >= 16000:
            return "large"
        if self.has_gpu() and self.gpu_vram_total_mb >= 8000:
            return "medium"
        if self.ram_total_gb >= 32:
            return "medium"
        if self.ram_total_gb >= 16:
            return "small"
        return "tiny"

    def has_apple_silicon(self) -> bool:
        return self.is_apple_silicon or any(a.startswith("apple-silicon:") for a in self.accelerators)

    def available_local_capabilities(self) -> tuple[str, ...]:
        caps: list[str] = ["cpu"]
        if self.has_gpu():
            caps.append("gpu")
        return tuple(caps)


def hardware_profile_from_probe(probe_text: str) -> HardwareProfile:
    profile = HardwareProfile()
    if "Apple Silicon" in probe_text or "apple-silicon:" in probe_text:
        profile.is_apple_silicon = True
        profile.tags.append("apple-silicon")
    if "NVIDIA GPUs" in probe_text or "nvidia:" in probe_text:
        profile.tags.append("nvidia")
    if "AMD GPUs" in probe_text or "amd:" in probe_text:
        profile.tags.append("amd")
    if "Intel GPU" in probe_text or "intel:igpu" in probe_text:
        profile.tags.append("intel-igpu")
    if "NPU" in probe_text or "npu:available" in probe_text:
        profile.npu_available = True
        profile.tags.append("npu")
    for line in probe_text.splitlines():
        line = line.strip()
        if line.startswith("CPU count:"):
            try:
                profile.cpu_count = int(line.split(":", 1)[1].strip())
            except (ValueError, IndexError):
                pass
        if line.startswith("RAM total:"):
            raw = line.split(":", 1)[1].strip()
            try:
                if raw.endswith("GB"):
                    profile.ram_total_gb = float(raw[:-2].strip())
                elif raw.endswith("MB"):
                    profile.ram_total_gb = float(raw[:-2].strip()) / 1024.0
                elif raw.endswith("TB"):
                    profile.ram_total_gb = float(raw[:-2].strip()) * 1024.0
            except (ValueError, IndexError):
                pass
        if "VRAM" in line and "MB" in line:
            try:
                vram_mb = int(line.split("VRAM")[1].split("MB")[0].strip())
                profile.gpu_vram_total_mb = max(profile.gpu_vram_total_mb, vram_mb)
                free_match = line.split("free")[1].split("MB")[0].strip() if "free" in line else None
                if free_match:
                    profile.gpu_vram_free_mb = max(profile.gpu_vram_free_mb, int(free_match))
            except (ValueError, IndexError):
                pass
        if "apple-silicon:" in line:
            profile.apple_chip = line.split("apple-silicon:", 1)[1].strip()
            profile.is_apple_silicon = True
    if profile.ram_total_gb == 0.0 and profile.cpu_count:
        profile.ram_total_gb = float(max(4, profile.cpu_count * 2))
    return profile


def provider_capabilities(provider: str) -> tuple[ResolvedCapabilityClass, ...]:
    normalized = provider.strip().lower()
    if normalized in {"local", "roo-router"}:
        return ("cpu",)
    if normalized == "ollama":
        return ("cpu", "gpu")
    if normalized in FREE_FIRST_PROVIDERS:
        return ("api",)
    return ("api",)


def infer_capability_for_provider(provider: str) -> CapabilityClass:
    if provider.strip().lower() in {"local", "roo-router", "ollama"}:
        return "cpu"
    return "api"


@dataclass(slots=True)
class ResourcePoolState:
    name: str
    location: PoolLocation
    capability: ResolvedCapabilityClass
    max_workers: int
    in_flight: int = 0
    healthy: bool = True
    safety_reserved: int = 0

    def available_slots(self, safety_tier: SafetyTier) -> int:
        available = self.max_workers - self.in_flight
        if safety_tier != "strict":
            available -= self.safety_reserved
        return max(0, available)

    def utilization(self) -> float:
        if self.max_workers <= 0:
            return 1.0 if self.in_flight > 0 else 0.0
        return max(0.0, min(1.0, self.in_flight / self.max_workers))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "location": self.location,
            "capability": self.capability,
            "max_workers": self.max_workers,
            "in_flight": self.in_flight,
            "healthy": self.healthy,
            "safety_reserved": self.safety_reserved,
            "utilization": round(self.utilization(), 3),
        }


def default_resource_pools(
    *,
    keep_reliability_reserve: bool = True,
) -> list[ResourcePoolState]:
    local_reserve = 1 if keep_reliability_reserve else 0
    return [
        ResourcePoolState(
            name="local_cpu_pool",
            location="local",
            capability="cpu",
            max_workers=2,
            safety_reserved=local_reserve,
        ),
        ResourcePoolState(
            name="local_gpu_pool",
            location="local",
            capability="gpu",
            max_workers=1,
        ),
        ResourcePoolState(
            name="cloud_cpu_pool",
            location="cloud",
            capability="cpu",
            max_workers=4,
        ),
        ResourcePoolState(
            name="cloud_gpu_pool",
            location="cloud",
            capability="gpu",
            max_workers=2,
        ),
        ResourcePoolState(
            name="api_model_pool",
            location="cloud",
            capability="api",
            max_workers=8,
        ),
    ]


@dataclass(slots=True, frozen=True)
class WorkloadRequest:
    workload_id: str
    capability: CapabilityClass
    safety_tier: SafetyTier = "standard"
    allow_degrade: bool = True


@dataclass(slots=True, frozen=True)
class WorkloadPressure:
    queue_depth: int
    p95_latency_seconds: float
    in_flight: int = 0
    retry_ratio: float = 0.0


@dataclass(slots=True, frozen=True)
class ScaleDecision:
    pool_name: str
    location: PoolLocation
    direction: ScaleDirection
    delta: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pool_name": self.pool_name,
            "location": self.location,
            "direction": self.direction,
            "delta": self.delta,
            "reason": self.reason,
        }


class ScaleHook(Protocol):
    def scale_out(
        self,
        *,
        pool_name: str,
        capability: ResolvedCapabilityClass,
        delta: int,
        reason: str,
    ) -> None: ...

    def scale_in(
        self,
        *,
        pool_name: str,
        capability: ResolvedCapabilityClass,
        delta: int,
        reason: str,
    ) -> None: ...


class NoOpScaleHook:
    def scale_out(
        self,
        *,
        pool_name: str,
        capability: ResolvedCapabilityClass,
        delta: int,
        reason: str,
    ) -> None:
        _ = pool_name, capability, delta, reason

    def scale_in(
        self,
        *,
        pool_name: str,
        capability: ResolvedCapabilityClass,
        delta: int,
        reason: str,
    ) -> None:
        _ = pool_name, capability, delta, reason


@dataclass(slots=True)
class ElasticScaleHooks:
    local_hook: ScaleHook = field(default_factory=NoOpScaleHook)
    cloud_hook: ScaleHook = field(default_factory=NoOpScaleHook)

    def apply(self, decision: ScaleDecision, *, capability: ResolvedCapabilityClass) -> None:
        hook = self.cloud_hook if decision.location == "cloud" else self.local_hook
        if decision.direction == "scale_out":
            hook.scale_out(
                pool_name=decision.pool_name,
                capability=capability,
                delta=decision.delta,
                reason=decision.reason,
            )
            return
        hook.scale_in(
            pool_name=decision.pool_name,
            capability=capability,
            delta=decision.delta,
            reason=decision.reason,
        )


@dataclass(slots=True)
class SchedulingPolicyConfig:
    high_pressure_queue_depth: int = 3
    high_pressure_latency_seconds: float = 4.0
    scale_out_queue_depth: int = 4
    scale_out_latency_seconds: float = 6.0
    scale_in_queue_depth: int = 0
    scale_in_max_utilization: float = 0.25
    allow_cloud_burst: bool = True
    strict_prefers_local: bool = True
    keep_reliability_reserve: bool = True

    def __post_init__(self) -> None:
        self.high_pressure_queue_depth = max(0, self.high_pressure_queue_depth)
        self.high_pressure_latency_seconds = max(0.0, self.high_pressure_latency_seconds)
        self.scale_out_queue_depth = max(0, self.scale_out_queue_depth)
        self.scale_out_latency_seconds = max(0.0, self.scale_out_latency_seconds)
        self.scale_in_queue_depth = max(0, self.scale_in_queue_depth)
        self.scale_in_max_utilization = min(1.0, max(0.0, self.scale_in_max_utilization))

    def pressure_level(self, pressure: WorkloadPressure) -> PressureLevel:
        if pressure.queue_depth >= self.high_pressure_queue_depth:
            return "high"
        if pressure.p95_latency_seconds >= self.high_pressure_latency_seconds:
            return "high"
        return "normal"


@dataclass(slots=True, frozen=True)
class SchedulingDecision:
    pool_name: str
    pool_location: PoolLocation
    pool_capability: ResolvedCapabilityClass
    degraded: bool
    pressure_level: PressureLevel
    reason: str
    execution_target: ExecutionTarget
    scale_actions: tuple[ScaleDecision, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "pool_name": self.pool_name,
            "pool_location": self.pool_location,
            "pool_capability": self.pool_capability,
            "degraded": self.degraded,
            "pressure_level": self.pressure_level,
            "reason": self.reason,
            "execution_target": {
                "provider": self.execution_target.provider,
                "model": self.execution_target.model,
            },
            "scale_actions": [action.to_dict() for action in self.scale_actions],
        }


def default_resource_pools(
    *,
    hardware_profile: HardwareProfile | None = None,
    keep_reliability_reserve: bool = True,
) -> list[ResourcePoolState]:
    if hardware_profile is None:
        return _legacy_default_resource_pools(keep_reliability_reserve=keep_reliability_reserve)
    profile = hardware_profile
    local_reserve = 1 if keep_reliability_reserve else 0
    local_cpu = max(1, min(profile.cpu_count, 2)) if profile.cpu_count else 2
    local_gpu = 1 if profile.has_gpu() else 0
    cloud_cpu = max(2, local_cpu)
    cloud_gpu = 1 if profile.has_gpu() else 0
    api_workers = max(4, local_cpu * 2)
    return [
        ResourcePoolState(
            name="local_cpu_pool",
            location="local",
            capability="cpu",
            max_workers=local_cpu,
            safety_reserved=local_reserve,
        ),
        ResourcePoolState(
            name="local_gpu_pool",
            location="local",
            capability="gpu",
            max_workers=local_gpu,
        ),
        ResourcePoolState(
            name="cloud_cpu_pool",
            location="cloud",
            capability="cpu",
            max_workers=cloud_cpu,
        ),
        ResourcePoolState(
            name="cloud_gpu_pool",
            location="cloud",
            capability="gpu",
            max_workers=cloud_gpu,
        ),
        ResourcePoolState(
            name="api_model_pool",
            location="cloud",
            capability="api",
            max_workers=api_workers,
        ),
    ]


def _legacy_default_resource_pools(
    *,
    keep_reliability_reserve: bool = True,
) -> list[ResourcePoolState]:
    local_reserve = 1 if keep_reliability_reserve else 0
    return [
        ResourcePoolState(
            name="local_cpu_pool",
            location="local",
            capability="cpu",
            max_workers=2,
            safety_reserved=local_reserve,
        ),
        ResourcePoolState(
            name="local_gpu_pool",
            location="local",
            capability="gpu",
            max_workers=1,
        ),
        ResourcePoolState(
            name="cloud_cpu_pool",
            location="cloud",
            capability="cpu",
            max_workers=4,
        ),
        ResourcePoolState(
            name="cloud_gpu_pool",
            location="cloud",
            capability="gpu",
            max_workers=2,
        ),
        ResourcePoolState(
            name="api_model_pool",
            location="cloud",
            capability="api",
            max_workers=8,
        ),
    ]


class ResourceScheduler:
    def __init__(
        self,
        *,
        primary_target: ExecutionTarget,
        provider_models: Mapping[str, str],
        failover_order: Sequence[str] = (),
        pools: Sequence[ResourcePoolState] | None = None,
        config: SchedulingPolicyConfig | None = None,
        scale_hooks: ElasticScaleHooks | None = None,
        hardware_profile: HardwareProfile | None = None,
    ) -> None:
        self.primary_target = primary_target
        self.config = config or SchedulingPolicyConfig()
        self.scale_hooks = scale_hooks or ElasticScaleHooks()
        self.hardware_profile = hardware_profile or HardwareProfile()
        self._lock = threading.Lock()

        pool_seed = (
            list(pools)
            if pools is not None
            else default_resource_pools(
                hardware_profile=hardware_profile,
                keep_reliability_reserve=self.config.keep_reliability_reserve,
            )
        )
        self._pools: dict[str, ResourcePoolState] = {
            pool.name: ResourcePoolState(
                name=pool.name,
                location=pool.location,
                capability=pool.capability,
                max_workers=max(0, int(pool.max_workers)),
                in_flight=max(0, int(pool.in_flight)),
                healthy=bool(pool.healthy),
                safety_reserved=max(0, int(pool.safety_reserved)),
            )
            for pool in pool_seed
        }

        self.provider_models = {
            str(provider): str(model)
            for provider, model in provider_models.items()
            if isinstance(provider, str) and isinstance(model, str)
        }
        self.provider_models.setdefault(primary_target.provider, primary_target.model)

        self._provider_order = _ordered_unique(
            [
                primary_target.provider,
                *[str(item) for item in failover_order],
                *self.provider_models.keys(),
            ]
        )

    def infer_capability_for_provider(self, provider: str) -> CapabilityClass:
        return infer_capability_for_provider(provider)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "high_pressure_queue_depth": self.config.high_pressure_queue_depth,
                "high_pressure_latency_seconds": self.config.high_pressure_latency_seconds,
                "scale_out_queue_depth": self.config.scale_out_queue_depth,
                "scale_out_latency_seconds": self.config.scale_out_latency_seconds,
                "scale_in_queue_depth": self.config.scale_in_queue_depth,
                "scale_in_max_utilization": self.config.scale_in_max_utilization,
                "allow_cloud_burst": self.config.allow_cloud_burst,
                "strict_prefers_local": self.config.strict_prefers_local,
                "provider_order": list(self._provider_order),
                "pools": [
                    self._pools[name].to_dict() for name in sorted(self._pools.keys())
                ],
            }

    def schedule(
        self,
        *,
        workload: WorkloadRequest,
        pressure: WorkloadPressure,
    ) -> SchedulingDecision:
        with self._lock:
            safety_tier: SafetyTier = (
                "strict"
                if str(workload.safety_tier).strip().lower() == "strict"
                else "standard"
            )
            requested_capability = _normalize_capability(workload.capability)
            pressure_level = self.config.pressure_level(pressure)

            selected_pool, pool_capability, degraded, reason = self._select_pool(
                requested_capability,
                safety_tier=safety_tier,
                pressure_level=pressure_level,
                allow_degrade=workload.allow_degrade,
            )

            scale_actions = tuple(self._decide_scaling(selected_pool, pressure=pressure))
            for action in scale_actions:
                self._apply_scale_action(action, capability=pool_capability)

            target = self._target_for_capability(pool_capability)
            selected_pool.in_flight += 1
            return SchedulingDecision(
                pool_name=selected_pool.name,
                pool_location=selected_pool.location,
                pool_capability=pool_capability,
                degraded=degraded,
                pressure_level=pressure_level,
                reason=reason,
                execution_target=target,
                scale_actions=scale_actions,
            )

    def release(self, pool_name: str) -> None:
        with self._lock:
            pool = self._pools.get(pool_name)
            if pool is None:
                return
            if pool.in_flight > 0:
                pool.in_flight -= 1

    def _preferred_location(
        self,
        *,
        safety_tier: SafetyTier,
        pressure_level: PressureLevel,
    ) -> PoolLocation:
        if safety_tier == "strict" and self.config.strict_prefers_local:
            return "local"
        if pressure_level == "high" and self.config.allow_cloud_burst:
            return "cloud"
        return "local"

    def _sorted_candidates(
        self,
        capability: ResolvedCapabilityClass,
        *,
        safety_tier: SafetyTier,
        pressure_level: PressureLevel,
    ) -> list[ResourcePoolState]:
        preferred_location = self._preferred_location(
            safety_tier=safety_tier,
            pressure_level=pressure_level,
        )
        candidates = [
            pool
            for pool in self._pools.values()
            if pool.healthy and pool.capability == capability
        ]
        return sorted(
            candidates,
            key=lambda pool: (
                0 if pool.location == preferred_location else 1,
                -pool.available_slots(safety_tier),
                pool.in_flight,
                -pool.max_workers,
                pool.name,
            ),
        )

    def _degradation_order(
        self,
        capability: ResolvedCapabilityClass,
    ) -> tuple[ResolvedCapabilityClass, ...]:
        if capability == "gpu":
            return ("cpu", "api")
        if capability == "cpu":
            return ("api",)
        return ("cpu",)

    def _select_pool(
        self,
        requested_capability: ResolvedCapabilityClass,
        *,
        safety_tier: SafetyTier,
        pressure_level: PressureLevel,
        allow_degrade: bool,
    ) -> tuple[ResourcePoolState, ResolvedCapabilityClass, bool, str]:
        preferred = self._sorted_candidates(
            requested_capability,
            safety_tier=safety_tier,
            pressure_level=pressure_level,
        )
        for pool in preferred:
            if pool.available_slots(safety_tier) > 0:
                return (
                    pool,
                    requested_capability,
                    False,
                    f"selected preferred capability '{requested_capability}'",
                )

        if allow_degrade:
            for degraded_capability in self._degradation_order(requested_capability):
                degraded_candidates = self._sorted_candidates(
                    degraded_capability,
                    safety_tier=safety_tier,
                    pressure_level=pressure_level,
                )
                for pool in degraded_candidates:
                    if pool.available_slots(safety_tier) > 0:
                        return (
                            pool,
                            degraded_capability,
                            True,
                            (
                                "degraded route from "
                                f"'{requested_capability}' to '{degraded_capability}'"
                            ),
                        )

        for pool in preferred:
            return (
                pool,
                requested_capability,
                True,
                f"preferred capability '{requested_capability}' saturated; using queued fallback",
            )

        if allow_degrade:
            for degraded_capability in self._degradation_order(requested_capability):
                degraded_candidates = self._sorted_candidates(
                    degraded_capability,
                    safety_tier=safety_tier,
                    pressure_level=pressure_level,
                )
                for pool in degraded_candidates:
                    return (
                        pool,
                        degraded_capability,
                        True,
                        (
                            f"all '{requested_capability}' pools unavailable; "
                            f"queued degraded route to '{degraded_capability}'"
                        ),
                    )

        raise RuntimeError(
            "No healthy resource pools available for workload capability "
            f"'{requested_capability}'."
        )

    def _target_for_capability(
        self,
        capability: ResolvedCapabilityClass,
    ) -> ExecutionTarget:
        for provider in self._provider_order:
            if capability not in provider_capabilities(provider):
                continue
            model = (
                self.primary_target.model
                if provider == self.primary_target.provider
                else self.provider_models.get(provider, "")
            )
            if model:
                return ExecutionTarget(provider=provider, model=model)
        return self.primary_target

    def _decide_scaling(
        self,
        pool: ResourcePoolState,
        *,
        pressure: WorkloadPressure,
    ) -> list[ScaleDecision]:
        actions: list[ScaleDecision] = []

        should_scale_out = (
            pressure.queue_depth >= self.config.scale_out_queue_depth
            or pressure.p95_latency_seconds >= self.config.scale_out_latency_seconds
        )
        if should_scale_out and (
            pool.location == "local" or self.config.allow_cloud_burst
        ):
            actions.append(
                ScaleDecision(
                    pool_name=pool.name,
                    location=pool.location,
                    direction="scale_out",
                    delta=1,
                    reason=(
                        "queue/latency pressure exceeded thresholds "
                        "for throughput balancing"
                    ),
                )
            )
            return actions

        should_scale_in = (
            pressure.queue_depth <= self.config.scale_in_queue_depth
            and pressure.p95_latency_seconds < self.config.high_pressure_latency_seconds
            and pool.utilization() <= self.config.scale_in_max_utilization
            and pool.max_workers > 1
        )
        if should_scale_in:
            actions.append(
                ScaleDecision(
                    pool_name=pool.name,
                    location=pool.location,
                    direction="scale_in",
                    delta=1,
                    reason="low utilization and queue pressure; reclaiming excess capacity",
                )
            )
        return actions

    def _apply_scale_action(
        self,
        decision: ScaleDecision,
        *,
        capability: ResolvedCapabilityClass,
    ) -> None:
        pool = self._pools.get(decision.pool_name)
        if pool is None:
            return

        if decision.direction == "scale_out":
            pool.max_workers = max(1, pool.max_workers + decision.delta)
        else:
            floor = max(1, pool.in_flight + pool.safety_reserved)
            pool.max_workers = max(floor, pool.max_workers - decision.delta)

        self.scale_hooks.apply(decision, capability=capability)


def _pool_location(value: Any, default: PoolLocation) -> PoolLocation:
    if str(value).strip().lower() == "cloud":
        return "cloud"
    if str(value).strip().lower() == "local":
        return "local"
    return default


def _pools_from_policy(
    raw_pools: Any,
    *,
    keep_reliability_reserve: bool,
    hardware_profile: HardwareProfile | None = None,
) -> list[ResourcePoolState]:
    base_pools = default_resource_pools(
        hardware_profile=hardware_profile,
        keep_reliability_reserve=keep_reliability_reserve,
    )
    pool_map = {pool.name: pool for pool in base_pools}
    base_order = [pool.name for pool in base_pools]

    if not isinstance(raw_pools, Mapping):
        return [pool_map[name] for name in base_order]

    for raw_name, raw_payload in raw_pools.items():
        if not isinstance(raw_name, str):
            continue
        if not isinstance(raw_payload, Mapping):
            continue

        existing = pool_map.get(raw_name)
        default_location: PoolLocation = "local"
        default_capability: ResolvedCapabilityClass = "cpu"
        default_max_workers = 1
        default_in_flight = 0
        default_healthy = True
        default_reserved = 0
        if existing is not None:
            default_location = existing.location
            default_capability = existing.capability
            default_max_workers = existing.max_workers
            default_in_flight = existing.in_flight
            default_healthy = existing.healthy
            default_reserved = existing.safety_reserved

        pool_map[raw_name] = ResourcePoolState(
            name=raw_name,
            location=_pool_location(raw_payload.get("location"), default_location),
            capability=_normalize_capability(
                raw_payload.get("capability", default_capability)
            ),
            max_workers=max(
                0,
                _coerce_int(raw_payload.get("max_workers"), default_max_workers),
            ),
            in_flight=max(
                0,
                _coerce_int(raw_payload.get("in_flight"), default_in_flight),
            ),
            healthy=bool(raw_payload.get("healthy", default_healthy)),
            safety_reserved=max(
                0,
                _coerce_int(raw_payload.get("safety_reserved"), default_reserved),
            ),
        )

    ordered_names = [*base_order]
    ordered_names.extend(
        name for name in sorted(pool_map.keys()) if name not in ordered_names
    )
    return [pool_map[name] for name in ordered_names]


def scheduler_from_chain_defaults(
    *,
    defaults: Mapping[str, Any],
    primary_target: ExecutionTarget,
    provider_models: Mapping[str, str],
    failover_order: Sequence[str],
    scale_hooks: ElasticScaleHooks | None = None,
    hardware_profile: HardwareProfile | None = None,
) -> ResourceScheduler:
    raw_policy = defaults.get("resource_policy", {})
    if not isinstance(raw_policy, Mapping):
        raw_policy = {}

    config = SchedulingPolicyConfig(
        high_pressure_queue_depth=max(
            0,
            _coerce_int(raw_policy.get("high_pressure_queue_depth"), 3),
        ),
        high_pressure_latency_seconds=max(
            0.0,
            _coerce_float(raw_policy.get("high_pressure_latency_seconds"), 4.0),
        ),
        scale_out_queue_depth=max(
            0,
            _coerce_int(raw_policy.get("scale_out_queue_depth"), 4),
        ),
        scale_out_latency_seconds=max(
            0.0,
            _coerce_float(raw_policy.get("scale_out_latency_seconds"), 6.0),
        ),
        scale_in_queue_depth=max(
            0,
            _coerce_int(raw_policy.get("scale_in_queue_depth"), 0),
        ),
        scale_in_max_utilization=min(
            1.0,
            max(
                0.0,
                _coerce_float(raw_policy.get("scale_in_max_utilization"), 0.25),
            ),
        ),
        allow_cloud_burst=bool(raw_policy.get("allow_cloud_burst", True)),
        strict_prefers_local=bool(raw_policy.get("strict_prefers_local", True)),
        keep_reliability_reserve=bool(
            raw_policy.get("keep_reliability_reserve", True)
        ),
    )

    pools = _pools_from_policy(
        raw_policy.get("pools"),
        keep_reliability_reserve=config.keep_reliability_reserve,
        hardware_profile=hardware_profile,
    )

    return ResourceScheduler(
        primary_target=primary_target,
        provider_models=provider_models,
        failover_order=failover_order,
        pools=pools,
        config=config,
        scale_hooks=scale_hooks,
        hardware_profile=hardware_profile,
    )
