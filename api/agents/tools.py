"""Typed deterministic domain tool wrappers for ORCA multi-agent architecture."""
from __future__ import annotations

import math
from datetime import UTC, datetime
from typing import Any, Callable
from pydantic import BaseModel, Field

from api.boundary_import import read_restricted_zones_csv
from api.live_marine import fetch_live_marine_conditions
from api.models import (
    Evidence,
    Location,
    RankedZone,
    SourceMode,
    VESSEL_PROFILES,
    VesselProfile,
    ZoneCandidate,
)
from api.routing import plan_safe_route
from api.scoring import rank_zones

from .context import OrcaExecutionContext


# --- Helper to import internal data parsers without circular imports ---
def _get_offline_service_helpers():
    from api.offline_service import (
        DATA,
        _distance_km,
        _latest_pfz,
        _ocean_cache,
        _score,
        _time,
        compute_zone_fishing_metrics,
        extract_location_from_text,
    )
    return {
        "DATA": DATA,
        "_distance_km": _distance_km,
        "_latest_pfz": _latest_pfz,
        "_ocean_cache": _ocean_cache,
        "_score": _score,
        "_time": _time,
        "compute_zone_fishing_metrics": compute_zone_fishing_metrics,
        "extract_location_from_text": extract_location_from_text,
    }


# ============================================================================
# TOOL 1: Resolve Coastal Entity
# ============================================================================
class ResolveLocationInput(BaseModel):
    query_text: str = Field(description="User query string to scan for coastal ports, harbours, or coordinates")


def tool_resolve_coastal_entity(context: OrcaExecutionContext, **kwargs) -> dict[str, Any]:
    """Extract coastal port or coordinates from user text, updating active location if found."""
    helpers = _get_offline_service_helpers()
    query_text = kwargs.get("query_text", context.user_query)
    extracted = helpers["extract_location_from_text"](query_text)

    if extracted is not None:
        # If user clicked coordinates near this named region (within ~100km / 0.9 deg), preserve exact clicked point
        if context.origin_location and context.origin_location.lat and context.origin_location.lon:
            if math.hypot(context.origin_location.lat - extracted.lat, context.origin_location.lon - extracted.lon) < 0.9:
                context.origin_location = Location(
                    lat=context.origin_location.lat,
                    lon=context.origin_location.lon,
                    name=context.origin_location.name or extracted.name,
                )
            else:
                context.origin_location = extracted
        else:
            context.origin_location = extracted
        return {"status": "RESOLVED", "location": context.origin_location.model_dump()}

    return {"status": "UNMODIFIED", "location": context.origin_location.model_dump()}


# ============================================================================
# TOOL 2: Fetch Marine & Ocean Telemetry
# ============================================================================
class FetchOceanTelemetryInput(BaseModel):
    use_live_data: bool = False


def tool_fetch_ocean_telemetry(context: OrcaExecutionContext, **kwargs) -> dict[str, Any]:
    """Retrieve live or cached sea-state observations and record typed evidence."""
    helpers = _get_offline_service_helpers()
    now = datetime.now(UTC)
    use_live = kwargs.get("use_live_data", context.use_live_data)

    if use_live:
        live_feed = fetch_live_marine_conditions(context.origin_location)
        feed_mode = live_feed.get("source_mode", "CACHED")
        context.source_mode = SourceMode.LIVE if feed_mode == "LIVE" else (SourceMode.DEMO if feed_mode == "DEMO" else SourceMode.CACHED)
        obs_list = live_feed.get("observations", [])
        context.ocean_observations = {item["parameter"]: item for item in obs_list}
        context.source_name = live_feed.get("source_name", "Open-Meteo Live Marine Feed")
        retrieved = now
        ocean_location = context.origin_location
    else:
        ocean = helpers["_ocean_cache"]()
        retrieved = helpers["_time"](ocean.get("retrieved_at"), now)
        point = ocean["location"]
        ocean_location = Location(lat=float(point["latitude"]), lon=float(point["longitude"]))
        context.ocean_observations = {item["parameter"]: item for item in ocean["observations"]}
        context.source_name = ocean.get("source_name", "INCOIS OSF cache")
        context.source_mode = SourceMode.CACHED

    # Populate evidence ledger
    for parameter, item in context.ocean_observations.items():
        quality_tag = "LIVE_FEED" if context.source_mode == SourceMode.LIVE else (
            "SIMULATION_MODEL" if context.source_mode == SourceMode.DEMO else "VALIDATED_CACHE"
        )
        context.evidence_ledger.append(Evidence(
            id=f"osf_{parameter}",
            source=context.source_name,
            parameter=parameter,
            value=item["value"],
            unit=item.get("unit", ""),
            location=ocean_location,
            valid_time=helpers["_time"](item.get("valid_time"), retrieved),
            issued_time=retrieved,
            retrieved_at=retrieved,
            source_mode=context.source_mode,
            quality=quality_tag,
        ))

    return {
        "source_mode": context.source_mode.value,
        "source_name": context.source_name,
        "observation_count": len(context.ocean_observations),
    }


# ============================================================================
# TOOL 3: Lookup PFZ Advisories
# ============================================================================
class LookupPfzInput(BaseModel):
    max_candidates: int = 5


def tool_lookup_pfz_advisory(context: OrcaExecutionContext, **kwargs) -> dict[str, Any]:
    """Ingest validated INCOIS PFZ advisory and select nearest candidates."""
    helpers = _get_offline_service_helpers()
    validity, pfz_candidates = helpers["_latest_pfz"]()
    now = datetime.now(UTC)

    # Attach PFZ advisory evidence
    context.evidence_ledger.append(Evidence(
        id="pfz_advisory",
        source="INCOIS PFZ advisory",
        parameter="pfz_validity",
        value=validity,
        unit="",
        location=context.origin_location,
        valid_time=now,
        issued_time=now,
        retrieved_at=now,
        source_mode=context.source_mode,
        quality="VALIDATED_FILE",
    ))

    # Sort closest candidates relative to origin
    closest = sorted(
        pfz_candidates,
        key=lambda item: helpers["_distance_km"](context.origin_location, Location(lat=item.latitude, lon=item.longitude))
    )[: kwargs.get("max_candidates", 5)]

    # Attach restricted boundary evidence if present
    boundary_file = helpers["DATA"] / "boundaries" / "restricted_zones.csv"
    if boundary_file.exists():
        for zone in read_restricted_zones_csv(boundary_file):
            context.evidence_ledger.append(Evidence(
                id=f"boundary_{len(context.evidence_ledger)}",
                source="ORCA boundary inventory",
                parameter="geofence_context",
                value=zone.enforcement,
                unit="",
                location=Location(lat=zone.latitude, lon=zone.longitude),
                valid_time=now,
                issued_time=now,
                retrieved_at=now,
                source_mode=SourceMode.CACHED,
                quality="CONTEXT_ONLY" if zone.enforcement == "CONTEXT_ONLY" else "OFFICIAL_BOUNDARY",
            ))

    wave = float(context.ocean_observations.get("significant_wave_height", {}).get("value", 1.4))
    wind = float(context.ocean_observations.get("wind_speed", {}).get("value", 6.0))
    swell = float(context.ocean_observations.get("swell_height", {}).get("value", 0.8))
    current = float(context.ocean_observations.get("surface_current_speed", {}).get("value", 0.2))
    vessel = context.target_vessel
    critical = wave > vessel.max_wave_m or wind > vessel.max_wind_ms

    candidates: list[ZoneCandidate] = []
    for number, item in enumerate(closest, 1):
        target = Location(lat=item.latitude, lon=item.longitude)
        distance = helpers["_distance_km"](context.origin_location, target)
        pfz_s, chloro_s, sst_s, ctx_s = helpers["compute_zone_fishing_metrics"](
            item, context.ocean_observations, context.source_mode
        )
        candidates.append(ZoneCandidate(
            id=f"pfz_{number}",
            name=f"PFZ near {item.coastal_reference}",
            location=target,
            distance_km=round(distance, 1),
            pfz_score=pfz_s,
            chlorophyll_score=chloro_s,
            sst_score=sst_s,
            ocean_context_score=ctx_s,
            wave_safety=helpers["_score"](wave, 0.8, vessel.max_wave_m),
            wind_safety=helpers["_score"](wind, 5.0, vessel.max_wind_ms),
            swell_safety=helpers["_score"](swell, 0.7, 1.5),
            current_safety=helpers["_score"](current, 0.3, 1.0),
            hazard_clearance=15 if critical else 90,
            accessibility_score=max(15, 100 - distance),
            data_quality_score=90 if context.source_mode == SourceMode.LIVE else (75 if context.source_mode == SourceMode.DEMO else 68),
            critical_hazard=critical,
            evidence_ids=[entry.id for entry in context.evidence_ledger],
        ))

    context.candidate_zones = candidates
    return {
        "validity": validity,
        "candidate_count": len(candidates),
    }


# ============================================================================
# TOOL 4: Evaluate Vessel Risk
# ============================================================================
class EvaluateVesselRiskInput(BaseModel):
    vessel_type: str | None = None


def tool_evaluate_vessel_risk(context: OrcaExecutionContext, **kwargs) -> dict[str, Any]:
    """Evaluate sea-state against vessel draft and wind speed constraints."""
    vessel_key = kwargs.get("vessel_type") or context.target_vessel.vessel_type.value
    vessel = VESSEL_PROFILES.get(vessel_key, context.target_vessel)
    context.target_vessel = vessel

    wave = float(context.ocean_observations.get("significant_wave_height", {}).get("value", 1.4))
    wind = float(context.ocean_observations.get("wind_speed", {}).get("value", 6.0))
    swell = float(context.ocean_observations.get("swell_height", {}).get("value", 0.8))
    current = float(context.ocean_observations.get("surface_current_speed", {}).get("value", 0.2))

    critical = wave > vessel.max_wave_m or wind > vessel.max_wind_ms
    departure_allowed = not critical

    reason = (
        f"Wave height ({wave:.1f} m) exceeds configured {vessel.name} limit ({vessel.max_wave_m} m)."
        if critical else f"Sea conditions are within safe limits for {vessel.name}."
    )

    context.safety_assessment = {
        "departure_allowed": departure_allowed,
        "wave_height_m": wave,
        "wind_speed_ms": wind,
        "swell_height_m": swell,
        "current_speed_ms": current,
        "reason": reason,
        "max_wave_limit_m": vessel.max_wave_m,
        "max_wind_limit_ms": vessel.max_wind_ms,
    }

    return context.safety_assessment


# ============================================================================
# TOOL 5: Check Marine Geofences
# ============================================================================
def tool_check_marine_geofences(context: OrcaExecutionContext, **kwargs) -> dict[str, Any]:
    """Verify origin and candidate proximity against restricted marine zones."""
    helpers = _get_offline_service_helpers()
    boundary_file = helpers["DATA"] / "boundaries" / "restricted_zones.csv"
    matches = []
    if boundary_file.exists():
        for zone in read_restricted_zones_csv(boundary_file):
            matches.append({
                "name": zone.name,
                "restriction_type": zone.restriction_type,
                "enforcement": zone.enforcement,
                "lat": zone.latitude,
                "lon": zone.longitude,
            })
    context.geofence_matches = matches
    return {"boundary_count": len(matches)}


# ============================================================================
# TOOL 6: Calculate Safe Route
# ============================================================================
class CalculateRouteInput(BaseModel):
    destination: Location | None = None


def tool_calculate_safe_route(context: OrcaExecutionContext, **kwargs) -> dict[str, Any]:
    """Execute A* obstacle-avoiding corridor pathfinding to target zone."""
    destination = kwargs.get("destination")
    if not destination:
        if context.ranked_zones:
            destination = context.ranked_zones[0].location
        elif context.candidate_zones:
            destination = context.candidate_zones[0].location
        else:
            destination = Location(lat=18.74, lon=72.48, name="Offshore Point")

    route_info = plan_safe_route(
        context.origin_location,
        destination,
        vessel_speed_kmh=context.target_vessel.cruising_speed_kmh,
    )
    context.navigation_route = route_info
    return {
        "distance_km": route_info["distance_km"],
        "duration_hours": route_info["estimated_duration_hours"],
        "waypoints_count": route_info["waypoints_count"],
    }


# ============================================================================
# TOOL 7: Rank Fishing Zones
# ============================================================================
def tool_rank_fishing_zones(context: OrcaExecutionContext, **kwargs) -> dict[str, Any]:
    """Apply transparent multi-factor ranking policy to candidate zones."""
    if not context.candidate_zones:
        tool_lookup_pfz_advisory(context)

    ranked = rank_zones(context.candidate_zones)
    context.ranked_zones = ranked
    top_name = ranked[0].name if ranked else "None"
    return {
        "ranked_count": len(ranked),
        "top_recommendation": top_name,
        "top_overall_score": ranked[0].overall_score if ranked else 0.0,
    }


# ============================================================================
# TOOL REGISTRY
# ============================================================================
TOOL_REGISTRY: dict[str, Callable[[OrcaExecutionContext], dict[str, Any]]] = {
    "tool_resolve_coastal_entity": tool_resolve_coastal_entity,
    "tool_fetch_ocean_telemetry": tool_fetch_ocean_telemetry,
    "tool_lookup_pfz_advisory": tool_lookup_pfz_advisory,
    "tool_evaluate_vessel_risk": tool_evaluate_vessel_risk,
    "tool_check_marine_geofences": tool_check_marine_geofences,
    "tool_calculate_safe_route": tool_calculate_safe_route,
    "tool_rank_fishing_zones": tool_rank_fishing_zones,
}
