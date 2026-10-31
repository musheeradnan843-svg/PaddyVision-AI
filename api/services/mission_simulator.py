"""Create a bounded, illustrative lawnmower path over the supplied AOI."""

from __future__ import annotations

import math
from typing import Any


class MissionPlanError(ValueError):
    """Raised when the AOI or assumed mission settings cannot form a plan."""


def _clip_convex(subject: list[tuple[float, float]], clip: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Clip a convex subject polygon to a convex AOI polygon (Sutherland-Hodgman)."""
    signed_area = sum(
        clip[index][0] * clip[(index + 1) % len(clip)][1]
        - clip[(index + 1) % len(clip)][0] * clip[index][1]
        for index in range(len(clip))
    )
    orientation = 1 if signed_area >= 0 else -1
    output = subject
    for index, edge_start in enumerate(clip):
        edge_end = clip[(index + 1) % len(clip)]
        input_points = output
        output = []
        if not input_points:
            break

        def side(point: tuple[float, float]) -> float:
            return orientation * (
                (edge_end[0] - edge_start[0]) * (point[1] - edge_start[1])
                - (edge_end[1] - edge_start[1]) * (point[0] - edge_start[0])
            )

        previous = input_points[-1]
        previous_inside = side(previous) >= -1e-8
        for current in input_points:
            current_inside = side(current) >= -1e-8
            if current_inside != previous_inside:
                dx1, dy1 = current[0] - previous[0], current[1] - previous[1]
                dx2, dy2 = edge_end[0] - edge_start[0], edge_end[1] - edge_start[1]
                denominator = dx1 * dy2 - dy1 * dx2
                if abs(denominator) > 1e-12:
                    t = ((edge_start[0] - previous[0]) * dy2 - (edge_start[1] - previous[1]) * dx2) / denominator
                    output.append((previous[0] + t * dx1, previous[1] + t * dy1))
            if current_inside:
                output.append(current)
            previous, previous_inside = current, current_inside
    return output


def build_illustrative_mission(
    boundary: dict[str, Any],
    altitude_m: float = 60,
    camera_fov_deg: float = 60,
    side_overlap_percent: float = 70,
    cruise_speed_mps: float = 5,
) -> dict[str, Any]:
    """Generate assumed flight lines and AOI-clipped swath shapes in EPSG:32647."""
    if not 30 <= altitude_m <= 120:
        raise MissionPlanError("altitude_m must be between 30 and 120 metres.")
    if not 45 <= camera_fov_deg <= 80:
        raise MissionPlanError("camera_fov_deg must be between 45 and 80 degrees.")
    if not 50 <= side_overlap_percent <= 85:
        raise MissionPlanError("side_overlap_percent must be between 50 and 85 percent.")
    if not 2 <= cruise_speed_mps <= 10:
        raise MissionPlanError("cruise_speed_mps must be between 2 and 10 metres per second.")

    coordinates = boundary.get("coordinates", [])
    if len(coordinates) != 1:
        raise MissionPlanError("The illustrative planner currently supports a single-ring AOI without holes.")
    ring = coordinates[0]
    if len(ring) < 4:
        raise MissionPlanError("The study boundary does not contain a valid polygon ring.")
    open_ring = ring[:-1] if ring[0] == ring[-1] else ring
    if len(open_ring) < 3:
        raise MissionPlanError("The study boundary does not contain enough polygon vertices.")

    try:
        from rasterio.warp import transform

        eastings, northings = transform(
            "EPSG:4326", "EPSG:32647",
            [point[0] for point in open_ring], [point[1] for point in open_ring],
        )
    except Exception as exc:
        raise MissionPlanError(f"Could not project the study boundary to EPSG:32647: {exc}") from exc

    projected = list(zip(eastings, northings))
    turn_signs = []
    for index, point in enumerate(projected):
        following = projected[(index + 1) % len(projected)]
        after = projected[(index + 2) % len(projected)]
        cross = (following[0] - point[0]) * (after[1] - following[1]) - (following[1] - point[1]) * (after[0] - following[0])
        if abs(cross) > 1e-6:
            turn_signs.append(1 if cross > 0 else -1)
    if not turn_signs or len(set(turn_signs)) != 1:
        raise MissionPlanError("The illustrative planner requires a convex single-ring AOI.")
    major_edge = max(
        (
            (projected[(index + 1) % len(projected)][0] - point[0],
             projected[(index + 1) % len(projected)][1] - point[1])
            for index, point in enumerate(projected)
        ),
        key=lambda delta: math.hypot(*delta),
    )
    major_length = math.hypot(*major_edge)
    if major_length == 0:
        raise MissionPlanError("The study boundary has no measurable edge length.")
    ux, uy = major_edge[0] / major_length, major_edge[1] / major_length
    center_e = sum(point[0] for point in projected) / len(projected)
    center_n = sum(point[1] for point in projected) / len(projected)
    polygon = [
        ((easting - center_e) * ux + (northing - center_n) * uy,
         -(easting - center_e) * uy + (northing - center_n) * ux)
        for easting, northing in projected
    ]
    min_x, max_x = min(point[0] for point in polygon), max(point[0] for point in polygon)
    min_y, max_y = min(point[1] for point in polygon), max(point[1] for point in polygon)
    cross_track_width = max_y - min_y
    swath_width = 2 * altitude_m * math.tan(math.radians(camera_fov_deg) / 2)
    line_spacing = swath_width * (1 - side_overlap_percent / 100)
    pass_count = max(1, math.ceil(cross_track_width / line_spacing))
    if pass_count > 200:
        raise MissionPlanError("The selected assumptions produce too many illustrative passes.")
    actual_spacing = cross_track_width / pass_count if pass_count > 1 else 0
    scan_lines = (
        [min_y + actual_spacing * (index + 0.5) for index in range(pass_count)]
        if pass_count > 1 else [(min_y + max_y) / 2]
    )

    route_local: list[tuple[float, float]] = []
    footprints_local: list[list[tuple[float, float]]] = []
    pass_lengths = []
    for index, scan_y in enumerate(scan_lines):
        intersections = []
        for edge_index, start in enumerate(polygon):
            end = polygon[(edge_index + 1) % len(polygon)]
            if (start[1] <= scan_y < end[1]) or (end[1] <= scan_y < start[1]):
                ratio = (scan_y - start[1]) / (end[1] - start[1])
                intersections.append(start[0] + ratio * (end[0] - start[0]))
        intersections.sort()
        if len(intersections) < 2:
            continue
        x_start, x_end = intersections[0], intersections[-1]
        if index % 2:
            x_start, x_end = x_end, x_start
        start_point, end_point = (x_start, scan_y), (x_end, scan_y)
        if not route_local:
            route_local.append(start_point)
        else:
            route_local.append(start_point)
        route_local.append(end_point)
        pass_lengths.append(abs(x_end - x_start))
        footprint_rect = [
            (min(x_start, x_end), scan_y - swath_width / 2),
            (max(x_start, x_end), scan_y - swath_width / 2),
            (max(x_start, x_end), scan_y + swath_width / 2),
            (min(x_start, x_end), scan_y + swath_width / 2),
        ]
        clipped = _clip_convex(footprint_rect, polygon)
        if len(clipped) >= 3:
            footprints_local.append(clipped)

    if len(route_local) < 2:
        raise MissionPlanError("No flight transects could be placed inside the supplied boundary.")

    distance_m = sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(route_local, route_local[1:]))
    local_points = route_local + [point for footprint in footprints_local for point in footprint]
    source_eastings = [center_e + point[0] * ux - point[1] * uy for point in local_points]
    source_northings = [center_n + point[0] * uy + point[1] * ux for point in local_points]
    try:
        longitudes, latitudes = transform("EPSG:32647", "EPSG:4326", source_eastings, source_northings)
    except Exception as exc:
        raise MissionPlanError(f"Could not convert the illustrative plan back to EPSG:4326: {exc}") from exc

    point_index = 0
    route = []
    for sequence, point in enumerate(route_local, start=1):
        route.append({"sequence": sequence, "longitude": longitudes[point_index], "latitude": latitudes[point_index]})
        point_index += 1
    footprints = []
    for index, polygon_points in enumerate(footprints_local, start=1):
        corners = []
        for _ in polygon_points:
            corners.append({"longitude": longitudes[point_index], "latitude": latitudes[point_index]})
            point_index += 1
        footprints.append({"pass": index, "corners": corners})

    return {
        "evidence_class": "SYNTHETIC",
        "status": "ILLUSTRATIVE_SCENARIO_NOT_A_FLIGHT_INSTRUCTION",
        "area_id": "sekinchan_67ha",
        "boundary": boundary,
        "crs": "EPSG:32647",
        "parameters": {
            "altitude_m_assumed": altitude_m,
            "camera_fov_deg_assumed": camera_fov_deg,
            "side_overlap_percent_assumed": side_overlap_percent,
            "cruise_speed_mps_assumed": cruise_speed_mps,
            "swath_width_m_calculated": swath_width,
            "line_spacing_m_planned": line_spacing,
        },
        "summary": {
            "transect_count": len(pass_lengths),
            "route_point_count": len(route),
            "estimated_path_length_m": distance_m,
            "estimated_air_time_minutes": distance_m / cruise_speed_mps / 60,
            "footprints_clipped_to_aoi": True,
        },
        "route": route,
        "footprints": footprints,
        "limitations": "Synthetic geometry only: assumes a convex, single-ring AOI, flat ground, constant altitude, nadir camera, and straight connectors. Time estimate omits turns, climb, wind, battery reserve, obstacles, airspace, and legal/operational checks. Not a flyable route or coverage guarantee.",
    }
