"""Google Gemini LLM Agent integration for natural multi-turn marine reasoning."""
from __future__ import annotations

import json
import os
from pathlib import Path
import urllib.request
import urllib.error
from typing import Any


def load_env_file():
    """Load key-value pairs from .env file into os.environ if present, without overwriting live host env vars."""
    root = Path(__file__).resolve().parents[1]
    env_paths = [root / ".env", Path.cwd() / ".env", root.parent / ".env"]
    for path in env_paths:
        if path.exists():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"").strip()
                        # Do not overwrite live environment variables already injected by Render / host OS
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


load_env_file()


def get_gemini_api_key(passed_key: str | None = None) -> str | None:
    """Retrieve active Gemini API key from parameters, live environment (Render/Docker), or .env file."""
    load_env_file()
    candidate = (passed_key or "").strip().strip("'\"").strip()
    if candidate and not ("YOUR_KEY" in candidate or candidate == "YOUR_GEMINI_API_KEY"):
        return candidate

    # Check common environment variable aliases used in Render, Docker, and cloud hosting
    for var_name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GEMINI_API_KEY", "GEMINI_KEY", "API_KEY"):
        env_val = os.getenv(var_name, "").strip().strip("'\"").strip()
        if env_val and not ("YOUR_KEY" in env_val or env_val == "YOUR_GEMINI_API_KEY"):
            return env_val

    return None


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
    primary_key = get_gemini_api_key(api_key)

    lang_names = {"en": "English", "hi": "Hindi", "mr": "Marathi"}
    lang_name = lang_names.get(language, "English")

    # Production-tested Google Gemini models available on Generative Language API
    models_to_try = [
        os.getenv("GEMINI_MODEL", "").strip(),
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]
    seen_models: set = set()
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
            "temperature": 0.3,
            "maxOutputTokens": 600,
        },
    }

    if not primary_key:
        return None

    for model_name in models:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={primary_key}"
        try:
            req = urllib.request.Request(
                endpoint,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
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


def generate_structured_plan(
    user_query: str,
    active_vessel: str = "small_boat",
    api_key: str | None = None,
) -> dict[str, Any] | None:
    """Invoke Google Gemini to produce a bounded, structured task execution plan in JSON."""
    primary_key = get_gemini_api_key(api_key)
    if not primary_key:
        return None

    models_to_try = [
        os.getenv("GEMINI_MODEL", "").strip(),
        "gemini-2.0-flash",
        "gemini-1.5-flash",
        "gemini-2.5-flash",
        "gemini-2.0-flash-lite",
        "gemini-1.5-pro",
        "gemini-3.5-flash-lite",
        "gemini-3.1-flash-lite",
    ]
    seen_models: set = set()
    models = [m for m in models_to_try if m and not (m in seen_models or seen_models.add(m))]

    system_prompt = (
        "You are the ORCA Multi-Agent Task Planner for marine safety and navigation.\n"
        "Your role is to analyze the user's maritime query and construct a bounded Directed Acyclic Graph (DAG) of tasks.\n\n"
        "WHITELISTED REGISTERED TOOLS:\n"
        "- tool_resolve_coastal_entity: Extracts coastal ports, harbours, or coordinates from query text. (arguments: {'query_text': string})\n"
        "- tool_fetch_ocean_telemetry: Retrieves wave, wind, swell, and SST observations. (arguments: {'use_live_data': boolean})\n"
        "- tool_evaluate_vessel_risk: Evaluates wave & wind limits against the vessel's threshold. (arguments: {'vessel_type': string})\n"
        "- tool_lookup_pfz_advisory: Parses validated INCOIS Potential Fishing Zone advisories. (arguments: {'max_candidates': integer})\n"
        "- tool_check_marine_geofences: Evaluates proximity to restricted CZMP marine zones. (arguments: {})\n"
        "- tool_calculate_safe_route: Computes obstacle-avoiding A* navigation route to top zone. (arguments: {})\n"
        "- tool_rank_fishing_zones: Calculates multi-factor pelagic fishing scores for zones. (arguments: {})\n\n"
        "STRICT PLANNING RULES:\n"
        "1. Max 6 tasks total (MAX_TASKS = 6).\n"
        "2. ONLY use tools from the whitelist above. Never invent tool names.\n"
        "3. SELECT ONLY NECESSARY TOOLS based on intent:\n"
        "   - If the user asks only about sea conditions/safety/weather, DO NOT include PFZ ranking or routing tools.\n"
        "   - If the user asks about worst/avoidance zones or comparison, include ranking but DO NOT include routing.\n"
        "   - If the user asks for fishing recommendations, route, or nearest PFZ, include PFZ, ranking, and routing.\n"
        "4. DEPENDENCY ORDERING: Ensure tools that depend on previous outputs list their task_ids in 'dependencies' (e.g. task_2 depends on task_1, task_5 depends on task_3 and task_4). No cyclic dependencies.\n"
        "5. INTENT CLASSIFICATION: Classify intent into one of: 'safety', 'recommendation', 'worst', 'comparison', 'nearest', 'route'.\n"
        "6. STRICT JSON ONLY: Return ONLY a raw valid JSON object with NO markdown formatting, NO backticks, NO explanation."
    )

    schema_instruction = """
Output JSON Schema:
{
  "intent": "safety" | "recommendation" | "worst" | "comparison" | "nearest" | "route",
  "location_query": "Ratnagiri" or null,
  "vessel_type": "small_boat" | "trawler" | "deep_sea",
  "tasks": [
    {
      "task_id": "task_1",
      "agent_role": "planner" | "marine" | "hazard" | "geospatial",
      "tool_name": "tool_resolve_coastal_entity",
      "arguments": {"query_text": "user query"},
      "dependencies": []
    }
  ],
  "rationale": "Short explanation of DAG"
}
"""

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": f"{system_prompt}\n\n{schema_instruction}\n\nUser Query: \"{user_query}\"\nActive Vessel: \"{active_vessel}\"\n\nGenerate the JSON Execution Plan:"}],
            }
        ],
        "generationConfig": {
            "temperature": 0.1,
            "maxOutputTokens": 600,
            "responseMimeType": "application/json",
        },
    }

    for model_name in models:
        endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={primary_key}"
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
                        raw_text = parts[0]["text"].strip()
                        # Strip markdown backticks if wrapped
                        if raw_text.startswith("```json"):
                            raw_text = raw_text[7:]
                        if raw_text.startswith("```"):
                            raw_text = raw_text[3:]
                        if raw_text.endswith("```"):
                            raw_text = raw_text[:-3]
                        raw_text = raw_text.strip()
                        return json.loads(raw_text)
        except Exception as exc:
            # Fall through to deterministic planner
            continue

    return None
