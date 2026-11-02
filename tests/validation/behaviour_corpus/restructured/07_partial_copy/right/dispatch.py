"""Courier dispatch: job intake, driver assignment and invoicing."""

import heapq
import itertools
import logging
import math
from collections import namedtuple
from datetime import datetime, timedelta

log = logging.getLogger("dispatch")

EARTH_RADIUS_KM = 6371.0088
BASE_FARE = 4.50
PER_KM = 1.35
NIGHT_SURCHARGE = 0.25
MAX_JOBS_PER_DRIVER = 6

Job = namedtuple("Job", "job_id pickup dropoff weight_kg ready_at priority")
Driver = namedtuple("Driver", "driver_id name position capacity_kg shift_end")
Loc = namedtuple("Loc", "lat lon")


def haversine_km(a, b):
    """Great-circle distance between two points in kilometres."""
    phi1 = math.radians(a.lat)
    phi2 = math.radians(b.lat)
    dphi = math.radians(b.lat - a.lat)
    dlmb = math.radians(b.lon - a.lon)
    h = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(min(1.0, math.sqrt(h)))


def bounding_box(center, radius_km):
    """Return (min_lat, min_lon, max_lat, max_lon) enclosing a circle."""
    dlat = math.degrees(radius_km / EARTH_RADIUS_KM)
    cos_lat = math.cos(math.radians(center.lat))
    if cos_lat < 1e-12:
        dlon = 180.0
    else:
        dlon = math.degrees(radius_km / (EARTH_RADIUS_KM * cos_lat))
    min_lat = max(-90.0, center.lat - dlat)
    max_lat = min(90.0, center.lat + dlat)
    min_lon = max(-180.0, center.lon - dlon)
    max_lon = min(180.0, center.lon + dlon)
    return (min_lat, min_lon, max_lat, max_lon)


class JobQueue:
    """Priority queue of pending jobs ordered by (priority, ready_at)."""

    def __init__(self):
        self._heap = []
        self._counter = itertools.count()
        self._cancelled = set()

    def push(self, job):
        heapq.heappush(self._heap, (job.priority, job.ready_at, next(self._counter), job))
        log.debug("queued job %s", job.job_id)

    def cancel(self, job_id):
        self._cancelled.add(job_id)

    def pop_ready(self, now):
        deferred = []
        found = None
        while self._heap:
            item = heapq.heappop(self._heap)
            job = item[3]
            if job.job_id in self._cancelled:
                continue
            if job.ready_at <= now:
                found = job
                break
            deferred.append(item)
        for item in deferred:
            heapq.heappush(self._heap, item)
        return found

    def __len__(self):
        return sum(1 for item in self._heap if item[3].job_id not in self._cancelled)


class Assignment:
    def __init__(self, driver):
        self.driver = driver
        self.jobs = []
        self.load_kg = 0.0

    def can_take(self, job, now):
        if len(self.jobs) >= MAX_JOBS_PER_DRIVER:
            return False
        if self.load_kg + job.weight_kg > self.driver.capacity_kg:
            return False
        if now + timedelta(minutes=45) > self.driver.shift_end:
            return False
        return True

    def take(self, job):
        self.jobs.append(job)
        self.load_kg += job.weight_kg


def candidate_drivers(job, assignments, radius_km, now):
    box = bounding_box(job.pickup, radius_km)
    min_lat, min_lon, max_lat, max_lon = box
    out = []
    for a in assignments:
        pos = a.driver.position
        if not (min_lat <= pos.lat <= max_lat and min_lon <= pos.lon <= max_lon):
            continue
        if not a.can_take(job, now):
            continue
        dist = haversine_km(pos, job.pickup)
        if dist <= radius_km:
            out.append((dist, a))
    out.sort(key=lambda t: t[0])
    return out


def dispatch_round(queue, assignments, now, radius_km=8.0):
    """Assign as many ready jobs as possible; return unassigned jobs."""
    unassigned = []
    while True:
        job = queue.pop_ready(now)
        if job is None:
            break
        options = candidate_drivers(job, assignments, radius_km, now)
        if not options:
            wider = candidate_drivers(job, assignments, radius_km * 2, now)
            if not wider:
                unassigned.append(job)
                log.info("no driver for job %s", job.job_id)
                continue
            options = wider
        _, chosen = options[0]
        chosen.take(job)
        log.info("job %s -> driver %s", job.job_id, chosen.driver.driver_id)
    return unassigned


def fare_for(job, when):
    distance = haversine_km(job.pickup, job.dropoff)
    fare = BASE_FARE + PER_KM * distance
    if job.weight_kg > 20:
        fare += 0.10 * (job.weight_kg - 20)
    if when.hour >= 22 or when.hour < 6:
        fare *= 1 + NIGHT_SURCHARGE
    return round(fare, 2)


def invoice(assignments, when):
    lines = []
    grand = 0.0
    for a in assignments:
        subtotal = 0.0
        for job in a.jobs:
            amount = fare_for(job, when)
            subtotal += amount
            lines.append("%-10s %-12s %8.2f" % (a.driver.driver_id, job.job_id, amount))
        if a.jobs:
            lines.append("%-10s %-12s %8.2f" % (a.driver.driver_id, "SUBTOTAL", subtotal))
        grand += subtotal
    lines.append("%-23s %8.2f" % ("TOTAL", grand))
    return lines


def driver_utilisation(assignments):
    stats = {}
    for a in assignments:
        cap = a.driver.capacity_kg or 1.0
        stats[a.driver.driver_id] = {
            "jobs": len(a.jobs),
            "load_pct": round(100.0 * a.load_kg / cap, 1),
            "slots_left": MAX_JOBS_PER_DRIVER - len(a.jobs),
        }
    return stats


def simulate(jobs, drivers, start, minutes=120, step=5):
    queue = JobQueue()
    for j in jobs:
        queue.push(j)
    assignments = [Assignment(d) for d in drivers]
    now = start
    end = start + timedelta(minutes=minutes)
    backlog = []
    while now < end and (len(queue) or backlog):
        for j in backlog:
            queue.push(j)
        backlog = dispatch_round(queue, assignments, now)
        now += timedelta(minutes=step)
    return assignments, backlog


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    t0 = datetime(2026, 3, 1, 21, 30)
    demo_jobs = [
        Job("J1", Loc(37.5665, 126.9780), Loc(37.5512, 126.9882), 3.0, t0, 1),
        Job("J2", Loc(37.5700, 126.9920), Loc(37.5796, 126.9770), 25.0, t0, 2),
        Job("J3", Loc(37.4979, 127.0276), Loc(37.5172, 127.0473), 1.0, t0 + timedelta(minutes=10), 1),
    ]
    demo_drivers = [
        Driver("D1", "Kim", Loc(37.5600, 126.9750), 40.0, t0 + timedelta(hours=3)),
        Driver("D2", "Lee", Loc(37.5000, 127.0300), 15.0, t0 + timedelta(hours=1)),
    ]
    result, left = simulate(demo_jobs, demo_drivers, t0)
    for line in invoice(result, t0):
        print(line)
    print("unassigned:", [j.job_id for j in left])
