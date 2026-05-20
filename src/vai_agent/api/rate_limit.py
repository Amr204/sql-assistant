"""In-process rate limiting for HTTP handlers (per user, IP, group, daily, concurrency)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class RateLimitDecision:
    """RateLimitDecision."""
    allowed: bool
    reason: str | None = None


class SlidingWindowRateLimiter:
    """Sliding-window + optional in-flight cap (thread-safe, in-memory)."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, list[float]] = defaultdict(list)
        self._active: dict[str, int] = defaultdict(int)

    def _prune_idle_active(self) -> None:
        """Drop concurrency counters that reached zero (keys never appear in ``_hits``)."""
        idle = [k for k, v in self._active.items() if v <= 0]
        for k in idle:
            del self._active[k]

    def _cleanup_expired(self) -> None:
        """Remove hit buckets with no activity in the last 24 hours."""
        now = time.monotonic()
        cutoff = now - 86400
        expired = [k for k, v in self._hits.items() if v and v[-1] < cutoff]
        for k in expired:
            del self._hits[k]
            self._active.pop(k, None)
        self._prune_idle_active()

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
        """Return whether the request is within rate limits."""
        per_user = int(getattr(settings, "rate_limit_per_user_per_minute", 120))
        per_ip = int(getattr(settings, "rate_limit_per_ip_per_minute", 240))
        per_group = int(getattr(settings, "rate_limit_per_group_per_minute", 500))
        daily = int(getattr(settings, "rate_limit_per_user_per_day", 2000))

        with self._lock:
            if len(self._hits) % 50 == 0:
                self._cleanup_expired()
            elif len(self._active) % 50 == 0:
                self._prune_idle_active()
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
        """Increment in-flight counter; fail when at limit."""
        with self._lock:
            if self._active[key] >= limit:
                return RateLimitDecision(False, "Concurrent request limit exceeded.")
            self._active[key] += 1
        return RateLimitDecision(True)

    def release_concurrency(self, key: str) -> None:
        """Decrement in-flight counter and prune idle keys."""
        with self._lock:
            if key not in self._active:
                return
            self._active[key] = max(0, self._active[key] - 1)
            if self._active[key] == 0:
                del self._active[key]


_LIMITER = SlidingWindowRateLimiter()


def get_rate_limiter() -> SlidingWindowRateLimiter:
    """Return the process-wide rate limiter singleton."""
    return _LIMITER
