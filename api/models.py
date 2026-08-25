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


class ChatRequest(BaseModel):
    message: str = Field(min_length=2, max_length=1000)
    location: Location
    language: Literal["auto", "en", "hi", "mr"] = "auto"
    session_id: str | None = None


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
