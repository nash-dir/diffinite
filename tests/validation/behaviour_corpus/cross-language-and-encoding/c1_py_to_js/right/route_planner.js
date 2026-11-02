/**
 * Route planner for the depot delivery scheduler.
 *
 * Builds a weighted graph from road segments, runs Dijkstra to find the
 * cheapest route between depots and estimates delivery windows.
 */

'use strict';

class MinHeap {
  constructor() {
    this.items = [];
  }

  push(item) {
    this.items.push(item);
    this.items.sort((a, b) => a[0] - b[0]);
  }

  pop() {
    return this.items.shift();
  }

  get size() {
    return this.items.length;
  }
}

class RoadGraph {
  constructor() {
    this.edges = new Map();
    this.closed = new Set();
  }

  addSegment(src, dst, distance, toll = 0.0, bidirectional = true) {
    const cost = distance + toll * 2.5;
    if (!this.edges.has(src)) this.edges.set(src, []);
    this.edges.get(src).push([dst, cost]);
    if (bidirectional) {
      if (!this.edges.has(dst)) this.edges.set(dst, []);
      this.edges.get(dst).push([src, cost]);
    }
  }

  closeRoad(src, dst) {
    this.closed.add(`${src}->${dst}`);
    this.closed.add(`${dst}->${src}`);
  }

  *neighbours(node) {
    for (const [dst, cost] of this.edges.get(node) || []) {
      if (this.closed.has(`${node}->${dst}`)) {
        continue;
      }
      yield [dst, cost];
    }
  }
}

function shortestPath(graph, start, goal) {
  const dist = new Map([[start, 0.0]]);
  const prev = new Map();
  const queue = new MinHeap();
  queue.push([0.0, start]);
  const visited = new Set();
  while (queue.size > 0) {
    const [cost, node] = queue.pop();
    if (visited.has(node)) {
      continue;
    }
    visited.add(node);
    if (node === goal) {
      break;
    }
    for (const [nxt, weight] of graph.neighbours(node)) {
      const candidate = cost + weight;
      if (candidate < (dist.has(nxt) ? dist.get(nxt) : Infinity)) {
        dist.set(nxt, candidate);
        prev.set(nxt, node);
        queue.push([candidate, nxt]);
      }
    }
  }
  if (!dist.has(goal)) {
    return [null, Infinity];
  }
  const path = [goal];
  while (path[path.length - 1] !== start) {
    path.push(prev.get(path[path.length - 1]));
  }
  path.reverse();
  return [path, dist.get(goal)];
}

function deliveryWindow(totalCost, avgSpeedKmh = 42.0, stops = 0, stopMinutes = 6) {
  if (avgSpeedKmh <= 0) {
    throw new Error('average speed must be positive');
  }
  const drivingMinutes = totalCost / avgSpeedKmh * 60.0;
  const serviceMinutes = stops * stopMinutes;
  const earliest = Math.round(drivingMinutes + serviceMinutes);
  const latest = Math.round(earliest * 1.25 + 10);
  return [earliest, latest];
}

function planRoutes(graph, depot, orders) {
  const plans = [];
  const sorted = [...orders].sort((a, b) => b.priority - a.priority);
  for (const order of sorted) {
    const [path, cost] = shortestPath(graph, depot, order.destination);
    if (path === null) {
      plans.push({ order: order.id, status: 'unreachable' });
      continue;
    }
    const [earliest, latest] = deliveryWindow(cost, 42.0, path.length - 2);
    plans.push({
      order: order.id,
      status: 'planned',
      path: path,
      cost: Math.round(cost * 100) / 100,
      window: [earliest, latest],
    });
  }
  return plans;
}

function summarize(plans) {
  const planned = plans.filter((p) => p.status === 'planned');
  const unreachable = plans.filter((p) => p.status === 'unreachable');
  const total = planned.reduce((acc, p) => acc + p.cost, 0);
  let longest = null;
  for (const p of planned) {
    if (longest === null || p.cost > longest.cost) longest = p;
  }
  return {
    planned: planned.length,
    unreachable: unreachable.length,
    total_cost: Math.round(total * 100) / 100,
    longest_order: longest ? longest.order : null,
  };
}

if (require.main === module) {
  const g = new RoadGraph();
  g.addSegment('A', 'B', 7);
  g.addSegment('A', 'C', 9);
  g.addSegment('A', 'F', 14, 1.0);
  g.addSegment('B', 'C', 10);
  g.addSegment('B', 'D', 15);
  g.addSegment('C', 'D', 11);
  g.addSegment('C', 'F', 2);
  g.addSegment('D', 'E', 6);
  g.addSegment('E', 'F', 9);
  g.closeRoad('C', 'F');
  const orders = [
    { id: 'o-1', destination: 'E', priority: 2 },
    { id: 'o-2', destination: 'D', priority: 5 },
    { id: 'o-3', destination: 'Z', priority: 1 },
  ];
  const result = planRoutes(g, 'A', orders);
  console.log(summarize(result));
}

module.exports = { RoadGraph, shortestPath, deliveryWindow, planRoutes, summarize };
