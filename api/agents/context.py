"""Shared execution context and task data models for ORCA multi-agent orchestration."""
from __future__ import annotations

from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

from api.models import Evidence, Location, RankedZone, SourceMode, VesselProfile, ZoneCandidate


class TaskStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PlannedTask(BaseModel):
    task_id: str
    agent_role: str = Field(description="Conceptual agent role: planner, marine, hazard, geospatial, synthesis")
    tool_name: str = Field(description="Exact registered tool name")
    arguments: dict[str, Any] = Field(default_factory=dict)
    dependencies: list[str] = Field(default_factory=list, description="IDs of tasks that must finish before this runs")
    status: TaskStatus = TaskStatus.PENDING
    output: dict[str, Any] | None = None
    error: str | None = None
    duration_ms: float = 0.0


class ExecutionPlan(BaseModel):
    intent: str
    location_query: str | None = None
    vessel_type: str = "small_boat"
    tasks: list[PlannedTask] = Field(default_factory=list)
    rationale: str = "Deterministic plan"


class OrcaExecutionContext(BaseModel):
    request_id: str
    user_query: str
    detected_language: str = "en"
    query_intent: str = "recommendation"
    origin_location: Location
    target_vessel: VesselProfile
    use_live_data: bool = False
    api_key: str | None = None

    # Execution Plan
    plan: ExecutionPlan | None = None
    executed_tools: list[str] = Field(default_factory=list)

    # Domain Working Memory
    ocean_observations: dict[str, Any] = Field(default_factory=dict)
    candidate_zones: list[ZoneCandidate] = Field(default_factory=list)
    ranked_zones: list[RankedZone] = Field(default_factory=list)
    safety_assessment: dict[str, Any] = Field(default_factory=dict)
    navigation_route: dict[str, Any] | None = None
    geofence_matches: list[dict[str, Any]] = Field(default_factory=list)

    # Provenance Ledger & Trace
    evidence_ledger: list[Evidence] = Field(default_factory=list)
    operational_trace: list[str] = Field(default_factory=list)
    source_mode: SourceMode = SourceMode.CACHED
    source_name: str = "INCOIS OSF cache"

    # Synthesis Output & Performance Metrics
    final_answer: str | None = None
    ai_provider: str = "DETERMINISTIC"
    planner_provider: str = "DETERMINISTIC RULE PLANNER"
    planner_duration_ms: float = 0.0
    synthesis_duration_ms: float = 0.0
    gemini_calls_count: int = 0
    execution_duration_ms: float = 0.0
