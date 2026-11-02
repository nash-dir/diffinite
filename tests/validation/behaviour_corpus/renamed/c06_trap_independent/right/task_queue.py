# Task queue with priorities -- written independently by author B.
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple
import bisect
import logging

log = logging.getLogger(__name__)

RETRY_LIMIT = 2


@dataclass(order=True)
class Task:
    rank: Tuple[int, int]
    label: str = field(compare=False)
    target: Callable[..., Any] = field(compare=False)
    payload: tuple = field(default=(), compare=False)
    attempts: int = field(default=0, compare=False)
    dead: bool = field(default=False, compare=False)


class TaskQueue:
    """Keeps tasks in a sorted list instead of a heap."""

    def __init__(self) -> None:
        self.queue: List[Task] = []
        self.index: Dict[str, Task] = {}
        self.ticket = 0
        self.results: Dict[str, Any] = {}
        self.errors: Dict[str, str] = {}

    def enqueue(self, label: str, target: Callable[..., Any], payload=(), urgency: int = 0) -> Task:
        assert label not in self.index, "label already queued: " + label
        self.ticket += 1
        task = Task((-urgency, self.ticket), label, target, tuple(payload))
        bisect.insort(self.queue, task)
        self.index[label] = task
        log.debug("queued %s at urgency %d", label, urgency)
        return task

    def drop(self, label: str) -> bool:
        task = self.index.get(label)
        if not task:
            return False
        task.dead = True
        del self.index[label]
        return True

    def step(self) -> Optional[str]:
        # discard dead entries lazily from the front
        while self.queue and self.queue[0].dead:
            self.queue.pop(0)
        if not self.queue:
            return None
        task = self.queue.pop(0)
        self.index.pop(task.label, None)
        task.attempts += 1
        try:
            self.results[task.label] = task.target(*task.payload)
        except Exception as err:
            log.warning("task %s failed (attempt %d): %s", task.label, task.attempts, err)
            if task.attempts <= RETRY_LIMIT:
                self.ticket += 1
                task.rank = (task.rank[0] + 1, self.ticket)
                bisect.insort(self.queue, task)
                self.index[task.label] = task
            else:
                self.errors[task.label] = str(err)
        return task.label

    def drain(self) -> int:
        n = 0
        while self.step() is not None:
            n += 1
        return n

    def snapshot(self) -> List[str]:
        return [t.label for t in self.queue if not t.dead]
