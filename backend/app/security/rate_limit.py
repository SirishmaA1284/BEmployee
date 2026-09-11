"""Rate limiting (Phase 8 in-process, Phase 9 distributed via Redis).

Per-IP fixed-window limits on the endpoints that need them (auth + agent
chat). Two backends behind one interface:

- `_FixedWindowCounter` — in-process, threaded (Phase 8). Fine for the
  single-instance MVP and for tests (no external dependency).
- `_RedisFixedWindowCounter` — Redis INCR + EXPIRE (Phase 9), so multiple
  API instances share one budget. Used when `REDIS_URL` is configured;
  `init_rate_limiter()` (called from the FastAPI lifespan) pings Redis once
  and falls back to the in-process counter with a warning when it is
  unreachable, so a Redis outage never takes the API down.

`rate_limit(...)` is a FastAPI dependency factory:
    Depends(rate_limit(limit=10, window_seconds=60))

The bucket is keyed by (client_ip, route_path). Uses a fixed-window counter
reset on the window boundary (simple, deterministic, good enough for the
stated goal of throttling brute-force / abuse).
"""

import logging
import time
from threading import Lock
from typing import Callable

from fastapi import HTTPException, Request, status

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class _FixedWindowCounter:
    def __init__(self) -> None:
        self._lock = Lock()
        # key -> (window_start, count)
        self._buckets: dict[str, tuple[float, int]] = {}

    def check(self, key: str, limit: int, window_seconds: float) -> bool:
        """Returns True when the key is under the limit, False when over.
        Advances the window when it has elapsed."""
        now = time.monotonic()
        with self._lock:
            start, count = self._buckets.get(key, (now, 0))
            if now - start >= window_seconds:
                start, count = now, 0
            count += 1
            self._buckets[key] = (start, count)
            return count <= limit


class _RedisFixedWindowCounter:
    def __init__(self, client) -> None:
        self._client = client

    async def check(self, key: str, limit: int, window_seconds: float) -> bool:
        """Fixed-window counter in Redis: INCR + EXPIRE in one pipeline so
        every instance sees the same window and the key self-expires."""
        redis_key = f"ratelimit:{key}"
        pipeline = self._client.pipeline()
        pipeline.incr(redis_key)
        pipeline.expire(redis_key, int(window_seconds))
        count, _ = await pipeline.execute()
        return int(count) <= limit


_memory = _FixedWindowCounter()
_redis_counter: _RedisFixedWindowCounter | None = None


async def init_rate_limiter() -> None:
    """Connect the Redis-backed limiter when REDIS_URL is configured.
    Called once from the FastAPI lifespan. Falls back to the in-process
    counter (with a logged warning) when Redis is unreachable so the API
    keeps serving requests.
    """
    global _redis_counter
    settings = get_settings()
    if not settings.redis_url:
        _redis_counter = None
        return
    import redis.asyncio as aioredis

    client = aioredis.from_url(settings.redis_url, decode_responses=True)
    try:
        await client.ping()
    except Exception as exc:  # connection refused / DNS / auth — fail soft
        logger.warning(
            "Redis at %s unreachable (%s); using in-process rate limiting",
            settings.redis_url,
            exc,
        )
        await client.aclose()
        _redis_counter = None
        return
    _redis_counter = _RedisFixedWindowCounter(client)
    logger.info("Rate limiter using Redis at %s", settings.redis_url)


def reset_rate_limits() -> None:
    """Clear the in-process rate-limit buckets. Exposed for tests so the
    limiter doesn't carry counts between test cases (each test's client
    presents as the same 'testserver' IP). Redis buckets expire on their
    window and are not touched here.
    """
    with _memory._lock:
        _memory._buckets.clear()


def rate_limit(*, limit: int, window_seconds: float) -> Callable:
    """Dependency factory: 429 when the client IP has exceeded `limit`
    requests in `window_seconds` for this route.
    """

    async def _depends(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        key = f"{ip}:{request.url.path}"

        if _redis_counter is not None:
            try:
                over = not await _redis_counter.check(key, limit, window_seconds)
            except Exception as exc:  # Redis went down mid-flight — fail soft
                logger.warning("Redis rate-limit check failed (%s); falling back", exc)
                over = not _memory.check(key, limit, window_seconds)
        else:
            over = not _memory.check(key, limit, window_seconds)

        if over:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please try again shortly.",
            )

    return _depends