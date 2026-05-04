from fastapi import FastAPI
from atomic_rate_limiter.middleware.fastapi import RateLimiterMiddleware
from src.config import RateLimiterConfig

app = FastAPI()

app.add_middleware(
    RateLimiterMiddleware,
    config=RateLimiterConfig(limit=5, window=60),
    algorithm="token_bucket",
)

@app.get("/")
async def root():
    return {"message": "Request allowed"}

@app.get("/hello/{name}")
async def hello(name: str):
    return {"message": f"Hello {name}"}