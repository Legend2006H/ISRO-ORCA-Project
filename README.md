# ORCA — Marine Ecosystem Reasoning with Collaborative Agents

An SIH 2026 prototype for problem statement **SIH26176**. ORCA turns a fisherman’s question into an inspectable plan: marine data, weather, GIS/geofencing, deterministic risk scoring, ranked fishing zones, and source-linked evidence.

## What is implemented

- A polished, responsive mission-control web prototype for the Mumbai–Konkan vertical slice.
- English, Hindi, and Marathi response presentation.
- Interactive recommendation comparison, marine safety status, map layers, evidence ledger, and safe reasoning trace.
- A fully visible `CACHED` data mode, so demo values cannot be mistaken for live official advisories.
- Clear decision-support and safety caveats throughout the product.

## Run it

The prototype is a cached-data application. Install dependencies and run the API:

```text
python -m pip install -r requirements.txt
uvicorn api.main:app --reload
```

Then open `index.html` in a browser. The dashboard calls `http://127.0.0.1:8000` and analyses the supplied PFZ advisory plus cached INCOIS OSF observation.

`POST /api/v1/chat` accepts a message, location, language and optional session ID. It returns the five closest PFZ candidates, deterministic vessel-risk decision, typed evidence and an inspectable trace. It is intentionally **CACHED** decision support, never a live operational advisory.

### Cached data inputs

- Put daily PFZ `.xls` advisories in `data/raw/pfz/`; the latest file is validated and used automatically.
- Put validated ocean-observation JSON files in `data/raw/ocean/`; the latest file supplies wave, wind, swell and current values.
- Point-only boundary records remain context only. They become route-blocking only after an official source plus radius or polygon is supplied.

The default demonstration vessel is a 3.5 m beam small fishing boat with a 1.5 m wave limit, 10 m/s wind limit, 80 km range and Mumbai Harbour starting position (18.95, 72.85). The provided cache exceeds its wave limit, so ORCA correctly advises against departure.

## Production architecture

The companion documentation defines the intended production system:

`React/TypeScript → FastAPI → orchestrator → marine/weather/GIS agents → deterministic scoring/routing → PostGIS evidence store`

Production adapters must use INCOIS/MOSDAC permitted sources, attach source and timestamp metadata to every observation, and never allow an LLM to invent measurements or safety facts.

## PFZ advisory import

`api/pfz_import.py` validates the supplied Maharashtra PFZ `.xls` advisory and normalizes its candidate coordinates, bearing, offshore-distance and depth ranges. PFZ records are fishing-opportunity inputs only: they cannot produce a safety recommendation until wave, wind, current and hazard data are supplied.

## Public INCOIS OSF adapter

`api/incois_osf.py` constructs read-only, auditable requests to the public INCOIS Ocean State Forecast WMS map source for wind, significant wave height, wave period, swell height/period and surface-current speed. It uses no API key, but every fetched value still needs validation, a forecast timestamp, and an explicit `LIVE` or `CACHED` source mode before it can affect a recommendation.

The first verified live point sample is retained at `data/raw/ocean/incois_osf_mumbai_pfz_2026-08-26.json`. It is an offshore PFZ point near Mumbai, not a harbour/land coordinate.

## Boundary safety rule

The imported CZMP maps are official visual references for coastal-zone context. They are not converted to navigation prohibitions. `api/boundary_import.py` enforces that a point becomes a route-blocking geofence only when it includes a valid official source URL and an explicit boundary polygon or radius. The current source inventory is in `data/manifests/boundary_sources.json`.

## Next engineering milestones

1. Add Pydantic evidence/tool contracts and FastAPI endpoints.
2. Load a permitted PFZ/OSF cache into PostGIS and implement nearest-PFZ/geofence operations.
3. Move the displayed scoring policy to a versioned backend configuration.
4. Add golden-query regression tests, then replace the static canvas with MapLibre + attributed map tiles.
