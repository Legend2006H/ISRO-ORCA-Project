# ORCA: Development Status & Handoff Document

This document outlines the current state of the ORCA Marine Intelligence Project to help any new developer or AI model quickly understand what has been built so far and what the architecture looks like.

## Architecture & Technology Stack
- **Frontend**: A single-page HTML application (`index.html`, `styles.css`, `app.js`). It features a modern "cyber-ocean" glassmorphism theme and uses **Leaflet** for the interactive WebGIS radar.
- **Backend**: A Python **FastAPI** backend (`api/main.py`) serving as the orchestration layer and REST API.
- **AI/LLM**: Google Gemini (`gemini_agent.py`) is used for generating human-readable, grounded multilingual marine intelligence with automatic `.env` loading and multi-model fallback (`gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`).

## What Has Been Developed (Current Capabilities)

### 1. User Interface (Frontend)
- **Responsive WebGIS Dashboard**: A fully responsive mobile-friendly dashboard.
- **Hardware-Accelerated WebGIS Radar**: Ultra-fast, lag-free Leaflet map powered by HTML5 Canvas rendering (`preferCanvas: true`), tile buffer caching, GeoJSON layer memory caching, and GPU composite transforms. Auto-centers with smooth `flyTo` animation when location changes via chat or map click, and auto-fits route bounds to ensure navigation corridors are always visible.
- **Dynamic Location & Suggestion Auto-Sync**: When a location is mentioned in chat or clicked on the map (e.g. Ratnagiri, Malvan, Mumbai, Alibaug, Harne, Murud, Devgad), the system automatically centers the radar, reverses geocodes the nearest coastal port, and dynamically updates all quick prompt suggestion chips and placeholders to that specific location.
- **Voice & Multilingual UI**: Speech-to-text voice input controls and language selection (English, Hindi, Marathi).
- **Vessel Profiles**: Selectable vessel profiles (Small Boat, Trawler, Deep Sea) that dynamically adjust safety wave height thresholds.
- **Evidence Ledger & Reasoning Trace**: Dedicated UI panels to display the agentic orchestration pipeline and data provenance.

### 2. Backend Orchestration (FastAPI)
- **Location Entity Extraction**: Automatically extracts coastal cities and ports (Mumbai, Ratnagiri, Malvan, Alibaug, Dahanu, Murud, Harne, etc.) or explicit coordinates from user chat messages (`offline_service.py`), recalculating geodesic distances and A* routes relative to that point.
- **Context-Aware Intent & Query Deliberation**: Differentiates between requests for best zones, worst/riskiest zones to avoid, weather/safety checks, and comparative reasoning.
- **Grounded Gemini Agent**: Generates natural conversational answers tailored directly to the user's specific question using live context (candidate zones, wave/wind limits, A* route) with zero hallucination.
- **Data Ingestion**: Parsers for reading `.xls` PFZ data (`pfz_import.py`) and `.csv` boundary geofences (`boundary_import.py`).
- **Live Marine Engine**: A service (`live_marine.py`, `incois_osf.py`) checking safety clearances based on vessel types and real-time/simulated wave heights and wind speeds.
- **Routing & Scoring**: Multi-factor ranking (`scoring.py`) evaluating yield potential, accessibility, wave hazard clearance, and SST/Chlorophyll indicators. Fishing sub-scores (PFZ, SST, Chlorophyll proxy, Ocean Context) are dynamically computed from live/cached ocean telemetry — SST peaks at 28°C for tropical waters, chlorophyll proxy incorporates current-driven upwelling indicators, and ocean context factors in swell and current conditions. Generates smoothed Chaikin A* navigation corridors (`routing.py`) avoiding restricted CZMP zones and connecting the active vessel origin cleanly into the highlighted destination PFZ beacon.
- **Dynamic Scoring System**: A multi-factor scoring engine (`scoring.py`, `offline_service.py`) that dynamically calculates Potential Fishing Zone (PFZ) yields and sub-scores (PFZ satellite advisory clarity, Chlorophyll-a upwelling index, Sea Surface Temperature thermal fronts, and ocean dynamic convergence) based on live/cached ocean observations and candidate bathymetry.
- **Routing**: Implementation of A* shortest path routing (`routing.py`) to calculate safe navigation corridors while avoiding restricted zones.
- **Agent Fallback System**: The `offline_service.py` manages the deterministic calculation pipeline and acts as a cached-data decision service if live fetching fails.

### 3. Environment & Configuration
- **Gemini API Key Setup**: Reads `GEMINI_API_KEY` from `.env`, system environment, or directly from the in-app `🔑 Gemini AI` configuration modal (stored locally in browser). When enabled, it provides real-time conversational LLM reasoning that gracefully interprets typos, broken grammar, phonetic phrasing, and glitchy inputs. If no key is configured, it falls back to an intelligent query-responsive offline engine.

## How to Run Locally
1. Install dependencies: `pip install -r requirements.txt`
2. Configure `.env` (optional): Add `GEMINI_API_KEY=your_key_here`
3. Start the API server: `uvicorn api.main:app --reload`
4. Open a browser and navigate to `http://127.0.0.1:8000/` to access the application.
