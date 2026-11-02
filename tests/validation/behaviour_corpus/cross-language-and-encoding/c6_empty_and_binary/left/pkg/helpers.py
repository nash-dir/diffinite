"""Token-bucket and sliding-window rate limiters for the API gateway."""

import time
from collections import deque


class TokenBucket:
    def __init__(self, capacity, refill_per_sec, clock=time.monotonic):
        if capacity <= 0 or refill_per_sec <= 0:
            raise ValueError("capacity and refill rate must be positive")
        self.capacity = capacity
        self.refill_per_sec = refill_per_sec
        self.tokens = float(capacity)
        self.clock = clock
        self.last = clock()

    def _refill(self):
        now = self.clock()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.refill_per_sec)

    def try_acquire(self, cost=1):
        self._refill()
        if self.tokens >= cost:
            self.tokens -= cost
            return True
        return False

    def wait_time(self, cost=1):
        self._refill()
        if self.tokens >= cost:
            return 0.0
        return (cost - self.tokens) / self.refill_per_sec


