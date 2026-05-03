import time
import threading
import statistics
from dataclasses import dataclass
from src import RedisBackend
from src import RateLimiterConfig
from src import TokenBucket
from src import SlidingWindowLog
from src import SlidingWindowCounter

# ------ Configuration ------
LIMIT = 100
WINDOW = 10
TOTAL_REQUESTS = 200
CONCURRENT_THREADS = 10
RUNS_PER_SCENARIO = 5

ALGORITHMS = {
    "token_bucket": TokenBucket,
    "sliding_window_log": SlidingWindowLog,
    "sliding_window_counter": SlidingWindowCounter,
}


# ------ Result dataclass ------
@dataclass
class BenchmarkResult:
    algorithm: str          # chosen algorithm
    scenario: str           # chosen scenario
    throughput: float       # requests per second
    allowed: int            # number of allowed requests
    rejected: int           # number of rejected requests
    accuracy_error: float   # how far off we are from the ideal allowed count (%)
    latency_mean: float     # mean latency per request in milliseconds
    latency_p99: float      # 99th percentile latency in milliseconds

# ------ Helper to build a fresh rate limiter ------
def build_limiter(algorithm_name: str, backend: RedisBackend):
    config = RateLimiterConfig(limit=LIMIT, window=WINDOW)
    return ALGORITHMS[algorithm_name](config, backend)


# ------ Scenarios ------
def run_steady(limiter, user_key: str) -> tuple[list[bool], list[float]]:
    """
    Fire TOTAL_REQUESTS at a time, record result and latency of each
    This is the baseline scenario without concurrency or bursting.
    """
    results = []
    latencies = []
    for _ in range(TOTAL_REQUESTS):
        start = time.perf_counter()
        allowed = limiter.is_allowed(user_key)
        latencies.append((time.perf_counter() - start) * 1000)
        results.append(allowed)
    return results, latencies

def run_burst(limiter, user_key: str) -> tuple[list[bool], list[float]]:
    """
    Fire all TOTAL_REQUESTS as fast as possible in a tight loop.
    This stresses the Lua atomicity guarantees and measures how the
    algorithm behaves under traffic spikes.
    """
    results = []
    latencies = []
    for _ in range(TOTAL_REQUESTS):
        start = time.perf_counter()
        allowed = limiter.is_allowed(user_key)
        latencies.append((time.perf_counter() - start) * 1000)
        results.append(allowed)
    return results, latencies

def run_concurrent(limiter, user_key: str) -> tuple[list[bool], list[float]]:
    """
    Spawn CONCURRENT_THREADS threads, each firing TOTAL_REQUESTS //
    CONCURRENT_THREADS requests simultaneously. This is the true distributed
    scenario — multiple app instances hitting Redis concurrently. Correctness
    here depends entirely on the atomic Lua scripts.
    """
    results = []
    latencies = []
    lock = threading.Lock()

    def worker():
        local_results = []
        local_latencies = []
        per_thread = TOTAL_REQUESTS // CONCURRENT_THREADS
        for _ in range(per_thread):
            start = time.perf_counter()
            allowed = limiter.is_allowed(user_key)
            local_latencies.append((time.perf_counter() - start) * 1000)
            local_results.append(allowed)
        with lock:
            results.extend(local_results)
            latencies.extend(local_latencies)

    threads = [threading.Thread(target=worker) for _ in range(CONCURRENT_THREADS)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results, latencies


# ------ Benchamrk runner ------
def run_benchmark(algorithm_name: str, scenario_name: str, scenario_fn) -> BenchmarkResult:
    """
    Runs a single algorithm/scenario combination RUNS_PER_SCENARIO times
    and averages the results to reduce noise from OS scheduling and
    network jitter.
    """
    backend = RedisBackend()
    throughputs = []
    allowed_counts = []
    all_latencies = []

    for run in range(RUNS_PER_SCENARIO):
        backend.client.flushall()
        limiter = build_limiter(algorithm_name, backend)
        user_key = f"bench_user_{algorithm_name}_{scenario_name}_{run}"

        start = time.perf_counter()
        results, latencies = scenario_fn(limiter, user_key)
        elapsed = time.perf_counter() - start

        throughputs.append(TOTAL_REQUESTS / elapsed)
        allowed_counts.append(sum(results))
        all_latencies.extend(latencies)

    backend.client.flushall()

    avg_allowed = statistics.mean(allowed_counts)
    ideal_allowed = min(LIMIT, TOTAL_REQUESTS)
    accuracy_error = abs(avg_allowed - ideal_allowed) /ideal_allowed * 100

    all_latencies.sort()
    p99_index = int(len(all_latencies) * 0.99)

    return BenchmarkResult(
        algorithm=algorithm_name,
        scenario=scenario_name,
        throughput=statistics.mean(throughputs),
        allowed=int(avg_allowed),
        rejected=int(TOTAL_REQUESTS - avg_allowed),
        accuracy_error=accuracy_error,
        latency_mean=statistics.mean(all_latencies),
        latency_p99=all_latencies[p99_index],
    )


# ------ Results printer ------
def print_results(results: list[BenchmarkResult]):
    scenarios = sorted(set(r.scenario for r in results))

    for scenario in scenarios:
        print(f"\n{'═' * 86}")
        print(f"Scenario: {scenario.upper()}")
        print(f"{'═' * 86}")
        print(
            f"{'Algorithm':<28} {'Throughput':>12} {'Allowed':>8} "
            f"{'Rejected':>9} {'Err%':>6} {'Mean ms':>9} {'P99 ms':>8}"
        )
        print(f"{'─' * 86}")

        scenario_results = [r for r in results if r.scenario == scenario]
        for r in scenario_results:
            print(
                f"{r.algorithm:<28} {r.throughput:>10.1f}/s "
                f"{r.allowed:>8} {r.rejected:>9} "
                f"{r.accuracy_error:>5.1f}% "
                f"{r.latency_mean:>8.2f} "
                f"{r.latency_p99:>8.2f}"
            )

    print(f"\n{'═' * 86}")
    print("Settings")
    print(f"{'─' * 86}")
    print(f"Limit:               {LIMIT} requests")
    print(f"Window:              {WINDOW} seconds")
    print(f"Total requests:      {TOTAL_REQUESTS} per run")
    print(f"Concurrent threads:  {CONCURRENT_THREADS}")
    print(f"Runs per scenario:   {RUNS_PER_SCENARIO} (results averaged)")
    print(f"{'═' * 86}\n")


# ------ Main ------

if __name__ == "__main__":
    scenarios = {
        "steady": run_steady,
        "burst": run_burst,
        "concurrent": run_concurrent,
    }

    results = []
    total = len(ALGORITHMS) * len(scenarios)
    current = 0

    for algorithm_name in ALGORITHMS:
        for scenario_name, scenario_fn in scenarios.items():
            current += 1
            print(f"[{current}/{total}] {algorithm_name} / {scenario_name}...", end=" ", flush=True)
            result = run_benchmark(algorithm_name, scenario_name, scenario_fn)
            results.append(result)
            print(f"done - {result.throughput:.0f} req/s")

    print_results(results)
