from __future__ import annotations

import unittest

from substrate.reliability import ExecutionTarget
from substrate.resource_orchestration import (
    ElasticScaleHooks,
    NoOpScaleHook,
    ResourcePoolState,
    ResourceScheduler,
    SchedulingPolicyConfig,
    WorkloadPressure,
    WorkloadRequest,
)


class _RecordingScaleHook(NoOpScaleHook):
    def __init__(self) -> None:
        self.scale_out_calls: list[dict[str, str | int]] = []
        self.scale_in_calls: list[dict[str, str | int]] = []

    def scale_out(
        self,
        *,
        pool_name: str,
        capability: str,
        delta: int,
        reason: str,
    ) -> None:
        self.scale_out_calls.append(
            {
                "pool_name": pool_name,
                "capability": capability,
                "delta": delta,
                "reason": reason,
            }
        )

    def scale_in(
        self,
        *,
        pool_name: str,
        capability: str,
        delta: int,
        reason: str,
    ) -> None:
        self.scale_in_calls.append(
            {
                "pool_name": pool_name,
                "capability": capability,
                "delta": delta,
                "reason": reason,
            }
        )


class ResourceSchedulerPolicyTest(unittest.TestCase):
    def test_policy_routes_gpu_workload_to_gpu_provider(self) -> None:
        scheduler = ResourceScheduler(
            primary_target=ExecutionTarget(provider="local", model="gpt-primary"),
            provider_models={
                "local": "roo-router",
                "anthropic": "claude-fallback",
                "ollama": "llama3-local",
            },
            failover_order=["anthropic", "ollama"],
        )

        decision = scheduler.schedule(
            workload=WorkloadRequest(
                workload_id="gpu-route",
                capability="gpu",
                safety_tier="standard",
            ),
            pressure=WorkloadPressure(queue_depth=0, p95_latency_seconds=0.2),
        )

        self.assertEqual("local_gpu_pool", decision.pool_name)
        self.assertEqual("gpu", decision.pool_capability)
        self.assertFalse(decision.degraded)
        self.assertEqual("ollama", decision.execution_target.provider)
        self.assertEqual("llama3-local", decision.execution_target.model)

        scheduler.release(decision.pool_name)

    def test_degrades_when_gpu_pools_are_saturated(self) -> None:
        scheduler = ResourceScheduler(
            primary_target=ExecutionTarget(provider="local", model="gpt-primary"),
            provider_models={
                "local": "roo-router",
                "ollama": "llama3-local",
            },
            failover_order=["ollama"],
            pools=[
                ResourcePoolState(
                    name="local_gpu_pool",
                    location="local",
                    capability="gpu",
                    max_workers=1,
                    in_flight=1,
                ),
                ResourcePoolState(
                    name="cloud_gpu_pool",
                    location="cloud",
                    capability="gpu",
                    max_workers=1,
                    in_flight=1,
                ),
                ResourcePoolState(
                    name="local_cpu_pool",
                    location="local",
                    capability="cpu",
                    max_workers=2,
                    in_flight=0,
                ),
                ResourcePoolState(
                    name="api_model_pool",
                    location="cloud",
                    capability="api",
                    max_workers=8,
                    in_flight=0,
                ),
            ],
        )

        decision = scheduler.schedule(
            workload=WorkloadRequest(
                workload_id="gpu-degrade",
                capability="gpu",
                safety_tier="strict",
                allow_degrade=True,
            ),
            pressure=WorkloadPressure(queue_depth=5, p95_latency_seconds=8.0),
        )

        self.assertTrue(decision.degraded)
        self.assertEqual("cpu", decision.pool_capability)
        self.assertIn("degraded route", decision.reason)
        self.assertEqual("local_cpu_pool", decision.pool_name)

        scheduler.release(decision.pool_name)

    def test_scale_hooks_invoked_for_scale_out_and_scale_in(self) -> None:
        local_hook = _RecordingScaleHook()
        cloud_hook = _RecordingScaleHook()
        scheduler = ResourceScheduler(
            primary_target=ExecutionTarget(provider="local", model="gpt-primary"),
            provider_models={
                "local": "roo-router",
            },
            failover_order=[],
            pools=[
                ResourcePoolState(
                    name="local_cpu_pool",
                    location="local",
                    capability="cpu",
                    max_workers=3,
                    in_flight=0,
                ),
                ResourcePoolState(
                    name="cloud_cpu_pool",
                    location="cloud",
                    capability="cpu",
                    max_workers=1,
                    in_flight=0,
                ),
                ResourcePoolState(
                    name="api_model_pool",
                    location="cloud",
                    capability="api",
                    max_workers=6,
                    in_flight=0,
                ),
            ],
            config=SchedulingPolicyConfig(
                high_pressure_queue_depth=2,
                high_pressure_latency_seconds=3.0,
                scale_out_queue_depth=2,
                scale_out_latency_seconds=4.0,
                scale_in_queue_depth=0,
                scale_in_max_utilization=0.2,
                allow_cloud_burst=True,
            ),
            scale_hooks=ElasticScaleHooks(local_hook=local_hook, cloud_hook=cloud_hook),
        )

        scale_out_decision = scheduler.schedule(
            workload=WorkloadRequest(workload_id="cpu-scale-out", capability="cpu"),
            pressure=WorkloadPressure(queue_depth=4, p95_latency_seconds=6.0),
        )
        self.assertEqual("cloud_cpu_pool", scale_out_decision.pool_name)
        self.assertEqual(1, len(cloud_hook.scale_out_calls))
        self.assertEqual(0, len(local_hook.scale_out_calls))
        scheduler.release(scale_out_decision.pool_name)

        scale_in_decision = scheduler.schedule(
            workload=WorkloadRequest(workload_id="cpu-scale-in", capability="cpu"),
            pressure=WorkloadPressure(queue_depth=0, p95_latency_seconds=0.1),
        )
        self.assertEqual("local_cpu_pool", scale_in_decision.pool_name)
        self.assertEqual(1, len(local_hook.scale_in_calls))
        scheduler.release(scale_in_decision.pool_name)

    def test_stability_under_mixed_workload_inputs(self) -> None:
        scheduler = ResourceScheduler(
            primary_target=ExecutionTarget(provider="local", model="gpt-primary"),
            provider_models={
                "local": "roo-router",
                "anthropic": "claude-fallback",
                "ollama": "llama3-local",
            },
            failover_order=["anthropic", "ollama"],
        )

        held: list[str] = []
        decisions = []
        capabilities = ["api", "cpu", "gpu", "model", "cpu", "gpu"]
        for index in range(36):
            capability = capabilities[index % len(capabilities)]
            decision = scheduler.schedule(
                workload=WorkloadRequest(
                    workload_id=f"mixed-{index}",
                    capability=capability,  # type: ignore[arg-type]
                    allow_degrade=True,
                ),
                pressure=WorkloadPressure(
                    queue_depth=index % 6,
                    p95_latency_seconds=float((index * 3) % 9),
                ),
            )
            decisions.append(decision)
            if index % 4 == 0:
                held.append(decision.pool_name)
            else:
                scheduler.release(decision.pool_name)
            if index % 5 == 0 and held:
                scheduler.release(held.pop(0))

        for pool_name in held:
            scheduler.release(pool_name)

        snapshot = scheduler.snapshot()
        pools = snapshot["pools"]
        self.assertEqual(36, len(decisions))
        self.assertTrue(all(decision.pool_name for decision in decisions))
        self.assertTrue(all(decision.execution_target.provider for decision in decisions))
        self.assertTrue(all(decision.execution_target.model for decision in decisions))
        self.assertTrue(all(pool["in_flight"] >= 0 for pool in pools))
        self.assertTrue(all(pool["max_workers"] >= 1 for pool in pools))


if __name__ == "__main__":
    unittest.main()
