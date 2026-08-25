"""Google Gemini LLM Agent integration for natural multi-turn marine reasoning."""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Any

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "AQ.Ab8RN6K1gCJhxQFkjHNUw1fSADsDtL9rGg4DealdowIYB6mqDg")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


def generate_marine_synthesis(
    user_query: str,
    language: str,
    intent: str,
    vessel_profile: dict[str, Any],
    safety_assessment: dict[str, Any],
    top_candidate: dict[str, Any],
    alternative_candidates: list[dict[str, Any]],
    route_info: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> str | None:
    """Call Google Gemini to generate natural, grounded, multilingual marine intelligence."""
    key = api_key or os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    if not key or "YOUR_KEY" in key:
        return None

    lang_names = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
    lang_name = lang_names.get(language, "English")

    system_prompt = (
        "You are ORCA, an advanced ISRO/INCOIS Marine Intelligence Decision Support AI Assistant.\n"
        "Your job is to provide clear, actionable, safety-first advice to fishermen, vessel captains, and maritime operators.\n\n"
        "STRICT GROUNDING RULES:\n"
        "1. Strictly ground all facts in the provided operational data. NEVER invent wave heights, wind speeds, or coordinates.\n"
        "2. If safety departure is blocked (departure_allowed is false), ALWAYS prioritize the warning and state the exact wave/wind limits.\n"
        "3. Provide concise, respectful, and authoritative responses in 2-3 sentences.\n"
        f"4. Output your entire response ONLY in {lang_name}.\n"
    )

    context_payload = {
        "vessel": vessel_profile,
        "safety_assessment": safety_assessment,
        "recommended_zone": top_candidate,
        "alternative_zones": alternative_candidates[:2],
        "route": route_info,
    }

    user_prompt = (
        f"User Query: {user_query}\n"
        f"Detected Intent: {intent}\n"
        f"Operational Marine Context (JSON):\n{json.dumps(context_payload, indent=2)}\n\n"
        f"Please provide a synthesized, direct answer in {lang_name}. Highlight the recommended zone name, distance in km, and safety status."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}]
            }
        ],
        "generationConfig": {
            "temperature": 0.2,
            "maxOutputTokens": 300,
        }
    }

    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={key}"
    try:
        req = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            resp_data = json.loads(resp.read().decode("utf-8"))
            candidates = resp_data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip()
    except Exception as exc:
        print(f"Gemini API call fallback to deterministic agent: {exc}")
        return None

    return None
