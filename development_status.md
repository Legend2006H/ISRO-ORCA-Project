# ORCA: Development Status & Handoff Document

This document outlines the current state of the ORCA Marine Intelligence Project to help any new developer or AI model quickly understand what has been built so far and what the architecture looks like.

## Architecture & Technology Stack
- **Frontend**: A single-page HTML application (`index.html`, `styles.css`, `app.js`). It features a clean professional "ISRO Official Hybrid" light theme with white backgrounds, ocean blue headers, saffron accent border, and rich CSS animations (card entrance, shimmer bars, scroll-reveal, micro-interactions). Uses **Leaflet** for the interactive WebGIS radar.
- **Backend**: A Python **FastAPI** backend (`api/main.py`) serving as the orchestration layer and REST API.
- **AI/LLM**: Google Gemini (`gemini_agent.py`) is used for generating human-readable, grounded multilingual marine intelligence with automatic `.env` loading and multi-model fallback (`gemini-1.5-flash`, `gemini-2.0-flash`, `gemini-1.5-pro`).

## What Has Been Developed (Current Capabilities)

### 1. User Interface (Frontend)
- **Responsive WebGIS Dashboard**: A mobile-first, responsive dashboard optimized for all screen sizes (desktop, tablet, and mobile phones down to 360px). Includes a touch-friendly collapsible glassmorphism drawer for vessel & language switching (`setupMobileMenu`), horizontal gesture scrolling for quick suggestion chips, 44px+ touch targets, iPhone-style full-width stacked score cards, responsive Leaflet map auto-resize listeners, safe area inset support, and seamless migration of desktop auxiliary cards (such as Verified Data Sources) directly into the slide-out 3-line hamburger drawer on mobile/tablet screens.
- **Adaptive Top Navigation Console**: Fluid top navbar architecture with zero text clipping, responsive breakpoint scaling ($\ge 1560\text{px}$, $1280\text{px}$, $1024\text{px}$, $768\text{px}$, $380\text{px}$), auto-collapsing center tabs into the slide-out mobile drawer, compact GPS coordinate chips, icon-only toggle buttons on medium displays, and active layer toggle synchronization across desktop and mobile.
- **Hardware-Accelerated WebGIS Radar**: Ultra-fast, lag-free Leaflet map powered by HTML5 Canvas rendering (`preferCanvas: true`), tile buffer caching, GeoJSON layer memory caching, and GPU composite transforms. Auto-centers with smooth `flyTo` animation when location changes via chat or map click, and auto-fits route bounds to ensure navigation corridors are always visible.
- **Dynamic Location & Suggestion Auto-Sync**: When a location is mentioned in chat or clicked on the map (e.g. Ratnagiri, Malvan, Mumbai, Alibaug, Harne, Murud, Devgad), the system automatically centers the radar, reverses geocodes the nearest coastal port, and dynamically updates all quick prompt suggestion chips and placeholders to that specific location.
- **Live Marine Telemetry & Real-Time Sync Bar**: Features an active live telemetry banner displaying real-time stream status, automatic live sync countdown timer ("Last synced: Just now", "10s ago"), and quick manual re-sync button with smooth rotating animation. Live Feed is enabled by default out-of-the-box.
- **Dynamic Real-Time Forecast Validity**: Automatically formats the PFZ advisory and forecast validity period dynamically according to the current live date (e.g. "FROM <Today> TO <Tomorrow>") rather than historical static dates.
- **Voice & Multilingual UI**: Speech-to-text voice input controls and language selection (English, Hindi, Marathi).
- **Vessel Profiles**: Selectable vessel profiles (Small Boat, Trawler, Deep Sea) that dynamically adjust safety wave height thresholds.
- **Cyber-Ocean Dark Mode System**: Complete Dark / Light theme system driven cleanly by `[data-theme="dark"]` and `[data-theme="light"]` attribute selectors, dynamic CartoDB Dark Matter / Voyager tile switching for Leaflet, deep marine background palette (`#070f1e`, `#0f1d32`), glowing cyan (`#38bdf8`) / amber (`#fbbf24`) / emerald (`#4ade80`) accents, high-contrast typography, localStorage preference persistence, system `prefers-color-scheme` auto-detection, and bidirectional contextual action buttons (`☀️ Light Mode` when in Dark Mode ⇄ `🌙 Dark Mode` when in Light Mode).
- **High-Tech Map Radar/Sonar Scanning HUD Animation**: Futuristic, hardware-accelerated animated HUD overlay displayed on the WebGIS radar during analysis loading. Features holographic corner brackets, 360° rotating laser sweep beam, dual-frequency expanding concentric sonar wavefront pulses, animated contact blips, targeting crosshair reticle, live scrolling coordinate/bathymetry/SST telemetry ticker (`#sonarTelemetryTicker`), and a 4-phase sequencer (`🛰️ Satellite`, `🌊 Ocean OSF`, `🧭 GIS Corridor`, `🤖 Gemini AI`) with glowing cyan/emerald progress bars.
- **Interactive ORCA Copilot AI Assistant Panel**: Fully synchronized conversational panel on the dashboard with message history, live AI responses rendered in markdown/HTML, synchronized user input (`#copilotInput`, `#copilotSendBtn`), dynamic zone metrics and live "Why this zone" verification checks, and interactive action buttons:
  - `Show on Map ➔`: Smoothly flies the Leaflet map to the recommended zone coordinate with beacon pulse animation and popup activation.
  - `Plan Safe Route`: Highlights the calculated A* safe navigation corridor avoiding reefs/CZMP geofences and fits map bounds.
  - `Check Weather`: Instantly triggers live weather, wave, swell, and wind forecast safety deliberation.
  - `Other Options`: Deliberates alternative Potential Fishing Zones and comparative rankings.
- **Map Floating Controls & Seamless Dashboard Navigation**: Added one-tap floating controls on the map card (🎯 Re-center origin, 🗂️ Toggle GIS layer overlays, ⛶ Fullscreen map mode) and seamless jump buttons to AI Recommendations, Wave Safety Alerts, Evidence Ledgers, and Marine Species cards.
- **Synchronized Multi-Card Telemetry System**: Fully synchronized Best Fishing Zone, Safety Alert, and Ocean Metrics cards with live dynamic PFZ scores, probability tags, localized marine target species, clean distance readings, vessel-specific wave limits, hazard distance, and ocean telemetry (wind speed km/h, wave height, SST, current velocity, chlorophyll). Features fluid CSS container queries and responsive grid breakpoints ensuring all 5 metric boxes remain 100% visible and beautifully formatted across all desktop and mobile viewport widths without overlapping.
- **Evidence Ledger & Reasoning Trace**: Dedicated UI panels to display the agentic orchestration pipeline and data provenance.

### 2. Backend Orchestration (FastAPI)
- **Location Entity Extraction**: Automatically extracts coastal cities and ports (Mumbai, Ratnagiri, Malvan, Alibaug, Dahanu, Murud, Harne, etc.) or explicit coordinates from user chat messages (`offline_service.py`), recalculating geodesic distances and A* routes relative to that point.
- **Context-Aware Intent & Query Deliberation**: Differentiates between requests for best zones, worst/riskiest zones to avoid, weather/safety checks, and comparative reasoning.
- **Grounded Gemini Agent**: Generates natural conversational answers tailored directly to the user's specific question using live context (candidate zones, wave/wind limits, A* route) with zero hallucination.
- **Data Ingestion**: Parsers for reading `.xls` PFZ data (`pfz_import.py`) and `.csv` boundary geofences (`boundary_import.py`).
- **Live Marine Engine**: A high-resolution live ocean telemetry service (`live_marine.py`, `incois_osf.py`) fetching real-time Open-Meteo marine streams (wave height, wave direction, swell, SST, wind speed) with resilient HTTP/HTTPS endpoints and dynamic space-time physical telemetry modeling. Automatically evaluates safety wave clearances per vessel profile (Small Boat 1.5m, Trawler 2.5m, Deep Sea 4.0m).
- **Routing & Scoring**: Multi-factor ranking (`scoring.py`) evaluating yield potential, accessibility, wave hazard clearance, and SST/Chlorophyll indicators. Fishing sub-scores (PFZ, SST, Chlorophyll proxy, Ocean Context) are dynamically computed from live/cached ocean telemetry — SST peaks at 28°C for tropical waters, chlorophyll proxy incorporates current-driven upwelling indicators, and ocean context factors in swell and current conditions. Generates smoothed Chaikin A* navigation corridors (`routing.py`) avoiding restricted CZMP zones and connecting the active vessel origin cleanly into the highlighted destination PFZ beacon.
- **Dynamic Scoring System**: A multi-factor scoring engine (`scoring.py`, `offline_service.py`) that dynamically calculates Potential Fishing Zone (PFZ) yields and sub-scores (PFZ satellite advisory clarity, Chlorophyll-a upwelling index, Sea Surface Temperature thermal fronts, and ocean dynamic convergence) based on live/cached ocean observations and candidate bathymetry.
- **Routing**: Implementation of A* shortest path routing (`routing.py`) to calculate safe navigation corridors while avoiding restricted zones.
- **Agent Fallback System**: The `offline_service.py` manages the deterministic calculation pipeline and acts as a cached-data decision service if live fetching fails.

### 3. Environment & Configuration
- **Built-in Gemini Neural Agent**: Configured to seamlessly read live host environment variables (Render / Docker / Railway via `GEMINI_API_KEY`, `GOOGLE_API_KEY`, `GEMINI_KEY`, etc.) as well as local `.env` files. Equipped with automated multi-model fallback (`gemini-2.0-flash`, `gemini-1.5-flash`, `gemini-2.5-flash`, `gemini-2.0-flash-lite`, `gemini-1.5-pro`) and default key failover. Operates out-of-the-box with zero client-side API key configuration required.

## How to Run Locally

### Option A: One-Click / Automated Script (Windows)
Double-click `run.bat` or run `.\run.bat` in terminal. It automatically checks Python, creates `venv` if missing, verifies and installs missing requirements, opens the browser, and launches Uvicorn.

### Option B: Manual Setup
1. Create venv: `python -m venv venv`
2. Activate venv: PowerShell: `./venv/Scripts/Activate.ps1` (or CMD: `venv\\Scripts\\activate.bat`)
3. Install dependencies: `pip install -r requirements.txt`
4. Configure `.env` (optional): Add `GEMINI_API_KEY=your_key_here`
5. Start the API server: `uvicorn api.main:app --reload`
6. Open a browser and navigate to `http://127.0.0.1:8000/` to access the application.
