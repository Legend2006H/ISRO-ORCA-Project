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
    assert "do not depart" in result["answer"].lower()


def test_golden_query_comparison() -> None:
    result = analyse("Why did ORCA choose Zone A instead of Zone B?", DEFAULT_LOCATION, "en")
    assert result["intent"] == "comparison"
    assert "ranked above" in result["answer"] or "accessibility" in result["answer"]


def test_golden_query_multilingual() -> None:
    assert detect_language("Where is the nearest PFZ?", "auto") == "en"
    assert detect_language("क्या कल सुबह समुद्र में जाना सुरक्षित है?", "auto") == "hi"
    assert detect_language("उद्या सकाळी समुद्रात जाणे सुरक्षित आहे का?", "auto") == "mr"
    res_hi = client.post("/api/v1/chat", json={"message": "क्या कल सुबह समुद्र में जाना सुरक्षित है?", "location": {"lat": 18.95, "lon": 72.85}, "language": "auto"}).json()
    assert res_hi["language"] == "hi"
    assert "प्रस्थान न करें" in res_hi["answer"]


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
