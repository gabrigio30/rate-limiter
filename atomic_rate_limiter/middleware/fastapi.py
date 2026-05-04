from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse
from atomic_rate_limiter.backends.redis_backend import RedisBackend
from atomic_rate_limiter.config import RateLimiterConfig
from atomic_rate_limiter.algorithms.token_bucket import TokenBucket
from atomic_rate_limiter.algorithms.sliding_window_log import SlidingWindowLog
from atomic_rate_limiter.algorithms.sliding_window_counter import SlidingWindowCounter

ALGORITHMS = {
    "token_bucket": TokenBucket,
    "sliding_window_log": SlidingWindowLog,
    "sliding_window_counter": SlidingWindowCounter,
}

class RateLimiterMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app: FastAPI,
        config: RateLimiterConfig,
        algorithm: str = "token_bucket",
        redis_host: str = "localhost",
        redis_port: int = 6379,
    ):
        super().__init__(app)
        if algorithm not in ALGORITHMS:
            raise ValueError(
                f"Unknown algorithm '{algorithm}'. "
                f"Choose from: {list(ALGORITHMS.keys())}"
            )
        backend = RedisBackend(host=redis_host, port=redis_port)
        self.limiter = ALGORITHMS[algorithm](config, backend)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_key = self._get_client_key(request)

        if not self.limiter.is_allowed(client_key):
            return JSONResponse(
                status_code=429,
                content={
                    "error": "Too many requests",
                    "detail": "Rate limit exceeded. Please try again later."
                }
            )

        response = await call_next(request)
        return response

    def _get_client_key(self, request: Request) -> str:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()
        return request.client.host