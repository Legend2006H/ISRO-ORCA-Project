# ORCA: Development Status & Handoff Document

This document outlines the current state of the ORCA Marine Intelligence Project to help any new developer or AI model quickly understand what has been built so far and what the architecture looks like.

## Architecture & Technology Stack
- **Frontend**: A single-page HTML application (`index.html`, `styles.css`, `app.js`). It features a modern "cyber-ocean" glassmorphism theme and uses **Leaflet** for the interactive WebGIS radar.
- **Backend**: A Python **FastAPI** backend (`api/main.py`) serving as the orchestration layer and REST API.
- **AI/LLM**: Google Gemini (`gemini_agent.py`) is used for generating human-readable, multilingual marine intelligence based on deterministic inputs.

## What Has Been Developed (Current Capabilities)

### 1. User Interface (Frontend)
- **Responsive WebGIS Dashboard**: A fully responsive mobile-friendly dashboard.
- **Interactive Map**: Leaflet map plotted with Potential Fishing Zones (PFZs), candidate zones, restricted zones, and route overlays.
- **Voice & Multilingual UI**: Speech-to-text voice input controls and language selection (English, Hindi, Marathi).
- **Vessel Profiles**: Selectable vessel profiles (Small Boat, Trawler, Deep Sea) that dynamically adjust safety wave height thresholds.
- **Evidence Ledger & Reasoning Trace**: Dedicated UI panels to display the agentic orchestration pipeline and the data provenance (timestamps, sources).

### 2. Backend Orchestration (FastAPI)
- **Data Ingestion**: Parsers for reading `.xls` PFZ data (`pfz_import.py`) and `.csv` boundary geofences (`boundary_import.py`).
- **Live Marine Engine**: A service (`live_marine.py`, `incois_osf.py`) that checks safety clearances based on vessel types and real-time/simulated wave heights and wind speeds.
- **Scoring System**: A deterministic scoring engine (`scoring.py`) that ranks fishing zones based on fishing potential, safety, and accessibility.
- **Routing**: Implementation of A* shortest path routing (`routing.py`) to calculate safe navigation corridors while avoiding restricted zones.
- **Agent Fallback System**: The `offline_service.py` manages the deterministic calculation pipeline and acts as a cached-data decision service if live fetching fails.

### 3. Known Issues & Next Steps
- **Gemini API Configuration**: The `api/gemini_agent.py` file currently contains an invalid placeholder API key (`AQ.Ab8RN6K...`). If a valid key is not provided in the environment variables, the system falls back to the deterministic offline service (which handles the logic gracefully but lacks dynamic LLM prose).
- **Package Warnings**: A lingering `~ympy` warning may appear during `pip install -r requirements.txt`. This is a local Windows Pip cache issue and can be safely ignored, as it doesn't affect the project dependencies.

## How to Run Locally
1. Install dependencies: `pip install -r requirements.txt`
2. Start the API server: `uvicorn api.main:app --reload`
3. Open a browser and navigate to `http://127.0.0.1:8000/` to access the application.
