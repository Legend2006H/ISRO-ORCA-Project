"""Compact voice response formatter for telephony and IVR interactions."""
from __future__ import annotations

from typing import Any


LOCALIZED_PORTS: dict[str, dict[str, str]] = {
    "mr": {
        "Mumbai": "मुंबई",
        "Ratnagiri": "रत्नागिरी",
        "Malvan": "मालवण",
        "Alibaug": "अलिबाग",
        "Dahanu": "डहाणू",
    },
    "hi": {
        "Mumbai": "मुंबई",
        "Ratnagiri": "रत्नागिरी",
        "Malvan": "मालवण",
        "Alibaug": "अलीबाग",
        "Dahanu": "डहाणू",
    },
    "en": {
        "Mumbai": "Mumbai",
        "Ratnagiri": "Ratnagiri",
        "Malvan": "Malvan",
        "Alibaug": "Alibaug",
        "Dahanu": "Dahanu",
    },
}


def get_provenance_prefix(source_mode: str, language: str) -> str:
    """Return concise spoken provenance tag to ensure data honesty."""
    if source_mode == "LIVE":
        return {
            "mr": "थेट उपग्रह व सागरी माहितीनुसार: ",
            "hi": "लाइव समुद्री आंकड़ों के अनुसार: ",
            "en": "Live marine telemetry: ",
        }.get(language, "")
    elif source_mode == "DEMO":
        return {
            "mr": "अंदाजित मॉडेलनुसार: ",
            "hi": "अनुमानित मॉडल के अनुसार: ",
            "en": "Fallback model advisory: ",
        }.get(language, "")
    else:  # CACHED
        return {
            "mr": "नवीनतम अधिकृत माहितीनुसार: ",
            "hi": "अद्यतन आधिकारिक आंकड़ों के अनुसार: ",
            "en": "Latest cached advisory: ",
        }.get(language, "")


class VoiceResponseFormatter:
    """Formats OrcaOrchestrator results into short, clear, multilingual voice messages."""

    @staticmethod
    def format_safety_response(result: dict[str, Any], language: str, port_name: str) -> str:
        display_port = LOCALIZED_PORTS.get(language, {}).get(port_name, port_name)
        safety = result.get("safety", {})
        source_mode = str(result.get("source_mode", "CACHED")).upper()
        prefix = get_provenance_prefix(source_mode, language)
        wave = float(safety.get("wave_height_m", 1.4))
        wind = float(safety.get("wind_speed_ms", 6.0))
        limit = float(safety.get("max_wave_limit_m", 1.5))
        departure_allowed = bool(safety.get("departure_allowed", True))

        if language == "mr":
            if not departure_allowed:
                return (
                    f"{prefix}{display_port} परिसर: गंभीर इशारा. समुद्रात जाऊ नका! "
                    f"लाटांची उंची {wave:.1f} मीटर आहे, जी {limit:.1f} मीटरच्या सुरक्षित मर्यादेपेक्षा जास्त आहे. "
                    f"वाऱ्याचा वेग {wind:.0f} मीटर प्रति सेकंद आहे."
                )
            return (
                f"{prefix}{display_port} परिसर: समुद्र सुरक्षित आहे. "
                f"लाटांची उंची {wave:.1f} मीटर आणि वाऱ्याचा वेग {wind:.0f} मीटर प्रति सेकंद आहे. "
                f"मासेमारीसाठी परिस्थिती अनुकूल आहे."
            )
        elif language == "hi":
            if not departure_allowed:
                return (
                    f"{prefix}{display_port} क्षेत्र: चेतावनी! समुद्र में न जाएँ। "
                    f"लहरों की ऊँचाई {wave:.1f} मीटर है, जो सुरक्षित सीमा {limit:.1f} मीटर से अधिक है। "
                    f"हवा की गति {wind:.0f} मीटर प्रति सेकंड है।"
                )
            return (
                f"{prefix}{display_port} क्षेत्र: समुद्र सुरक्षित है। "
                f"लहरों की ऊँचाई {wave:.1f} मीटर और हवा {wind:.0f} मीटर प्रति सेकंड है। "
                f"नौकायन की अनुमति है।"
            )
        else:  # en
            if not departure_allowed:
                return (
                    f"{prefix}{display_port} area: High Risk Alert. Do not depart! "
                    f"Wave height is {wave:.1f} metres, exceeding the safe limit of {limit:.1f} metres. "
                    f"Wind speed is {wind:.0f} metres per second."
                )
            return (
                f"{prefix}{display_port} area: Sea conditions are safe to depart. "
                f"Wave height is {wave:.1f} metres and wind speed is {wind:.0f} metres per second."
            )

    @staticmethod
    def format_pfz_response(result: dict[str, Any], language: str, port_name: str) -> str:
        display_port = LOCALIZED_PORTS.get(language, {}).get(port_name, port_name)
        source_mode = str(result.get("source_mode", "CACHED")).upper()
        prefix = get_provenance_prefix(source_mode, language)
        rec = result.get("recommendation")
        safety = result.get("safety", {})
        departure_allowed = bool(safety.get("departure_allowed", True))

        if not rec:
            if language == "mr":
                return f"{prefix}{display_port} जवळ सध्या कोणतेही अधिकृत मासेमारी क्षेत्र उपलब्ध नाही."
            elif language == "hi":
                return f"{prefix}{display_port} के पास वर्तमान में कोई संभावित मत्स्य क्षेत्र उपलब्ध नहीं है।"
            return f"{prefix}No active Potential Fishing Zone advisory available near {display_port}."

        zone_name = rec.get("name", "PFZ")
        dist = float(rec.get("distance_km", 15.0))
        score = float(rec.get("overall_score", 75.0))

        if language == "mr":
            warning_msg = " परंतु सध्या लाटा जास्त असल्याने सतर्क राहा." if not departure_allowed else ""
            return (
                f"{prefix}{display_port} पासून सर्वोत्तम मासेमारी क्षेत्र: {zone_name}. "
                f"अंतर अंदाजे {dist:.0f} किलोमीटर आहे. गुणवत्ता गुण {score:.0f} पैकी १००.{warning_msg}"
            )
        elif language == "hi":
            warning_msg = " लेकिन वर्तमान में समुद्र अशांत होने के कारण सतर्क रहें।" if not departure_allowed else ""
            return (
                f"{prefix}{display_port} से सर्वोत्तम मत्स्य क्षेत्र: {zone_name}. "
                f"दूरी लगभग {dist:.0f} किलोमीटर है। समग्र स्कोर {score:.0f} है।{warning_msg}"
            )
        else:  # en
            warning_msg = " Warning: Sea conditions are rough, proceed with caution." if not departure_allowed else ""
            return (
                f"{prefix}Top fishing zone from {display_port}: {zone_name}. "
                f"Distance is approximately {dist:.0f} kilometres with quality score {score:.0f} out of 100.{warning_msg}"
            )

    @staticmethod
    def format_route_response(result: dict[str, Any], language: str, port_name: str) -> str:
        display_port = LOCALIZED_PORTS.get(language, {}).get(port_name, port_name)
        source_mode = str(result.get("source_mode", "CACHED")).upper()
        prefix = get_provenance_prefix(source_mode, language)
        route = result.get("route")
        rec = result.get("recommendation")
        safety = result.get("safety", {})
        departure_allowed = bool(safety.get("departure_allowed", True))

        if not route:
            return VoiceResponseFormatter.format_pfz_response(result, language, port_name)

        dist = float(route.get("distance_km", 20.0))
        dur = float(route.get("estimated_duration_hours", 1.5))
        zone_name = rec.get("name", "PFZ") if rec else "लक्ष्य क्षेत्र"

        if language == "mr":
            status_msg = " चेतावणी: समुद्र धोकादायक आहे!" if not departure_allowed else " सुरक्षित मार्ग तयार आहे."
            return (
                f"{prefix}{display_port} ते {zone_name} जलमार्ग: एकूण अंतर {dist:.0f} किलोमीटर. "
                f"अंदाजे वेळ {dur:.1f} तास.{status_msg}"
            )
        elif language == "hi":
            status_msg = " चेतावनी: समुद्र में खतरा है!" if not departure_allowed else " सुरक्षित मार्ग तैयार है।"
            return (
                f"{prefix}{display_port} से {zone_name} जलमार्ग: कुल दूरी {dist:.0f} किलोमीटर. "
                f"अनुमानित समय {dur:.1f} घंटे।{status_msg}"
            )
        else:  # en
            status_msg = " Alert: High waves detected on route!" if not departure_allowed else " Safe corridor cleared."
            return (
                f"{prefix}Safe route from {display_port} to {zone_name}: Total distance {dist:.0f} kilometres, "
                f"estimated travel time {dur:.1f} hours.{status_msg}"
            )
