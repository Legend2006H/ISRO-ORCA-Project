from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .live_marine import fetch_live_marine_conditions
from .models import ChatRequest, Location, RouteRequest, VESSEL_PROFILES
from .offline_service import (
    DEFAULT_LOCATION,
    ROOT,
    analyse,
    detect_language,
    get_all_boundaries_geojson,
    get_all_pfz_geojson,
)
from .routing import plan_safe_route

from .gemini_agent import get_gemini_api_key, load_env_file

load_env_file()

app = FastAPI(title="ORCA API", version="2.0.0", description="Production-grade AI Marine Intelligence Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    )
sessions: dict[str, list[dict[str, str]]] = {}


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve the local dashboard from the same origin as the API."""
    return FileResponse(ROOT / "index.html")


@app.get("/styles.css", include_in_schema=False)
def styles() -> FileResponse:
    return FileResponse(ROOT / "styles.css", media_type="text/css")


@app.get("/app.js", include_in_schema=False)
def script() -> FileResponse:
    return FileResponse(ROOT / "app.js", media_type="text/javascript")


@app.get("/runtime.css", include_in_schema=False)
def runtime_styles() -> FileResponse:
    return FileResponse(ROOT / "runtime.css", media_type="text/css")


@app.get("/health")
def health() -> dict:
    has_gemini = bool(get_gemini_api_key())
    return {
        "status": "ok",
        "system": "ORCA Marine Intelligence Platform",
        "version": "2.0.0",
        "source_mode": "CACHED",
        "gemini_configured": has_gemini,
        "default_location": DEFAULT_LOCATION.model_dump(),
        "available_vessels": list(VESSEL_PROFILES.keys()),
        "warning": "Cached data only; verify official advisories before departure.",
    }


@app.get("/api/v1/vessels")
def get_vessels() -> dict:
    return {k: v.model_dump() for k, v in VESSEL_PROFILES.items()}


@app.get("/api/v1/pfz/all")
def get_all_pfz() -> dict:
    return get_all_pfz_geojson()


@app.get("/api/v1/boundaries/all")
def get_all_boundaries() -> dict:
    return get_all_boundaries_geojson()


@app.get("/api/v1/ocean/live")
def get_live_ocean(lat: float = 18.95, lon: float = 72.85) -> dict:
    loc = Location(lat=lat, lon=lon)
    return fetch_live_marine_conditions(loc)


@app.post("/api/v1/route")
def calculate_route(request: RouteRequest) -> dict:
    return plan_safe_route(request.origin, request.destination, request.vessel_speed_kmh)


@app.get("/api/v1/evidence/{evidence_id}")
def get_evidence(evidence_id: str) -> dict:
    try:
        result = analyse("show evidence", DEFAULT_LOCATION, "en")
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    for item in result["evidence"]:
        if item["id"] == evidence_id:
            return item
    raise HTTPException(status_code=404, detail="Evidence item not found")


@app.post("/api/v1/chat")
def chat(request: ChatRequest) -> dict:
    language = detect_language(request.message, request.language)
    try:
        result = analyse(
            message=request.message,
            location=request.location,
            language=language,
            vessel_type=request.vessel_type,
            use_live_data=request.use_live_data,
            api_key=request.api_key,
        )
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if request.session_id:
        history = sessions.setdefault(request.session_id, [])
        history.extend(({"role": "user", "message": request.message}, {"role": "assistant", "message": result["answer"]}))
        result["conversation"] = history[-10:]
    return result
