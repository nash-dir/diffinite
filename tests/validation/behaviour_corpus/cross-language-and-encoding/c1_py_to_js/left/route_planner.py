"""Route planner for the depot delivery scheduler.

Builds a weighted graph from road segments, runs Dijkstra to find the
cheapest route between depots and estimates delivery windows.
"""

import heapq
from collections import defaultdict


class RoadGraph:
    def __init__(self):
        self.edges = defaultdict(list)
        self.closed = set()

    def add_segment(self, src, dst, distance, toll=0.0, bidirectional=True):
        cost = distance + toll * 2.5
        self.edges[src].append((dst, cost))
        if bidirectional:
            self.edges[dst].append((src, cost))

    def close_road(self, src, dst):
        self.closed.add((src, dst))
        self.closed.add((dst, src))

    def neighbours(self, node):
        for dst, cost in self.edges.get(node, []):
            if (node, dst) in self.closed:
                continue
            yield dst, cost


def shortest_path(graph, start, goal):
    dist = {start: 0.0}
    prev = {}
    queue = [(0.0, start)]
    visited = set()
    while queue:
        cost, node = heapq.heappop(queue)
        if node in visited:
            continue
        visited.add(node)
        if node == goal:
            break
        for nxt, weight in graph.neighbours(node):
            candidate = cost + weight
            if candidate < dist.get(nxt, float("inf")):
                dist[nxt] = candidate
                prev[nxt] = node
                heapq.heappush(queue, (candidate, nxt))
    if goal not in dist:
        return None, float("inf")
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[goal]


def delivery_window(total_cost, avg_speed_kmh=42.0, stops=0, stop_minutes=6):
    if avg_speed_kmh <= 0:
        raise ValueError("average speed must be positive")
    driving_minutes = total_cost / avg_speed_kmh * 60.0
    service_minutes = stops * stop_minutes
    earliest = round(driving_minutes + service_minutes)
    latest = round(earliest * 1.25 + 10)
    return earliest, latest


def plan_routes(graph, depot, orders):
    plans = []
    for order in sorted(orders, key=lambda o: o["priority"], reverse=True):
        path, cost = shortest_path(graph, depot, order["destination"])
        if path is None:
            plans.append({"order": order["id"], "status": "unreachable"})
            continue
        earliest, latest = delivery_window(cost, stops=len(path) - 2)
        plans.append({
            "order": order["id"],
            "status": "planned",
            "path": path,
            "cost": round(cost, 2),
            "window": (earliest, latest),
        })
    return plans


def summarize(plans):
    planned = [p for p in plans if p["status"] == "planned"]
    unreachable = [p for p in plans if p["status"] == "unreachable"]
    total = sum(p["cost"] for p in planned)
    longest = max(planned, key=lambda p: p["cost"], default=None)
    return {
        "planned": len(planned),
        "unreachable": len(unreachable),
        "total_cost": round(total, 2),
        "longest_order": longest["order"] if longest else None,
    }


if __name__ == "__main__":
    g = RoadGraph()
    g.add_segment("A", "B", 7)
    g.add_segment("A", "C", 9)
    g.add_segment("A", "F", 14, toll=1.0)
    g.add_segment("B", "C", 10)
    g.add_segment("B", "D", 15)
    g.add_segment("C", "D", 11)
    g.add_segment("C", "F", 2)
    g.add_segment("D", "E", 6)
    g.add_segment("E", "F", 9)
    g.close_road("C", "F")
    orders = [
        {"id": "o-1", "destination": "E", "priority": 2},
        {"id": "o-2", "destination": "D", "priority": 5},
        {"id": "o-3", "destination": "Z", "priority": 1},
    ]
    result = plan_routes(g, "A", orders)
    print(summarize(result))
