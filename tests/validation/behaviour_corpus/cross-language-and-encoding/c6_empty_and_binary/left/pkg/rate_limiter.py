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


class SlidingWindow:
    def __init__(self, limit, window_sec, clock=time.monotonic):
        self.limit = limit
        self.window = window_sec
        self.clock = clock
        self.hits = deque()

    def _evict(self, now):
        while self.hits and now - self.hits[0] >= self.window:
            self.hits.popleft()

    def allow(self):
        now = self.clock()
        self._evict(now)
        if len(self.hits) < self.limit:
            self.hits.append(now)
            return True
        return False

    def remaining(self):
        self._evict(self.clock())
        return max(0, self.limit - len(self.hits))


class LimiterRegistry:
    def __init__(self, factory):
        self.factory = factory
        self.limiters = {}

    def for_key(self, key):
        limiter = self.limiters.get(key)
        if limiter is None:
            limiter = self.factory()
            self.limiters[key] = limiter
        return limiter

    def purge_idle(self, predicate):
        stale = [k for k, v in self.limiters.items() if predicate(v)]
        for k in stale:
            del self.limiters[k]
        return len(stale)
