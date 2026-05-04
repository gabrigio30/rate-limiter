import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from atomic_rate_limiter import RateLimiterMiddleware, RateLimiterConfig, RedisBackend

@pytest.fixture
def app():
    app = FastAPI()
    app.add_middleware(
        RateLimiterMiddleware,
        config=RateLimiterConfig(limit=3, window=60),
        algorithm="token_bucket",
    )

    @app.get("/")
    async def root():
        return {"message": "Ok"}

    return app

@pytest.fixture
def client(app):
    return TestClient(app, raise_server_exceptions=False)


def test_allows_requests_within_limit(client):
    for _ in range(3):
        response = client.get("/")
        assert response.status_code == 200

def test_rejects_requests_over_limit(client):
    for _ in range(3):
        client.get("/")
    response = client.get("/")
    assert response.status_code == 429

def test_429_response_has_correct_body(client):
    for _ in range(3):
        client.get("/")
    response = client.get("/")
    assert response.status_code == 429
    body = response.json()
    assert "error" in body
    assert "detail" in body

def test_all_routes_are_rate_limited(app):
    @app.get("/other")
    async def other():
        return {"message": "other"}

    client = TestClient(app, raise_server_exceptions=False)
    for _ in range(3):
        client.get("/other")
    response = client.get("/other")
    assert response.status_code == 429

def test_invalid_algorithm_raises_on_startup():
    with pytest.raises(ValueError):
        RateLimiterMiddleware(
            app=FastAPI(),
            config=RateLimiterConfig(limit=5, window=60),
            algorithm="invalid_algorithm",
        )
        TestClient(app)

def test_all_algorithms_work_as_middleware():
    for algorithm in ["token_bucket", "sliding_window_log", "sliding_window_counter"]:
        backend = RedisBackend()
        backend.client.flushall()

        app = FastAPI()
        app.add_middleware(
            RateLimiterMiddleware,
            config=RateLimiterConfig(limit=3, window=60),
            algorithm=algorithm
        )

        @app.get("/")
        async def root():
            return {"message": "Ok"}

        client = TestClient(app, raise_server_exceptions=False)

        for _ in range(3):
            assert client.get("/").status_code == 200
        assert client.get("/").status_code == 429