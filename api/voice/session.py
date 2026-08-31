"""In-memory voice call session manager with TTL expiration for ORCA IVR."""
from __future__ import annotations

import threading
import time
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


def mask_phone_number(phone: str | None) -> str:
    """Mask caller phone number for privacy: e.g. +919876543210 -> +91******3210."""
    if not phone or phone == "anonymous":
        return "anonymous"
    clean = phone.strip()
    if len(clean) >= 7:
        return clean[:3] + "*" * (len(clean) - 7) + clean[-4:]
    return "***"


class VoiceCallStep(str, Enum):
    LANG_SELECT = "LANG_SELECT"
    INTENT_SELECT = "INTENT_SELECT"
    LOCATION_SELECT = "LOCATION_SELECT"
    RESULT = "RESULT"


class VoiceCallSession(BaseModel):
    call_id: str
    caller_number: str = "anonymous"
    language: str = "mr"  # default Marathi for coastal Maharashtra / Konkan
    intent: str = "safety"
    location_key: str = "ratnagiri"
    vessel_type: str = "small_boat"
    current_step: VoiceCallStep = VoiceCallStep.LANG_SELECT
    created_at: float = Field(default_factory=time.time)
    expires_at: float = Field(default_factory=lambda: time.time() + 300.0)  # 5 minutes TTL
    last_response_text: str = ""
    last_action_input: str = ""
    source_mode: str = "CACHED"
    duration_ms: float = 0.0

    def is_expired(self) -> bool:
        return time.time() > self.expires_at

    def refresh(self, ttl_seconds: float = 300.0) -> None:
        self.expires_at = time.time() + ttl_seconds


class VoiceSessionStore:
    """Thread-safe in-memory session store for Exotel telephony interactions."""

    def __init__(self, default_ttl_seconds: float = 300.0):
        self._sessions: dict[str, VoiceCallSession] = {}
        self._lock = threading.Lock()
        self._default_ttl = default_ttl_seconds
        self._telemetry_log: list[dict[str, Any]] = []

    def get_or_create(self, call_id: str, caller_number: str = "anonymous") -> VoiceCallSession:
        masked_number = mask_phone_number(caller_number)
        with self._lock:
            self._cleanup_expired()
            session = self._sessions.get(call_id)
            if not session or session.is_expired():
                session = VoiceCallSession(
                    call_id=call_id,
                    caller_number=masked_number,
                    expires_at=time.time() + self._default_ttl,
                )
                self._sessions[call_id] = session
            else:
                session.refresh(self._default_ttl)
            return session

    def get(self, call_id: str) -> VoiceCallSession | None:
        with self._lock:
            self._cleanup_expired()
            session = self._sessions.get(call_id)
            if session and not session.is_expired():
                session.refresh(self._default_ttl)
                return session
            return None

    def save(self, session: VoiceCallSession) -> None:
        with self._lock:
            self._sessions[session.call_id] = session

    def record_telemetry(self, session: VoiceCallSession, status: str = "SUCCESS") -> None:
        with self._lock:
            entry = {
                "voice_session_id": session.call_id,
                "intent": session.intent,
                "language": session.language,
                "location": session.location_key,
                "decision": session.last_response_text[:80] if session.last_response_text else "N/A",
                "duration_ms": session.duration_ms,
                "source_mode": session.source_mode,
                "status": status,
                "timestamp": time.time(),
            }
            self._telemetry_log.append(entry)
            if len(self._telemetry_log) > 50:
                self._telemetry_log = self._telemetry_log[-50:]

    def get_telemetry(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._telemetry_log)

    def _cleanup_expired(self) -> None:
        now = time.time()
        expired_keys = [k for k, v in self._sessions.items() if v.expires_at < now]
        for k in expired_keys:
            del self._sessions[k]


# Global singleton session store
voice_session_store = VoiceSessionStore()
