"""Google Gemini LLM Agent integration for natural multi-turn marine reasoning."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.request
import urllib.error
from typing import Any


def load_env_file():
    """Load key-value pairs from .env file into os.environ if present."""
    root = Path(__file__).resolve().parents[1]
    env_paths = [root / ".env", Path.cwd() / ".env", root.parent / ".env"]
    for path in env_paths:
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip().strip("'\"")
                        if k:
                            os.environ[k] = v
            except Exception:
                pass


load_env_file()


def get_gemini_api_key(passed_key: str | None = None) -> str | None:
    """Retrieve active Gemini API key from parameters, env, or .env file."""
    load_env_file()
    key = (passed_key or os.getenv("GEMINI_API_KEY", "")).strip()
    if not key or "YOUR_KEY" in key or key == "YOUR_GEMINI_API_KEY":
        return None
    return key


def generate_marine_synthesis(
    user_query: str,
    language: str,
    intent: str,
    vessel_profile: dict[str, Any],
    safety_assessment: dict[str, Any],
    top_candidate: dict[str, Any],
    alternative_candidates: list[dict[str, Any]],
    worst_candidate: dict[str, Any] | None = None,
    origin_location: dict[str, Any] | None = None,
    route_info: dict[str, Any] | None = None,
    api_key: str | None = None,
) -> str | None:
    """Call Google Gemini LLM to generate natural, grounded, conversational, and typo-tolerant marine intelligence."""
    key = get_gemini_api_key(api_key)
    if not key:
        return None

    lang_names = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
    lang_name = lang_names.get(language, "English")

    models_to_try = [
        os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        "gemini-2.5-flash",
        "gemini-3.5-flash-lite",
        "gemini-3.7-flash",
        "gemini-3.1-pro-preview",
    ]
    seen_models = set()
    models = [m for m in models_to_try if m and not (m in seen_models or seen_models.add(m))]

    origin_desc = "Maharashtra Coast"
    if origin_location:
        origin_desc = f"{origin_location.get('name', 'Origin Point')} ({origin_location.get('lat', 18.95):.2f}°N, {origin_location.get('lon', 72.85):.2f}°E)"

    system_prompt = (
        "You are ORCA, an advanced, highly intelligent, and compassionate AI Marine Safety & Intelligence Assistant for coastal fishermen, maritime operators, and port officials.\n\n"
        "YOUR CORE CAPABILITIES:\n"
        "1. ROBUST TYPO & GLITCHY TEXT TOLERANCE: Fishermen and sailors often type in a rush on rocking boats, using typos, phonetic spellings, abbreviations, or broken grammar (e.g. 'whr is best spot', 'is sea dnger tmro', 'khrab zne', 'saf for sml bot', 'can i sail', 'wrost fshing zne'). ALWAYS decipher their intended meaning with high emotional intelligence and answer the real question.\n"
        "2. REAL-TIME CONVERSATIONAL LLM PROSE: Talk naturally, warmly, and helpfully like an expert assistant. Directly answer what the user asked.\n"
        "   - If they ask for the best/nearest zone: explain the recommended zone, fishing potential, distance in km, and direction.\n"
        "   - If they ask which zone is worst or riskiest: identify the lowest-rated zone, explain why its score is low or why hazards are high, and advise avoiding it.\n"
        "   - If they ask about safety, waves, wind, or weather: provide an authoritative, caring sea-state breakdown tailored to their vessel profile.\n"
        "   - If they ask a general or casual question: answer politely and explain how ORCA can guide their voyage.\n"
        "3. STRICT FACTUAL GROUNDING: Ground all numerical data (wave height, wind speed, swell, distance km, scores) strictly in the provided Operational Marine Context. Never invent fake coordinates or fake weather values.\n"
        "4. CRITICAL SAFETY: If departure is blocked (departure_allowed is false), clearly explain the hazard (e.g. wave height exceeds vessel limit) to protect the fisherman's life.\n"
        "5. CLEAN READABLE FORMAT: Do NOT output raw markdown asterisks (no '**' and no '*'). Write clean, flowing sentences or clearly styled text so it is easy to read and sounds natural when spoken aloud by text-to-speech.\n"
        f"6. LANGUAGE: Respond fluently, warmly, and naturally ONLY in {lang_name}."
    )

    context_payload = {
        "user_query": user_query,
        "query_intent": intent,
        "origin_location": origin_desc,
        "vessel_profile": vessel_profile,
        "sea_state_safety": safety_assessment,
        "recommended_best_zone": top_candidate,
        "alternative_zones": alternative_candidates[:3],
        "worst_riskiest_zone": worst_candidate,
        "route_navigation": route_info,
    }

    user_prompt = (
        f"User Query: \"{user_query}\"\n\n"
        f"Operational Marine Telemetry & GIS Context (JSON):\n{json.dumps(context_payload, indent=2)}\n\n"
        f"Please write a direct, warm, and natural response answering the user's specific query in {lang_name}."
    )

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{user_prompt}"}],
            }
        ],
        "generationConfig": {
            "temperature": 0.35,
            "maxOutputTokens": 800,
        },
    }

    for model_name in models:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={key}"
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=9) as resp:
                resp_data = json.loads(resp.read().decode("utf-8"))
                candidates = resp_data.get("candidates", [])
                if candidates:
                    parts = candidates[0].get("content", {}).get("parts", [])
                    if parts and "text" in parts[0]:
                        answer_text = parts[0]["text"].strip()
                        if answer_text:
                            return answer_text
        except urllib.error.HTTPError as err:
            err_body = err.read().decode("utf-8", errors="ignore")
            print(f"Gemini API ({model_name}) HTTP Error {err.code}: {err_body}")
            continue
        except Exception as exc:
            print(f"Gemini API ({model_name}) error: {exc}")
            continue

    return None
