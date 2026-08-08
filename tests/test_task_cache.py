from __future__ import annotations

from pathlib import Path

import pytest

from substrate.cache_store import CacheStore
from substrate.task_cache import TaskCache


@pytest.fixture
def task_cache(tmp_path: Path) -> TaskCache:
    return TaskCache(CacheStore(tmp_path / "cache"))


def test_summarize_trims_long_text(task_cache: TaskCache) -> None:
    text = "Line one.\nLine two.\nLine three.\nLine four.\nLine five.\nLine six."
    summary = task_cache.summarize(text, max_lines=3, max_chars=200)
    assert "Line one" in summary
    assert "Line six" not in summary


def test_summarize_empty(task_cache: TaskCache) -> None:
    assert task_cache.summarize("") == ""


def test_decompose_splits_objective(task_cache: TaskCache) -> None:
    objective = "First research the topic. Then write a summary. Finally review it."
    subtasks = task_cache.decompose(objective, "")
    assert len(subtasks) >= 2
    assert all(len(st) > 10 for st in subtasks)


def test_cached_invoke_avoids_runner_on_hit(task_cache: TaskCache) -> None:
    calls: list[str] = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return f"result for {prompt}"

    result1, meta1 = task_cache.cached_invoke(
        "openai", "gpt-4", "prompt", runner, temperature=0
    )
    result2, meta2 = task_cache.cached_invoke(
        "openai", "gpt-4", "prompt", runner, temperature=0
    )
    assert result1 == result2 == "result for prompt"
    assert meta1["cached"] is False
    assert meta2["cached"] is True
    assert len(calls) == 1


def test_cached_invoke_respects_no_cache(task_cache: TaskCache) -> None:
    calls: list[str] = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return "x"

    task_cache.cached_invoke("p", "m", "q", runner, use_cache=False)
    task_cache.cached_invoke("p", "m", "q", runner, use_cache=False)
    assert len(calls) == 2


def test_run_cached_subtasks_reuses_results(task_cache: TaskCache) -> None:
    calls: list[str] = []

    def runner(prompt: str) -> str:
        calls.append(prompt)
        return f"done: {prompt}"

    objective = "Step A. Step B."
    result1 = task_cache.run_cached_subtasks(
        objective, "ctx", runner, provider="openai", model="gpt-4"
    )
    result2 = task_cache.run_cached_subtasks(
        objective, "ctx", runner, provider="openai", model="gpt-4"
    )
    assert result1["result"] == result2["result"]
    assert result1["cache_misses"] == len(task_cache.decompose(objective, "ctx"))
    assert result2["cache_hits"] == len(task_cache.decompose(objective, "ctx"))
    assert result2["ai_calls_avoided"] == len(task_cache.decompose(objective, "ctx"))
    assert len(calls) == len(task_cache.decompose(objective, "ctx"))


def test_cached_plan_stores_and_reuses(task_cache: TaskCache) -> None:
    calls: list[str] = []

    def planner(prompt: str) -> str:
        calls.append(prompt)
        return "plan: do x then y"

    r1 = task_cache.cached_plan("obj", "ctx", planner)
    r2 = task_cache.cached_plan("obj", "ctx", planner)
    assert r1["plan"] == r2["plan"]
    assert r1["cached"] is False
    assert r2["cached"] is True
    assert len(calls) == 1


def test_load_trace_returns_summaries(task_cache: TaskCache) -> None:
    def runner(prompt: str) -> str:
        return f"output for {prompt}"

    objective = "Do thing one. Do thing two."
    task_cache.run_cached_subtasks(objective, "", runner)
    trace = task_cache.load_trace(objective, "")
    assert trace is not None
    assert len(trace["subtasks"]) == len(task_cache.decompose(objective, ""))
    for item in trace["subtasks"]:
        assert "summary" in item
        assert item["cached"] is True
