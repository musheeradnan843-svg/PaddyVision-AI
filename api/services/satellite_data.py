import csv
import json
import math
import os
import sqlite3
import threading
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from api.runtime_paths import get_runtime_data_dir


_BUILD_LOCK = threading.Lock()
_SCHEMA_VERSION = "2"
_METRICS = {"NDVI", "NDMI", "NDWI", "S1_VV", "S1_VH"}
_COMPARISON_YEARS = (2023, 2024, 2025)


class SatelliteDataError(RuntimeError):
    """Raised when the Sekinchan satellite package is unavailable or invalid."""


def _dataset_root() -> Path:
    configured = os.getenv("PADDYVISION_DATASET_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.extend([
        Path(r"C:\Paddyvision_AI_Dataset"),
        Path(__file__).resolve().parents[2] / "data" / "external" / "sekinchan-67ha",
    ])
    for candidate in candidates:
        if (candidate / "01_Satellite_Imagery_Spatial_Data" / "paddyvision_v3_pixels_panel_2023_2025.csv").is_file():
            return candidate
    expected = " or ".join(str(path) for path in candidates)
    raise SatelliteDataError(
        "Sekinchan satellite CSV was not found. Set PADDYVISION_DATASET_ROOT to the "
        f"folder containing 01_Satellite_Imagery_Spatial_Data. Checked: {expected}"
    )


def _paths() -> dict[str, Path]:
    root = _dataset_root()
    return {
        "panel": root / "01_Satellite_Imagery_Spatial_Data" / "paddyvision_v3_pixels_panel_2023_2025.csv",
        "summary": root / "01_Satellite_Imagery_Spatial_Data" / "paddyvision_v3_window_summary_2023_2025.csv",
        "boundary": root / "04_Soil_and_Ground_Truth" / "02_Boundary" / "sekinchan_study_area_polygon.geojson",
    }


def _read_boundary(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8-sig") as source:
            feature = json.load(source)["features"][0]
        geometry = feature["geometry"]
        if geometry["type"] != "Polygon":
            raise ValueError("Expected a GeoJSON Polygon.")
        return {
            "type": geometry["type"],
            "coordinates": geometry["coordinates"],
            "area_ha": 66.878,
            "area_ha_basis": "soil package QA report, UTM 47N",
            "crs": "EPSG:4326",
            "coordinate_order": "longitude,latitude",
        }
    except (OSError, KeyError, IndexError, ValueError, json.JSONDecodeError) as exc:
        raise SatelliteDataError(f"Could not read the Sekinchan study boundary: {exc}") from exc


def _number(value: str | None) -> float | None:
    try:
        parsed = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def get_satellite_catalogue() -> dict[str, Any]:
    paths = _paths()
    for key in ("summary", "boundary"):
        if not paths[key].is_file():
            raise SatelliteDataError(f"Required satellite file is missing: {paths[key]}")
    windows: list[dict[str, Any]] = []
    try:
        with paths["summary"].open("r", newline="", encoding="utf-8-sig") as source:
            for row in csv.DictReader(source):
                windows.append({
                    "window_id": row.get("window_id"),
                    "year": int(row["year"]) if row.get("year", "").isdigit() else None,
                    "window_start": row.get("window_start"),
                    "window_end": row.get("window_end"),
                    "usable_s2_or_s1": row.get("usable_s2_or_s1") == "1",
                    "haze_window_removed": row.get("haze_window_removed") == "1",
                    "s2_valid_pct_after_fill": _number(row.get("s2_valid_pct_after_fill")),
                    "n_s2_v3": _number(row.get("n_s2_v3")),
                    "n_s2_fill": _number(row.get("n_s2_fill")),
                    "n_s1": _number(row.get("n_s1")),
                    "mean_ndvi": _number(row.get("NDVI_mean_all")),
                    "mean_ndmi": _number(row.get("NDMI_mean_all")),
                    "mean_ndwi": _number(row.get("NDWI_mean_all")),
                    "mean_s1_vv": _number(row.get("S1_VV_mean")),
                    "mean_s1_vh": _number(row.get("S1_VH_mean")),
                    "fill_confidence": row.get("fill_confidence") or None,
                    "fill_month": row.get("fill_month") or None,
                    "fill_decision": row.get("fill_decision_for_month") or None,
                })
    except OSError as exc:
        raise SatelliteDataError(f"Could not read the satellite window summary: {exc}") from exc
    windows.sort(key=lambda item: (item["window_start"] or "", item["window_id"] or ""))
    boundary = _read_boundary(paths["boundary"])
    return {
        "area_id": "sekinchan_67ha",
        "evidence_class": "LOCAL_REMOTE_SENSING",
        "source": "PaddyVision v3 merged Sentinel-1/2 pixel panel and window summary",
        "period": "2023-01-01/2025-12-31",
        "crs": "EPSG:4326",
        "pixel_size_m": 10,
        "boundary": boundary,
        "windows": windows,
    }


def _inside_polygon(longitude: float, latitude: float, ring: list[list[float]]) -> bool:
    inside = False
    for index in range(len(ring) - 1):
        x1, y1 = ring[index]
        x2, y2 = ring[index + 1]
        if (y1 > latitude) != (y2 > latitude):
            crossing_x = (x2 - x1) * (latitude - y1) / (y2 - y1) + x1
            if longitude < crossing_x:
                inside = not inside
    return inside


def _index_path() -> Path:
    return get_runtime_data_dir() / "sekinchan_satellite_panel.sqlite3"


def _source_signature(paths: dict[str, Path]) -> str:
    parts = []
    for key in ("panel", "boundary"):
        path = paths[key]
        if not path.is_file():
            raise SatelliteDataError(f"Required satellite file is missing: {path}")
        stat = path.stat()
        parts.append(f"{path.resolve()}:{stat.st_size}:{stat.st_mtime_ns}")
    return "|".join(parts)


def _index_is_current(path: Path, signature: str) -> bool:
    if not path.is_file():
        return False
    try:
        with sqlite3.connect(path) as connection:
            metadata = dict(connection.execute("SELECT key, value FROM metadata"))
        return metadata.get("source_signature") == signature and metadata.get("schema_version") == _SCHEMA_VERSION
    except sqlite3.Error:
        return False


def _build_index(index_path: Path, paths: dict[str, Path], signature: str) -> None:
    boundary = _read_boundary(paths["boundary"])
    ring = boundary["coordinates"][0]
    temporary = index_path.with_suffix(".building.sqlite3")
    if temporary.exists():
        temporary.unlink()
    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA journal_mode = OFF")
        connection.execute("PRAGMA synchronous = OFF")
        connection.executescript("""
            CREATE TABLE metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE pixels (
                window_id TEXT NOT NULL, latitude REAL NOT NULL, longitude REAL NOT NULL,
                ndvi REAL, ndmi REAL, ndwi REAL, s1_vv REAL, s1_vh REAL,
                s2_source TEXT, s2_fill_confidence TEXT
            );
        """)
        connection.executemany("INSERT INTO metadata VALUES (?, ?)", [
            ("source_signature", signature), ("schema_version", _SCHEMA_VERSION)
        ])
        batch: list[tuple[Any, ...]] = []
        with paths["panel"].open("r", newline="", encoding="utf-8-sig") as source:
            reader = csv.DictReader(source)
            required = {"window_id", "latitude", "longitude", "NDVI", "NDMI", "NDWI", "S1_VV", "S1_VH"}
            if not required.issubset(set(reader.fieldnames or [])):
                raise SatelliteDataError("The satellite pixel panel is missing required columns.")
            for row in reader:
                latitude = _number(row.get("latitude"))
                longitude = _number(row.get("longitude"))
                if latitude is None or longitude is None or not _inside_polygon(longitude, latitude, ring):
                    continue
                batch.append((
                    row["window_id"], latitude, longitude,
                    _number(row.get("NDVI")), _number(row.get("NDMI")), _number(row.get("NDWI")),
                    _number(row.get("S1_VV")), _number(row.get("S1_VH")),
                    row.get("s2_source") or None, row.get("s2_fill_confidence") or None,
                ))
                if len(batch) >= 10000:
                    connection.executemany("INSERT INTO pixels VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
                    batch.clear()
        if batch:
            connection.executemany("INSERT INTO pixels VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)", batch)
        connection.execute(
            "CREATE INDEX pixels_by_window_location "
            "ON pixels(window_id, s2_source, latitude, longitude)"
        )
        connection.commit()
        connection.close()
        os.replace(temporary, index_path)
    except Exception:
        connection.close()
        if temporary.exists():
            temporary.unlink()
        raise


def _ensure_index() -> Path:
    paths = _paths()
    signature = _source_signature(paths)
    index_path = _index_path()
    if _index_is_current(index_path, signature):
        return index_path
    with _BUILD_LOCK:
        if not _index_is_current(index_path, signature):
            try:
                _build_index(index_path, paths, signature)
            except SatelliteDataError:
                raise
            except (OSError, sqlite3.Error, csv.Error) as exc:
                raise SatelliteDataError(f"Could not prepare the local satellite cache: {exc}") from exc
    return index_path


def get_satellite_window(window_id: str, metric: str = "NDVI", s2_source: str = "all") -> dict[str, Any]:
    metric = metric.upper()
    if metric not in _METRICS:
        raise ValueError(f"metric must be one of {', '.join(sorted(_METRICS))}")
    if s2_source not in {"all", "v3_10day", "v2_monthly_fill"}:
        raise ValueError("s2_source must be all, v3_10day, or v2_monthly_fill")

    catalogue = get_satellite_catalogue()
    summary = next((item for item in catalogue["windows"] if item["window_id"] == window_id), None)
    if summary is None:
        raise ValueError("Unknown satellite window_id")
    column = {"NDVI": "ndvi", "NDMI": "ndmi", "NDWI": "ndwi", "S1_VV": "s1_vv", "S1_VH": "s1_vh"}[metric]
    query = f"SELECT latitude, longitude, {column}, s2_source, s2_fill_confidence FROM pixels WHERE window_id = ? AND {column} IS NOT NULL"
    params: list[Any] = [window_id]
    if metric.startswith("ND") and s2_source != "all":
        query += " AND s2_source = ?"
        params.append(s2_source)
    query += " ORDER BY latitude, longitude"
    index_path = _ensure_index()
    try:
        with sqlite3.connect(index_path) as connection:
            rows = connection.execute(query, params).fetchall()
    except sqlite3.Error as exc:
        raise SatelliteDataError(f"Could not query the satellite pixel cache: {exc}") from exc

    values = [row[2] for row in rows]
    source_counts: dict[str, int] = {}
    points = []
    for latitude, longitude, value, source, confidence in rows:
        key = "Sentinel-1 observation" if metric.startswith("S1_") else (source or "no_s2_value")
        source_counts[key] = source_counts.get(key, 0) + 1
        points.append({
            "latitude": latitude, "longitude": longitude, "value": value,
            "s2_source": source, "s2_fill_confidence": confidence,
        })
    return {
        "area_id": "sekinchan_67ha",
        "window_id": window_id,
        "window_start": summary["window_start"],
        "window_end": summary["window_end"],
        "metric": metric,
        "unit": "index" if metric.startswith("ND") else "dB",
        "s2_source_filter": s2_source,
        "evidence_class": "LOCAL_REMOTE_SENSING",
        "boundary": catalogue["boundary"],
        "summary": {
            "pixel_count": len(points),
            "mean": sum(values) / len(values) if values else None,
            "min": min(values) if values else None,
            "max": max(values) if values else None,
            "source_counts": source_counts,
            "window_summary": summary,
        },
        "points": points,
    }


def get_satellite_window_statistics(window_ids: list[str], metric: str = "NDVI") -> dict[str, dict[str, Any]]:
    """Return polygon-clipped per-window source statistics without materializing pixel arrays."""
    metric = metric.upper()
    if metric not in _METRICS:
        raise ValueError(f"metric must be one of {', '.join(sorted(_METRICS))}")
    catalogue = get_satellite_catalogue()
    known_ids = {item["window_id"] for item in catalogue["windows"]}
    selected = list(dict.fromkeys(item for item in window_ids if item in known_ids))
    if not selected:
        return {}
    column = {"NDVI": "ndvi", "NDMI": "ndmi", "NDWI": "ndwi", "S1_VV": "s1_vv", "S1_VH": "s1_vh"}[metric]
    placeholders = ",".join("?" for _ in selected)
    query = (
        f"SELECT window_id, COALESCE(s2_source, 'unknown'), COUNT(*), AVG({column}) "
        f"FROM pixels WHERE window_id IN ({placeholders}) AND {column} IS NOT NULL "
        "GROUP BY window_id, COALESCE(s2_source, 'unknown')"
    )
    index_path = _ensure_index()
    output: dict[str, dict[str, Any]] = {window_id: {"sources": {}} for window_id in selected}
    try:
        with sqlite3.connect(index_path) as connection:
            for window_id, source, count, mean in connection.execute(query, selected):
                output[window_id]["sources"][source] = {"pixel_count": int(count), "mean": float(mean)}
    except sqlite3.Error as exc:
        raise SatelliteDataError(f"Could not calculate the polygon-clipped seasonal satellite summary: {exc}") from exc
    return output


def get_satellite_year_comparison() -> dict[str, Any]:
    """Compare satellite NDVI using the same calendar dekad in each year."""
    catalogue = get_satellite_catalogue()
    windows = catalogue["windows"]
    statistics = get_satellite_window_statistics(
        [item["window_id"] for item in windows],
        "NDVI",
    )
    years = [year for year in _COMPARISON_YEARS if any(item["year"] == year for item in windows)]
    year_slots = _calendar_dekad_windows(windows)
    comparison_pairs = []
    observations = []

    for month in range(1, 13):
        for dekad in range(1, 4):
            period_index = (month - 1) * 3 + dekad - 1
            slot: dict[str, Any] = {
                "period_index": period_index,
                "month": month,
                "dekad": dekad,
                "period_label": _dekad_label(month, dekad),
                "years": {},
            }
            for year in years:
                item = year_slots.get(year, {}).get((month, dekad))
                if item is None:
                    continue
                window_id = item["window_id"]
                sources = statistics.get(window_id, {}).get("sources", {})
                direct = sources.get("v3_10day", {})
                monthly_fill = sources.get("v2_monthly_fill", {})
                slot["years"][str(year)] = {
                    "window_id": window_id,
                    "window_start": item["window_start"],
                    "window_end": item["window_end"],
                    "direct_mean": direct.get("mean"),
                    "direct_pixel_count": direct.get("pixel_count", 0),
                    "monthly_fill_mean": monthly_fill.get("mean"),
                    "monthly_fill_pixel_count": monthly_fill.get("pixel_count", 0),
                }
            baseline = slot["years"].get("2023", {})
            comparison = slot["years"].get("2025", {})
            if baseline.get("direct_pixel_count", 0) and comparison.get("direct_pixel_count", 0):
                comparison_pairs.append((baseline["window_id"], comparison["window_id"]))
            observations.append(slot)

    paired_statistics = _paired_direct_statistics(comparison_pairs)
    for slot in observations:
        baseline = slot["years"].get("2023", {})
        comparison = slot["years"].get("2025", {})
        paired = paired_statistics.get(baseline.get("window_id"))
        slot["change_2025_minus_2023"] = paired["mean"] if paired else None
        slot["paired_pixel_count"] = paired["pixel_count"] if paired else 0

    return {
        "area_id": catalogue["area_id"],
        "evidence_class": catalogue["evidence_class"],
        "source": catalogue["source"],
        "metric": "NDVI",
        "unit": "unitless",
        "years": years,
        "reference_max_direct_pixel_count": max(
            (
                source_stats.get("pixel_count", 0)
                for window_stats in statistics.values()
                for source, source_stats in window_stats["sources"].items()
                if source == "v3_10day"
            ),
            default=0,
        ),
        "observations": observations,
        "comparison_note": (
            "Windows are assigned to the calendar month/dekad they overlap most; "
            "actual window dates are shown. Annual lines use direct Sentinel-2 "
            "observations only. The 2025–2023 difference is the mean per-pixel "
            "difference on shared 10 m grid cells with direct observations in both "
            "years. Monthly fills are shown separately and excluded. Statistics are "
            "clipped to the supplied study-area boundary."
        ),
    }


def get_satellite_year_difference_map(month: int, dekad: int) -> dict[str, Any]:
    """Return same-grid direct NDVI differences for one calendar period."""
    if not 1 <= month <= 12 or not 1 <= dekad <= 3:
        raise ValueError("month must be 1–12 and dekad must be 1–3")

    catalogue = get_satellite_catalogue()
    year_slots = _calendar_dekad_windows(catalogue["windows"])
    baseline = year_slots.get(2023, {}).get((month, dekad))
    comparison = year_slots.get(2025, {}).get((month, dekad))
    if baseline is None or comparison is None:
        raise SatelliteDataError("Satellite windows are unavailable for the selected calendar period.")

    window_2023 = baseline["window_id"]
    window_2025 = comparison["window_id"]
    statistics = get_satellite_window_statistics([window_2023, window_2025], "NDVI")
    index_path = _ensure_index()
    query = """
        SELECT older.latitude, older.longitude, newer.ndvi - older.ndvi
        FROM pixels AS older
        JOIN pixels AS newer
          ON newer.window_id = ?
         AND newer.s2_source = 'v3_10day'
         AND newer.latitude = older.latitude
         AND newer.longitude = older.longitude
         AND newer.ndvi IS NOT NULL
        WHERE older.window_id = ?
          AND older.s2_source = 'v3_10day'
          AND older.ndvi IS NOT NULL
        ORDER BY older.latitude, older.longitude
    """
    try:
        with sqlite3.connect(index_path) as connection:
            rows = connection.execute(query, (window_2025, window_2023)).fetchall()
    except sqlite3.Error as exc:
        raise SatelliteDataError(f"Could not calculate the paired-pixel NDVI difference: {exc}") from exc

    differences = [row[2] for row in rows]
    direct_pixels_2023 = statistics.get(window_2023, {}).get("sources", {}).get("v3_10day", {}).get("pixel_count", 0)
    direct_pixels_2025 = statistics.get(window_2025, {}).get("sources", {}).get("v3_10day", {}).get("pixel_count", 0)
    smaller_direct_coverage = min(direct_pixels_2023, direct_pixels_2025)
    return {
        "area_id": catalogue["area_id"],
        "evidence_class": catalogue["evidence_class"],
        "month": month,
        "dekad": dekad,
        "period_label": _dekad_label(month, dekad),
        "metric": "NDVI",
        "unit": "index difference",
        "window_2023": {
            "window_id": window_2023,
            "window_start": baseline["window_start"],
            "window_end": baseline["window_end"],
            "direct_pixel_count": direct_pixels_2023,
        },
        "window_2025": {
            "window_id": window_2025,
            "window_start": comparison["window_start"],
            "window_end": comparison["window_end"],
            "direct_pixel_count": direct_pixels_2025,
        },
        "paired_pixel_count": len(rows),
        "overlap_percent_of_smaller_direct_coverage": (
            len(rows) / smaller_direct_coverage * 100 if smaller_direct_coverage else None
        ),
        "mean_difference": sum(differences) / len(differences) if differences else None,
        "min_difference": min(differences) if differences else None,
        "max_difference": max(differences) if differences else None,
        "comparison_note": (
            "Each value is 2025 NDVI minus 2023 NDVI at the same pixel coordinate, "
            "using direct Sentinel-2 observations in both selected windows. "
            "Monthly fills and unpaired pixels are excluded."
        ),
        "points": [
            {"latitude": latitude, "longitude": longitude, "difference": difference}
            for latitude, longitude, difference in rows
        ],
    }


def _paired_direct_statistics(
    window_pairs: list[tuple[str, str]],
) -> dict[str, dict[str, float | int]]:
    if not window_pairs:
        return {}

    values = ",".join("(?, ?)" for _ in window_pairs)
    params = [window_id for pair in window_pairs for window_id in pair]
    query = f"""
        WITH comparisons(window_2023, window_2025) AS (VALUES {values})
        SELECT comparisons.window_2023, COUNT(*), AVG(newer.ndvi - older.ndvi)
        FROM comparisons
        JOIN pixels AS older
          ON older.window_id = comparisons.window_2023
         AND older.s2_source = 'v3_10day'
         AND older.ndvi IS NOT NULL
        JOIN pixels AS newer
          ON newer.window_id = comparisons.window_2025
         AND newer.s2_source = 'v3_10day'
         AND newer.latitude = older.latitude
         AND newer.longitude = older.longitude
         AND newer.ndvi IS NOT NULL
        GROUP BY comparisons.window_2023
    """
    index_path = _ensure_index()
    try:
        with sqlite3.connect(index_path) as connection:
            return {
                window_2023: {"pixel_count": int(count), "mean": float(mean)}
                for window_2023, count, mean in connection.execute(query, params)
            }
    except sqlite3.Error as exc:
        raise SatelliteDataError(f"Could not summarize paired satellite pixels: {exc}") from exc


def _calendar_dekad_windows(
    windows: list[dict[str, Any]],
) -> dict[int, dict[tuple[int, int], dict[str, Any]]]:
    """Assign each satellite window to the calendar dekad with greatest date overlap."""
    selected: dict[int, dict[tuple[int, int], tuple[tuple[int, int, int], dict[str, Any]]]] = {}
    for item in windows:
        year = item.get("year")
        if year not in _COMPARISON_YEARS or not item.get("window_id"):
            continue
        try:
            start = date.fromisoformat(item["window_start"])
            end = date.fromisoformat(item["window_end"])
        except (TypeError, ValueError) as exc:
            raise SatelliteDataError(f"Invalid date in satellite window {item.get('window_id')}.") from exc
        if start.year != year or end < start:
            raise SatelliteDataError(f"Invalid date range in satellite window {item.get('window_id')}.")

        duration = (end - start).days + 1
        for month in range(1, 13):
            for dekad, first_day, last_day in ((1, 1, 10), (2, 11, 20), (3, 21, None)):
                bin_start = date(year, month, first_day)
                if last_day is None:
                    bin_end = (
                        date(year + 1, 1, 1) - timedelta(days=1)
                        if month == 12
                        else date(year, month + 1, 1) - timedelta(days=1)
                    )
                else:
                    bin_end = date(year, month, last_day)
                overlap = max(0, (min(end, bin_end) - max(start, bin_start)).days + 1)
                if overlap == 0:
                    continue
                key = (month, dekad)
                rank = (overlap, duration, -start.toordinal())
                existing = selected.setdefault(year, {}).get(key)
                if existing is None or rank > existing[0]:
                    selected[year][key] = (rank, item)

    return {
        year: {period: item for period, (_, item) in periods.items()}
        for year, periods in selected.items()
    }


def _dekad_label(month: int, dekad: int) -> str:
    month_name = date(2000, month, 1).strftime("%b")
    date_range = {1: "1–10", 2: "11–20", 3: "21–end"}[dekad]
    return f"{month_name} {date_range}"
