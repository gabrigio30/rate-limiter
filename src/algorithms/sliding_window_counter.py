import time
from src.backends.redis_backend import RedisBackend
from src.config import RateLimiterConfig

SCRIPT = """
local curr_key = KEYS[1]
local prev_key = KEYS[2]
local limit = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local curr_window = math.floor(now / window)
local elapsed = (now / window) - curr_window
local prev_weight = 1 - elapsed

local prev_count = tonumber(redis.call('GET', prev_key)) or 0
local curr_count = tonumber(redis.call('GET', curr_key)) or 0

local weighted_count = prev_count * prev_weight + curr_count

if weighted_count < limit then
    redis.call('INCR', curr_key)
    redis.call('EXPIRE', curr_key, window * 2)
    return 1
else
    return 0
end
"""

class SlidingWindowCounter:
    def __init__(self, config: RateLimiterConfig, backend: RedisBackend):
        self.config = config
        self.backend = backend

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        curr_window = int(now / self.config.window)
        prev_window = curr_window - 1
        curr_key = f"rate_limit:sliding_window_counter:{key}:{curr_window}"
        prev_key = f"rate_limit:sliding_window_counter:{key}:{prev_window}"

        result = self.backend.eval(
            SCRIPT,
            keys=[curr_key, prev_key],
            args=[self.config.limit, self.config.window, now],
        )
        return result == 1
