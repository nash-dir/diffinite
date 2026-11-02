"""Priority job scheduler (author A)."""
import heapq
import itertools
import time


class Job:
    __slots__ = ("priority", "seq", "name", "func", "args", "retries", "cancelled")

    def __init__(self, priority, seq, name, func, args, retries):
        self.priority = priority
        self.seq = seq
        self.name = name
        self.func = func
        self.args = args
        self.retries = retries
        self.cancelled = False

    def __lt__(self, other):
        return (self.priority, self.seq) < (other.priority, other.seq)


class Scheduler:
    def __init__(self, max_retries=3):
        self._heap = []
        self._counter = itertools.count()
        self._by_name = {}
        self.max_retries = max_retries
        self.completed = []
        self.failed = []

    def submit(self, name, func, *args, priority=5):
        if name in self._by_name:
            raise ValueError(f"job {name!r} already scheduled")
        job = Job(priority, next(self._counter), name, func, args, self.max_retries)
        heapq.heappush(self._heap, job)
        self._by_name[name] = job
        return job

    def cancel(self, name):
        job = self._by_name.pop(name, None)
        if job is None:
            return False
        job.cancelled = True
        return True

    def _pop(self):
        while self._heap:
            job = heapq.heappop(self._heap)
            if not job.cancelled:
                self._by_name.pop(job.name, None)
                return job
        return None

    def run_next(self):
        job = self._pop()
        if job is None:
            return None
        started = time.perf_counter()
        try:
            value = job.func(*job.args)
        except Exception as exc:  # noqa: BLE001
            if job.retries > 0:
                job.retries -= 1
                job.priority += 1
                heapq.heappush(self._heap, job)
                self._by_name[job.name] = job
            else:
                self.failed.append((job.name, repr(exc)))
            return None
        elapsed = time.perf_counter() - started
        self.completed.append((job.name, value, elapsed))
        return value

    def run_all(self, limit=None):
        executed = 0
        while self._heap and (limit is None or executed < limit):
            self.run_next()
            executed += 1
        return executed

    def pending(self):
        return sorted(j.name for j in self._heap if not j.cancelled)
