import time
import pytest
from src.backends.redis_backend import RedisBackend
from src.config import RateLimiterConfig
from src.algorithms.sliding_window_counter import SlidingWindowCounter

@pytest.fixture(autouse=True)
def flush_redis():
    backend = RedisBackend()
    backend.client.flushall()
    yield
    backend.client.flushall()

@pytest.fixture
def backend():
    return RedisBackend()

@pytest.fixture
def limiter(backend):
    config = RateLimiterConfig(limit=5, window=10)
    return SlidingWindowCounter(config, backend)


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

def test_counter_resets_after_window(backend):
    config = RateLimiterConfig(limit=3, window=2)
    limiter = SlidingWindowCounter(config, backend)
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is False
    time.sleep(2)
    assert limiter.is_allowed('user_1') is True
