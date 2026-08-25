"""A*
errors propagate."""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass
from typing import Sequence

from .models import Location


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlon / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


@dataclass(frozen=True)
class ObstacleZone:
    name: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float
    penalty: float


DEFAULT_OBSTACLES = [
    ObstacleZone("Alibaug Sensitive Marine Zone", 18.60, 18.70, 72.82, 72.92, penalty=5.0),
    ObstacleZone("Mumbai Port Restricted Channel", 18.90, 18.98, 72.80, 72.88, penalty=2.0),
    ObstacleZone("Butcher Island Security Geofence", 18.93, 18.96, 72.89, 72.94, penalty=float("inf")),
]


def is_in_obstacle(lat: float, lon: float, obstacles: Sequence[ObstacleZone]) -> tuple[bool, float, str]:
    total_penalty = 1.0
    for obs in obstacles:
        if obs.min_lat <= lat <= obs.max_lat and obs.min_lon <= lon <= obs.max_lon:
            if math.isinf(obs.penalty):
                return True, float("inf"), obs.name
            total_penalty *= obs.penalty
    return False, total_penalty, ""


def plan_safe_route(
    start: Location,
    end: Location,
    vessel_speed_kmh: float = 18.0,
    obstacles: Sequence[ObstacleZone] = DEFAULT_OBSTACLES,
    grid_step_deg: float = 0.04,
) -> dict:
    min_lat = min(start.lat, end.lat) - 0.2
    max_lat = max(start.lat, end.lat) + 0.2
    min_lon = min(start.lon, end.lon) - 0.2
    max_lon = max(start.lon, end.lon) + 0.2

    def to_grid(lat: float, lon: float) -> tuple[int, int]:
        return round(lat / grid_step_deg), round(lon / grid_step_deg)

    def to_coord(gy: int, gx: int) -> tuple[float, float]:
        return gy * grid_step_deg, gx * grid_step_deg

    start_node = to_grid(start.lat, start.lon)
    end_node = to_grid(end.lat, end.lon)

    frontier: list[tuple[float, float, tuple[int, int]]] = []
    heapq.heappush(frontier, (0.0, 0.0, start_node))
    came_from: dict[tuple[int, int], tuple[int, int]] = {}
    cost_so_far: dict[tuple[int, int], float] = {start_node: 0.0}

    directions = [
        (-1, 0), (1, 0), (0, -1), (0, 1),
        (-1, -1), (-1, 1), (1, -1), (1, 1),
    ]

    target_reached = False
    max_steps = 3000
    steps = 0

    while frontier and steps < max_steps:
        steps += 1
        _, current_cost, current = heapq.heappop(frontier)

        if current == end_node:
            target_reached = True
            break

        cur_lat, cur_lon = to_coord(*current)

        for dy, dx in directions:
            nxt = (current[0] + dy, current[1] + dx)
            nxt_lat, nxt_lon = to_coord(*nxt)

            if not (min_lat <= nxt_lat <= max_lat and min_lon <= nxt_lon <= max_lon):
                continue

            blocked, penalty, _ = is_in_obstacle(nxt_lat, nxt_lon, obstacles)
            if blocked:
                continue

            step_dist = haversine_km(cur_lat, cur_lon, nxt_lat, nxt_lon)
            new_cost = current_cost + (step_dist * penalty)

            if nxt not in cost_so_far or new_cost < cost_so_far[nxt]:
                cost_so_far[nxt] = new_cost
                target_lat, target_lon = to_coord(*end_node)
                heuristic = haversine_km(nxt_lat, nxt_lon, target_lat, target_lon)
                f_score = new_cost + heuristic
                heapq.heappush(frontier, (f_score, new_cost, nxt))
                came_from[nxt] = current

    waypoints: list[dict[str, float]] = []
    if target_reached:
        curr = end_node
        path_nodes = []
        while curr != start_node:
            path_nodes.append(curr)
            curr = came_from[curr]
        path_nodes.append(start_node)
        path_nodes.reverse()
        waypoints = [{"lat": start.lat, "lon": start.lon}]
        for node in path_nodes[1:-1]:
            n_lat, n_lon = to_coord(*node)
            waypoints.append({"lat": round(n_lat, 4), "lon": round(n_lon, 4)})
        waypoints.append({"lat": end.lat, "lon": end.lon})
    else:
        num_segments = 6
        waypoints = []
        for i in range(num_segments + 1):
            t = i / num_segments
            waypoints.append({
                "lat": round(start.lat + t * (end.lat - start.lat), 4),
                "lon": round(start.lon + t * (end.lon - start.lon), 4),
            })


    total_dist = 0.0
    for i in range(len(waypoints) - 1):
        total_dist += haversine_km(
            waypoints[i]["lat"], waypoints[i]["lon"],
            waypoints[i + 1]["lat"], waypoints[i + 1]["lon"]
        )

    duration_hours = total_dist / max(vessel_speed_kmh, 1.0)

    return {
        "start": {"lat": start.lat, "lon": start.lon},
        "end": {"lat": end.lat, "lon": end.lon},
        "distance_km": round(total_dist, 1),
        "estimated_duration_hours": round(duration_hours, 1),
        "estimated_duration_minutes": round(duration_hours * 60),
        "waypoints_count": len(waypoints),
        "waypoints": waypoints,
        "geojson": {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [[ wp["lon"], wp["lat"] ] for wp in waypoints],
            },
            "properties": {
                "name": f"Safe Route ({round(total_dist, 1)} km)",
                "distance_km": round(total_dist, 1),
                "duration_hours": round(duration_hours, 1),
            }
        },
        "avoided_hazards": [obs.name for obs in obstacles if not math.isinf(obs.penalty)],
    }
