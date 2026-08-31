"""Bounded multi-agent orchestrator for ORCA Marine Intelligence Platform."""
from __future__ import annotations

import time
import uuid
from typing import Any

from api.gemini_agent import generate_marine_synthesis, generate_structured_plan, get_gemini_api_key
from api.models import (
    Location,
    RankedZone,
    SourceMode,
    VESSEL_PROFILES,
    VesselProfile,
    ZoneCandidate,
)
from api.offline_service import (
    DEFAULT_LOCATION,
    _answer,
    detect_intent,
    detect_language,
)

from .context import ExecutionPlan, OrcaExecutionContext, PlannedTask, TaskStatus
from .tools import TOOL_REGISTRY


MAX_TASKS = 6
MAX_TOOL_CALLS = 8


def _has_cycles(tasks: list[PlannedTask]) -> bool:
    """Detect if a task DAG has cyclic dependencies using graph coloring (DFS)."""
    adj: dict[str, list[str]] = {t.task_id: list(t.dependencies) for t in tasks}
    visited: dict[str, int] = {}  # 0=unvisited, 1=visiting (in stack), 2=visited

    def dfs(node: str) -> bool:
        visited[node] = 1
        for neighbor in adj.get(node, []):
            if neighbor in adj:
                if visited.get(neighbor, 0) == 1:
                    return True
                if visited.get(neighbor, 0) == 0:
                    if dfs(neighbor):
                        return True
        visited[node] = 2
        return False

    for task in tasks:
        if visited.get(task.task_id, 0) == 0:
            if dfs(task.task_id):
                return True
    return False


class OrcaOrchestrator:
    """Coordinates specialized agent roles over typed deterministic domain tools."""

    def __init__(self):
        self.tool_registry = TOOL_REGISTRY

    def plan_deterministic(
        self,
        query: str,
        intent: str,
        vessel_type: str = "small_boat",
    ) -> ExecutionPlan:
        """Formulate a bounded, intent-specific task DAG using deterministic policy templates."""
        tasks: list[PlannedTask] = []

        # Task 1 is always entity resolution
        tasks.append(PlannedTask(
            task_id="task_1",
            agent_role="planner",
            tool_name="tool_resolve_coastal_entity",
            arguments={"query_text": query},
        ))

        # Task 2 is ocean condition retrieval
        tasks.append(PlannedTask(
            task_id="task_2",
            agent_role="hazard",
            tool_name="tool_fetch_ocean_telemetry",
            dependencies=["task_1"],
        ))

        # Task 3 is vessel risk evaluation
        tasks.append(PlannedTask(
            task_id="task_3",
            agent_role="hazard",
            tool_name="tool_evaluate_vessel_risk",
            arguments={"vessel_type": vessel_type},
            dependencies=["task_2"],
        ))

        if intent == "safety":
            # Weather / Safety assessment does not require PFZ or A* routing
            return ExecutionPlan(
                intent=intent,
                vessel_type=vessel_type,
                tasks=tasks[:MAX_TASKS],
                rationale="Safety-only execution template: bypassed PFZ and routing tools",
            )

        # Task 4 is PFZ lookup
        tasks.append(PlannedTask(
            task_id="task_4",
            agent_role="marine",
            tool_name="tool_lookup_pfz_advisory",
            dependencies=["task_2"],
        ))

        # Task 5 is ranking
        tasks.append(PlannedTask(
            task_id="task_5",
            agent_role="marine",
            tool_name="tool_rank_fishing_zones",
            dependencies=["task_3", "task_4"],
        ))

        if intent in ("worst", "comparison"):
            # Avoidance or comparison queries do not require primary corridor pathfinding
            return ExecutionPlan(
                intent=intent,
                vessel_type=vessel_type,
                tasks=tasks[:MAX_TASKS],
                rationale=f"Intent '{intent}' template: calculated ranking, bypassed routing tool",
            )

        # Task 6 is route planning to top recommendation
        tasks.append(PlannedTask(
            task_id="task_6",
            agent_role="geospatial",
            tool_name="tool_calculate_safe_route",
            dependencies=["task_5"],
        ))

        return ExecutionPlan(
            intent=intent,
            vessel_type=vessel_type,
            tasks=tasks[:MAX_TASKS],
            rationale="Full zone recommendation and navigational corridor template",
        )

    def plan(
        self,
        query: str,
        intent: str,
        vessel_type: str = "small_boat",
        api_key: str | None = None,
    ) -> tuple[ExecutionPlan, str, float, int]:
        """Formulate an execution plan using Gemini Neural Planner with seamless Deterministic Fallback."""
        t_start = time.perf_counter()
        gemini_calls = 0

        if api_key:
            try:
                gemini_calls += 1
                raw_plan = generate_structured_plan(query, active_vessel=vessel_type, api_key=api_key)
                if raw_plan and isinstance(raw_plan, dict):
                    plan = ExecutionPlan.model_validate(raw_plan)
                    # Validate task limits
                    if 0 < len(plan.tasks) <= MAX_TASKS:
                        # Validate tool whitelist
                        all_whitelisted = all(t.tool_name in self.tool_registry for t in plan.tasks)
                        # Validate cycle-free DAG
                        no_cycles = not _has_cycles(plan.tasks)
                        if all_whitelisted and no_cycles:
                            duration = round((time.perf_counter() - t_start) * 1000, 2)
                            return plan, "GEMINI NEURAL PLANNER", duration, gemini_calls
            except Exception:
                pass

        # Deterministic Fallback Planner
        det_plan = self.plan_deterministic(query, intent, vessel_type=vessel_type)
        duration = round((time.perf_counter() - t_start) * 1000, 2)
        return det_plan, "DETERMINISTIC RULE PLANNER", duration, gemini_calls

    def dispatch_plan(self, context: OrcaExecutionContext, plan: ExecutionPlan) -> None:
        """Execute the planned task DAG sequentially while respecting dependency ordering and limits."""
        context.plan = plan
        executed_count = 0

        trace = [
            f"Planner: [{context.planner_provider}] parsed intent '{context.query_intent}' for reference '{context.origin_location.name or 'Origin'}' ({context.origin_location.lat:.2f}°N, {context.origin_location.lon:.2f}°E) with vessel '{context.target_vessel.name}'. Plan rationale: {plan.rationale}",
        ]

        completed_tasks: set[str] = set()

        for task in plan.tasks:
            if executed_count >= MAX_TOOL_CALLS:
                task.status = TaskStatus.SKIPPED
                task.error = "Max tool call limit reached"
                continue

            # Check dependencies
            if any(dep not in completed_tasks for dep in task.dependencies):
                task.status = TaskStatus.SKIPPED
                task.error = "Unmet task dependencies"
                continue

            # Verify tool is registered
            if task.tool_name not in self.tool_registry:
                task.status = TaskStatus.FAILED
                task.error = f"Unknown tool: {task.tool_name}"
                trace.append(f"Tool Dispatcher: rejected unregistered tool '{task.tool_name}'.")
                continue

            tool_fn = self.tool_registry[task.tool_name]
            task.status = TaskStatus.RUNNING
            t_start = time.perf_counter()

            try:
                out = tool_fn(context, **task.arguments)
                task.output = out
                task.status = TaskStatus.COMPLETED
                completed_tasks.add(task.task_id)
                context.executed_tools.append(task.tool_name)
                executed_count += 1
            except Exception as exc:
                task.status = TaskStatus.FAILED
                task.error = str(exc)
                trace.append(f"Tool Failure [{task.tool_name}]: {exc}")
                continue
            finally:
                task.duration_ms = round((time.perf_counter() - t_start) * 1000, 2)

            # Generate specific operational trace messages based on completed tool
            if task.tool_name == "tool_fetch_ocean_telemetry":
                wave = float(context.ocean_observations.get("significant_wave_height", {}).get("value", 1.4))
                wind = float(context.ocean_observations.get("wind_speed", {}).get("value", 6.0))
                swell = float(context.ocean_observations.get("swell_height", {}).get("value", 0.8))
                trace.append(
                    f"Marine data agent: retrieved {context.source_mode.value} conditions (wave: {wave:.1f} m, wind: {wind:.1f} m/s, swell: {swell:.1f} m)."
                )
            elif task.tool_name == "tool_lookup_pfz_advisory":
                trace.append(
                    f"PFZ agent: loaded validated PFZ advisory ({len(context.candidate_zones)} candidate zones along Maharashtra/Konkan/Goa coast)."
                )
            elif task.tool_name == "tool_evaluate_vessel_risk":
                critical = not context.safety_assessment.get("departure_allowed", True)
                wave = float(context.safety_assessment.get("wave_height_m", 1.4))
                limit = context.target_vessel.max_wave_m
                status_str = "BLOCKED (HIGH RISK)" if critical else "SAFE TO DEPART"
                trace.append(f"Risk engine: compared wave height ({wave:.1f} m) with vessel limit ({limit} m) -> {status_str}.")
            elif task.tool_name == "tool_calculate_safe_route" and context.navigation_route:
                dist = context.navigation_route.get("distance_km", 0)
                dur = context.navigation_route.get("estimated_duration_hours", 0)
                trace.append(f"Route engine: computed {dist} km safe A* route ({dur} hrs cruising).")

        trace.append(f"Recommendation agent: synthesized {context.query_intent} decision with typed evidence ledger.")
        context.operational_trace = trace

    def apply_safety_gate(self, context: OrcaExecutionContext) -> None:
        """Safety gate: hard enforcement of vessel safety limits over fishing scores."""
        wave = float(context.ocean_observations.get("significant_wave_height", {}).get("value", 1.4))
        wind = float(context.ocean_observations.get("wind_speed", {}).get("value", 6.0))
        critical = wave > context.target_vessel.max_wave_m or wind > context.target_vessel.max_wind_ms

        if critical:
            context.safety_assessment["departure_allowed"] = False
            for zone in context.ranked_zones:
                if "critical hazard advisory" not in zone.rejected_reason:
                    zone.rejected_reason.append("critical hazard advisory")

    def synthesize_response(self, context: OrcaExecutionContext) -> str:
        """Call Gemini synthesis with verified structured context, falling back to deterministic templates."""
        t_start = time.perf_counter()
        top_cand = context.ranked_zones[0] if context.ranked_zones else None
        alt_cands = context.ranked_zones[1:] if len(context.ranked_zones) > 1 else []
        worst_cand = context.ranked_zones[-1] if context.ranked_zones else None

        wave = float(context.ocean_observations.get("significant_wave_height", {}).get("value", 1.4))
        wind = float(context.ocean_observations.get("wind_speed", {}).get("value", 6.0))
        swell = float(context.ocean_observations.get("swell_height", {}).get("value", 0.8))
        critical = not context.safety_assessment.get("departure_allowed", True)

        vessel_dict = {
            "type": context.target_vessel.vessel_type.value,
            "name": context.target_vessel.name,
            "beam_m": context.target_vessel.beam_m,
            "cruising_speed_kmh": context.target_vessel.cruising_speed_kmh,
            "max_wave_m": context.target_vessel.max_wave_m,
            "max_wind_ms": context.target_vessel.max_wind_ms,
            "range_km": context.target_vessel.range_km,
        }

        origin_dict = {
            "lat": context.origin_location.lat,
            "lon": context.origin_location.lon,
            "name": context.origin_location.name or "Origin Point",
        }

        # 1. Attempt Gemini Neural Synthesis
        if context.api_key:
            context.gemini_calls_count += 1
            gemini_answer = generate_marine_synthesis(
                user_query=context.user_query,
                language=context.detected_language,
                intent=context.query_intent,
                vessel_profile=vessel_dict,
                safety_assessment=context.safety_assessment,
                top_candidate=top_cand.model_dump(mode="json") if top_cand else {},
                alternative_candidates=[item.model_dump(mode="json") for item in alt_cands],
                worst_candidate=worst_cand.model_dump(mode="json") if worst_cand else None,
                origin_location=origin_dict,
                route_info=context.navigation_route,
                api_key=context.api_key,
            )

            if gemini_answer:
                context.ai_provider = "GEMINI NEURAL AGENT"
                context.synthesis_duration_ms = round((time.perf_counter() - t_start) * 1000, 2)
                context.operational_trace.append("Gemini agent: generated grounded conversational neural synthesis addressing specific user query.")
                return gemini_answer

        # 2. Deterministic Fallback Template Synthesis
        context.ai_provider = "DETERMINISTIC GIS AGENT"
        dummy_top = RankedZone(
            id="default_zone",
            name=f"Zone near {context.origin_location.name or 'Origin'}",
            location=context.origin_location,
            distance_km=15.0,
            pfz_score=75.0,
            chlorophyll_score=70.0,
            sst_score=75.0,
            ocean_context_score=70.0,
            wave_safety=70.0,
            wind_safety=70.0,
            swell_safety=70.0,
            current_safety=70.0,
            hazard_clearance=80.0,
            accessibility_score=80.0,
            data_quality_score=75.0,
            restricted_zone=False,
            critical_hazard=critical,
            evidence_ids=[],
            fishing_score=75.0,
            safety_score=70.0,
            overall_score=72.0,
            rank=1,
            decision_status="BLOCKED" if critical else "RECOMMENDED",
            rejected_reason=["critical hazard advisory"] if critical else [],
        )
        effective_top = top_cand or dummy_top
        context.synthesis_duration_ms = round((time.perf_counter() - t_start) * 1000, 2)

        return _answer(
            context.detected_language,
            context.query_intent,
            critical,
            effective_top,
            alt_cands[0] if alt_cands else None,
            worst_cand,
            wave,
            wind,
            swell,
            context.target_vessel.name,
            context.target_vessel.max_wave_m,
            origin_name=context.origin_location.name or "Mumbai Harbour",
        )

    def run(
        self,
        message: str,
        location: Location,
        language: str = "auto",
        vessel_type: str = "small_boat",
        use_live_data: bool = False,
        api_key: str | None = None,
    ) -> dict[str, Any]:
        """Execute the end-to-end multi-agent orchestration pipeline."""
        t_start = time.perf_counter()
        req_id = str(uuid.uuid4())

        # Resolve initial configuration
        detected_lang = detect_language(message, language)
        intent = detect_intent(message)
        vessel = VESSEL_PROFILES.get(vessel_type, VESSEL_PROFILES["small_boat"])

        resolved_key = api_key or get_gemini_api_key()

        # Initialize shared context
        context = OrcaExecutionContext(
            request_id=req_id,
            user_query=message,
            detected_language=detected_lang,
            query_intent=intent,
            origin_location=location or DEFAULT_LOCATION,
            target_vessel=vessel,
            use_live_data=use_live_data,
            api_key=resolved_key,
        )

        # Step 1: Formulate execution plan with optional Gemini planner & deterministic failover
        plan, planner_provider, plan_duration_ms, calls_count = self.plan(
            query=message,
            intent=intent,
            vessel_type=vessel_type,
            api_key=resolved_key,
        )
        context.planner_provider = planner_provider
        context.planner_duration_ms = plan_duration_ms
        context.gemini_calls_count += calls_count

        # Step 2: Dispatch tasks and execute typed tools
        self.dispatch_plan(context, plan)

        # Step 3: Hard safety gate enforcement
        self.apply_safety_gate(context)

        # Step 4: Synthesize response
        final_answer = self.synthesize_response(context)
        context.final_answer = final_answer
        context.execution_duration_ms = round((time.perf_counter() - t_start) * 1000, 2)

        top_cand = context.ranked_zones[0] if context.ranked_zones else None
        alt_cands = context.ranked_zones[1:] if len(context.ranked_zones) > 1 else []
        worst_cand = context.ranked_zones[-1] if context.ranked_zones else None

        freshness_str = (
            "Live real-time feed active."
            if context.source_mode == SourceMode.LIVE
            else ("Simulated observation model active." if context.source_mode == SourceMode.DEMO else "Cached data only: verify official advisories immediately before departure.")
        )

        # Return backward-compatible API payload with extended metrics
        return {
            "answer": final_answer,
            "intent": context.query_intent,
            "language": context.detected_language,
            "source_mode": context.source_mode.value,
            "ai_provider": context.ai_provider,
            "origin": {
                "lat": context.origin_location.lat,
                "lon": context.origin_location.lon,
                "name": context.origin_location.name or f"Point ({context.origin_location.lat:.2f}°N, {context.origin_location.lon:.2f}°E)",
            },
            "recommendation": top_cand.model_dump(mode="json") if top_cand else None,
            "alternatives": [item.model_dump(mode="json") for item in alt_cands],
            "worst_zone": worst_cand.model_dump(mode="json") if worst_cand else None,
            "evidence": [item.model_dump(mode="json") for item in context.evidence_ledger],
            "trace": context.operational_trace,
            "vessel_profile": {
                "type": context.target_vessel.vessel_type.value,
                "name": context.target_vessel.name,
                "beam_m": context.target_vessel.beam_m,
                "cruising_speed_kmh": context.target_vessel.cruising_speed_kmh,
                "max_wave_m": context.target_vessel.max_wave_m,
                "max_wind_ms": context.target_vessel.max_wind_ms,
                "range_km": context.target_vessel.range_km,
            },
            "route": context.navigation_route,
            "safety": context.safety_assessment,
            "freshness": freshness_str,
            "metrics": {
                "planner_provider": context.planner_provider,
                "planner_duration_ms": context.planner_duration_ms,
                "synthesis_duration_ms": context.synthesis_duration_ms,
                "gemini_calls_count": context.gemini_calls_count,
                "total_duration_ms": context.execution_duration_ms,
            },
        }
