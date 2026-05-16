"""Rate limiter decisions for sliding windows."""

from __future__ import annotations

from vai_agent.api.rate_limit import SlidingWindowRateLimiter, get_rate_limiter


class _S:
    rate_limit_per_user_per_minute = 2
    rate_limit_per_ip_per_minute = 100
    rate_limit_per_group_per_minute = 100
    rate_limit_per_user_per_day = 1000
    rate_limit_max_concurrent_per_user = 5


def test_per_user_minute_limit() -> None:
    lim = SlidingWindowRateLimiter()
    s = _S()
    assert lim.allow_request(user_id="u1", ip="1.1.1.1", groups=["analyst"], settings=s).allowed
    assert lim.allow_request(user_id="u1", ip="1.1.1.1", groups=["analyst"], settings=s).allowed
    d = lim.allow_request(user_id="u1", ip="1.1.1.1", groups=["analyst"], settings=s)
    assert not d.allowed


def test_get_rate_limiter_singleton() -> None:
    assert get_rate_limiter() is get_rate_limiter()


def test_concurrency_second_acquire_fails_until_release() -> None:
    lim = SlidingWindowRateLimiter()
    key = "user:conc_test"
    assert lim.try_acquire_concurrency(key, limit=1).allowed
    assert not lim.try_acquire_concurrency(key, limit=1).allowed
    lim.release_concurrency(key)
    assert lim.try_acquire_concurrency(key, limit=1).allowed
    lim.release_concurrency(key)
