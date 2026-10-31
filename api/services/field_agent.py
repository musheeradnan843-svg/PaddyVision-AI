"""Bounded, read-only, deterministic Field Intelligence Agent.

The agent routes a small set of question types to existing read-only project
services. It does not call an LLM, the public internet, a database mutation,
or an operational agronomy tool.
"""

from __future__ import annotations

import re
from typing import Any

from api.services.context_data import get_environment_context
from api.services.satellite_data import SatelliteDataError, get_satellite_catalogue, get_satellite_window
from api.services.soil_reference import get_soil_reference
from api.services.synthetic_water import get_synthetic_water_campaign, get_synthetic_water_options
from api.services.synthetic_yield import get_synthetic_yield_outlook


_WINDOW_RE = re.compile(r"\b20\d{2}-\d{3}\b")
_CAMPAIGN_RE = re.compile(r"\bSIM-F\d{2}\b", re.IGNORECASE)
_YEAR_RE = re.compile(r"\b20\d{2}\b")
_METRICS = {
    "ndvi": "NDVI", "ndmi": "NDMI", "ndwi": "NDWI",
    "vv": "S1_VV", "vh": "S1_VH", "sentinel-1 vv": "S1_VV", "sentinel-1 vh": "S1_VH",
}
_SOIL_PROPERTIES = {
    "organic carbon": "soil_organic_carbon", "soc": "soil_organic_carbon",
    "nitrogen": "nitrogen", "clay": "clay", "sand": "sand", "silt": "silt",
    "cec": "cec", "ph": "phh2o", "phh2o": "phh2o",
}
_ADVICE_RE = re.compile(
    r"\b(recommend|recommendation|should i|should we|what should|advise|advice|"
    r"prescribe|treatment|treat|spray|pesticide|fungicide|herbicide|fertili[sz]er|"
    r"dose|apply chemical|chemical application|when to irrigate|irrigation schedule|"
    r"how much water|irrigate today)\b",
    re.IGNORECASE,
)
_DISEASE_RE = re.compile(r"\b(disease|pest|blast|blight|tungro|diagnos\w*|outbreak)\b", re.IGNORECASE)


def _citation(tool: str, source: str, evidence_class: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "C1",
        "tool": tool,
        "source": source,
        "evidence_class": evidence_class,
        "detail": detail,
    }


def _unsupported(reason: str, explanation: str) -> dict[str, Any]:
    return {
        "agent": "PaddyVision Field Intelligence Agent",
        "status": "refused",
        "read_only": True,
        "answer": explanation,
        "citations": [],
        "uncertainty": ["No approved local, validated evidence supports this requested conclusion or action."],
        "refusal_reason": reason,
    }


def _latest_window() -> dict[str, Any]:
    catalogue = get_satellite_catalogue()
    windows = [window for window in catalogue["windows"] if window.get("window_start")]
    if not windows:
        raise SatelliteDataError("No dated satellite windows are available.")
    return max(windows, key=lambda window: (window["window_start"], window.get("window_id") or ""))


def _selected_window(question: str) -> tuple[dict[str, Any], str | None]:
    catalogue = get_satellite_catalogue()
    match = _WINDOW_RE.search(question)
    if match:
        selected = next((row for row in catalogue["windows"] if row["window_id"] == match.group(0)), None)
        if selected is None:
            raise ValueError(f"Satellite window {match.group(0)} is not present in the supplied catalogue.")
        return selected, None
    windows = [window for window in catalogue["windows"] if window.get("window_start")]
    year_match = _YEAR_RE.search(question)
    if year_match:
        year = year_match.group(0)
        year_windows = [window for window in windows if str(window.get("year") or "") == year]
        if not year_windows:
            raise ValueError(f"No satellite window is available for {year} in the supplied catalogue.")
        return max(year_windows, key=lambda window: (window["window_start"], window.get("window_id") or "")), f"No dekad was specified; I selected the latest dated window in {year}."
    if not windows:
        raise SatelliteDataError("No dated satellite windows are available.")
    return max(windows, key=lambda window: (window["window_start"], window.get("window_id") or "")), "No window was specified; I selected the latest dated window in the supplied catalogue."


def _format_number(value: Any, digits: int = 2) -> str:
    if value is None:
        return "unavailable"
    return f"{float(value):.{digits}f}"


def _satellite_answer(question: str) -> dict[str, Any]:
    window, selection_note = _selected_window(question)
    lowered = question.lower()
    metric = next((value for key, value in _METRICS.items() if re.search(rf"\b{re.escape(key)}\b", lowered)), "NDVI")
    source_filter = "all"
    if metric.startswith("ND"):
        if "monthly fill" in lowered or "monthly-fill" in lowered:
            source_filter = "v2_monthly_fill"
        elif "direct" in lowered or "10-day" in lowered or "10 day" in lowered:
            source_filter = "v3_10day"
    data = get_satellite_window(window["window_id"], metric, source_filter)
    summary = data["summary"]
    window_summary = summary["window_summary"]
    mean = _format_number(summary["mean"], 3)
    min_value = _format_number(summary["min"], 3)
    max_value = _format_number(summary["max"], 3)
    sources = ", ".join(f"{name}: {count}" for name, count in summary["source_counts"].items()) or "no valid pixel values"
    flags = summary["quality_flags"]
    flag_note = "; ".join(
        f"{name}: {values['flagged']} flagged / {values['clear']} clear / {values['missing']} missing"
        for name, values in flags.items()
    )
    availability_note = ""
    if window_summary.get("usable_s2_or_s1") is False:
        availability_note = " The source summary marks this window unusable even though row-level pixel values are present; that flag mismatch is not explained by the supplied README."
    answer = (
        f"{metric} for satellite window {data['window_id']} ({data['window_start']} to {data['window_end']}): "
        f"mean {mean} {data['unit']}, range {min_value} to {max_value}, across {summary['pixel_count']:,} valid values. "
        f"Source counts: {sources}. Window quality-flag counts ({flag_note}); flags are QA indicators, not diagnoses."
        f"{availability_note} [C1]"
    )
    if selection_note:
        answer += " " + selection_note
    citation = _citation(
        "satellite_window_summary",
        "PaddyVision v3 merged Sentinel-1/2 pixel panel and window summary",
        "LOCAL_REMOTE_SENSING",
        {"window_id": data["window_id"], "period": [data["window_start"], data["window_end"]], "metric": metric, "s2_source_filter": source_filter, "valid_value_count": summary["pixel_count"]},
    )
    uncertainty = [
        "These are AOI-clipped satellite-derived values, not field-sensor or laboratory measurements.",
        "A ten-day slot may contain a reused monthly fill; direct observations and monthly fills must not be treated as equivalent acquisitions.",
    ]
    if source_filter == "all" and metric.startswith("ND"):
        uncertainty.append("The combined source counts can include direct and monthly-fill values.")
    return {
        "agent": "PaddyVision Field Intelligence Agent", "status": "answered", "read_only": True,
        "answer": answer, "citations": [citation], "uncertainty": uncertainty,
        "tools_called": ["satellite_window_summary"],
    }


def _context_answer(question: str) -> dict[str, Any]:
    window, selection_note = _selected_window(question)
    data = get_environment_context(window["window_id"])
    weather = data["weather"]
    weather_coverage = f"{data['weather_days_available']} of {data['weather_days_expected']} days ({data['weather_coverage_percent']}%)"
    answer_parts = []
    citations = []
    if re.search(r"weather|temperature|rain|precipitation|wind", question, re.IGNORECASE):
        answer_parts.append(
            f"For {data['window_start']} to {data['window_end']}, regional archive context reports mean temperature "
            f"{_format_number(weather['mean_temperature_c'])} °C, total precipitation "
            f"{_format_number(weather['precipitation_total_mm'])} mm, and mean daily maximum wind "
            f"{_format_number(weather['mean_daily_max_wind_kmh'])} km/h ({weather_coverage}). [C{len(citations) + 1}]"
        )
        citations.append(_citation(
            "regional_weather_context",
            data["weather_source"],
            data["evidence_class"],
            {"window_id": data["window_id"], "period": [data["window_start"], data["window_end"]], "spatial_support": data["weather_spatial_support"], "days_available": data["weather_days_available"], "days_expected": data["weather_days_expected"]},
        ))
    if re.search(r"calendar|crop stage|growth stage|season", question, re.IGNORECASE):
        stages = data.get("calendar", [])
        stage_summary = "; ".join(
            f"{row['season']}: {row['expected_crop_stage']} ({row['days_in_window']} days)" for row in stages
        ) or "no calendar interval found"
        answer_parts.append(
            f"Recurring crop-calendar reference for this window: {stage_summary}. It is not a verified planting or harvest record. [C{len(citations) + 1}]"
        )
        citations.append(_citation(
            "crop_calendar_context",
            "Sekinchan paddy crop calendar reference CSV",
            "REFERENCE",
            {"window_id": data["window_id"], "period": [data["window_start"], data["window_end"]], "calendar_status": data["calendar_status"]},
        ))
    if selection_note:
        answer_parts.append(selection_note)
    return {
        "agent": "PaddyVision Field Intelligence Agent", "status": "answered", "read_only": True,
        "answer": " ".join(answer_parts), "citations": citations,
        "uncertainty": ["Weather is a regional Open-Meteo grid archive, not an in-field sensor.", "Crop stage is a recurring calendar estimate, not a verified field-stage observation."],
        "tools_called": [citation["tool"] for citation in citations],
    }


def _soil_answer(question: str) -> dict[str, Any]:
    data = get_soil_reference()
    matches = [(key, value) for key, value in _SOIL_PROPERTIES.items() if re.search(rf"\b{re.escape(key)}\b", question, re.IGNORECASE)]
    properties = {value for _, value in matches}
    layers = [layer for layer in data["layers"] if not properties or layer["property"] in properties]
    formatted = "; ".join(
        f"{layer['property']} {layer['depth_cm']} cm: {_format_number(layer['area_weighted_mean'], 3)} {layer['unit']}"
        for layer in layers
    ) or "No matching soil reference rows were found."
    citation = _citation(
        "soil_reference_summary",
        "; ".join(sorted({layer["source"] for layer in layers})) or "SoilGrids summary",
        data["evidence_class"],
        {"spatial_support": data["spatial_support"], "layers_returned": len(layers)},
    )
    return {
        "agent": "PaddyVision Field Intelligence Agent", "status": "answered", "read_only": True,
        "answer": f"Soil reference estimates: {formatted}. [C1] These are area-weighted coarse-grid estimates, not within-field samples.",
        "citations": [citation],
        "uncertainty": [data["limitations"], "SoilGrids cells are roughly 251 × 264 m and the AOI has only about ten pixel centres."],
        "tools_called": ["soil_reference_summary"],
    }


def _synthetic_yield_answer(question: str) -> dict[str, Any]:
    data = get_synthetic_yield_outlook()
    years = {int(year) for year in _YEAR_RE.findall(question)}
    seasons = [season for season in data["seasons"] if re.search(rf"\b{re.escape(season)}\b", question, re.IGNORECASE)]
    records = [record for record in data["records"] if (not years or record["year"] in years) and (not seasons or record["season"] in seasons)]
    lines = [
        f"{record['year']} {record['season']}: {record['yield_t_ha']:.2f} t/ha, {record['total_harvest_t']:.1f} t total ({record['record_status']})"
        for record in records[:6]
    ]
    citation = _citation(
        "synthetic_yield_demo",
        "data/demo/sekinchan_yield_synthetic.csv plus derived synthetic trend scenarios",
        "SYNTHETIC",
        {"area_basis": data["area_basis"], "records_included": len(lines)},
    )
    return {
        "agent": "PaddyVision Field Intelligence Agent", "status": "answered", "read_only": True,
        "answer": "Synthetic yield demonstration only: " + ("; ".join(lines) if lines else "no matching demo record") + f". This is not measured Sekinchan yield or a validated forecast. [C1]",
        "citations": [citation], "uncertainty": [data["caveat"], data["method"]],
        "tools_called": ["synthetic_yield_demo"],
    }


def _synthetic_water_answer(question: str) -> dict[str, Any]:
    field_match = _CAMPAIGN_RE.search(question)
    year_match = _YEAR_RE.search(question)
    season_match = re.search(r"season\s*([12])", question, re.IGNORECASE)
    if not field_match or not year_match or not season_match:
        options = get_synthetic_water_options()
        choices = ", ".join(f"{item['field_id']} {item['year']} {item['season']}" for item in options["options"][:8])
        return {
            "agent": "PaddyVision Field Intelligence Agent", "status": "needs_input", "read_only": True,
            "answer": "I can inspect only an explicitly selected synthetic campaign, for example “SIM-F01 2024 Season 1 water demo”. The available sample choices include: " + (choices or "none available") + ". These are not Sekinchan fields.",
            "citations": [_citation("synthetic_water_campaign_options", "06_Water_and_Irrigation_Data synthetic campaign files", "SYNTHETIC", {"available_option_count": len(options["options"])})],
            "uncertainty": ["SIM-Fxx identifiers are generated examples and are not linked to the Sekinchan AOI."],
            "tools_called": ["synthetic_water_campaign_options"],
        }
    data = get_synthetic_water_campaign(field_match.group(0).upper(), int(year_match.group(0)), f"Season {season_match.group(1)}")
    citation = _citation(
        "synthetic_water_campaign",
        "06_Water_and_Irrigation_Data synthetic observations and irrigation events",
        data["evidence_class"],
        {"field_id": data["field_id"], "year": data["year"], "season": data["season"], "observation_count": len(data["observations"]), "event_count": len(data["events"])},
    )
    return {
        "agent": "PaddyVision Field Intelligence Agent", "status": "answered", "read_only": True,
        "answer": f"{data['field_id']} {data['year']} {data['season']} synthetic demo contains {len(data['observations'])} simulated water observations and {len(data['events'])} simulated events. No local irrigation status or recommendation can be inferred. [C1]",
        "citations": [citation], "uncertainty": [data["caveat"]], "tools_called": ["synthetic_water_campaign"],
    }


def _combine_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    answer_parts = []
    citations = []
    uncertainty = []
    tools_called = []
    for result in results:
        replacement = {}
        for citation in result.get("citations", []):
            new_id = f"C{len(citations) + 1}"
            replacement[citation["id"]] = new_id
            citation["id"] = new_id
            citations.append(citation)
        answer = re.sub(
            r"\[(C\d+)\]",
            lambda match: f"[{replacement.get(match.group(1), match.group(1))}]",
            result["answer"],
        )
        answer_parts.append(answer)
        uncertainty.extend(result.get("uncertainty", []))
        tools_called.extend(result.get("tools_called", []))
    return {
        "agent": "PaddyVision Field Intelligence Agent", "status": "answered", "read_only": True,
        "answer": " ".join(answer_parts), "citations": citations,
        "uncertainty": list(dict.fromkeys(uncertainty)), "tools_called": tools_called,
    }


def ask_field_agent(question: str) -> dict[str, Any]:
    """Answer supported questions with cited internal data; otherwise refuse or ask for scope."""
    question = " ".join(question.strip().split())
    if not 3 <= len(question) <= 500:
        raise ValueError("Question must contain between 3 and 500 characters.")

    if _ADVICE_RE.search(question):
        return _unsupported(
            "agronomic_or_chemical_advice",
            "I can summarize the connected records, but I cannot recommend irrigation, fertilizer, pesticide, fungicide, treatment, or chemical actions. The supplied local data does not validate those decisions.",
        )
    if _DISEASE_RE.search(question):
        return _unsupported(
            "disease_or_pest_diagnosis",
            "I cannot diagnose or report a Sekinchan disease/pest event. The image classifier is trained on external images, and no Sekinchan-labelled disease observations are connected.",
        )
    if re.search(r"\b(yield|harvest)\b", question, re.IGNORECASE):
        if re.search(r"\bsynthetic\b|\bdemo\b", question, re.IGNORECASE):
            return _synthetic_yield_answer(question)
        return _unsupported(
            "unsupported_local_yield_claim",
            "I cannot predict or report local Sekinchan yield: there are no measured, plot-linked harvest records. If you want to inspect the dashboard's generated example, explicitly ask for the synthetic yield demo.",
        )

    if re.search(r"\bSIM-F\d{2}\b|synthetic water|water demo", question, re.IGNORECASE):
        if _ADVICE_RE.search(question):
            return _unsupported("irrigation_advice", "The available water records are synthetic demos and cannot support a Sekinchan irrigation decision.")
        try:
            return _synthetic_water_answer(question)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

    if re.search(r"\b(water|irrigat\w*)\b", question, re.IGNORECASE):
        return _unsupported(
            "unavailable_local_water_observation",
            "There are no measured Sekinchan water-level or irrigation records connected. The available SIM-Fxx campaigns are synthetic examples, not local water status.",
        )

    wants_soil = bool(re.search(r"\bsoil|clay|sand|silt|cec|phh2o|organic carbon|\bsoc\b|nitrogen\b", question, re.IGNORECASE))
    wants_context = bool(re.search(r"weather|temperature|precipitation|\brain\b|\bwind\b|calendar|crop stage|growth stage|\bseason\b", question, re.IGNORECASE))
    wants_satellite = bool(re.search(r"satellite|sentinel|ndvi|ndmi|ndwi|\bvv\b|\bvh\b|window\s+20\d{2}-\d{3}", question, re.IGNORECASE))
    if wants_soil and re.search(r"recommend|fertili[sz]er|amend|lime|how much (fertili[sz]er|lime|amendment)", question, re.IGNORECASE):
        return _unsupported("soil_recommendation", "The coarse SoilGrids layers are reference estimates and cannot support a field-level soil or fertilizer recommendation.")
    results = []
    if wants_soil:
        results.append(_soil_answer(question))
    if wants_context:
        results.append(_context_answer(question))
    if wants_satellite:
        results.append(_satellite_answer(question))
    if results:
        return _combine_results(results)

    return {
        "agent": "PaddyVision Field Intelligence Agent", "status": "needs_input", "read_only": True,
        "answer": "I can summarize a satellite window (NDVI/NDMI/NDWI/VV/VH), regional weather and calendar context, coarse soil references, or explicitly selected synthetic demos. Include a window ID such as 2025-361 when you want a specific period.",
        "citations": [], "uncertainty": ["This agent uses a fixed set of internal read-only tools; it does not browse the web or invent answers."],
        "tools_called": [],
    }
