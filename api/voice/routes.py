"""FastAPI routes for Exotel Voice IVR, DTMF handling, and voice telemetry."""
from __future__ import annotations

from typing import Any
from fastapi import APIRouter, Form, Query, Request, Response
from pydantic import BaseModel

from .exotel import voice_flow_controller
from .session import voice_session_store

voice_router = APIRouter(prefix="/api/v1/voice", tags=["Voice Access"])


def _extract_param(
    form_val: str | None,
    query_val: str | None,
    default: str = "",
) -> str:
    """Safely extract parameter from either form-data (POST) or query string (GET)."""
    return (form_val or query_val or default).strip()


@voice_router.api_route("/incoming", methods=["GET", "POST"])
async def incoming_call(
    request: Request,
    CallSid: str | None = Form(None),
    CallUUID: str | None = Form(None),
    CallFrom: str | None = Form(None),
    From: str | None = Form(None),
    call_sid: str | None = Query(None),
    call_uuid: str | None = Query(None),
    caller: str | None = Query(None),
) -> Response:
    """Webhook entrypoint triggered by Exotel when a phone call is connected."""
    sid = _extract_param(CallSid or CallUUID, call_sid or call_uuid, default="sim-call-001")
    phone = _extract_param(CallFrom, From or caller, default="anonymous")

    xml_response = voice_flow_controller.handle_incoming_call(call_id=sid, caller_number=phone)
    return Response(content=xml_response, media_type="application/xml; charset=utf-8")


@voice_router.api_route("/input", methods=["GET", "POST"])
async def handle_dtmf_input(
    request: Request,
    CallSid: str | None = Form(None),
    CallUUID: str | None = Form(None),
    Digits: str | None = Form(None),
    CallFrom: str | None = Form(None),
    From: str | None = Form(None),
    call_sid: str | None = Query(None),
    call_uuid: str | None = Query(None),
    digits: str | None = Query(None),
    caller: str | None = Query(None),
) -> Response:
    """Webhook handling DTMF keypad selections sent by Exotel."""
    sid = _extract_param(CallSid or CallUUID, call_sid or call_uuid, default="sim-call-001")
    key_digits = _extract_param(Digits, digits, default="")
    phone = _extract_param(CallFrom, From or caller, default="anonymous")

    xml_response = voice_flow_controller.handle_input(
        call_id=sid,
        digits=key_digits,
        caller_number=phone,
    )
    return Response(content=xml_response, media_type="application/xml; charset=utf-8")


@voice_router.api_route("/status", methods=["GET", "POST"])
async def call_status_callback(
    CallSid: str | None = Form(None),
    Status: str | None = Form(None),
    call_sid: str | None = Query(None),
    status: str | None = Query(None),
) -> dict[str, Any]:
    """Status callback invoked by Exotel on call completion, disconnect, or busy."""
    sid = _extract_param(CallSid, call_sid, default="unknown")
    call_status = _extract_param(Status, status, default="completed")
    return {
        "status": "acknowledged",
        "call_sid": sid,
        "call_status": call_status,
    }


class SimulateVoiceRequest(BaseModel):
    call_id: str = "sim-call-001"
    digits: str | None = None
    caller_number: str = "+919876543210"


@voice_router.get("/telemetry")
def get_voice_telemetry() -> dict[str, Any]:
    """Retrieve anonymized voice session telemetry metrics."""
    return {
        "active_voice_sessions": len(voice_session_store._sessions),
        "recent_calls": voice_session_store.get_telemetry(),
    }


@voice_router.post("/simulate")
def simulate_voice_turn(payload: SimulateVoiceRequest) -> dict[str, Any]:
    """Interactive helper endpoint to test and simulate IVR state transitions via JSON."""
    call_id = payload.call_id
    digits = payload.digits
    caller_number = payload.caller_number

    if digits is None:
        xml_res = voice_flow_controller.handle_incoming_call(call_id=call_id, caller_number=caller_number)
    else:
        xml_res = voice_flow_controller.handle_input(call_id=call_id, digits=digits, caller_number=caller_number)

    session = voice_session_store.get(call_id)
    return {
        "call_id": call_id,
        "current_step": session.current_step.value if session else "UNKNOWN",
        "language": session.language if session else "mr",
        "intent": session.intent if session else "safety",
        "location": session.location_key if session else "N/A",
        "exoml_xml": xml_res,
        "last_speech": session.last_response_text if session else "",
    }
