import time
import pytest
from atomic_rate_limiter import RedisBackend, RateLimiterConfig, SlidingWindowLog

@pytest.fixture
def backend():
    return RedisBackend()

@pytest.fixture
def limiter(backend):
    config = RateLimiterConfig(limit=5, window=10)
    return SlidingWindowLog(config, backend)


def test_allows_requests_within_limit(limiter):
    for _ in range(5):
        assert limiter.is_allowed('user_1') is True

def test_rejects_requests_over_limit(limiter):
    for _ in range(5):
        limiter.is_allowed('user_1')
    assert limiter.is_allowed('user_1') is False

def test_different_users_are_independent(limiter):
    for _ in range(5):
        limiter.is_allowed('user_1')
    assert limiter.is_allowed('user_2') is True

def test_old_requests_fall_outside_window(backend):
    config = RateLimiterConfig(limit=3, window=2)
    limiter = SlidingWindowLog(config, backend)
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is False
    time.sleep(2)
    assert limiter.is_allowed('user_1') is True

def test_window_is_sliding_not_fixed(backend):
    config = RateLimiterConfig(limit=3, window=3)
    limiter = SlidingWindowLog(config, backend)
    limiter.is_allowed('user_1')
    limiter.is_allowed('user_1')
    limiter.is_allowed('user_1')
    assert limiter.is_allowed('user_1') is False
    time.sleep(1.1)
    assert limiter.is_allowed('user_1') is False
    time.sleep(2)
    assert limiter.is_allowed('user_1') is True
