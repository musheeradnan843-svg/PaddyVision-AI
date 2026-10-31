"""Synthetic yield examples and future scenario estimates for the Sekinchan demo."""

import csv
import os
from datetime import date
from pathlib import Path
from typing import Any

import api.config  # Load project-local .env before reading dataset settings.
from api.services.satellite_data import SatelliteDataError, get_satellite_catalogue, get_satellite_window_statistics

DATA_FILE = Path(__file__).resolve().parents[2] / "data" / "demo" / "sekinchan_yield_synthetic.csv"
AOI_AREA_HA = 66.878
FIELD_ID = "SEKINCHAN-AOI-66.878HA"
CAVEAT = (
    "Synthetic demo only. 2023–2025 values are generated examples, not observed harvests. "
    "2026–2027 values are linear-trend scenarios derived only from those synthetic examples. "
    "No yield model has been trained or validated on Sekinchan harvest ground truth. "
    "Satellite, weather, and crop-calendar summaries are context only and are not model inputs. "
    "The 66.878 ha is the reported GIS AOI area, not a measured harvested area."
)


def _historical_records() -> list[dict[str, Any]]:
    if not DATA_FILE.is_file():
        raise FileNotFoundError(f"Synthetic yield demo file was not found: {DATA_FILE}")
    records: list[dict[str, Any]] = []
    with DATA_FILE.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            year = int(row["year"])
            value = float(row["synthetic_yield_t_ha"])
            records.append({
                "field_id": row["field_id"],
                "plot_id": row["plot_id"],
                "year": year,
                "season": row["season"],
                "yield_t_ha": value,
                "total_harvest_t": float(row["synthetic_harvest_weight_t"]),
                "area_ha": float(row["area_ha_reference"]),
                "area_basis": row["area_basis"],
                "record_status": "SYNTHETIC_EXAMPLE",
                "source_note": row["source_note"],
            })
    if not records:
        raise ValueError("Synthetic yield demo file contains no example records.")
    return records


def _linear_scenario(records: list[dict[str, Any]], season: str, target_year: int) -> float:
    """Ordinary least-squares trend over generated examples; illustrative only."""
    points = [(float(row["year"]), float(row["yield_t_ha"])) for row in records if row["season"] == season]
    if len(points) < 2:
        raise ValueError(f"At least two synthetic values are required for {season}.")
    mean_x = sum(point[0] for point in points) / len(points)
    mean_y = sum(point[1] for point in points) / len(points)
    denominator = sum((x - mean_x) ** 2 for x, _ in points)
    slope = sum((x - mean_x) * (y - mean_y) for x, y in points) / denominator
    return round(mean_y + slope * (target_year - mean_x), 3)


def _dataset_root() -> Path:
    configured = os.getenv("PADDYVISION_DATASET_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.append(Path(r"C:\Paddyvision_AI_Dataset"))
    for candidate in candidates:
        if (candidate / "03_Paddy_Crop_Calendar" / "sekinchan_paddy_crop_calendar_reference.csv").is_file():
            return candidate
    raise FileNotFoundError("Sekinchan crop calendar and historical context files are unavailable.")


def _season_bounds(year: int, season: str, rows: list[dict[str, str]]) -> tuple[date, date]:
    intervals = [row for row in rows if row.get("season", "").strip().replace("_", " ") == season]
    if not intervals:
        raise ValueError(f"No crop-calendar interval exists for {season}.")
    starts, ends = [], []
    for row in intervals:
        start_month, start_day = (int(value) for value in row["start_month_day"].split("-"))
        end_month, end_day = (int(value) for value in row["end_month_day"].split("-"))
        start = date(year, start_month, start_day)
        end_year = year + (1 if (end_month, end_day) < (start_month, start_day) else 0)
        end = date(end_year, end_month, end_day)
        starts.append(start)
        ends.append(end)
    return min(starts), max(ends)


def _season_context(year: int, season: str) -> dict[str, Any]:
    empty = {
        "status": "ARCHIVE_CONTEXT_UNAVAILABLE",
        "calendar": {"start_date": None, "end_date": None, "evidence_class": "REFERENCE"},
        "satellite": {"mean_ndvi": None, "direct_windows": 0, "filled_windows": 0, "valid_pixel_window_values": 0},
        "weather": {"mean_temperature_c": None, "precipitation_total_mm": None, "mean_daily_max_wind_kmh": None, "days_available": 0, "days_expected": 0},
        "note": "Historical context could not be joined to this reference season window.",
    }
    try:
        root = _dataset_root()
        calendar_path = root / "03_Paddy_Crop_Calendar" / "sekinchan_paddy_crop_calendar_reference.csv"
        with calendar_path.open("r", encoding="utf-8-sig", newline="") as source:
            calendar_rows = list(csv.DictReader(source))
        start, end = _season_bounds(year, season, calendar_rows)
    except (OSError, ValueError) as exc:
        empty["note"] = str(exc)
        return empty

    result = {
        "status": "PARTIAL_ARCHIVE_CONTEXT",
        "calendar": {"start_date": start.isoformat(), "end_date": end.isoformat(), "evidence_class": "REFERENCE", "note": "Recurring crop-calendar dates; not verified field dates."},
        "satellite": {"mean_ndvi": None, "direct_windows": 0, "filled_windows": 0, "valid_pixel_window_values": 0, "evidence_class": "LOCAL_REMOTE_SENSING"},
        "weather": {"mean_temperature_c": None, "precipitation_total_mm": None, "mean_daily_max_wind_kmh": None, "days_available": 0, "days_expected": (end-start).days+1, "evidence_class": "REFERENCE"},
        "note": "Satellite is an AOI-clipped Sentinel-2 window summary; weather is a regional archive point, not a field sensor. These context values do not feed the synthetic yield scenario.",
    }

    if year > 2025:
        result["status"] = "NO_ARCHIVE_DATA"
        result["note"] = "The recurring calendar window is reference-only; the supplied satellite and historical weather archives end in 2025, so future-season observations are unavailable."
        return result

    weather_path = root / "02_Historical_Weather_Data" / "sekincan_historical_weather_daily_2021_2025.csv"
    try:
        with weather_path.open("r", encoding="utf-8-sig", newline="") as source:
            lines = [line for line in source if line.strip()]
        if len(lines) >= 3:
            days = []
            for row in csv.DictReader(lines[2:]):
                try:
                    observed = date.fromisoformat(row["time"][:10])
                except (KeyError, ValueError):
                    continue
                if start <= observed <= end:
                    days.append(row)
            def numbers(key: str) -> list[float]:
                values = []
                for row in days:
                    try:
                        values.append(float(row[key]))
                    except (KeyError, TypeError, ValueError):
                        pass
                return values
            temps = numbers("temperature_2m_mean (°C)")
            rain = numbers("precipitation_sum (mm)")
            wind = numbers("wind_speed_10m_max (km/h)")
            result["weather"].update({
                "mean_temperature_c": round(sum(temps)/len(temps), 2) if temps else None,
                "precipitation_total_mm": round(sum(rain), 1) if rain else None,
                "mean_daily_max_wind_kmh": round(sum(wind)/len(wind), 2) if wind else None,
                "days_available": len(days),
                "source": "Open-Meteo historical daily archive · regional grid 3.5501°N, 101.0859°E",
            })
    except OSError:
        pass

    try:
        catalogue = get_satellite_catalogue()
        windows = [item for item in catalogue["windows"] if item.get("window_start") and item.get("window_end")
                   and date.fromisoformat(item["window_start"]) <= end and date.fromisoformat(item["window_end"]) >= start]
        statistics = get_satellite_window_statistics([item["window_id"] for item in windows], "NDVI")
        weighted_sum = 0.0
        direct_count = 0
        fill_count = 0
        pixel_values = 0
        for window in windows:
            source_stats = statistics.get(window["window_id"], {}).get("sources", {})
            direct = source_stats.get("v3_10day")
            filled = source_stats.get("v2_monthly_fill")
            if direct:
                weighted_sum += direct["mean"] * direct["pixel_count"]
                direct_count += 1
                pixel_values += direct["pixel_count"]
            if filled:
                fill_count += 1
        result["satellite"].update({
            "mean_ndvi": round(weighted_sum / pixel_values, 4) if pixel_values else None,
            "direct_windows": direct_count,
            "filled_windows": fill_count,
            "valid_pixel_window_values": pixel_values,
            "source": "Sekinchan Sentinel-2 pixel panel · AOI-clipped, 10 m grid",
        })
    except (SatelliteDataError, OSError, ValueError):
        result["satellite"]["source"] = "Satellite seasonal summary unavailable"

    available = result["weather"]["days_available"] > 0 or result["satellite"]["valid_pixel_window_values"] > 0
    if available:
        result["status"] = "ARCHIVE_CONTEXT_AVAILABLE"
    return result


def get_synthetic_yield_outlook() -> dict[str, Any]:
    historical = _historical_records()
    forecasts = []
    for year in (2026, 2027):
        for season in ("Season 1", "Season 2"):
            value = _linear_scenario(historical, season, year)
            forecasts.append({
                "field_id": FIELD_ID,
                "plot_id": "AOI-AGGREGATE-NOT-SUBPLOT",
                "year": year,
                "season": season,
                "yield_t_ha": value,
                "total_harvest_t": round(value * AOI_AREA_HA, 3),
                "area_ha": AOI_AREA_HA,
                "area_basis": "reported GIS AOI area; not measured harvested area",
                "record_status": "SYNTHETIC_TREND_SCENARIO",
                "source_note": "Linear trend over generated synthetic examples; not a trained yield model.",
            })
    records = sorted(historical + forecasts, key=lambda item: (item["year"], item["season"]))
    context_cache: dict[tuple[int, str], dict[str, Any]] = {}
    for record in records:
        key = (record["year"], record["season"])
        if key not in context_cache:
            context_cache[key] = _season_context(*key)
        record["season_context"] = context_cache[key]
    return {
        "field_id": FIELD_ID,
        "plot_id": "AOI-AGGREGATE-NOT-SUBPLOT",
        "aoi_area_ha": AOI_AREA_HA,
        "area_basis": "reported GIS AOI area; not measured harvested area",
        "years": [2023, 2024, 2025, 2026, 2027],
        "seasons": ["Season 1", "Season 2"],
        "records": records,
        "method": "Historical synthetic examples for 2023–2025; 2026–2027 are ordinary least-squares season-specific trends fitted only to those generated examples.",
        "caveat": CAVEAT,
    }
