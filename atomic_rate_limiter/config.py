from dataclasses import dataclass

@dataclass
class RateLimiterConfig:
    limit: int          # max requests allowed
    window: int         # time window (seconds)
    capacity: int = 0   # token bucket only: max burst size

    def __post_init__(self):
        if self.capacity == 0:
            self.capacity = self.limit
