from __future__ import annotations

from pathlib import Path

import pytest

from substrate.cache_store import CacheStore


@pytest.fixture
def cache_store(tmp_path: Path) -> CacheStore:
    return CacheStore(tmp_path / "cache")


def test_cache_key_is_deterministic(cache_store: CacheStore) -> None:
    key1 = cache_store.make_key("ai_call", {"provider": "openai", "prompt": "hello"})
    key2 = cache_store.make_key("ai_call", {"provider": "openai", "prompt": "hello"})
    assert key1 == key2
    assert len(key1) == 64


def test_store_and_retrieve(cache_store: CacheStore) -> None:
    key = cache_store.make_key("test", {"x": 1})
    cache_store.set(key, {"result": "ok"}, kind="test", summary="test result")
    assert cache_store.has(key)
    assert cache_store.get(key) == {"result": "ok"}
    assert cache_store.get_summary(key) == "test result"


def test_missing_key_returns_none(cache_store: CacheStore) -> None:
    key = cache_store.make_key("missing", {"x": 1})
    assert cache_store.get(key) is None
    assert cache_store.has(key) is False
    assert cache_store.get_summary(key) is None


def test_ttl_expiration(cache_store: CacheStore) -> None:
    key = cache_store.make_key("ttl", {"x": 1})
    cache_store.set(key, "value", kind="ttl", ttl_seconds=-1)
    # Negative TTL means already expired.
    assert cache_store.has(key) is False
    assert cache_store.get(key) is None


def test_invalidate_by_kind(cache_store: CacheStore) -> None:
    k1 = cache_store.make_key("a", {"x": 1})
    k2 = cache_store.make_key("b", {"x": 2})
    cache_store.set(k1, "a", kind="kind_a")
    cache_store.set(k2, "b", kind="kind_b")
    removed = cache_store.invalidate(kind="kind_a")
    assert removed == 1
    assert cache_store.get(k1) is None
    assert cache_store.get(k2) == "b"


def test_invalidate_by_tags(cache_store: CacheStore) -> None:
    k1 = cache_store.make_key("a", {"x": 1})
    cache_store.set(k1, "a", kind="test", tags={"tag_a", "tag_b"})
    removed = cache_store.invalidate(tags={"tag_a"})
    assert removed == 1
    assert cache_store.get(k1) is None


def test_prune_removes_old_entries(cache_store: CacheStore) -> None:
    k1 = cache_store.make_key("old", {"x": 1})
    cache_store.set(k1, "old", kind="test")
    result = cache_store.prune(max_age_days=0)
    assert result["total_removed"] == 1
    assert cache_store.get(k1) is None


def test_stats_tracks_entries_and_hits(cache_store: CacheStore) -> None:
    key = cache_store.make_key("stats", {"x": 1})
    cache_store.set(key, {"result": "ok"}, kind="test")
    cache_store.get(key)
    cache_store.get(key)
    stats = cache_store.stats()
    assert stats["entries"] == 1
    assert stats["total_hits"] == 2
    assert stats["kinds"]["test"] == 1


def test_list_entries_paginated(cache_store: CacheStore) -> None:
    for i in range(3):
        key = cache_store.make_key(f"list_{i}", {"x": i})
        cache_store.set(key, f"v{i}", kind="list_test")
    entries = cache_store.list_entries(kind="list_test", limit=2, offset=0)
    assert len(entries) == 2


def test_update_overwrites_existing(cache_store: CacheStore) -> None:
    key = cache_store.make_key("update", {"x": 1})
    cache_store.set(key, "first", kind="test")
    cache_store.set(key, "second", kind="test")
    assert cache_store.get(key) == "second"
