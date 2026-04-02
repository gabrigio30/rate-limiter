import time
import pytest
from src.backends.redis_backend import RedisBackend
from src.config import RateLimiterConfig
from src.algorithms.token_bucket import TokenBucket

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
def config():
    return RateLimiterConfig(limit=5, window=10)

@pytest.fixture
def limiter(config, backend):
    return TokenBucket(config, backend)


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

def test_tokens_refill_over_time(config, backend):
    fast_config = RateLimiterConfig(limit=2, window=2)
    fast_limiter = TokenBucket(fast_config, backend)
    assert fast_limiter.is_allowed('user_1') is True
    assert fast_limiter.is_allowed('user_1') is True
    assert fast_limiter.is_allowed('user_1') is False
    time.sleep(2)
    assert fast_limiter.is_allowed('user_1') is True

def test_capacity_limits_burst(backend):
    config = RateLimiterConfig(limit=10, window=10, capacity=3)
    limiter = TokenBucket(config, backend)
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is True
    assert limiter.is_allowed('user_1') is False
