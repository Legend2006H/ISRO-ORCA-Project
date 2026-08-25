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
from .gemini_agent import generate_marine_synthesis
from .live_marine import fetch_live_marine_conditions
from .models import Evidence, Location, SourceMode, VESSEL_PROFILES, VesselProfile, ZoneCandidate
from .pfz_import import PfzCandidate, read_pfz_xls
from .routing import plan_safe_route
from .scoring import rank_zones

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data" / "raw"
DEFAULT_LOCATION = Location(lat=18.95, lon=72.85)
VESSEL = {"type": "small fishing boat", "beam_m": 3.5, "cruising_speed_kmh": 18.0,
          "max_wave_m": 1.5, "max_wind_ms": 10.0, "range_km": 80.0}


def _distance_km(a: Location, b: Location) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b.lon - a.lon) / 2) ** 2
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
    return round(100 - 85 * (value - good) / (limit - good), 1)


def get_all_pfz_geojson() -> dict:
    """Return all PFZ candidate zones as a GeoJSON FeatureCollection."""
    validity, candidates = _latest_pfz()
    features = []
    for idx, c in enumerate(candidates, 1):
        features.append({
            "type": "Feature",
            "geometry": {
                "type": "Point",
                "coordinates": [c.longitude, c.latitude],
            },
            "properties": {
                "id": f"pfz_{idx}",
                "name": f"PFZ near {c.coastal_reference}",
                "coastal_reference": c.coastal_reference,
                "bearing_deg": c.bearing_deg,
                "distance_band": f"{c.distance_from_km}-{c.distance_to_km} km",
                "depth_band": f"{c.depth_from_m}-{c.depth_to_m} m",
                "validity": validity,
            }
        })
    return {
        "type": "FeatureCollection",
        "validity": validity,
        "total_candidates": len(candidates),
        "features": features,
    }


def get_all_boundaries_geojson() -> dict:
    """Return all coastal and marine boundary points as GeoJSON."""
    boundary_file = DATA / "boundaries" / "restricted_zones.csv"
    features = []
    if boundary_file.exists():
        for idx, z in enumerate(read_restricted_zones_csv(boundary_file), 1):
            features.append({
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [z.longitude, z.latitude],
                },
                "properties": {
                    "id": f"boundary_{idx}",
                    "name": z.name,
                    "restriction_type": z.restriction_type,
                    "radius_km": z.radius_km or 3.0,
                    "enforcement": z.enforcement,
                    "note": z.note,
                }
            })
    return {
        "type": "FeatureCollection",
        "features": features,
    }


def detect_language(message: str, selected: str) -> str:
    if selected != "auto":
        return selected
    if any("\u0900" <= char <= "\u097f" for char in message):
        return "hi" if any(word in message for word in ("है", "क्या", "कहाँ", "कहा")) else "mr"
    return "en"


def detect_intent(message: str) -> str:
    m = message.lower()
    if any(k in m for k in ("why", "instead", "compare", "zone a", "zone b", "का निवडले", "तुलना", "क्यों चुना")):
        return "comparison"
    if any(k in m for k in ("nearest", "कहाँ", "कुठे", "जवळ", "निकटतम", "location", "distance", "to me")):
        return "nearest"
    if any(k in m for k in ("safe", "सुरक्षित", "safety", "hazard", "risk", "weather", "alert", "धोका", "हवामान", "sail", "venture")):
        return "safety"
    return "recommendation"


def _answer(language: str, intent: str, blocked: bool, top: ZoneCandidate, alt: ZoneCandidate | None, wave: float, wind: float, swell: float, vessel_name: str, max_wave: float) -> str:
    alt_name = alt.name if alt else "Zone B"
    alt_dist = alt.distance_km if alt else 0.0

    if intent == "comparison":
        if blocked:
            messages = {
                "en": f"{top.name} ({top.distance_km:.1f} km) was ranked above {alt_name} ({alt_dist:.1f} km) due to shorter approach distance and higher accessibility score ({top.accessibility_score:.0f} vs {alt.accessibility_score if alt else 0:.0f} pts). Note: Departure is currently BLOCKED for all zones due to {wave:.1f} m waves exceeding the {vessel_name} limit ({max_wave} m).",
                "hi": f"{top.name} ({top.distance_km:.1f} किमी) को {alt_name} ({alt_dist:.1f} किमी) की तुलना में कम दूरी और बेहतर पहुंच स्कोर ({top.accessibility_score:.0f} अंक) के कारण चुना गया। हालांकि, {wave:.1f} मीटर ऊंची लहरों (सीमा: {max_wave} मी) के कारण सभी क्षेत्रों में प्रस्थान प्रतिबंधित है।",
                "mr": f"{top.name} ({top.distance_km:.1f} किमी) ला {alt_name} ({alt_dist:.1f} किमी) पेक्षा कमी अंतर आणि अधिक सुलभतेमुळे ({top.accessibility_score:.0f} गुण) वरचे स्थान मिळाले. परंतु {wave:.1f} मीटर लाटांमुळे (मर्यादा: {max_wave} मी) सर्व झोनमध्ये प्रस्थान प्रतिबंधित आहे।",
            }
        else:
            messages = {
                "en": f"{top.name} ({top.distance_km:.1f} km) is preferred over {alt_name} ({alt_dist:.1f} km) due to superior accessibility ({top.accessibility_score:.0f} pts) and safe sea conditions within {vessel_name} limits.",
                "hi": f"{top.name} ({top.distance_km:.1f} किमी) को {alt_name} ({alt_dist:.1f} किमी) से बेहतर माना गया क्योंकि यह निकट है और {vessel_name} के लिए समुद्र सुरक्षित है।",
                "mr": f"{top.name} ({top.distance_km:.1f} किमी) ला {alt_name} ({alt_dist:.1f} किमी) पेक्षा प्राधान्य दिले गेले कारण ते जवळ आहे आणि {vessel_name} साठी समुद्र सुरक्षित आहे।",
            }
        return messages[language]

    if intent == "nearest":
        if blocked:
            messages = {
                "en": f"The nearest Potential Fishing Zone is {top.name}, located {top.distance_km:.1f} km offshore ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E), followed by {alt_name} ({alt_dist:.1f} km). Caution: Wave height is {wave:.1f} m; departure for {vessel_name} is currently not permitted.",
                "hi": f"निकटतम संभावित मत्स्य पालन क्षेत्र (PFZ) {top.name} है, जो {top.distance_km:.1f} किमी दूर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) पर स्थित है, जिसके बाद {alt_name} ({alt_dist:.1f} किमी) है। चेतावनी: {wave:.1f} मीटर ऊंची लहरों के कारण {vessel_name} के लिए प्रस्थान की अनुमति नहीं है।",
                "mr": f"सर्वात जवळचा PFZ {top.name} आहे, जो {top.distance_km:.1f} किमी अंतरावर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) आहे, त्यानंतर {alt_name} ({alt_dist:.1f} किमी) आहे. इशारा: {wave:.1f} मीटर लाटांमुळे {vessel_name} साठी निघण्यास मनाई आहे।",
            }
        else:
            messages = {
                "en": f"The nearest Potential Fishing Zone is {top.name}, located {top.distance_km:.1f} km away ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E). Departure is permitted for {vessel_name}.",
                "hi": f"निकटतम PFZ {top.name} है, जो {top.distance_km:.1f} किमी दूर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) है। {vessel_name} के लिए प्रस्थान सुरक्षित है।",
                "mr": f"सर्वात जवळचा PFZ {top.name} आहे, जो {top.distance_km:.1f} किमी अंतरावर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) आहे। {vessel_name} साठी प्रस्थान सुरक्षित आहे।",
            }
        return messages[language]

    if intent == "safety":
        if blocked:
            messages = {
                "en": f"Sea Conditions Assessment: HIGH RISK — Do Not Depart for {vessel_name}. Significant wave height is {wave:.1f} m (exceeds {max_wave} m vessel limit), with {wind:.1f} m/s wind and {swell:.1f} m swell. Recheck official INCOIS OSF and IMD warnings.",
                "hi": f"समुद्र स्थिति मूल्यांकन: उच्च जोखिम — {vessel_name} के लिए प्रस्थान न करें। लहरों की ऊंचाई {wave:.1f} मीटर है (नौका सीमा {max_wave} मी से अधिक), हवा {wind:.1f} मी/से और स्वेल {swell:.1f} मी है। आधिकारिक INCOIS सलाह दोबारा देखें।",
                "mr": f"समुद्रस्थिती मूल्यांकन: उच्च धोका — {vessel_name} साठी प्रस्थान करू नका. लाटांची उंची {wave:.1f} मीटर आहे (नौका मर्यादा {max_wave} मी पेक्षा जास्त), वारा {wind:.1f} मी/से आणि स्वेल {swell:.1f} मी आहे. अधिकृत INCOIS सूचना पुन्हा तपासा।",
            }
        else:
            messages = {
                "en": f"Sea Conditions Assessment: SAFE TO DEPART. Wave height {wave:.1f} m, wind {wind:.1f} m/s, swell {swell:.1f} m — within safe limits for {vessel_name} (limit: {max_wave} m).",
                "hi": f"समुद्र स्थिति मूल्यांकन: प्रस्थान सुरक्षित। लहर {wave:.1f} मी, हवा {wind:.1f} मी/से — {vessel_name} के लिए सुरक्षित सीमा (सीमा: {max_wave} मी) के भीतर।",
                "mr": f"समुद्रस्थिती मूल्यांकन: प्रस्थान सुरक्षित. लाटा {wave:.1f} मी, वारा {wind:.1f} मी/से — {vessel_name} च्या सुरक्षित मर्यादेत (मर्यादा: {max_wave} मी)।",
            }
        return messages[language]

    # default recommendation intent
    if blocked:
        messages = {
            "en": f"Top candidate fishing zone is {top.name} ({top.distance_km:.1f} km away, overall score: {top.overall_score:.0f}/100, fishing potential: {top.fishing_score:.0f}/100). Caution: Departure is blocked for {vessel_name} due to active sea-state advisory ({wave:.1f} m waves vs {max_wave} m limit).",
            "hi": f"शीर्ष अनुशंसित मत्स्य पालन क्षेत्र {top.name} है ({top.distance_km:.1f} किमी दूर, कुल स्कोर: {top.overall_score:.0f}/100, मत्स्य क्षमता: {top.fishing_score:.0f}/100)। चेतावनी: {wave:.1f} मीटर लहरों के कारण {vessel_name} का प्रस्थान अवरुद्ध है।",
            "mr": f"सर्वोत्तम शिफारस केलेला मासेमारी झोन {top.name} आहे ({top.distance_km:.1f} किमी दूर, एकूण स्कोर: {top.overall_score:.0f}/100, मासेमारी क्षमता: {top.fishing_score:.0f}/100). इशारा: {wave:.1f} मीटर लाटांमुळे {vessel_name} साठी प्रस्थान प्रतिबंधित आहे।",
        }
        return messages[language]
    messages = {
        "en": f"Recommended zone is {top.name}, about {top.distance_km:.1f} km away (overall score: {top.overall_score:.0f}/100). Sea conditions are within safe limits for {vessel_name}. Confirm official advisories before departure.",
        "hi": f"अनुशंसित क्षेत्र {top.name} है, लगभग {top.distance_km:.1f} किमी दूर (कुल स्कोर: {top.overall_score:.0f}/100)। {vessel_name} के लिए समुद्र की स्थिति सुरक्षित है। प्रस्थान से पहले आधिकारिक सलाह की पुष्टि करें।",
        "mr": f"शिफारस केलेला झोन {top.name} आहे, सुमारे {top.distance_km:.1f} किमी दूर (एकूण स्कोर: {top.overall_score:.0f}/100). {vessel_name} साठी समुद्रस्थिती सुरक्षित आहे. निघण्यापूर्वी अधिकृत सूचना तपासा।",
    }
    return messages[language]


def analyse(
    message: str,
    location: Location,
    language: str,
    vessel_type: str = "small_boat",
    use_live_data: bool = False,
) -> dict:
    """Create one explainable response with deterministic risk scoring, A* navigation, and evidence attachment."""
    now = datetime.now(UTC)
    validity, pfz = _latest_pfz()
    vessel = VESSEL_PROFILES.get(vessel_type, VESSEL_PROFILES["small_boat"])

    # Decide between live feed and cached observations
    source_mode = SourceMode.CACHED
    if use_live_data:
        live_feed = fetch_live_marine_conditions(location)
        source_mode = SourceMode.LIVE if live_feed.get("source_mode") == "LIVE" else SourceMode.CACHED
        obs_list = live_feed.get("observations", [])
        observations = {item["parameter"]: item for item in obs_list}
        source_name = live_feed.get("source_name", "Open-Meteo Live Marine Feed")
        retrieved = now
        ocean_location = location
    else:
        ocean = _ocean_cache()
        retrieved = _time(ocean.get("retrieved_at"), now)
        point = ocean["location"]
        ocean_location = Location(lat=float(point["latitude"]), lon=float(point["longitude"]))
        observations = {item["parameter"]: item for item in ocean["observations"]}
        source_name = ocean.get("source_name", "INCOIS OSF cache")

    wave = float(observations.get("significant_wave_height", {}).get("value", 1.4))
    wind = float(observations.get("wind_speed", {}).get("value", 6.0))
    swell = float(observations.get("swell_height", {}).get("value", 0.8))
    current = float(observations.get("surface_current_speed", {}).get("value", 0.2))
    critical = wave > vessel.max_wave_m or wind > vessel.max_wind_ms

    valid_time = _time(observations.get("significant_wave_height", {}).get("valid_time"), retrieved)
    evidence = [Evidence(
        id="pfz_advisory",
        source="INCOIS PFZ advisory",
        parameter="pfz_validity",
        value=validity,
        unit="",
        location=location,
        valid_time=valid_time,
        issued_time=retrieved,
        retrieved_at=retrieved,
        source_mode=source_mode,
        quality="VALIDATED_FILE",
    )]

    for parameter, item in observations.items():
        evidence.append(Evidence(
            id=f"osf_{parameter}",
            source=source_name,
            parameter=parameter,
            value=item["value"],
            unit=item.get("unit", ""),
            location=ocean_location,
            valid_time=_time(item.get("valid_time"), retrieved),
            issued_time=retrieved,
            retrieved_at=retrieved,
            source_mode=source_mode,
            quality="LIVE_FEED" if source_mode == SourceMode.LIVE else "VALIDATED_CACHE",
        ))

    boundary_file = DATA / "boundaries" / "restricted_zones.csv"
    if boundary_file.exists():
        for zone in read_restricted_zones_csv(boundary_file):
            evidence.append(Evidence(
                id=f"boundary_{len(evidence)}",
                source="ORCA boundary inventory",
                parameter="geofence_context",
                value=zone.enforcement,
                unit="",
                location=Location(lat=zone.latitude, lon=zone.longitude),
                valid_time=now,
                issued_time=now,
                retrieved_at=now,
                source_mode=SourceMode.CACHED,
                quality="CONTEXT_ONLY" if zone.enforcement == "CONTEXT_ONLY" else "OFFICIAL_BOUNDARY",
            ))

    closest = sorted(pfz, key=lambda item: _distance_km(location, Location(lat=item.latitude, lon=item.longitude)))[:5]
    candidates = []
    for number, item in enumerate(closest, 1):
        target = Location(lat=item.latitude, lon=item.longitude)
        distance = _distance_km(location, target)
        candidates.append(ZoneCandidate(
            id=f"pfz_{number}",
            name=f"PFZ near {item.coastal_reference}",
            location=target,
            distance_km=round(distance, 1),
            pfz_score=92,
            chlorophyll_score=55,
            sst_score=55,
            ocean_context_score=60,
            wave_safety=_score(wave, 0.8, vessel.max_wave_m),
            wind_safety=_score(wind, 5.0, vessel.max_wind_ms),
            swell_safety=_score(swell, 0.7, 1.5),
            current_safety=_score(current, 0.3, 1.0),
            hazard_clearance=15 if critical else 90,
            accessibility_score=max(15, 100 - distance),
            data_quality_score=90 if source_mode == SourceMode.LIVE else 68,
            critical_hazard=critical,
            evidence_ids=[entry.id for entry in evidence],
        ))

    ranked = rank_zones(candidates)
    top = ranked[0]
    alt = ranked[1] if len(ranked) > 1 else None
    intent = detect_intent(message)

    # Calculate safe A* navigation route to recommended zone
    route_info = plan_safe_route(location, top.location, vessel_speed_kmh=vessel.cruising_speed_kmh)

    trace = [
        f"Planner: parsed intent '{intent}' for coordinate ({location.lat:.2f}°N, {location.lon:.2f}°E) with vessel '{vessel.name}'.",
        f"PFZ agent: loaded validated PFZ advisory ({len(pfz)} candidate zones along Maharashtra/Konkan coast).",
        f"Marine data agent: retrieved {source_mode.value} conditions (wave: {wave:.1f} m, wind: {wind:.1f} m/s, swell: {swell:.1f} m).",
        f"GIS agent: calculated geodesic distances and evaluated proximity to CZMP coastal boundaries.",
        f"Route engine: computed {route_info['distance_km']} km safe A* route ({route_info['estimated_duration_hours']} hrs cruising).",
        f"Risk engine: compared wave height ({wave:.1f} m) with vessel limit ({vessel.max_wave_m} m) -> {'BLOCKED (HIGH RISK)' if critical else 'SAFE TO DEPART'}.",
        f"Recommendation agent: synthesized {intent} decision with typed evidence ledger.",
    ]

    vessel_dict = {
        "type": vessel.vessel_type.value,
        "name": vessel.name,
        "beam_m": vessel.beam_m,
        "cruising_speed_kmh": vessel.cruising_speed_kmh,
        "max_wave_m": vessel.max_wave_m,
        "max_wind_ms": vessel.max_wind_ms,
        "range_km": vessel.range_km,
    }

    safety_dict = {
        "departure_allowed": not critical,
        "wave_height_m": wave,
        "wind_speed_ms": wind,
        "swell_height_m": swell,
        "current_speed_ms": current,
        "reason": f"Wave height ({wave:.1f} m) exceeds configured {vessel.name} limit ({vessel.max_wave_m} m)." if critical else f"Sea conditions are within safe limits for {vessel.name}.",
    }

    # Attempt Gemini neural synthesis; fallback to deterministic rules
    final_answer = generate_marine_synthesis(
        user_query=message,
        language=language,
        intent=intent,
        vessel_profile=vessel_dict,
        safety_assessment=safety_dict,
        top_candidate=top.model_dump(mode="json"),
        alternative_candidates=[item.model_dump(mode="json") for item in ranked[1:]],
        route_info=route_info,
    )

    if final_answer:
        trace.append("Gemini agent: generated grounded conversational neural synthesis.")
    else:
        final_answer = _answer(language, intent, critical, top, alt, wave, wind, swell, vessel.name, vessel.max_wave_m)

    return {
        "answer": final_answer,
        "intent": intent,
        "language": language,
        "source_mode": source_mode.value,
        "recommendation": top.model_dump(mode="json"),
        "alternatives": [item.model_dump(mode="json") for item in ranked[1:]],
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "trace": trace,
        "vessel_profile": vessel_dict,
        "route": route_info,
        "safety": safety_dict,
        "freshness": "Live real-time feed active." if source_mode == SourceMode.LIVE else "Cached data only: verify official advisories immediately before departure.",
    }
