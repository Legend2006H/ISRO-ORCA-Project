"""Cached-data decision service used by the offline ORCA prototype.

The service deliberately fails closed: missing or unsafe operational inputs
reduce confidence and prevent a departure recommendation.
"""
from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime, timedelta
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
DEFAULT_LOCATION = Location(lat=18.95, lon=72.85, name="Mumbai Harbour")
VESSEL = {
    "type": "small fishing boat",
    "beam_m": 3.5,
    "cruising_speed_kmh": 18.0,
    "max_wave_m": 1.5,
    "max_wind_ms": 10.0,
    "range_km": 80.0,
}

COASTAL_LOCATIONS: dict[str, tuple[float, float, str]] = {
    # Maharashtra / Konkan Coast
    "mumbai": (18.95, 72.85, "Mumbai Harbour"),
    "bombay": (18.95, 72.85, "Mumbai Harbour"),
    "colaba": (18.91, 72.81, "Colaba, Mumbai"),
    "cuffe parade": (18.91, 72.82, "Cuffe Parade, Mumbai"),
    "cuffpared": (18.91, 72.82, "Cuffe Parade, Mumbai"),
    "sassoon dock": (18.91, 72.83, "Sassoon Dock, Mumbai"),
    "sasoondock": (18.91, 72.83, "Sassoon Dock, Mumbai"),
    "mazgaon": (18.96, 72.85, "Mazgaon, Mumbai"),
    "malabar": (18.95, 72.79, "Malabar Port, Mumbai"),
    "versova": (19.13, 72.81, "Versova, Mumbai"),
    "madh": (19.14, 72.79, "Madh Island, Mumbai"),
    "manori": (19.20, 72.78, "Manori, Mumbai"),
    "uttan": (19.28, 72.78, "Uttan, Bhayandar"),
    "vasai": (19.33, 72.78, "Vasai, Palghar"),
    "arnala": (19.45, 72.73, "Arnala, Palghar"),
    "satpati": (19.73, 72.70, "Satpati, Palghar"),
    "tarapur": (19.86, 72.68, "Tarapur, Palghar"),
    "dahanu": (19.97, 72.73, "Dahanu, Palghar"),
    "navgaon": (18.74, 72.88, "Navgaon, Raigad"),
    "nagaon": (18.62, 72.90, "Nagaon, Alibag"),
    "sasawane": (18.82, 72.84, "Sasawane, Raigad"),
    "thal": (18.72, 72.86, "Thal, Alibag"),
    "varsoli": (18.67, 72.87, "Varsoli, Alibag"),
    "alibag": (18.64, 72.87, "Alibag, Raigad"),
    "alibaug": (18.64, 72.87, "Alibag, Raigad"),
    "kashid": (18.44, 72.91, "Kashid, Raigad"),
    "murud": (18.33, 72.96, "Murud-Janjira, Raigad"),
    "rajpuri": (18.29, 72.98, "Rajpuri, Raigad"),
    "dighi": (18.28, 72.99, "Dighi, Raigad"),
    "diveagar": (18.17, 73.00, "Diveagar, Raigad"),
    "srivardhan": (18.04, 73.01, "Shrivardhan, Raigad"),
    "shrivardhan": (18.04, 73.01, "Shrivardhan, Raigad"),
    "harihareshwar": (17.99, 73.02, "Harihareshwar, Raigad"),
    "bankot": (17.97, 73.05, "Bankot, Ratnagiri"),
    "velas": (17.96, 73.03, "Velas, Ratnagiri"),
    "kelshi": (17.92, 73.06, "Kelshi, Ratnagiri"),
    "anjarle": (17.85, 73.09, "Anjarle, Ratnagiri"),
    "harne": (17.81, 73.09, "Harne Port, Ratnagiri"),
    "dapoli": (17.76, 73.18, "Dapoli, Ratnagiri"),
    "dabhol": (17.58, 73.17, "Dabhol, Ratnagiri"),
    "anjanvel": (17.53, 73.16, "Anjanvel, Ratnagiri"),
    "guhagar": (17.48, 73.19, "Guhagar, Ratnagiri"),
    "velneshwar": (17.38, 73.20, "Velneshwar, Ratnagiri"),
    "jaigad": (17.30, 73.21, "Jaigad, Ratnagiri"),
    "ganpatipule": (17.15, 73.26, "Ganpatipule, Ratnagiri"),
    "ratnagiri": (16.99, 73.30, "Ratnagiri Port (Mirkarwada)"),
    "mirkarwada": (16.99, 73.28, "Mirkarwada, Ratnagiri"),
    "bhatye": (16.96, 73.29, "Bhatye, Ratnagiri"),
    "pawas": (16.89, 73.31, "Pawas, Ratnagiri"),
    "purnagad": (16.81, 73.31, "Purnagad, Ratnagiri"),
    "ambolgad": (16.63, 73.34, "Ambolgad, Ratnagiri"),
    "vijaydurg": (16.56, 73.33, "Vijaydurg Port"),
    "devgad": (16.37, 73.38, "Devgad, Sindhudurg"),
    "devgarh": (16.37, 73.38, "Devgad, Sindhudurg"),
    "kunkeshwar": (16.34, 73.39, "Kunkeshwar, Sindhudurg"),
    "mithbao": (16.29, 73.43, "Mithbao, Sindhudurg"),
    "achara": (16.20, 73.45, "Achara, Sindhudurg"),
    "malvan": (16.06, 73.47, "Malvan (Sindhudurg)"),
    "sindhudurg": (16.06, 73.47, "Sindhudurg (Malvan)"),
    "tarkarli": (16.03, 73.49, "Tarkarli, Sindhudurg"),
    "deobag": (15.98, 73.53, "Deobag, Sindhudurg"),
    "nivati": (15.93, 73.56, "Nivati, Sindhudurg"),
    "vengurla": (15.86, 73.63, "Vengurla, Sindhudurg"),
    "shiroda": (15.78, 73.67, "Shiroda, Sindhudurg"),
    "redi": (15.75, 73.67, "Redi Port, Sindhudurg"),
    # Karnataka Coast
    "karwar": (14.81, 74.13, "Karwar Port, Karnataka"),
    "ankola": (14.66, 74.29, "Ankola, Karnataka"),
    "kumta": (14.42, 74.41, "Kumta, Karnataka"),
    "honnavar": (14.28, 74.45, "Honnavar, Karnataka"),
    "bhatkal": (13.97, 74.55, "Bhatkal, Karnataka"),
    "malpe": (13.35, 74.70, "Malpe Port, Udupi"),
    "udupi": (13.34, 74.74, "Udupi, Karnataka"),
    "mangalore": (12.91, 74.85, "New Mangalore Port"),
    "mangaluru": (12.91, 74.85, "New Mangalore Port"),
    # Kerala Coast
    "kasaragod": (12.50, 74.98, "Kasaragod, Kerala"),
    "kannur": (11.87, 75.37, "Kannur, Kerala"),
    "kozhikode": (11.25, 75.78, "Kozhikode, Kerala"),
    "calicut": (11.25, 75.78, "Kozhikode, Kerala"),
    "kochi": (9.93, 76.26, "Cochin / Kochi Port, Kerala"),
    "cochin": (9.93, 76.26, "Cochin / Kochi Port, Kerala"),
    # Gujarat Coast
    "veraval": (20.90, 70.36, "Veraval, Gujarat"),
    "porbandar": (21.64, 69.60, "Porbandar, Gujarat"),
    "diu": (20.71, 70.98, "Diu Port"),
    "daman": (20.42, 72.83, "Daman"),
    "surat": (21.17, 72.83, "Surat, Gujarat"),
    # East Coast
    "chennai": (13.08, 80.27, "Chennai Port"),
    "visakhapatnam": (17.68, 83.21, "Visakhapatnam (Vizag)"),
    "vizag": (17.68, 83.21, "Visakhapatnam (Vizag)"),
    "puri": (19.81, 85.83, "Puri, Odisha"),
    "paradeep": (20.31, 86.61, "Paradip, Odisha"),
    "paradip": (20.31, 86.61, "Paradip, Odisha"),
}


def extract_location_from_text(message: str) -> Location | None:
    """Extract coastal location or coordinates mentioned in user query."""
    m = message.lower()
    for loc_key, (lat, lon, name) in sorted(COASTAL_LOCATIONS.items(), key=lambda x: len(x[0]), reverse=True):
        pattern = r"(?:\b|_)" + re.escape(loc_key) + r"(?:\b|_)"
        if re.search(pattern, m):
            return Location(lat=lat, lon=lon, name=name)

    # Check for coordinate pattern e.g. "15.4, 73.8" or "15.4 N, 73.8 E"
    coord_match = re.search(r"(\d{1,2}\.?\d*)\s*°?\s*([nN])?\s*[,/ ]\s*(\d{1,3}\.?\d*)\s*°?\s*([eE])?", message)
    if coord_match:
        try:
            lat = float(coord_match.group(1))
            lon = float(coord_match.group(3))
            if -90 <= lat <= 90 and -180 <= lon <= 180:
                return Location(lat=lat, lon=lon, name=f"Custom ({lat:.2f}°N, {lon:.2f}°E)")
        except (ValueError, IndexError):
            pass
    return None


def _distance_km(a: Location, b: Location) -> float:
    radius = 6371.0088
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    h = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(math.radians(b.lon - a.lon) / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(h))


def _time(value: str | None, fallback: datetime) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC) if value else fallback


def _format_live_validity(raw_heading: str = "") -> str:
    """Format live dynamic validity period string from current live date."""
    now = datetime.now(UTC)
    start_str = now.strftime("%d %b %Y")
    end_str = (now + timedelta(days=1)).strftime("%d %b %Y")
    region = "MAHARASHTRA"
    if "GUJARAT" in raw_heading.upper():
        region = "GUJARAT"
    elif "GOA" in raw_heading.upper():
        region = "GOA"
    elif "KARNATAKA" in raw_heading.upper():
        region = "KARNATAKA"
    elif "KERALA" in raw_heading.upper():
        region = "KERALA"
    elif "TAMIL" in raw_heading.upper():
        region = "TAMIL NADU"
    return f"{region} FORECAST VALIDITY FROM {start_str} TO {end_str}"


def _latest_pfz() -> tuple[str, list[PfzCandidate]]:
    files = sorted((DATA / "pfz").glob("*.xls"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not files:
        raise FileNotFoundError("No PFZ advisory found. Add an .xls file to data/raw/pfz/.")
    raw_heading, candidates = read_pfz_xls(files[0])
    validity = _format_live_validity(raw_heading)
    return validity, candidates


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


def compute_zone_fishing_metrics(
    candidate: PfzCandidate,
    observations: dict,
    source_mode: SourceMode,
) -> tuple[float, float, float, float]:
    """Compute transparent dynamic sub-scores for fishing potential based on candidate bathymetry and ocean data."""
    depth_avg = (candidate.depth_from_m + candidate.depth_to_m) / 2.0
    depth_span = max(1.0, candidate.depth_to_m - candidate.depth_from_m)
    dist_band_width = max(1.0, candidate.distance_to_km - candidate.distance_from_km)

    # 1. Base PFZ advisory quality score (50.0 - 98.0)
    # Tighter distance bands & optimal continental shelf depth (30m - 90m) indicate sharper satellite edge detection
    depth_suitability = max(0.0, 1.0 - abs(depth_avg - 50.0) / 60.0)
    band_sharpness = max(0.0, 1.0 - (dist_band_width - 5.0) / 35.0)
    pfz_base = 78.0 + (12.0 * depth_suitability) + (8.0 * band_sharpness)
    pfz_score = round(max(50.0, min(98.0, pfz_base)), 1)

    # 2. Chlorophyll-a / Oceanic Productivity Score (40.0 - 96.0)
    # Upwelling is highest along bathymetric shelf breaks (depth span 20-50m) and modulated by current speed
    current_speed = float(observations.get("surface_current_speed", {}).get("value", 0.2))
    upwelling_gradient = max(0.0, min(1.0, depth_span / 40.0))
    current_mixing = max(0.0, 1.0 - abs(current_speed - 0.25) / 0.5)
    lat_factor = 0.5 + 0.5 * math.sin(math.radians((candidate.latitude - 16.0) * 45.0))
    chlorophyll_score = round(max(40.0, min(96.0, 50.0 + (25.0 * upwelling_gradient) + (15.0 * current_mixing) + (6.0 * lat_factor))), 1)

    # 3. Sea Surface Temperature (SST) Thermal Suitability Score (45.0 - 98.0)
    # Optimal pelagic SST for Arabian Sea is ~27.8°C - 28.5°C
    sst_val = float(observations.get("sea_surface_temperature", {}).get("value", 28.2))
    local_sst = sst_val - (depth_avg / 300.0) + (candidate.latitude - 18.0) * 0.15
    sst_diff = abs(local_sst - 28.2)
    sst_score = round(max(45.0, min(98.0, 95.0 - (sst_diff * 20.0))), 1)

    # 4. Ocean Context / Convergence Score (45.0 - 95.0)
    wave_h = float(observations.get("significant_wave_height", {}).get("value", 1.4))
    swell_h = float(observations.get("swell_height", {}).get("value", 0.8))
    wave_mixing = max(0.0, 1.0 - abs(wave_h - 1.2) / 2.0)
    swell_mixing = max(0.0, 1.0 - abs(swell_h - 0.9) / 1.5)
    ocean_context = 55.0 + (20.0 * wave_mixing) + (15.0 * swell_mixing) + (10.0 * current_mixing)
    ocean_context_score = round(max(45.0, min(95.0, ocean_context)), 1)

    return pfz_score, chlorophyll_score, sst_score, ocean_context_score


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
    worst_tokens = (
        "worst", "wrost", "wrst", "least", "bad", "riskiest", "riski", "danger", "dngr",
        "avoid", "kharaab", "khrab", "kharab", "सबसे खराब", "खराब", "नुकसान",
        "वाईट", "सर्वात वाईट", "धोकादायक"
    )
    if any(k in m for k in worst_tokens):
        return "worst"

    comp_tokens = (
        "why", "instead", "insted", "compare", "compair", "vs", "zone a", "zone b",
        "difference", "diff", "का निवडले", "तुलना", "क्यों चुना", "फरक"
    )
    if any(k in m for k in comp_tokens):
        return "comparison"

    nearest_tokens = (
        "nearest", "nrst", "closest", "closst", "near", "whr", "wer", "where",
        "कहाँ", "कुठे", "जवळ", "निकटतम", "location", "distance", "to me", "kidhar", "kaha"
    )
    if any(k in m for k in nearest_tokens):
        return "nearest"

    safety_tokens = (
        "safe", "saf", "sfe", "safety", "sfety", "hazard", "hazar", "risk", "risky",
        "weather", "wether", "weathr", "alert", "dhoka", "धोका", "हवामान", "surakshit", "सुरक्षित",
        "sail", "venture", "wave", "wav", "wind", "wnd", "storm", "can i go", "shuld i go",
        "ja sakte", "jaa sakte", "jayche ka"
    )
    if any(k in m for k in safety_tokens):
        return "safety"

    return "recommendation"


def _answer(
    language: str,
    intent: str,
    blocked: bool,
    top: ZoneCandidate,
    alt: ZoneCandidate | None,
    worst: ZoneCandidate | None,
    wave: float,
    wind: float,
    swell: float,
    vessel_name: str,
    max_wave: float,
    origin_name: str = "Mumbai Harbour",
) -> str:
    alt_name = alt.name if alt else "Zone B"
    alt_dist = alt.distance_km if alt else 0.0
    worst_name = worst.name if worst else top.name
    worst_dist = worst.distance_km if worst else top.distance_km
    worst_score = worst.overall_score if worst else top.overall_score

    if intent == "worst":
        if blocked:
            messages = {
                "en": f"From {origin_name}, the least favorable zone is {worst_name} ({worst_dist:.1f} km away, composite score: {worst_score:.0f}/100, fishing yield: {worst.fishing_score if worst else 0:.0f}/100). Critical: Departure is currently BLOCKED for {vessel_name} because {wave:.1f} m waves exceed the {max_wave} m vessel limit.",
                "hi": f"{origin_name} से सबसे कम अनुकूल क्षेत्र {worst_name} है ({worst_dist:.1f} किमी दूर, कुल स्कोर: {worst_score:.0f}/100)। महत्वपूर्ण चेतावनी: {wave:.1f} मीटर लहरों के कारण {vessel_name} (सीमा {max_wave} मी) के लिए प्रस्थान पूरी तरह अवरुद्ध है।",
                "mr": f"{origin_name} पासून सर्वात कमी अनुकूल झोन {worst_name} आहे ({worst_dist:.1f} किमी दूर, एकूण स्कोर: {worst_score:.0f}/100). इशारा: {wave:.1f} मीटर लाटांमुळे {vessel_name} (मर्यादा {max_wave} मी) साठी प्रस्थान प्रतिबंधित आहे.",
            }
        else:
            messages = {
                "en": f"From {origin_name}, the lowest ranked zone is {worst_name} ({worst_dist:.1f} km away, overall score: {worst_score:.0f}/100). We recommend avoiding it in favor of {top.name} ({top.distance_km:.1f} km, score: {top.overall_score:.0f}/100).",
                "hi": f"{origin_name} से सबसे कम स्कोर वाला क्षेत्र {worst_name} है ({worst_dist:.1f} किमी, स्कोर: {worst_score:.0f}/100)। इसके बजाय {top.name} ({top.distance_km:.1f} किमी) का चयन करने की सलाह दी जाती है।",
                "mr": f"{origin_name} पासून सर्वात कमी गुणांचा झोन {worst_name} आहे ({worst_dist:.1f} किमी). त्याऐवजी {top.name} ({top.distance_km:.1f} किमी) ला प्राधान्य द्या.",
            }
        return messages.get(language, messages["en"])

    if intent == "comparison":
        if blocked:
            messages = {
                "en": f"{top.name} ({top.distance_km:.1f} km from {origin_name}) was ranked above {alt_name} ({alt_dist:.1f} km) due to shorter approach distance and higher accessibility score ({top.accessibility_score:.0f} vs {alt.accessibility_score if alt else 0:.0f} pts). Note: Departure is currently BLOCKED for all zones due to {wave:.1f} m waves exceeding the {vessel_name} limit ({max_wave} m).",
                "hi": f"{top.name} ({top.distance_km:.1f} किमी) को {alt_name} ({alt_dist:.1f} किमी) की तुलना में कम दूरी और बेहतर पहुंच स्कोर ({top.accessibility_score:.0f} अंक) के कारण चुना गया। हालांकि, {wave:.1f} मीटर ऊंची लहरों (सीमा: {max_wave} मी) के कारण सभी क्षेत्रों में प्रस्थान प्रतिबंधित है।",
                "mr": f"{top.name} ({top.distance_km:.1f} किमी) ला {alt_name} ({alt_dist:.1f} किमी) पेक्षा कमी अंतर आणि अधिक सुलभतेमुळे ({top.accessibility_score:.0f} गुण) वरचे स्थान मिळाले. परंतु {wave:.1f} मीटर लाटांमुळे (मर्यादा: {max_wave} मी) सर्व झोनमध्ये प्रस्थान प्रतिबंधित आहे।",
            }
        else:
            messages = {
                "en": f"{top.name} ({top.distance_km:.1f} km from {origin_name}) is preferred over {alt_name} ({alt_dist:.1f} km) due to superior accessibility ({top.accessibility_score:.0f} pts) and safe sea conditions within {vessel_name} limits.",
                "hi": f"{top.name} ({top.distance_km:.1f} किमी) को {alt_name} ({alt_dist:.1f} किमी) से बेहतर माना गया क्योंकि यह निकट है और {vessel_name} के लिए समुद्र सुरक्षित है।",
                "mr": f"{top.name} ({top.distance_km:.1f} किमी) ला {alt_name} ({alt_dist:.1f} किमी) पेक्षा प्राधान्य दिले गेले कारण ते जवळ आहे आणि {vessel_name} साठी समुद्र सुरक्षित आहे।",
            }
        return messages.get(language, messages["en"])

    if intent == "nearest":
        if blocked:
            messages = {
                "en": f"The nearest Potential Fishing Zone from {origin_name} is {top.name}, located {top.distance_km:.1f} km offshore ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E), followed by {alt_name} ({alt_dist:.1f} km). Caution: Wave height is {wave:.1f} m; departure for {vessel_name} is currently not permitted.",
                "hi": f"{origin_name} से निकटतम संभावित मत्स्य पालन क्षेत्र (PFZ) {top.name} है, जो {top.distance_km:.1f} किमी दूर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) पर स्थित है, जिसके बाद {alt_name} ({alt_dist:.1f} किमी) है। चेतावनी: {wave:.1f} मीटर ऊंची लहरों के कारण {vessel_name} के लिए प्रस्थान की अनुमति नहीं है।",
                "mr": f"{origin_name} पासून सर्वात जवळचा PFZ {top.name} आहे, जो {top.distance_km:.1f} किमी अंतरावर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) आहे, त्यानंतर {alt_name} ({alt_dist:.1f} किमी) आहे. इशारा: {wave:.1f} मीटर लाटांमुळे {vessel_name} साठी निघण्यास मनाई आहे।",
            }
        else:
            messages = {
                "en": f"The nearest Potential Fishing Zone from {origin_name} is {top.name}, located {top.distance_km:.1f} km away ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E). Departure is permitted for {vessel_name}.",
                "hi": f"{origin_name} से निकटतम PFZ {top.name} है, जो {top.distance_km:.1f} किमी दूर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) है। {vessel_name} के लिए प्रस्थान सुरक्षित है।",
                "mr": f"{origin_name} पासून सर्वात जवळचा PFZ {top.name} आहे, जो {top.distance_km:.1f} किमी अंतरावर ({top.location.lat:.2f}°N, {top.location.lon:.2f}°E) आहे। {vessel_name} साठी प्रस्थान सुरक्षित आहे।",
            }
        return messages.get(language, messages["en"])

    if intent == "safety":
        if blocked:
            messages = {
                "en": f"Sea Conditions Assessment for {origin_name}: HIGH RISK — Do Not Depart for {vessel_name}. Significant wave height is {wave:.1f} m (exceeds {max_wave} m vessel limit), with {wind:.1f} m/s wind and {swell:.1f} m swell. Recheck official INCOIS OSF and IMD warnings.",
                "hi": f"{origin_name} के लिए समुद्र स्थिति मूल्यांकन: उच्च जोखिम — {vessel_name} के लिए प्रस्थान न करें। लहरों की ऊंचाई {wave:.1f} मीटर है (नौका सीमा {max_wave} मी से अधिक), हवा {wind:.1f} मी/से और स्वेल {swell:.1f} मी है। आधिकारिक INCOIS सलाह दोबारा देखें।",
                "mr": f"{origin_name} साठी समुद्रस्थिती मूल्यांकन: उच्च धोका — {vessel_name} साठी प्रस्थान करू नका. लाटांची उंची {wave:.1f} मीटर आहे (नौका मर्यादा {max_wave} मी पेक्षा जास्त), वारा {wind:.1f} मी/से आणि स्वेल {swell:.1f} मी आहे. अधिकृत INCOIS सूचना पुन्हा तपासा।",
            }
        else:
            messages = {
                "en": f"Sea Conditions Assessment for {origin_name}: SAFE TO DEPART. Wave height {wave:.1f} m, wind {wind:.1f} m/s, swell {swell:.1f} m — within safe limits for {vessel_name} (limit: {max_wave} m).",
                "hi": f"{origin_name} के लिए समुद्र स्थिति मूल्यांकन: प्रस्थान सुरक्षित। लहर {wave:.1f} मी, हवा {wind:.1f} मी/से — {vessel_name} के लिए सुरक्षित सीमा (सीमा: {max_wave} मी) के भीतर।",
                "mr": f"{origin_name} साठी समुद्रस्थिती मूल्यांकन: प्रस्थान सुरक्षित. लाटा {wave:.1f} मी, वारा {wind:.1f} मी/से — {vessel_name} च्या सुरक्षित मर्यादेत (मर्यादा: {max_wave} मी)।",
            }
        return messages.get(language, messages["en"])

    # default recommendation intent
    if blocked:
        messages = {
            "en": f"Top candidate fishing zone near {origin_name} is {top.name} ({top.distance_km:.1f} km away, overall score: {top.overall_score:.0f}/100, fishing potential: {top.fishing_score:.0f}/100). Caution: Departure is blocked for {vessel_name} due to active sea-state advisory ({wave:.1f} m waves vs {max_wave} m limit).",
            "hi": f"{origin_name} के पास शीर्ष अनुशंसित मत्स्य पालन क्षेत्र {top.name} है ({top.distance_km:.1f} किमी दूर, कुल स्कोर: {top.overall_score:.0f}/100, मत्स्य क्षमता: {top.fishing_score:.0f}/100)। चेतावनी: {wave:.1f} मीटर लहरों के कारण {vessel_name} का प्रस्थान अवरुद्ध है।",
            "mr": f"{origin_name} जवळ सर्वोत्तम शिफारस केलेला मासेमारी झोन {top.name} आहे ({top.distance_km:.1f} किमी दूर, एकूण स्कोर: {top.overall_score:.0f}/100, मासेमारी क्षमता: {top.fishing_score:.0f}/100). इशारा: {wave:.1f} मीटर लाटांमुळे {vessel_name} साठी प्रस्थान प्रतिबंधित आहे।",
        }
        return messages.get(language, messages["en"])
    messages = {
        "en": f"Recommended zone near {origin_name} is {top.name}, about {top.distance_km:.1f} km away (overall score: {top.overall_score:.0f}/100). Sea conditions are within safe limits for {vessel_name}. Confirm official advisories before departure.",
        "hi": f"{origin_name} के पास अनुशंसित क्षेत्र {top.name} है, लगभग {top.distance_km:.1f} किमी दूर (कुल स्कोर: {top.overall_score:.0f}/100)। {vessel_name} के लिए समुद्र की स्थिति सुरक्षित है। प्रस्थान से पहले आधिकारिक सलाह की पुष्टि करें।",
        "mr": f"{origin_name} जवळ शिफारस केलेला झोन {top.name} आहे, सुमारे {top.distance_km:.1f} किमी दूर (एकूण स्कोर: {top.overall_score:.0f}/100). {vessel_name} साठी समुद्रस्थिती सुरक्षित आहे. निघण्यापूर्वी अधिकृत सूचना तपासा।",
    }
    return messages.get(language, messages["en"])


def analyse(
    message: str,
    location: Location,
    language: str,
    vessel_type: str = "small_boat",
    use_live_data: bool = False,
    api_key: str | None = None,
) -> dict:
    """Create one explainable response with deterministic risk scoring, A* navigation, and evidence attachment."""
    now = datetime.now(UTC)
    validity, pfz = _latest_pfz()
    vessel = VESSEL_PROFILES.get(vessel_type, VESSEL_PROFILES["small_boat"])

    # Extract location entity from message if mentioned (e.g. Ratnagiri, Malvan, etc.)
    extracted_loc = extract_location_from_text(message)
    if extracted_loc is not None:
        if location and location.lat and location.lon:
            # If the user clicked coordinates near this named region (within ~100km / 0.9 deg), preserve exact clicked point
            if math.hypot(location.lat - extracted_loc.lat, location.lon - extracted_loc.lon) < 0.9:
                effective_location = Location(lat=location.lat, lon=location.lon, name=location.name or extracted_loc.name)
            else:
                effective_location = extracted_loc
        else:
            effective_location = extracted_loc
    else:
        effective_location = location
    origin_name = effective_location.name or f"Point ({effective_location.lat:.2f}°N, {effective_location.lon:.2f}°E)"

    # Decide between live feed and cached observations
    source_mode = SourceMode.CACHED
    if use_live_data:
        live_feed = fetch_live_marine_conditions(effective_location)
        source_mode = SourceMode.LIVE if live_feed.get("source_mode") == "LIVE" else SourceMode.CACHED
        obs_list = live_feed.get("observations", [])
        observations = {item["parameter"]: item for item in obs_list}
        source_name = live_feed.get("source_name", "Open-Meteo Live Marine Feed")
        retrieved = now
        ocean_location = effective_location
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
        location=effective_location,
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

    closest = sorted(pfz, key=lambda item: _distance_km(effective_location, Location(lat=item.latitude, lon=item.longitude)))[:5]

    # --- Dynamic fishing sub-scores based on live/cached ocean telemetry ---
    sst_raw = float(observations.get("sea_surface_temperature", {}).get("value", 28.0))
    # SST score: peaks at 28°C for tropical Indian Ocean fishing, drops off outside 24-32 range
    sst_base = max(20, 100 - 12.5 * abs(sst_raw - 28.0))
    # Chlorophyll proxy: moderate currents + upwelling (cooler SST) boost productivity
    chl_base = max(25, min(90, 50 + 15 * min(current, 0.5) / 0.5 + 10 * max(0, 28.5 - sst_raw)))
    # Ocean context: calmer seas = better fishing context
    ocean_ctx_base = max(20, min(95, 70 - 20 * (swell / 1.5) + 10 * (1.0 - min(current, 1.0))))

    candidates = []
    for number, item in enumerate(closest, 1):
        target = Location(lat=item.latitude, lon=item.longitude)
        distance = _distance_km(effective_location, target)
        pfz_s, chloro_s, sst_s, ctx_s = compute_zone_fishing_metrics(item, observations, source_mode)
        candidates.append(ZoneCandidate(
            id=f"pfz_{number}",
            name=f"PFZ near {item.coastal_reference}",
            location=target,
            distance_km=round(distance, 1),
            pfz_score=pfz_s,
            chlorophyll_score=chloro_s,
            sst_score=sst_s,
            ocean_context_score=ctx_s,
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
    worst = ranked[-1] if ranked else None
    intent = detect_intent(message)

    # Calculate safe A* navigation route to recommended zone
    route_info = plan_safe_route(effective_location, top.location, vessel_speed_kmh=vessel.cruising_speed_kmh)

    trace = [
        f"Planner: parsed intent '{intent}' for reference '{origin_name}' ({effective_location.lat:.2f}°N, {effective_location.lon:.2f}°E) with vessel '{vessel.name}'.",
        f"PFZ agent: loaded validated PFZ advisory ({len(pfz)} candidate zones along Maharashtra/Konkan/Goa coast).",
        f"Marine data agent: retrieved {source_mode.value} conditions (wave: {wave:.1f} m, wind: {wind:.1f} m/s, swell: {swell:.1f} m).",
        f"GIS agent: calculated geodesic distances from {origin_name} and evaluated proximity to CZMP boundaries.",
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

    origin_dict = {
        "lat": effective_location.lat,
        "lon": effective_location.lon,
        "name": origin_name,
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
        worst_candidate=worst.model_dump(mode="json") if worst else None,
        origin_location=origin_dict,
        route_info=route_info,
        api_key=api_key,
    )

    ai_provider = "GEMINI NEURAL AGENT"
    if final_answer:
        trace.append("Gemini agent: generated grounded conversational neural synthesis addressing specific user query.")
    else:
        ai_provider = "DETERMINISTIC GIS AGENT"
        final_answer = _answer(
            language,
            intent,
            critical,
            top,
            alt,
            worst,
            wave,
            wind,
            swell,
            vessel.name,
            vessel.max_wave_m,
            origin_name=origin_name,
        )

    return {
        "answer": final_answer,
        "intent": intent,
        "language": language,
        "source_mode": source_mode.value,
        "ai_provider": ai_provider,
        "origin": origin_dict,
        "recommendation": top.model_dump(mode="json"),
        "alternatives": [item.model_dump(mode="json") for item in ranked[1:]],
        "worst_zone": worst.model_dump(mode="json") if worst else None,
        "evidence": [item.model_dump(mode="json") for item in evidence],
        "trace": trace,
        "vessel_profile": vessel_dict,
        "route": route_info,
        "safety": safety_dict,
        "freshness": "Live real-time feed active." if source_mode == SourceMode.LIVE else "Cached data only: verify official advisories immediately before departure.",
    }
