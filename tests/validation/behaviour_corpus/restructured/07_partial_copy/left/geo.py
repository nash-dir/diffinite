"""Geographic helpers for the fleet-tracking service."""

import math
from dataclasses import dataclass

EARTH_RADIUS_KM = 6371.0088


@dataclass(frozen=True)
class Point:
    lat: float
    lon: float

    def __post_init__(self):
        if not -90.0 <= self.lat <= 90.0:
            raise ValueError("latitude out of range: %r" % self.lat)
        if not -180.0 <= self.lon <= 180.0:
            raise ValueError("longitude out of range: %r" % self.lon)


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


def initial_bearing(a, b):
    """Compass bearing in degrees from a to b."""
    phi1 = math.radians(a.lat)
    phi2 = math.radians(b.lat)
    dlmb = math.radians(b.lon - a.lon)
    x = math.sin(dlmb) * math.cos(phi2)
    y = math.cos(phi1) * math.sin(phi2) - math.sin(phi1) * math.cos(phi2) * math.cos(dlmb)
    return (math.degrees(math.atan2(x, y)) + 360.0) % 360.0


def destination(start, bearing_deg, distance_km):
    """Point reached travelling distance_km from start on a bearing."""
    delta = distance_km / EARTH_RADIUS_KM
    theta = math.radians(bearing_deg)
    phi1 = math.radians(start.lat)
    lmb1 = math.radians(start.lon)
    phi2 = math.asin(math.sin(phi1) * math.cos(delta) + math.cos(phi1) * math.sin(delta) * math.cos(theta))
    lmb2 = lmb1 + math.atan2(
        math.sin(theta) * math.sin(delta) * math.cos(phi1),
        math.cos(delta) - math.sin(phi1) * math.sin(phi2),
    )
    lon = (math.degrees(lmb2) + 540.0) % 360.0 - 180.0
    return Point(math.degrees(phi2), lon)


def route_length_km(points):
    """Total length of a polyline route."""
    total = 0.0
    for prev, cur in zip(points, points[1:]):
        total += haversine_km(prev, cur)
    return total


def nearest(target, candidates):
    """Return (index, distance) of the candidate closest to target."""
    best_i = -1
    best_d = float("inf")
    for i, c in enumerate(candidates):
        d = haversine_km(target, c)
        if d < best_d:
            best_i, best_d = i, d
    return best_i, best_d


def point_in_polygon(p, polygon):
    """Ray-casting test; polygon is a list of Points, implicitly closed."""
    inside = False
    n = len(polygon)
    j = n - 1
    for i in range(n):
        yi, xi = polygon[i].lat, polygon[i].lon
        yj, xj = polygon[j].lat, polygon[j].lon
        if (yi > p.lat) != (yj > p.lat):
            x_cross = (xj - xi) * (p.lat - yi) / (yj - yi) + xi
            if p.lon < x_cross:
                inside = not inside
        j = i
    return inside


def simplify(points, tolerance_km):
    """Drop consecutive points closer than tolerance_km to the last kept one."""
    if not points:
        return []
    kept = [points[0]]
    for p in points[1:-1]:
        if haversine_km(kept[-1], p) >= tolerance_km:
            kept.append(p)
    if len(points) > 1:
        kept.append(points[-1])
    return kept
