import time
from src.backends.redis_backend import RedisBackend
from src.config import RateLimiterConfig

SCRIPT = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])
local window_start = now - window
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local count = redis.call('ZCARD', key)

if count < limit then
    redis.call('ZADD', key, now, now)
    redis.call('EXPIRE', key, window)
    return 1
else
    return 0
end
"""

class SlidingWindowLog:
    def __init__(self, config: RateLimiterConfig, backend: RedisBackend):
        self.config = config
        self.backend = backend

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        result = self.backend.eval(
            SCRIPT,
            keys=[f"rate_limit:sliding_window_log:{key}"],
            args=[self.config.limit, self.config.window, now]
        )
        return result == 1