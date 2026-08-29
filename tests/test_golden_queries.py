from datetime import datetime
from fastapi.testclient import TestClient

from api.main import app
from api.models import Location
from api.offline_service import DEFAULT_LOCATION, analyse, detect_language
from api.scoring import rank_zones, ZoneCandidate

client = TestClient(app)

def test_golden_query_nearest_pfz() -> None:
    result = analyse("Where is the nearest Potential Fishing Zone to me today?", DEFAULT_LOCATION, "en")
    assert result["source_mode"] == "CACHED"
    assert "recommendation" in result
    assert result["recommendation"]["name"].startswith("PFZ near ")
    assert result["recommendation"]["distance_km"] > 0
    assert len(result["alternatives"]) == 4

def test_golden_query_safety_check() -> None:
    result = analyse("Is it safe to venture into the sea tomorrow morning?", DEFAULT_LOCATION, "en")
    assert result["safety"]["departure_allowed"] is False
    assert result["safety"]["wave_height_m"] > 1.5
    assert "exceed" in result["safety"]["reason"].lower()
    ans = result["answer"].lower()
    assert any(w in ans for w in ("do not depart", "not safe", "advise against", "not to head out", "dangerous", "risk", "hazard", "stay in", "blocked", "exceed", "harbor", "harbour", "wave", "caution", "hold off", "remain in port", "unsafe", "prohibited", "alert"))


def test_golden_query_comparison() -> None:
    result = analyse("Why did ORCA choose Zone A instead of Zone B?", DEFAULT_LOCATION, "en")
    assert result["intent"] == "comparison"
    ans = result["answer"].lower()
    assert any(w in ans for w in ("ranked above", "accessibility", "score", "preferred", "zone", "compared", "higher", "choose", "optimal", "fishing", "distance", "evaluat", "recommend", "pfz"))


def test_golden_query_multilingual() -> None:
    assert detect_language("Where is the nearest PFZ?", "auto") == "en"
    assert detect_language("क्या कल सुबह समुद्र में जाना सुरक्षित है?", "auto") == "hi"
    assert detect_language("उद्या सकाळी समुद्रात जाणे सुरक्षित आहे का?", "auto") == "mr"
    res_hi = client.post("/api/v1/chat", json={"message": "क्या कल सुबह समुद्र में जाना सुरक्षित है?", "location": {"lat": 18.95, "lon": 72.85}, "language": "auto"}).json()
    assert res_hi["language"] == "hi"
    ans = res_hi["answer"]
    assert any(w in ans for w in ("प्रस्थान", "सुरक्षित", "न करें", "न जाएं", "सलाह", "खतरा", "लहर", "समुद्र", "मत्स्य", "तट", "मौसम", "चेतावनी", "सावधानी", "नाव", "हवा", "रोक", "नहीं"))


def test_evidence_ledger_and_trace() -> None:
    result = analyse("Analyze fishing conditions", DEFAULT_LOCATION, "en")
    evidence_ids = {e["id"] for e in result["evidence"]}
    rec = result["recommendation"]
    for ev_id in rec["evidence_ids"]:
        assert ev_id in evidence_ids

    assert len(result["trace"]) >= 5
    assert any("Planner" in step for step in result["trace"])
    assert any("Risk" in step for step in result["trace"])


def test_api_health_and_evidence_endpoints() -> None:
    health = client.get("/health").json()
    assert health["status"] == "ok"
    assert health["source_mode"] == "CACHED"
    chat_res = client.post("/api/v1/chat", json={"message": "Check marine conditions", "location":{"lat": 18.95, "lon": 72.85}, "language": "en"}).json()
    first_ev_id = chat_res["evidence"][0]["id"]
    ev_res = client.get(f"/api/v1/evidence/{first_ev_id}")
    assert ev_res.status_code == 200
    assert ev_res.json()["id"] == first_ev_id    


def test_routing_api() -> None:
    res = client.post("/api/v1/route", json={
        "origin": {"lat": 18.95, "lon": 72.85},
        "destination": {"lat": 18.74, "lon": 72.48},
        "vessel_speed_kmh": 18.0,
    }).json()
    assert "distance_km" in res
    assert res["distance_km"] > 0
    assert res["waypoints_count"] >= 2
    assert res["geojson"]["geometry"]["type"] == "LineString"


def test_pfz_and_boundaries_geojson() -> None:
    pfz_res = client.get("/api/v1/pfz/all").json()
    assert pfz_res["type"] == "FeatureCollection"
    assert pfz_res["total_candidates"] == 89
    assert len(pfz_res["features"]) == 89

    bound_res = client.get("/api/v1/boundaries/all").json()
    assert bound_res["type"] == "FeatureCollection"
    assert len(bound_res["features"]) >= 1


def test_vessel_profile_simulation() -> None:
    # Small boat (1.5m max wave) should be BLOCKED in 2.2m wave
    res_small = client.post("/api/v1/chat", json={
        "message": "Is it safe to depart?",
        "location": {"lat": 18.95, "lon": 72.85},
        "vessel_type": "small_boat",
        "language": "en",
    }).json()
    assert res_small["safety"]["departure_allowed"] is False

    # Deep-sea vessel (4.0m max wave) should be SAFE in 2.2m wave
    res_deep = client.post("/api/v1/chat", json={
        "message": "Is it safe to depart?",
        "location": {"lat": 18.95, "lon": 72.85},
        "vessel_type": "deep_sea",
        "language": "en",
    }).json()
    assert res_deep["safety"]["departure_allowed"] is True
    assert any(w in res_deep["answer"].lower() for w in ("safe", "permitted", "clear", "allowed"))


def test_location_extraction_ratnagiri() -> None:
    res = client.post("/api/v1/chat", json={
        "message": "find the best pfz near Ratnagiri for my boat",
        "location": {"lat": 18.95, "lon": 72.85},
        "vessel_type": "small_boat",
        "language": "en",
    }).json()
    assert "origin" in res
    assert "Ratnagiri" in res["origin"]["name"]
    assert abs(res["origin"]["lat"] - 16.99) < 0.1
    # Check that the recommended PFZ is near Ratnagiri (Mirkarwada / Bhatye / Pawas / Jaigad)
    assert res["recommendation"]["distance_km"] < 60.0
    assert "Ratnagiri" in res["answer"] or "PFZ" in res["answer"]


def test_worst_zone_intent() -> None:
    res = client.post("/api/v1/chat", json={
        "message": "Which fishing zone near Mumbai is worst tomorrow morning, considering fishing potential and safety?",
        "location": {"lat": 18.95, "lon": 72.85},
        "vessel_type": "small_boat",
        "language": "en",
    }).json()
    assert res["intent"] == "worst"
    ans = res["answer"].lower()
    assert any(w in ans for w in ("least favorable", "lowest", "worst", "riskiest", "avoid", "risk", "hazard"))

