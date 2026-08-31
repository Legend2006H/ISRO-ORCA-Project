"""Comprehensive production-readiness test suite for Phase 6.1: ORCA Voice & Exotel IVR Layer."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from fastapi.testclient import TestClient

from api.main import app
from api.voice.exotel import ExoMLBuilder, SUPPORTED_VOICE_LOCATIONS, voice_flow_controller
from api.voice.formatter import VoiceResponseFormatter, get_provenance_prefix
from api.voice.session import VoiceCallSession, VoiceCallStep, VoiceSessionStore, mask_phone_number, voice_session_store

client = TestClient(app)


def test_realistic_exotel_incoming_webhook():
    """Verify POST /api/v1/voice/incoming handles standard Exotel parameters and returns valid ExoML."""
    response = client.post(
        "/api/v1/voice/incoming",
        data={
            "CallSid": "call-exotel-live-001",
            "CallFrom": "+919876543210",
            "CallTo": "08047101234",
            "Direction": "inbound",
            "CallType": "transferred",
        },
    )
    assert response.status_code == 200
    assert "application/xml" in response.headers["content-type"]

    root = ET.fromstring(response.text)
    assert root.tag == "Response"
    gather = root.find("Gather")
    assert gather is not None
    assert gather.get("action") == "/api/v1/voice/input"
    say = gather.find("Say")
    assert say is not None
    assert "मराठी" in say.text
    assert "हिंदी" in say.text
    assert "English" in say.text


def test_language_selection_updates_session_and_prompts_intent():
    """Verify pressing 1 selects Marathi and advances to intent selection menu."""
    sid = "call-test-lang-mr"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid, "From": "+919820011223"})

    res = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "1"})
    assert res.status_code == 200

    session = voice_session_store.get(sid)
    assert session is not None
    assert session.language == "mr"
    assert session.current_step == VoiceCallStep.INTENT_SELECT

    root = ET.fromstring(res.text)
    say = root.find(".//Say")
    assert say is not None
    assert "सागरी हवामान" in say.text


def test_intent_selection_prompts_location():
    """Verify selecting intent 1 (safety) advances to port selection menu."""
    sid = "call-test-intent"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid})
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "1"})  # Marathi

    res = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "1"})  # Safety
    assert res.status_code == 200

    session = voice_session_store.get(sid)
    assert session is not None
    assert session.intent == "safety"
    assert session.current_step == VoiceCallStep.LOCATION_SELECT

    root = ET.fromstring(res.text)
    say = root.find(".//Say")
    assert say is not None
    assert "रत्नागिरीसाठी २" in say.text


def test_location_selection_executes_orchestrator_and_returns_safety_advisory():
    """Verify selecting port 2 (Ratnagiri) runs orchestrator and returns spoken advisory."""
    sid = "call-test-exec"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid, "From": "+919876543210"})
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "1"})  # Marathi
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "1"})  # Safety

    res = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "2"})  # Ratnagiri
    assert res.status_code == 200

    session = voice_session_store.get(sid)
    assert session is not None
    assert session.current_step == VoiceCallStep.RESULT
    assert session.duration_ms > 0

    root = ET.fromstring(res.text)
    say = root.find(".//Say")
    assert say is not None
    assert "रत्नागिरी" in say.text
    assert "मीटर" in say.text
    assert "९ दाबा" in say.text  # Menu navigation option


def test_pfz_voice_response_in_hindi():
    """Verify PFZ query in Hindi returns formatted zone advisory."""
    sid = "call-test-pfz-hi"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid})
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "2"})  # Hindi
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "2"})  # PFZ intent

    res = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "1"})  # Mumbai
    assert res.status_code == 200

    root = ET.fromstring(res.text)
    say = root.find(".//Say")
    assert say is not None
    assert "मुंबई" in say.text
    assert "मत्स्य क्षेत्र" in say.text
    assert "किलोमीटर" in say.text


def test_route_voice_response_in_english():
    """Verify safe route query in English returns corridor distance and time."""
    sid = "call-test-route-en"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid})
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "3"})  # English
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "3"})  # Route intent

    res = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "3"})  # Malvan
    assert res.status_code == 200

    root = ET.fromstring(res.text)
    say = root.find(".//Say")
    assert say is not None
    assert "Malvan" in say.text
    assert "kilometres" in say.text
    assert "hours" in say.text


def test_safety_blocked_voice_response_formatting():
    """Verify VoiceResponseFormatter correctly creates blocked advisory when safety threshold breached."""
    mock_result = {
        "source_mode": "LIVE",
        "safety": {
            "wave_height_m": 2.4,
            "wind_speed_ms": 11.2,
            "max_wave_limit_m": 1.5,
            "departure_allowed": False,
        },
    }
    mr_speech = VoiceResponseFormatter.format_safety_response(mock_result, "mr", "Ratnagiri")
    assert "गंभीर इशारा" in mr_speech
    assert "2.4" in mr_speech or "२.४" in mr_speech

    hi_speech = VoiceResponseFormatter.format_safety_response(mock_result, "hi", "Ratnagiri")
    assert "चेतावनी" in hi_speech
    assert "2.4" in hi_speech or "२.४" in hi_speech

    en_speech = VoiceResponseFormatter.format_safety_response(mock_result, "en", "Ratnagiri")
    assert "High Risk Alert" in en_speech
    assert "2.4" in en_speech


def test_safety_allowed_voice_response_formatting():
    """Verify VoiceResponseFormatter correctly creates safe advisory when conditions are clear."""
    mock_result = {
        "source_mode": "CACHED",
        "safety": {
            "wave_height_m": 1.1,
            "wind_speed_ms": 5.4,
            "max_wave_limit_m": 1.5,
            "departure_allowed": True,
        },
    }
    mr_speech = VoiceResponseFormatter.format_safety_response(mock_result, "mr", "Malvan")
    assert "समुद्र सुरक्षित आहे" in mr_speech

    hi_speech = VoiceResponseFormatter.format_safety_response(mock_result, "hi", "Malvan")
    assert "समुद्र सुरक्षित है" in hi_speech

    en_speech = VoiceResponseFormatter.format_safety_response(mock_result, "en", "Malvan")
    assert "safe to depart" in en_speech


def test_data_provenance_prefixes():
    """Verify LIVE, CACHED, and DEMO sources generate honest spoken attribution."""
    assert "थेट" in get_provenance_prefix("LIVE", "mr")
    assert "लाइव" in get_provenance_prefix("LIVE", "hi")
    assert "Live" in get_provenance_prefix("LIVE", "en")

    assert "नवीनतम" in get_provenance_prefix("CACHED", "mr")
    assert "अद्यतन" in get_provenance_prefix("CACHED", "hi")
    assert "Latest" in get_provenance_prefix("CACHED", "en")

    assert "अंदाजित" in get_provenance_prefix("DEMO", "mr")
    assert "अनुमानित" in get_provenance_prefix("DEMO", "hi")
    assert "Fallback" in get_provenance_prefix("DEMO", "en")


def test_invalid_dtmf_digit_handling():
    """Verify pressing invalid digit reprompts gracefully without crash."""
    sid = "call-test-invalid"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid})
    res = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "8"})  # Invalid lang
    assert res.status_code == 200

    root = ET.fromstring(res.text)
    say = root.find(".//Say")
    assert "Invalid selection" in say.text


def test_global_navigation_hangup_and_main_menu():
    """Verify 0 hangs up and 9 resets to main menu."""
    sid = "call-test-nav"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid})
    client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "1"})  # Marathi

    # Press 0 (Hangup)
    res_hangup = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "0"})
    root_hangup = ET.fromstring(res_hangup.text)
    assert root_hangup.find("Hangup") is not None

    # Press 9 (Main Menu)
    res_menu = client.post("/api/v1/voice/input", data={"CallSid": sid, "Digits": "9"})
    root_menu = ET.fromstring(res_menu.text)
    say = root_menu.find(".//Say")
    assert "सागरी हवामान" in say.text


def test_session_ttl_expiration():
    """Verify session store cleans up expired calls."""
    store = VoiceSessionStore(default_ttl_seconds=0.1)
    s = store.get_or_create("temp-call")
    assert s is not None
    time.sleep(0.15)
    expired = store.get("temp-call")
    assert expired is None


def test_concurrent_call_session_isolation():
    """Verify concurrent calls have strictly isolated state."""
    sid1 = "call-user-1"
    sid2 = "call-user-2"

    client.post("/api/v1/voice/incoming", data={"CallSid": sid1})
    client.post("/api/v1/voice/incoming", data={"CallSid": sid2})

    # User 1 chooses Marathi, User 2 chooses Hindi
    client.post("/api/v1/voice/input", data={"CallSid": sid1, "Digits": "1"})
    client.post("/api/v1/voice/input", data={"CallSid": sid2, "Digits": "2"})

    s1 = voice_session_store.get(sid1)
    s2 = voice_session_store.get(sid2)

    assert s1.language == "mr"
    assert s2.language == "hi"
    assert s1.call_id != s2.call_id


def test_phone_number_masking_privacy():
    """Verify phone numbers are masked in session and telemetry."""
    masked = mask_phone_number("+919876543210")
    assert masked == "+91******3210"
    assert "987654" not in masked

    sid = "call-mask-check"
    client.post("/api/v1/voice/incoming", data={"CallSid": sid, "From": "+919876543210"})
    session = voice_session_store.get(sid)
    assert session.caller_number == "+91******3210"


def test_xml_escaping_and_sanitization():
    """Verify special XML characters in speech are escaped properly."""
    xml_out = ExoMLBuilder.gather(
        action_url="/api/v1/voice/input",
        say_text='Testing & Checking <Safety> for "Boats" & Trawlers',
    )
    root = ET.fromstring(xml_out)
    say = root.find(".//Say")
    assert say.text == 'Testing & Checking <Safety> for "Boats" & Trawlers'
    assert '<?xml version="1.0" encoding="UTF-8"?>' in xml_out


def test_voice_telemetry_endpoint():
    """Verify GET /api/v1/voice/telemetry returns session statistics."""
    res = client.get("/api/v1/voice/telemetry")
    assert res.status_code == 200
    data = res.json()
    assert "active_voice_sessions" in data
    assert "recent_calls" in data


def test_call_status_callback():
    """Verify POST /api/v1/voice/status acknowledges Exotel callbacks."""
    res = client.post(
        "/api/v1/voice/status",
        data={"CallSid": "call-status-001", "Status": "completed"},
    )
    assert res.status_code == 200
    assert res.json()["status"] == "acknowledged"


def test_voice_simulate_endpoint():
    """Verify interactive helper /api/v1/voice/simulate endpoint."""
    res = client.post(
        "/api/v1/voice/simulate",
        json={"call_id": "sim-user-1", "digits": None},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["call_id"] == "sim-user-1"
    assert data["current_step"] == "LANG_SELECT"
    assert "<Response>" in data["exoml_xml"]
