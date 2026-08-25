from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from .models import ChatRequest
from .offline_service import DEFAULT_LOCATION, ROOT, analyse, detect_language

app = FastAPI(title="ORCA API", version="0.2.0", description="Evidence-first cached marine decision support")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://localhost:8000", "http://127.0.0.1:8000", "null"], allow_methods=["*"], allow_headers=["*"])
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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "source_mode": "CACHED", "default_location": DEFAULT_LOCATION.model_dump(), "warning": "Cached data only; verify official advisories before departure."}


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
        result = analyse(request.message, request.location, language)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if request.session_id:
        history = sessions.setdefault(request.session_id, [])
        history.extend(({"role": "user", "message": request.message}, {"role": "assistant", "message": result["answer"]}))
        result["conversation"] = history[-10:]
    return result
