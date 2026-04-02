import time
from ..backends.redis_backend import RedisBackend
from ..config import RateLimiterConfig

SCRIPT = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])
local now = tonumber(ARGV[3])

local bucket = redis.call('HMGET', key, 'tokens', 'last_refill')
local tokens = tonumber(bucket[1]) or capacity
local last_refill = tonumber(bucket[2]) or now

local elapsed = now - last_refill
tokens = math.min(capacity, tokens + elapsed * refill_rate)

if tokens >= 1 then
    tokens = tokens - 1
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    redis.call('EXPIRE', key, 3600)
    return 1
else
    redis.call('HMSET', key, 'tokens', tokens, 'last_refill', now)
    return 0
end
"""

class TokenBucket(object):
    def __init__(self, config: RateLimiterConfig, backend: RedisBackend):
        self.config = config
        self.backend = backend
        self.refill_rate = config.limit / config.window

    def is_allowed(self, key: str) -> bool:
        now = time.time()
        result = self.backend.eval(
            SCRIPT,
            keys=[f"rate_limit:token_bucket:{key}"],
            args=[self.config.capacity, self.refill_rate, now],
        )
        return result == 1
