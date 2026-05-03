# Distributed Rate Limiter

This project is a Redis-backed rate limiting library for Python, implementing three algorithms with atomic distributed guarantees. Designed as a plug-and-play FastAPI middleware that works correctly across multiple application instances.

---

## Table of Contents

- [Overview](#overview)
- [Algorithms](#algorithms)
- [Architecture](#architecture)
- [Installation](#installation)
- [Usage](#usage)
- [Benchmarks](#benchmarks)
- [Design Decisions](#design-decisions)
- [Known Limitations](#known-limitations)

---

## Overview

Rate limiters are a fundamental building block of any public API. The crucial challenge in a distributed environment is that multiple instances of the same application must share the **rate limit state**, a counter stored in a single application instance is invisible to the others, making it trivially bypassable.

This library solves this problem by storing all rate limit state in Redis and executing all check-and-update operations as atomic Lua scripts using Redis `EVAL`. Because Redis executes Lua scripts atomically, the check-and-increment is a single indivisible operation regardless of how many application instances are running concurrently, so we have no race conditions or double-counting.

---

## Algorithms

Three algorithms are implemented, to represent different points in terms of the accuracy vs. memory trade-off space.

### Token Bucket

Maintains a bucket of tokens per client, refilled at a fixed rate. Each request consumes one token, if the bucket is empty the request is rejected. Allows bursting up to the configured capacity.

- **Memory:** O(1) per client — stores token count and last refill timestamp
- **Accuracy:** Approximate — burst-tolerant by design
- **Best for:** APIs where short bursts are acceptable

### Sliding Window Log

Stores the exact timestamp of every request in a Redis sorted set. On each request, entries older than the window are removed and the remaining count is compared against the limit.

- **Memory:** O(n) per client — stores one entry per request
- **Accuracy:** Exact — enforces the limit with perfect precision
- **Best for:** APIs requiring strict per-window enforcement regardless of memory cost

### Sliding Window Counter

Maintains integer counters for the current and previous fixed windows, using a weighted interpolation to approximate the rolling count: `weighted = prev_count * (1 - elapsed/window) + curr_count`. O(1) memory with accuracy approaching the sliding window log.

- **Memory:** O(1) per client — stores two integer counters
- **Accuracy:** Approximate — small error at window boundaries
- **Best for:** High-traffic APIs where memory efficiency and accuracy are both important

---

## Architecture

```
┌─────────────┐     ┌─────────────────────────┐     ┌───────────────────┐
│  Client A   │────▶│                         │────▶│                   │
├─────────────┤     │  RateLimiterMiddleware  │     │       Redis       │
│  Client B   │────▶│                         │     │                   │
├─────────────┤     │  • Extracts client key  │     │    Atomic Lua     │
│  Client C   │────▶│  • Calls algorithm      │◀────│  scripts via EVAL │
└─────────────┘     │  • Returns 200 or 429   │     │                   │
                    └─────────────────────────┘     └───────────────────┘
                               │ Allow
                               ▼
                    ┌─────────────────────────┐
                    │       App Service       │
                    │    (FastAPI routes)     │
                    └─────────────────────────┘
```

### Project Structure

```
rate-limiter/
├── src/
│   ├── algorithms/
│   │   ├── token_bucket.py
│   │   ├── sliding_window_log.py
│   │   └── sliding_window_counter.py
│   ├── backends/
│   │   └── redis_backend.py
│   ├── middleware/
│   │   └── fastapi.py
│   └── config.py
├── benchmarks/
│   └── benchmark.py
├── tests/
│   ├── test_token_bucket.py
│   ├── test_sliding_window_log.py
│   ├── test_sliding_window_counter.py
│   └── test_middleware.py
├── docker-compose.yml
└── pyproject.toml
```

---

## Installation

**Requirements:** Python 3.11+, Redis 7+

```bash
git clone https://github.com/gabrigio30/rate-limiter
cd rate-limiter
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

Start Redis via Docker:

```bash
docker compose up -d
```

---

## Usage

### As FastAPI Middleware

```python
from fastapi import FastAPI
from src import RateLimiterMiddleware, RateLimiterConfig

app = FastAPI()

app.add_middleware(
    RateLimiterMiddleware,
    config=RateLimiterConfig(limit=100, window=60),
    algorithm="token_bucket",   # or "sliding_window_log" / "sliding_window_counter"
)

@app.get("/")
async def root():
    return {"message": "ok"}
```

Requests exceeding the limit receive a `429 Too Many Requests` response:

```json
{
  "error": "Too many requests",
  "detail": "Rate limit exceeded. Please try again later."
}
```

### Directly

```python
from src import RedisBackend, RateLimiterConfig, SlidingWindowCounter

backend = RedisBackend(host="localhost", port=6379)
config = RateLimiterConfig(limit=100, window=60)
limiter = SlidingWindowCounter(config, backend)

if limiter.is_allowed("user_123"):
    print("Request allowed")
else:
    print("Rate limit exceeded")
```

### Configuration

| Parameter | Type | Description |
|---|---|---|
| `limit` | `int` | Maximum requests allowed per window |
| `window` | `int` | Time window in seconds |
| `capacity` | `int` | Token bucket only: max burst size (defaults to `limit`) |

### Selecting an Algorithm

| Use case | Recommended algorithm |
|---|---|
| General purpose API rate limiting | `sliding_window_counter` |
| APIs tolerating short bursts | `token_bucket` |
| Strict per-window enforcement | `sliding_window_log` |

---

## Benchmarks

Benchmarked on a MacBook Pro 2019, Redis 7 (Docker), Python 3.12. Each scenario run 5 times and averaged. Settings: limit=100, window=10 (seconds), 200 total requests, 10 concurrent threads.

### Steady Traffic

| Algorithm | Throughput | Allowed | Rejected | Error | Mean latency | P99 latency |
|---|---|---|---|---|---|---|
| Token bucket | 2,415 req/s | 100 | 100 | 0.0% | 0.41ms | 0.64ms |
| Sliding window log | 1,987 req/s | 100 | 100 | 0.0% | 0.51ms | 0.97ms |
| Sliding window counter | 2,505 req/s | 100 | 100 | 0.0% | 0.40ms | 0.56ms |

### Burst Traffic

| Algorithm | Throughput | Allowed | Rejected | Error | Mean latency | P99 latency |
|---|---|---|---|---|---|---|
| Token bucket | 2,483 req/s | 100 | 100 | 0.0% | 0.40ms | 0.58ms |
| Sliding window log | 2,422 req/s | 100 | 100 | 0.0% | 0.41ms | 0.63ms |
| Sliding window counter | 2,481 req/s | 100 | 100 | 0.0% | 0.40ms | 0.72ms |

### Concurrent Traffic (10 threads)

| Algorithm | Throughput | Allowed | Rejected | Error | Mean latency | P99 latency |
|---|---|---|---|---|---|---|
| Token bucket | 5,072 req/s | 100 | 100 | 0.0% | 1.78ms | 6.76ms |
| Sliding window log | 5,569 req/s | 100 | 100 | 0.0% | 1.60ms | 4.94ms |
| Sliding window counter | 5,621 req/s | 100 | 100 | 0.0% | 1.60ms | 5.25ms |

### Key Observations

**All three algorithms achieve 0% accuracy error across all scenarios**, including under 10 concurrent threads. This validates that the Redis-Lua atomicity guarantee eliminates race conditions entirely, no request was incorrectly allowed or rejected regardless of concurrency.

**Sliding window log is ~20% slower under steady traffic** due to the cost of sorted set operations (`ZREMRANGEBYSCORE`, `ZCARD`, `ZADD`) compared to hash fields (`HMGET`/`HMSET`) or simple counters (`GET`/`INCR`). This is the direct measurable cost of its exact accuracy guarantee.

**All algorithms roughly double throughput under concurrent load.** Python releases the GIL during Redis I/O, allowing threads to pipeline requests: while one thread waits for a Redis response, others proceed, effectively overlapping the network round trips.

**Token bucket shows higher P99 latency under concurrency** (6.76ms vs ~5ms for the others) due to its more computationally intensive Lua script, which amplifies under contention.

---

## Design Decisions

### Why Redis Lua scripts for atomicity

The check-and-update operation (read the current count, decide allow/reject, write the new count) must be atomic in a distributed environment. Without atomicity, two concurrent requests can both read the same counter value before either writes back, causing both to be allowed even when only one should be. Redis `EVAL` executes Lua scripts atomically: no other command runs on the server while the script executes, making the entire operation indivisible. This is preferable to distributed locks, which add latency and introduce their own failure modes.

### Why the `RedisBackend` abstraction

Wrapping the Redis client behind a `RedisBackend` class applies the dependency inversion principle — algorithms depend on an abstraction rather than a concrete Redis client. This makes the algorithms independently testable (a mock backend can be injected in unit tests) and decouples the rate limiting logic from the specific Redis client library used.

### Client identification via `X-Forwarded-For`

The middleware uses `X-Forwarded-For` headers when present rather than `request.client.host`. Behind a load balancer or reverse proxy, `request.client.host` is always the proxy's IP — all clients would share a single bucket and hit the limit almost immediately. `X-Forwarded-For` carries the original client IP set by the proxy, with the leftmost value being the true originating address in multi-hop scenarios.

### Key namespacing

All Redis keys are namespaced by algorithm and identifier, for example `rate_limit:token_bucket:user_123`. This prevents key collisions when multiple algorithms are used against the same Redis instance, and follows the standard Redis key naming convention for production deployments.

---

## Known Limitations

**Sliding window counter approximation at boundaries.** The weighted interpolation can theoretically allow slightly more than `limit` requests when a high-traffic previous window transitions into a new one. In the benchmarks this error was 0% because all requests fell within a single window, but real deployments spanning window boundaries may show a small deviation. This is an accepted trade-off for the memory efficiency gained.

**No Redis Cluster support.** The current implementation targets a single Redis node. Redis Cluster requires that all keys accessed in a single Lua script reside on the same node — the sliding window counter's two-key script would need hash tags (`{user_123}`) to guarantee co-location. This is a known extension point which could be covered with future work.

**No `EVALSHA` optimisation.** The implementation uses `EVAL` on every request, sending the full Lua script each time. Replacing this with `EVALSHA` (which sends only the script's SHA hash after the first call) would reduce network overhead under very high traffic.

**FastAPI middleware initialisation is lazy.** FastAPI defers middleware instantiation until the first request rather than at `add_middleware` call time. Configuration errors such as an invalid algorithm name are therefore only raised on the first request, not at startup. Instantiating the middleware class directly at application startup is the recommended workaround if eager validation is required.

**Clock skew across application instances.** All algorithms use `time.time()` on the application side to generate timestamps passed to Redis. In deployments where application servers have unsynchronised clocks, this can cause minor inaccuracies in window boundary calculations. NTP synchronisation across all nodes is assumed.

---

## Author

**Gabriele Giordanelli**  
M.Sc. Computer Science and Engineering — Politecnico di Milano  
[LinkedIn](https://linkedin.com/in/gabrigio30) · [GitHub](https://github.com/gabrigio30)