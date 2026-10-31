import csv
import os
from datetime import date
from pathlib import Path
from typing import Any

import api.config  # Load project-local .env before reading dataset settings.
from api.services.satellite_data import SatelliteDataError


def _root() -> Path:
    configured = os.getenv("PADDYVISION_DATASET_ROOT")
    candidates = [Path(configured).expanduser()] if configured else []
    candidates.append(Path(r"C:\Paddyvision_AI_Dataset"))
    for candidate in candidates:
        folder = candidate / "06_Water_and_Irrigation_Data"
        if (folder / "water_observations_SYNTHETIC.csv").is_file() and (folder / "irrigation_events_SYNTHETIC.csv").is_file():
            return folder
    raise SatelliteDataError("Synthetic water demo files were not found. Set PADDYVISION_DATASET_ROOT.")


def _campaign_year(day: str, season: str) -> int:
    parsed = date.fromisoformat(day)
    return parsed.year - 1 if season == "Season 2" and parsed.month <= 2 else parsed.year


def _read() -> tuple[list[dict[str, str]], list[dict[str, str]]]:
    folder = _root()
    with (folder / "water_observations_SYNTHETIC.csv").open("r", encoding="utf-8-sig", newline="") as source:
        observations = list(csv.DictReader(source))
    with (folder / "irrigation_events_SYNTHETIC.csv").open("r", encoding="utf-8-sig", newline="") as source:
        events = list(csv.DictReader(source))
    return observations, events


def get_synthetic_water_options() -> dict[str, Any]:
    observations, events = _read()
    combinations = set()
    for row in observations + events:
        combinations.add((row["field_id"], _campaign_year(row["observation_date"] if "observation_date" in row else row["event_date"], row["season"]), row["season"]))
    options = [{"field_id": field, "year": year, "season": season} for field, year, season in sorted(combinations)]
    return {"evidence_class": "SYNTHETIC", "label": "Synthetic water demo · simulated data only", "options": options}


def get_synthetic_water_campaign(field_id: str, year: int, season: str) -> dict[str, Any]:
    if not field_id.startswith("SIM-F") or season not in {"Season 1", "Season 2"}:
        raise ValueError("Unknown synthetic campaign selection")
    observations, events = _read()
    selected_observations = []
    selected_events = []
    for row in observations:
        if row["field_id"] == field_id and row["season"] == season and _campaign_year(row["observation_date"], season) == year:
            selected_observations.append({
                "date": row["observation_date"], "time": row["observation_time"],
                "water_depth_cm": float(row["water_depth_cm"]) if row["water_depth_cm"].strip() else None,
                "status": row["field_water_status"], "rainfall_recent_mm": float(row["rainfall_recent_mm"]) if row["rainfall_recent_mm"].strip() else None,
                "crop_stage": row["crop_stage"], "measurement_method": row["measurement_method"],
            })
    for row in events:
        if row["field_id"] == field_id and row["season"] == season and _campaign_year(row["event_date"], season) == year:
            selected_events.append({
                "date": row["event_date"], "event_type": row["event_type"], "water_source": row["water_source"],
                "duration_minutes": int(row["duration_minutes"]) if row["duration_minutes"].strip() else None,
                "crop_stage": row["crop_stage"],
            })
    if not selected_observations and not selected_events:
        raise ValueError("No synthetic records exist for this campaign")
    return {
        "evidence_class": "SYNTHETIC", "field_id": field_id, "year": year, "season": season,
        "observations": sorted(selected_observations, key=lambda row: (row["date"], row["time"])),
        "events": sorted(selected_events, key=lambda row: row["date"]),
        "caveat": "Simulated records only. SIM-Fxx is not a real Sekinchan field and is not linked to the 66.878 ha AOI or its satellite/weather layers.",
    }
