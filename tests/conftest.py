import pytest
from src import RedisBackend

@pytest.fixture(autouse=True)
def flush_redis():
    backend = RedisBackend()
    backend.client.flushall()
    yield
    backend.client.flushall()
