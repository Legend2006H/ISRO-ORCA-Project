"""Exotel IVR / DTMF call flow controller and ExoML XML generator for ORCA."""
from __future__ import annotations

import time
import xml.etree.ElementTree as ET
from typing import Any

from api.agents.orchestrator import OrcaOrchestrator
from api.models import Location
from .formatter import VoiceResponseFormatter
from .session import VoiceCallSession, VoiceCallStep, voice_session_store


# Supported coastal ports map for IVR selection
SUPPORTED_VOICE_LOCATIONS: dict[str, Location] = {
    "1": Location(lat=18.95, lon=72.85, name="Mumbai"),
    "2": Location(lat=16.98, lon=73.30, name="Ratnagiri"),
    "3": Location(lat=16.05, lon=73.47, name="Malvan"),
    "4": Location(lat=18.64, lon=72.87, name="Alibaug"),
    "5": Location(lat=19.97, lon=72.73, name="Dahanu"),
}

LANGUAGE_MAP: dict[str, str] = {
    "1": "mr",
    "2": "hi",
    "3": "en",
}

INTENT_MAP: dict[str, str] = {
    "1": "safety",
    "2": "nearest",
    "3": "route",
}


import re


def _clean_speech_text(text: str) -> str:
    """Sanitize spoken text for valid XML and clean speech delivery."""
    if not text:
        return ""
    # Strip non-printable control characters
    return re.sub(r"[\x00-\x08\x0B\x0C\x0E-\x1F]", "", text).strip()


class ExoMLBuilder:
    """Helper to construct valid Exotel ExoML XML responses."""

    @staticmethod
    def gather(
        action_url: str,
        say_text: str,
        num_digits: int = 1,
        timeout_seconds: int = 10,
        method: str = "POST",
    ) -> str:
        clean_text = _clean_speech_text(say_text)
        response = ET.Element("Response")
        gather = ET.SubElement(
            response,
            "Gather",
            action=action_url,
            method=method,
            numDigits=str(num_digits),
            timeout=str(timeout_seconds),
        )
        say = ET.SubElement(gather, "Say")
        say.text = clean_text
        xml_body = ET.tostring(response, encoding="utf-8", method="xml").decode("utf-8")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'

    @staticmethod
    def say_and_hangup(say_text: str) -> str:
        clean_text = _clean_speech_text(say_text)
        response = ET.Element("Response")
        say = ET.SubElement(response, "Say")
        say.text = clean_text
        ET.SubElement(response, "Hangup")
        xml_body = ET.tostring(response, encoding="utf-8", method="xml").decode("utf-8")
        return f'<?xml version="1.0" encoding="UTF-8"?>\n{xml_body}'


class ExotelVoiceFlowController:
    """Manages DTMF menu state progression and connects callers to OrcaOrchestrator."""

    def __init__(self):
        self.orchestrator = OrcaOrchestrator()

    def handle_incoming_call(self, call_id: str, caller_number: str = "anonymous") -> str:
        session = voice_session_store.get_or_create(call_id, caller_number)
        session.current_step = VoiceCallStep.LANG_SELECT
        voice_session_store.save(session)

        prompt = (
            "Welcome to ORCA Marine Safety Helpline. "
            "मराठी साठी १ दाबा. "
            "हिंदी के लिए २ दबाएँ. "
            "For English, press 3."
        )
        return ExoMLBuilder.gather(
            action_url="/api/v1/voice/input",
            say_text=prompt,
            num_digits=1,
            timeout_seconds=10,
        )

    def handle_input(self, call_id: str, digits: str, caller_number: str = "anonymous") -> str:
        session = voice_session_store.get_or_create(call_id, caller_number)
        digits = (digits or "").strip()

        # Global navigation shortcuts
        if digits == "9":
            session.current_step = VoiceCallStep.INTENT_SELECT
            voice_session_store.save(session)
            return self._build_intent_menu(session)
        elif digits == "0":
            farewell = {
                "mr": "ORCA सागरी सेवेत कॉल केल्याबद्दल धन्यवाद. आपला प्रवास सुरक्षित होवो.",
                "hi": "ORCA समुद्री सेवा में कॉल करने के लिए धन्यवाद। आपकी यात्रा सुरक्षित हो।",
                "en": "Thank you for calling ORCA Marine Helpline. Have a safe voyage.",
            }.get(session.language, "Thank you for calling ORCA. Safe voyage.")
            return ExoMLBuilder.say_and_hangup(farewell)

        if session.current_step == VoiceCallStep.LANG_SELECT:
            if digits in LANGUAGE_MAP:
                session.language = LANGUAGE_MAP[digits]
                session.current_step = VoiceCallStep.INTENT_SELECT
                voice_session_store.save(session)
                return self._build_intent_menu(session)
            else:
                prompt = "Invalid selection. मराठी साठी १ दाबा. हिंदी के लिए २ दबाएँ. For English, press 3."
                return ExoMLBuilder.gather(action_url="/api/v1/voice/input", say_text=prompt, num_digits=1)

        elif session.current_step == VoiceCallStep.INTENT_SELECT:
            if digits in INTENT_MAP:
                session.intent = INTENT_MAP[digits]
                session.current_step = VoiceCallStep.LOCATION_SELECT
                voice_session_store.save(session)
                return self._build_location_menu(session)
            else:
                return self._build_intent_menu(session, is_retry=True)

        elif session.current_step == VoiceCallStep.LOCATION_SELECT:
            if digits in SUPPORTED_VOICE_LOCATIONS:
                location = SUPPORTED_VOICE_LOCATIONS[digits]
                session.location_key = location.name or "Mumbai"
                session.current_step = VoiceCallStep.RESULT
                voice_session_store.save(session)
                return self._execute_and_format_result(session, location)
            else:
                return self._build_location_menu(session, is_retry=True)

        elif session.current_step == VoiceCallStep.RESULT:
            # Re-read result or go to main menu
            return self._build_intent_menu(session)

        return self.handle_incoming_call(call_id, caller_number)

    def _build_intent_menu(self, session: VoiceCallSession, is_retry: bool = False) -> str:
        lang = session.language
        retry_prefix = {
            "mr": "अवैध पर्याय. ",
            "hi": "अमान्य विकल्प। ",
            "en": "Invalid option. ",
        }.get(lang, "") if is_retry else ""

        if lang == "mr":
            prompt = (
                f"{retry_prefix}सागरी हवामान आणि सुरक्षेसाठी १ दाबा. "
                "जवळच्या मासेमारी क्षेत्रासाठी २ दाबा. "
                "सुरक्षित जलमार्गासाठी ३ दाबा."
            )
        elif lang == "hi":
            prompt = (
                f"{retry_prefix}समुद्री मौसम और सुरक्षा के लिए १ दबाएँ। "
                "निकटतम मत्स्य क्षेत्र के लिए २ दबाएँ। "
                "सुरक्षित नौकायन मार्ग के लिए ३ दबाएँ।"
            )
        else:  # en
            prompt = (
                f"{retry_prefix}Press 1 for Marine Weather and Safety. "
                "Press 2 for Nearest Fishing Zone. "
                "Press 3 for Safe Navigation Route."
            )

        return ExoMLBuilder.gather(
            action_url="/api/v1/voice/input",
            say_text=prompt,
            num_digits=1,
            timeout_seconds=10,
        )

    def _build_location_menu(self, session: VoiceCallSession, is_retry: bool = False) -> str:
        lang = session.language
        retry_prefix = {
            "mr": "अवैध बंदर. ",
            "hi": "अमान्य बंदरगाह। ",
            "en": "Invalid port. ",
        }.get(lang, "") if is_retry else ""

        if lang == "mr":
            prompt = (
                f"{retry_prefix}तुमचे बंदर निवडा: "
                "मुंबईसाठी १, रत्नागिरीसाठी २, मालवणसाठी ३, अलिबागसाठी ४, डहाणूसाठी ५ दाबा."
            )
        elif lang == "hi":
            prompt = (
                f"{retry_prefix}अपना बंदरगाह चुनें: "
                "मुंबई के लिए १, रत्नागिरी के लिए २, मालवण के लिए ३, अलीबाग के लिए ४, डहाणू के लिए ५ दबाएँ।"
            )
        else:  # en
            prompt = (
                f"{retry_prefix}Select your coastal port: "
                "Press 1 for Mumbai, 2 for Ratnagiri, 3 for Malvan, 4 for Alibaug, 5 for Dahanu."
            )

        return ExoMLBuilder.gather(
            action_url="/api/v1/voice/input",
            say_text=prompt,
            num_digits=1,
            timeout_seconds=10,
        )

    def _execute_and_format_result(self, session: VoiceCallSession, location: Location) -> str:
        t_start = time.perf_counter()
        port_name = location.name or "Port"
        lang = session.language

        # Construct intent-specific message to pass to OrcaOrchestrator
        if session.intent == "safety":
            message = f"Is it safe to go fishing from {port_name}?"
        elif session.intent == "nearest":
            message = f"Where is the nearest PFZ from {port_name}?"
        else:
            message = f"What is the safest route to the nearest PFZ from {port_name}?"

        # Invoke existing OrcaOrchestrator core (using same live telemetry path as web application)
        try:
            result = self.orchestrator.run(
                message=message,
                location=location,
                language=lang,
                vessel_type=session.vessel_type,
                use_live_data=True,  # Live Open-Meteo telemetry with automatic offline fallback model
            )
            session.source_mode = result.get("source_mode", "LIVE")
        except Exception as exc:
            err_msg = {
                "mr": f"क्षमस्व, {port_name} ची माहिती मिळवण्यात अडचण आली. कृपया थोड्या वेळाने प्रयत्न करा.",
                "hi": f"क्षमा करें, {port_name} की जानकारी प्राप्त करने में असमर्थ। कृपया पुनः प्रयास करें।",
                "en": f"Sorry, unable to retrieve marine data for {port_name}. Please try again later.",
            }.get(lang, "Error retrieving marine data.")
            session.last_response_text = str(exc)
            voice_session_store.record_telemetry(session, status="FAILED")
            return ExoMLBuilder.say_and_hangup(err_msg)

        # Format concise spoken message using VoiceResponseFormatter
        if session.intent == "safety":
            speech = VoiceResponseFormatter.format_safety_response(result, lang, port_name)
        elif session.intent == "nearest":
            speech = VoiceResponseFormatter.format_pfz_response(result, lang, port_name)
        else:
            speech = VoiceResponseFormatter.format_route_response(result, lang, port_name)

        nav_suffix = {
            "mr": " मुख्य मेनूसाठी ९ दाबा. कॉल समाप्त करण्यासाठी ० दाबा.",
            "hi": " मुख्य मेनू के लिए ९ दबाएँ। कॉल समाप्त करने के लिए ० दबाएँ।",
            "en": " Press 9 for Main Menu. Press 0 to end call.",
        }.get(lang, " Press 9 for Main Menu. Press 0 to end.")

        full_speech = speech + nav_suffix
        session.duration_ms = round((time.perf_counter() - t_start) * 1000, 2)
        session.last_response_text = speech
        voice_session_store.record_telemetry(session, status="SUCCESS")

        return ExoMLBuilder.gather(
            action_url="/api/v1/voice/input",
            say_text=full_speech,
            num_digits=1,
            timeout_seconds=15,
        )


voice_flow_controller = ExotelVoiceFlowController()
