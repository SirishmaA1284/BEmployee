"""Simple in-process rate limiting (Phase 8, docs/security.md).

Per-IP sliding-window limits on the endpoints that need them (auth +
agent chat). In-memory and per-process — fine for the single-worker MVP
(ADR-007 has one worker, one API process); a distributed limiter (Redis)
is a documented scaling seam, not a claim of production-grade DDoS
protection.

`rate_limit(...)` is a FastAPI dependency factory:
    Depends(rate_limit(limit=10, window_seconds=60))

The bucket is keyed by (client_ip, route_path). Uses a fixed-window counter
reset on the window boundary (simple, deterministic, good enough for the
stated MVP goal of throttling brute-force / abuse).
"""

import time
from collections import defaultdict
from threading import Lock
from typing import Callable

from fastapi import HTTPException, Request, status


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


_counter = _FixedWindowCounter()


def reset_rate_limits() -> None:
    """Clear all rate-limit buckets. Exposed for tests so the in-memory
    limiter doesn't carry counts between test cases (each test's client
    presents as the same 'testserver' IP).
    """
    with _counter._lock:
        _counter._buckets.clear()


def rate_limit(*, limit: int, window_seconds: float) -> Callable:
    """Dependency factory: 429 when the client IP has exceeded `limit`
    requests in `window_seconds` for this route.
    """

    def _depends(request: Request) -> None:
        ip = request.client.host if request.client else "unknown"
        key = f"{ip}:{request.url.path}"
        if not _counter.check(key, limit, window_seconds):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Too many requests — please try again shortly.",
            )

    return _depends