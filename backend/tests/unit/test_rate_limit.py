"""Rate limiter unit tests (Phase 8 in-process + Phase 9 Redis backend).

The Redis backend is tested against a fake client/pipeline (no real Redis
needed in CI): it must count via INCR + EXPIRE and enforce the limit. The
in-process counter is tested for window reset semantics.
"""

from app.security.rate_limit import (
    _FixedWindowCounter,
    _RedisFixedWindowCounter,
    _memory,
    reset_rate_limits,
)


class FakePipeline:
    def __init__(self, client) -> None:
        self._client = client
        self._commands: list[tuple] = []

    def incr(self, key: str) -> "FakePipeline":
        self._commands.append(("incr", key))
        return self

    def expire(self, key: str, ttl: int) -> "FakePipeline":
        self._commands.append(("expire", key, ttl))
        return self

    async def execute(self) -> list:
        results = []
        for command in self._commands:
            if command[0] == "incr":
                key = command[1]
                self._client.counts[key] = self._client.counts.get(key, 0) + 1
                results.append(self._client.counts[key])
            else:
                results.append(True)
        return results


class FakeRedisClient:
    def __init__(self) -> None:
        self.counts: dict[str, int] = {}

    def pipeline(self) -> FakePipeline:
        return FakePipeline(self)


def test_fixed_window_counter_enforces_limit_and_resets():
    counter = _FixedWindowCounter()
    key = "1.2.3.4:/api/auth/login"
    assert all(counter.check(key, limit=3, window_seconds=60) for _ in range(3))
    assert counter.check(key, limit=3, window_seconds=60) is False
    # Window elapsed -> budget refreshed.
    counter._buckets[key] = (counter._buckets[key][0] - 61, 3)
    assert counter.check(key, limit=3, window_seconds=60) is True


async def test_redis_counter_counts_per_key_with_prefix():
    client = FakeRedisClient()
    counter = _RedisFixedWindowCounter(client)
    key = "1.2.3.4:/api/agent/chat"
    assert await counter.check(key, limit=20, window_seconds=60) is True
    assert await counter.check("other:/x", limit=20, window_seconds=60) is True
    assert client.counts["ratelimit:other:/x"] == 1


async def test_redis_counter_blocks_over_limit():
    client = FakeRedisClient()
    counter = _RedisFixedWindowCounter(client)
    key = "9.9.9.9:/api/auth/register"
    for _ in range(2):
        assert await counter.check(key, limit=2, window_seconds=60) is True
    assert await counter.check(key, limit=2, window_seconds=60) is False


async def test_redis_counter_sets_expiry_on_every_check():
    seen: list[tuple] = []

    class SpyPipeline(FakePipeline):
        def expire(self, key: str, ttl: int) -> "SpyPipeline":
            seen.append((key, ttl))
            return super().expire(key, ttl)

    class SpyClient(FakeRedisClient):
        def pipeline(self) -> SpyPipeline:
            return SpyPipeline(self)

    counter = _RedisFixedWindowCounter(SpyClient())
    await counter.check("k", limit=5, window_seconds=120)
    await counter.check("k", limit=5, window_seconds=120)
    # Every check pushes a self-expiring TTL for the window.
    assert seen == [("ratelimit:k", 120), ("ratelimit:k", 120)]


def test_reset_rate_limits_clears_memory_buckets():
    key = "reset-test:/api/auth/login"
    assert _memory.check(key, limit=1, window_seconds=60) is True
    assert _memory.check(key, limit=1, window_seconds=60) is False
    reset_rate_limits()
    assert _memory.check(key, limit=1, window_seconds=60) is True


async def test_redis_counter_is_async():
    """The Redis path is async (pipeline.execute is awaited); a real
    pipeline would need an event loop — the fake keeps it loop-free."""
    client = FakeRedisClient()
    counter = _RedisFixedWindowCounter(client)
    assert await counter.check("x:y", limit=1, window_seconds=60) is True
    assert await counter.check("x:y", limit=1, window_seconds=60) is False