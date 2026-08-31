from datetime import datetime
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field


class SourceMode(str, Enum):
    LIVE = "LIVE"
    CACHED = "CACHED"
    DEMO = "DEMO"


class Location(BaseModel):
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    name: str | None = None


class VesselType(str, Enum):
    SMALL_BOAT = "small_boat"
    TRAWLER = "trawler"
    DEEP_SEA = "deep_sea"


class VesselProfile(BaseModel):
    """Vessel operational configuration and safety thresholds.
    
    IMPORTANT AUDIT NOTE:
    Threshold parameters (max_wave_m, max_wind_ms, range_km) represent Category B:
    Configurable Prototype Operational Assumptions for decision-support demonstration.
    Production deployments must calibrate these parameters against authoritative maritime
    guidance (e.g. Directorate General of Shipping, IMO, INCOIS) and vessel-specific
    stability book certifications.
    """
    name: str = "Small Traditional Boat"
    vessel_type: VesselType = VesselType.SMALL_BOAT
    beam_m: float = 3.5
    cruising_speed_kmh: float = 18.0
    max_wave_m: float = 1.5
    max_wind_ms: float = 10.0
    range_km: float = 80.0


# Prototype operational profiles configured for demonstration decision support
VESSEL_PROFILES: dict[str, VesselProfile] = {
    "small_boat": VesselProfile(
        name="Small Traditional Boat",
        vessel_type=VesselType.SMALL_BOAT,
        beam_m=3.5,
        cruising_speed_kmh=18.0,
        max_wave_m=1.5,
        max_wind_ms=10.0,
        range_km=80.0,
    ),
    "trawler": VesselProfile(
        name="Motorized Mechanized Trawler",
        vessel_type=VesselType.TRAWLER,
        beam_m=5.8,
        cruising_speed_kmh=24.0,
        max_wave_m=2.5,
        max_wind_ms=15.0,
        range_km=180.0,
    ),
    "deep_sea": VesselProfile(
        name="Deep-Sea Commercial Vessel",
        vessel_type=VesselType.DEEP_SEA,
        beam_m=9.2,
        cruising_speed_kmh=32.0,
        max_wave_m=4.0,
        max_wind_ms=22.0,
        range_km=450.0,
    ),
}


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1000)
    location: Location
    language: Literal["auto", "en", "hi", "mr"] = "auto"
    session_id: str | None = None
    vessel_type: str = "small_boat"
    use_live_data: bool = False
    api_key: str | None = None


class RouteRequest(BaseModel):
    origin: Location
    destination: Location
    vessel_speed_kmh: float = 18.0


class SimulationRequest(BaseModel):
    location: Location
    vessel_type: str = "small_boat"
    simulated_wave_m: float | None = None
    simulated_wind_ms: float | None = None


class Evidence(BaseModel):
    id: str
    source: str
    parameter: str
    value: float | str
    unit: str
    location: Location
    valid_time: datetime
    issued_time: datetime
    retrieved_at: datetime
    source_mode: SourceMode
    quality: str


class ZoneCandidate(BaseModel):
    id: str
    name: str
    location: Location
    distance_km: float
    pfz_score: float = Field(ge=0, le=100)
    chlorophyll_score: float = Field(ge=0, le=100)
    sst_score: float = Field(ge=0, le=100)
    ocean_context_score: float = Field(ge=0, le=100)
    wave_safety: float = Field(ge=0, le=100)
    wind_safety: float = Field(ge=0, le=100)
    swell_safety: float = Field(ge=0, le=100)
    current_safety: float = Field(ge=0, le=100)
    hazard_clearance: float = Field(ge=0, le=100)
    accessibility_score: float = Field(ge=0, le=100)
    data_quality_score: float = Field(ge=0, le=100)
    restricted_zone: bool = False
    critical_hazard: bool = False
    evidence_ids: list[str]


class RankedZone(ZoneCandidate):
    fishing_score: float
    safety_score: float
    overall_score: float
    rank: int
    decision_status: Literal["RECOMMENDED", "SECONDARY", "BLOCKED"]
    rejected_reason: list[str] = []
