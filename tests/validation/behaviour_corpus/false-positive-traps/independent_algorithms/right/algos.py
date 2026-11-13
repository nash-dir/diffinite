# Utility algorithms for the scheduling service (M. Ortega)
from collections import deque
import heapq


def quick_sort(items):
    """Return a new sorted list (functional quicksort, middle pivot)."""
    if len(items) <= 1:
        return list(items)
    pivot = items[len(items) // 2]
    smaller = [x for x in items if x < pivot]
    equal = [x for x in items if x == pivot]
    larger = [x for x in items if x > pivot]
    return quick_sort(smaller) + equal + quick_sort(larger)


def binary_search(seq, key):
    """Leftmost index of key in sorted seq, or -1."""
    left, right = 0, len(seq)
    while left < right:
        middle = left + (right - left) // 2
        if seq[middle] < key:
            left = middle + 1
        else:
            right = middle
    if left < len(seq) and seq[left] == key:
        return left
    return -1


def breadth_first(adjacency, root):
    seen = set([root])
    q = deque()
    q.append(root)
    result = []
    while len(q) > 0:
        current = q.popleft()
        result.append(current)
        for neighbour in adjacency[current]:
            if neighbour in seen:
                continue
            seen.add(neighbour)
            q.append(neighbour)
    return result


def shortest_paths(edges, origin):
    best = {origin: 0}
    frontier = [(0, origin)]
    done = set()
    while frontier:
        cost, node = heapq.heappop(frontier)
        if node in done:
            continue
        done.add(node)
        for (target, weight) in edges.get(node, ()):
            candidate = cost + weight
            if target not in best or candidate < best[target]:
                best[target] = candidate
                heapq.heappush(frontier, (candidate, target))
    return best


def greatest_common_divisor(x, y):
    if y == 0:
        return abs(x)
    return greatest_common_divisor(y, x % y)


def primes_up_to(limit):
    sieve = [True] * (limit + 1)
    sieve[0:2] = [False, False]
    for n in range(2, int(limit ** 0.5) + 1):
        if sieve[n]:
            for m in range(n * n, limit + 1, n):
                sieve[m] = False
    return [i for i, ok in enumerate(sieve) if ok]


def fibonacci(n, _memo={0: 0, 1: 1}):
    if n not in _memo:
        _memo[n] = fibonacci(n - 1) + fibonacci(n - 2)
    return _memo[n]


def main():
    nums = [7, 3, 3, 10, -1]
    ordered = quick_sort(nums)
    print(ordered, binary_search(ordered, 3))
    adj = {1: [2, 3], 2: [4], 3: [4], 4: []}
    print(breadth_first(adj, 1))
    print(shortest_paths({"s": [("t", 4), ("u", 1)], "u": [("t", 2)]}, "s"))
    print(greatest_common_divisor(84, 36), primes_up_to(30), fibonacci(20))


if __name__ == "__main__":
    main()
