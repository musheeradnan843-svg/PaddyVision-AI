import csv
import os
from datetime import date, timedelta
from pathlib import Path
from typing import Any

import api.config  # Load project-local .env before reading dataset settings.
from api.services.satellite_data import SatelliteDataError, get_satellite_catalogue


def _root() -> Path:
    configured = os.getenv("PADDYVISION_DATASET_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.append(Path(r"C:\Paddyvision_AI_Dataset"))
    for candidate in candidates:
        if (candidate / "02_Historical_Weather_Data" / "sekincan_historical_weather_daily_2021_2025.csv").is_file():
            return candidate
    raise SatelliteDataError("Sekinchan weather context files were not found. Set PADDYVISION_DATASET_ROOT.")


def _number(row: dict[str, str], key: str) -> float | None:
    try:
        return float(row[key])
    except (KeyError, TypeError, ValueError):
        return None


def get_environment_context(window_id: str) -> dict[str, Any]:
    catalogue = get_satellite_catalogue()
    window = next((item for item in catalogue["windows"] if item["window_id"] == window_id), None)
    if window is None:
        raise ValueError("Unknown satellite window_id")
    start, end = date.fromisoformat(window["window_start"]), date.fromisoformat(window["window_end"])
    root = _root()
    weather_file = root / "02_Historical_Weather_Data" / "sekincan_historical_weather_daily_2021_2025.csv"
    calendar_file = root / "03_Paddy_Crop_Calendar" / "sekinchan_paddy_crop_calendar_reference.csv"

    days = []
    with weather_file.open("r", encoding="utf-8-sig", newline="") as source:
        weather_lines = [line for line in source if line.strip()]
    if len(weather_lines) < 3:
        raise SatelliteDataError("Sekinchan daily weather CSV is missing its header or observations.")
    weather_rows = csv.DictReader(weather_lines[2:])
    for row in weather_rows:
        try:
            observed = date.fromisoformat(row["time"][:10])
        except (KeyError, ValueError):
            continue
        if start <= observed <= end:
            days.append({
                "temperature": _number(row, "temperature_2m_mean (°C)"),
                "rain": _number(row, "precipitation_sum (mm)"),
                "wind": _number(row, "wind_speed_10m_max (km/h)"),
            })
    temps = [row["temperature"] for row in days if row["temperature"] is not None]
    rain = [row["rain"] for row in days if row["rain"] is not None]
    wind = [row["wind"] for row in days if row["wind"] is not None]

    calendar_records = []
    with calendar_file.open("r", encoding="utf-8-sig", newline="") as source:
        for row in csv.DictReader(source):
            try:
                row["growth_stage_id"] = int(row["growth_stage_id"]) if row.get("growth_stage_id", "").strip() else None
                row["start_month_day"] = row["start_month_day"].strip()
                row["end_month_day"] = row["end_month_day"].strip()
            except (KeyError, TypeError, ValueError) as exc:
                raise SatelliteDataError("Sekinchan crop calendar has an invalid interval or growth stage id.") from exc
            calendar_records.append(row)

    calendar_days = (end - start).days + 1
    calendar_coverage: dict[tuple[str, str, int | None, str], int] = {}
    cursor = start
    while cursor <= end:
        day_key = cursor.strftime("%m-%d")
        match = next((row for row in calendar_records if row["start_month_day"] <= day_key <= row["end_month_day"]), None)
        if match:
            key = (match["season"], match["expected_crop_stage"], match["growth_stage_id"], match["reference_status"])
            calendar_coverage[key] = calendar_coverage.get(key, 0) + 1
        cursor += timedelta(days=1)

    calendar = [
        {"season": key[0], "expected_crop_stage": key[1], "growth_stage_id": key[2],
         "reference_status": key[3], "days_in_window": count}
        for key, count in sorted(calendar_coverage.items(), key=lambda item: (-item[1], item[0][0], item[0][1]))
    ]
    calendar_stage_id = None
    calendar_stage_label = None
    calendar_stage_coverage = 0
    calendar_stage_kind = "unavailable"
    if calendar:
        stage_coverage: dict[int | None, int] = {}
        stage_labels: dict[int | None, list[str]] = {}
        for row in calendar:
            stage_id = row["growth_stage_id"]
            stage_coverage[stage_id] = stage_coverage.get(stage_id, 0) + row["days_in_window"]
            stage_labels.setdefault(stage_id, [])
            if row["expected_crop_stage"] not in stage_labels[stage_id]:
                stage_labels[stage_id].append(row["expected_crop_stage"])
        top_days = max(stage_coverage.values())
        leaders = [stage_id for stage_id, count in stage_coverage.items() if count == top_days]
        if len(leaders) == 1:
            winner_id = leaders[0]
            calendar_stage_label = " / ".join(stage_labels[winner_id])
            calendar_stage_coverage = top_days
            if winner_id is None:
                calendar_stage_kind = "between_seasons"
            else:
                calendar_stage_id = winner_id
                calendar_stage_kind = "crop_stage"
        else:
            calendar_stage_kind = "mixed"

    avg = lambda values: sum(values) / len(values) if values else None
    return {
        "area_id": "sekinchan_67ha", "window_id": window_id,
        "window_start": start.isoformat(), "window_end": end.isoformat(),
        "evidence_class": "REFERENCE",
        "weather_source": "Sekinchan historical daily weather dataset (Open-Meteo archive)",
        "weather_spatial_support": "regional grid point 3.5500877°N, 101.0859°E, elevation 6 m; not an in-field sensor",
        "weather_days_available": len(days),
        "weather_days_expected": (end - start).days + 1,
        "weather_coverage_percent": round(len(days) / ((end - start).days + 1) * 100, 1),
        "weather": {"mean_temperature_c": avg(temps), "precipitation_total_mm": sum(rain) if rain else None,
                    "mean_daily_max_wind_kmh": avg(wind)},
        "calendar": calendar,
        "calendar_days_in_window": calendar_days,
        "calendar_stage_id": calendar_stage_id,
        "calendar_stage_label": calendar_stage_label,
        "calendar_stage_coverage_days": calendar_stage_coverage,
        "calendar_stage_kind": calendar_stage_kind,
        "calendar_status": "Recurring Sekinchan seasonal anchors with interpolated growth substages; not verified for an individual field or year",
    }
