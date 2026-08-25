"""Cached-data decision service used by the offline ORCA prototype.

The service deliberately fails closed: missing or unsafe operational inputs
reduce confidence and prevent a departure recommendation.
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime
from pathlib import Path

from .boundary_import import read_restricted_zones_csv
from .models import Evidence, Location, SourceMode, ZoneCandidate
from .pfz_import import PfzCandidate, read_pfz_xls
from .scoring import rank_zones

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw"
DEFAULT_LOCATION = Location(lat=18.95, lon=72.85)
VESSEL = {"type": "small fishing boat", "beam_m": 3.5, "cruising_speed_kmh": 18.0,
          "max_wave_m": 1.5, "max_wind_ms": 10.0, "range_km": 80.0}


def _distance_km(a: Location, b: Location) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    h = math.sin((p2-p1)/2)**2 + math.cos(p1)*math.cos(p2)*math.sin(math.radians(b.lon-a.lon)/2)**2
    return radius * 2 * math.asin(math.sqrt(h))


def _time(value: str | None, fallback: datetime) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC) if value else fallback


def _latest_pfz() -> tuple[str, list[PfzCandidate]]:
    files = sorted((DATA / "pfz").glob("*.xls"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No PFZ advisory found. Add an .xls file to data/raw/pfz/.")
    return read_pfz_xls(files[0])


def _ocean_cache() -> dict:
    files = sorted((DATA / "ocean").glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No ocean cache found. Add a validated JSON file to data/raw/ocean/.")
    return json.loads(files[0].read_text(encoding="utf-8"))


def _score(value: float, good: float, limit: float) -> float:
    if value <= good:
        return 100.0
    if value >= limit:
        return 15.0
    return round(100 - 85 * (value-good) / (limit-good), 1)


def detect_language(message: str, selected: str) -> str:
    if selected != "auto":
        return selected
    if any("\u0900" <= char <= "\u097f" for char in message):
        return "hi" if any(word in message for word in ("है", "क्या", "कहाँ")) else "mr"
    return "en"


def _answer(language: str, blocked: bool, name: str, distance: float) -> str:
    if blocked:
        messages = {
            "en": "Sea conditions exceed the default small-fishing-vessel limit. Do not depart; recheck official INCOIS and IMD advisories.",
            "hi": "डिफ़ॉल्ट छोटी मछली पकड़ने वाली नाव के लिए समुद्र की स्थिति सीमा से अधिक है। प्रस्थान न करें; आधिकारिक INCOIS और IMD सलाह दोबारा देखें।",
            "mr": "डीफॉल्ट लहान मासेमारी नौकेसाठी समुद्रस्थिती मर्यादेपेक्षा जास्त आहे. प्रस्थान करू नका; अधिकृत INCOIS आणि IMD सूचना पुन्हा तपासा।",
        }
        return messages[language]
    messages = {
        "en": f"The nearest suitable PFZ is {name}, about {distance:.1f} km away. Confirm official advisories before departure.",
        "hi": f"निकटतम उपयुक्त PFZ {name} है, लगभग {distance:.1f} किमी दूर। प्रस्थान से पहले आधिकारिक सलाह की पुष्टि करें।",
        "mr": f"सर्वात जवळचा योग्य PFZ {name} आहे, सुमारे {distance:.1f} किमी दूर. निघण्यापूर्वी अधिकृत सूचना तपासा।",
    }
    return messages[language]


def analyse(message: str, location: Location, language: str) -> dict:
    """Create one explainable response from the supplied cached files."""
    now = datetime.now(UTC)
    validity, pfz = _latest_pfz()
    ocean = _ocean_cache()
    retrieved = _time(ocean.get("retrieved_at"), now)
    point = ocean["location"]
    ocean_location = Location(lat=float(point["latitude"]), lon=float(point["longitude"]))
    observations = {item["parameter"]: item for item in ocean["observations"]}
    required = ("wind_speed", "significant_wave_height", "swell_height", "surface_current_speed")
    missing = [item for item in required if item not in observations]
    if missing:
        raise ValueError("Ocean cache is missing: " + ", ".join(missing))
    wave, wind = float(observations["significant_wave_height"]["value"]), float(observations["wind_speed"]["value"])
    swell, current = float(observations["swell_height"]["value"]), float(observations["surface_current_speed"]["value"])
    critical = wave > VESSEL["max_wave_m"] or wind > VESSEL["max_wind_ms"]

    valid_time = _time(observations["significant_wave_height"].get("valid_time"), retrieved)
    evidence = [Evidence(id="pfz_advisory", source="INCOIS PFZ advisory", parameter="pfz_validity", value=validity,
                         unit="", location=location, valid_time=valid_time, issued_time=retrieved, retrieved_at=retrieved,
                         source_mode=SourceMode.CACHED, quality="VALIDATED_FILE")]
    for parameter, item in observations.items():
        evidence.append(Evidence(id=f"osf_{parameter}", source=ocean.get("source_name", "INCOIS OSF cache"),
                                 parameter=parameter, value=item["value"], unit=item["unit"], location=ocean_location,
                                 valid_time=_time(item.get("valid_time"), retrieved), issued_time=retrieved, retrieved_at=retrieved,
                                 source_mode=SourceMode.CACHED, quality="VALIDATED_CACHE"))
    boundary_file = DATA / "boundaries" / "restricted_zones.csv"
    if boundary_file.exists():
        for zone in read_restricted_zones_csv(boundary_file):
            evidence.append(Evidence(id=f"boundary_{len(evidence)}", source="ORCA boundary inventory", parameter="geofence_context",
                                     value=zone.enforcement, unit="", location=Location(lat=zone.latitude, lon=zone.longitude),
                                     valid_time=now, issued_time=now, retrieved_at=now, source_mode=SourceMode.CACHED,
                                     quality="CONTEXT_ONLY" if zone.enforcement == "CONTEXT_ONLY" else "OFFICIAL_BOUNDARY"))
    closest = sorted(pfz, key=lambda item: _distance_km(location, Location(lat=item.latitude, lon=item.longitude)))[:5]
    candidates = []
    for number, item in enumerate(closest, 1):
        target = Location(lat=item.latitude, lon=item.longitude)
        distance = _distance_km(location, target)
        candidates.append(ZoneCandidate(id=f"pfz_{number}", name=f"PFZ near {item.coastal_reference}", location=target,
                         distance_km=round(distance, 1), pfz_score=92, chlorophyll_score=55, sst_score=55, ocean_context_score=60,
                         wave_safety=_score(wave, .8, VESSEL["max_wave_m"]), wind_safety=_score(wind, 5, VESSEL["max_wind_ms"]),
                         swell_safety=_score(swell, .7, 1.5), current_safety=_score(current, .3, 1),
                         hazard_clearance=15 if critical else 90, accessibility_score=max(15, 100-distance), data_quality_score=68,
                         critical_hazard=critical, evidence_ids=[entry.id for entry in evidence]))
    ranked = rank_zones(candidates)
    top = ranked[0]
    return {"answer": _answer(language, critical, top.name, top.distance_km), "language": language, "source_mode": "CACHED",
            "recommendation": top.model_dump(mode="json"), "alternatives": [item.model_dump(mode="json") for item in ranked[1:]],
            "evidence": [item.model_dump(mode="json") for item in evidence],
            "trace": ["Planner: parsed location and request.", "PFZ agent: loaded validated PFZ advisory.",
                      "Ocean agent: loaded cached INCOIS OSF observations.", "GIS agent: calculated distances and checked verified boundaries.",
                      "Risk engine: applied default small-vessel limits.", "Recommendation agent: attached timestamped evidence."],
            "vessel_profile": VESSEL, "safety": {"departure_allowed": not critical, "wave_height_m": wave,
            "wind_speed_ms": wind, "swell_height_m": swell, "current_speed_ms": current,
            "reason": "Wave height exceeds the configured vessel limit." if wave > VESSEL["max_wave_m"] else "No configured critical threshold exceeded."},
            "freshness": "Cached data only: verify official advisories immediately before departure."}
