from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from .cache_store import CacheStore


class TaskCache:
    """Cache-aware task decomposition and AI-call memoization.

    Large or recurring objectives are split into smaller, independently cacheable
    subtasks.  Each subtask result is stored with a short summary so future runs
    can reuse previous reasoning without repeating the same AI calls.

    The cache store is intentionally decoupled: it is provided by the caller so
    the same cache can be shared across orchestrator, CLI, and scheduled jobs.
    """

    def __init__(self, store: CacheStore) -> None:
        self.store = store

    @staticmethod
    def summarize(text: str, max_lines: int = 5, max_chars: int = 400) -> str:
        """Return a short, deterministic extractive summary of ``text``."""
        if not text:
            return ""
        lines = text.splitlines()
        non_empty = [line.strip() for line in lines if line.strip()]
        if not non_empty:
            return ""
        summary_lines: list[str] = []
        length = 0
        for line in non_empty[:max_lines]:
            if length + len(line) > max_chars:
                remaining = max_chars - length
                if remaining > 20:
                    summary_lines.append(line[:remaining] + "...")
                break
            summary_lines.append(line)
            length += len(line) + 1
        return " | ".join(summary_lines)

    def _subtask_key(
        self,
        objective: str,
        context: str,
        subtask_index: int,
        subtask_prompt: str,
        provider: str,
        model: str,
    ) -> str:
        return self.store.make_key(
            "subtask",
            {
                "objective": objective.strip().lower(),
                "context": context.strip().lower(),
                "index": subtask_index,
                "subtask": subtask_prompt.strip().lower(),
                "provider": provider,
                "model": model,
            },
        )

    def _call_key(
        self,
        provider: str,
        model: str,
        prompt: str,
        temperature: float | None,
    ) -> str:
        return self.store.make_key(
            "ai_call",
            {
                "provider": provider,
                "model": model,
                "prompt": prompt.strip(),
                "temperature": temperature,
            },
        )

    def cached_invoke(
        self,
        provider: str,
        model: str,
        prompt: str,
        runner: Callable[[str], str],
        *,
        temperature: float | None = None,
        ttl_seconds: int | None = None,
        tags: list[str] | None = None,
        use_cache: bool = True,
    ) -> tuple[str, dict[str, Any]]:
        """Invoke ``runner(prompt)`` and cache the result.

        Returns ``(result, metadata)``.  When ``use_cache`` is False the runner is
        always executed and nothing is written to the cache.
        """
        if not use_cache:
            result = runner(prompt)
            return result, {"cached": False, "skipped": True}

        key = self._call_key(provider, model, prompt, temperature)
        cached = self.store.get(key)
        if cached is not None:
            return cached, {"cached": True, "key": key}

        result = runner(prompt)
        summary = self.summarize(result)
        self.store.set(
            key,
            result,
            kind="ai_call",
            summary=summary,
            tags=set(tags or []) | {"ai_call", provider, model},
            ttl_seconds=ttl_seconds,
        )
        return result, {"cached": False, "key": key, "summary": summary}

    def decompose(self, objective: str, context: str) -> list[str]:
        """Split an objective into a small list of atomic subtask prompts.

        This is a deterministic, rule-based splitter that does not require an
        AI call.  It keeps the decomposition stable so the cache keys for
        subtasks remain consistent across runs.
        """
        # Normalize the objective and break it on obvious action boundaries.
        text = f"{objective.strip()} {context.strip()}".strip()
        if not text:
            return []

        # Split on common sequencing punctuation, then on numbered/bulleted items.
        parts = re.split(r"\s*(?:\n|\.|;|\band then\b|\bfollowed by\b|\bnext\b)\s+", text, flags=re.IGNORECASE)
        parts = [part.strip() for part in parts if part.strip()]

        subtasks: list[str] = []
        for part in parts:
            # Drop leading numbers/bullets.
            cleaned = re.sub(r"^\s*[-*\d\.)\]]+\s+", "", part).strip()
            if cleaned and len(cleaned) > 10:
                subtasks.append(cleaned)

        if not subtasks:
            subtasks = [text]

        # Cap at a small number so the orchestration stays manageable.
        max_subtasks = 5
        if len(subtasks) > max_subtasks:
            merged = []
            chunk_size = (len(subtasks) + max_subtasks - 1) // max_subtasks
            for i in range(0, len(subtasks), chunk_size):
                chunk = subtasks[i : i + chunk_size]
                merged.append("; ".join(chunk))
            subtasks = merged

        return subtasks

    def run_cached_subtasks(
        self,
        objective: str,
        context: str,
        runner: Callable[[str], str],
        *,
        provider: str = "unknown",
        model: str = "unknown",
        ttl_seconds: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Decompose ``objective`` and run each subtask through the cache.

        Returns a dict with the assembled result, per-subtask metadata, and
        cache statistics.  Subtasks that hit the cache contribute their stored
        summary to the trace, while missing subtasks execute ``runner`` and are
        written back.
        """
        subtasks = self.decompose(objective, context)
        if not subtasks:
            return {
                "objective": objective,
                "context": context,
                "subtasks": [],
                "result": "",
                "cache_hits": 0,
                "cache_misses": 0,
                "ai_calls_avoided": 0,
            }

        subtask_results: list[str] = []
        metadata: list[dict[str, Any]] = []
        hits = 0
        misses = 0

        for index, subtask_prompt in enumerate(subtasks):
            key = self._subtask_key(
                objective, context, index, subtask_prompt, provider, model
            )
            cached = self.store.get(key) if use_cache else None
            if cached is not None:
                subtask_results.append(cached)
                hits += 1
                summary = self.store.get_summary(key) or self.summarize(cached)
                metadata.append(
                    {
                        "index": index,
                        "prompt": subtask_prompt,
                        "key": key,
                        "cached": True,
                        "summary": summary,
                    }
                )
                continue

            result = runner(subtask_prompt)
            summary = self.summarize(result)
            subtask_results.append(result)
            misses += 1
            if use_cache:
                self.store.set(
                    key,
                    result,
                    kind="subtask",
                    summary=summary,
                    tags={"subtask", provider, model},
                    ttl_seconds=ttl_seconds,
                )
            metadata.append(
                {
                    "index": index,
                    "prompt": subtask_prompt,
                    "key": key,
                    "cached": False,
                    "summary": summary,
                }
            )

        assembled = "\n\n".join(
            f"### Subtask {i + 1}\n{result}" for i, result in enumerate(subtask_results)
        )
        return {
            "objective": objective,
            "context": context,
            "subtasks": metadata,
            "result": assembled,
            "cache_hits": hits,
            "cache_misses": misses,
            "ai_calls_avoided": hits,
        }

    def cached_plan(
        self,
        objective: str,
        context: str,
        planner: Callable[[str], str],
        *,
        provider: str = "unknown",
        model: str = "unknown",
        ttl_seconds: int | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Cache a high-level plan for an objective.

        The plan is stored under a single key derived from the objective.  If a
        cached plan exists, it is returned directly; otherwise ``planner`` is
        invoked and the result is stored with a summary.
        """
        key = self.store.make_key(
            "plan", {"objective": objective.strip(), "context": context.strip()}
        )
        if use_cache:
            cached = self.store.get(key)
            if cached is not None:
                return {
                    "plan": cached,
                    "cached": True,
                    "key": key,
                    "summary": self.store.get_summary(key) or self.summarize(cached),
                }

        plan = planner(f"Objective: {objective}\nContext: {context}")
        summary = self.summarize(plan)
        if use_cache:
            self.store.set(
                key,
                plan,
                kind="plan",
                summary=summary,
                tags={"plan", provider, model},
                ttl_seconds=ttl_seconds,
            )
        return {
            "plan": plan,
            "cached": False,
            "key": key,
            "summary": summary,
        }

    def load_trace(self, objective: str, context: str) -> dict[str, Any] | None:
        """Return a lightweight trace of cached results for an objective.

        Useful for debugging or for assembling a final report from summaries
        without loading every full blob.
        """
        subtasks = self.decompose(objective, context)
        trace = []
        for index, subtask_prompt in enumerate(subtasks):
            key = self._subtask_key(objective, context, index, subtask_prompt, "unknown", "unknown")
            summary = self.store.get_summary(key)
            if summary is not None:
                trace.append(
                    {
                        "index": index,
                        "prompt": subtask_prompt,
                        "summary": summary,
                        "cached": self.store.has(key),
                    }
                )
        return {"objective": objective, "subtasks": trace} if trace else None
