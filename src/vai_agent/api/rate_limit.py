"""In-process rate limiting for HTTP handlers (per user, IP, group, daily, concurrency)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    allowed: bool
    reason: str | None = None


class SlidingWindowRateLimiter:
    """Sliding-window + optional in-flight cap (thread-safe, in-memory)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._active: dict[str, int] = defaultdict(int)

    def _allow_window(self, key: str, *, limit: int, window_seconds: float) -> bool:
        now = time.monotonic()
        cutoff = now - window_seconds
        bucket = self._hits[key]
        bucket[:] = [t for t in bucket if t >= cutoff]
        if len(bucket) >= limit:
            return False
        bucket.append(now)
        return True

    def allow_request(
        self,
        *,
        user_id: str,
        ip: str,
        groups: list[str],
        settings: object,
    ) -> RateLimitDecision:
        per_user = int(getattr(settings, "rate_limit_per_user_per_minute", 120))
        per_ip = int(getattr(settings, "rate_limit_per_ip_per_minute", 240))
        per_group = int(getattr(settings, "rate_limit_per_group_per_minute", 500))
        daily = int(getattr(settings, "rate_limit_per_user_per_day", 2000))

        with self._lock:
            if not self._allow_window(f"user:min:{user_id}", limit=per_user, window_seconds=60):
                return RateLimitDecision(False, "Per-user minute limit exceeded.")

            if not self._allow_window(f"ip:min:{ip}", limit=per_ip, window_seconds=60):
                return RateLimitDecision(False, "Per-IP minute limit exceeded.")

            if not self._allow_window(f"user:day:{user_id}", limit=daily, window_seconds=86400):
                return RateLimitDecision(False, "Daily user limit exceeded.")

            for group in groups or ["anonymous"]:
                if not self._allow_window(f"group:min:{group}", limit=per_group, window_seconds=60):
                    return RateLimitDecision(False, f"Group limit exceeded: {group}")

        return RateLimitDecision(True)

    def try_acquire_concurrency(self, key: str, *, limit: int) -> RateLimitDecision:
        with self._lock:
            if self._active[key] >= limit:
                return RateLimitDecision(False, "Concurrent request limit exceeded.")
            self._active[key] += 1
        return RateLimitDecision(True)

    def release_concurrency(self, key: str) -> None:
        with self._lock:
            self._active[key] = max(0, self._active[key] - 1)


_LIMITER = SlidingWindowRateLimiter()


def get_rate_limiter() -> SlidingWindowRateLimiter:
    return _LIMITER
