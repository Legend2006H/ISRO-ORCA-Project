"""Tests for ORCA multi-agent orchestration, bounded planning, and tool dispatching."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.agents.context import ExecutionPlan, OrcaExecutionContext, PlannedTask, TaskStatus
from api.agents.orchestrator import MAX_TASKS, MAX_TOOL_CALLS, OrcaOrchestrator
from api.agents.tools import TOOL_REGISTRY
from api.main import app
from api.models import Location, VESSEL_PROFILES
from api.offline_service import DEFAULT_LOCATION, analyse

client = TestClient(app)


def test_context_initialization() -> None:
    """Verify OrcaExecutionContext initializes with isolated defaults."""
    ctx1 = OrcaExecutionContext(
        request_id="req-1",
        user_query="test 1",
        origin_location=DEFAULT_LOCATION,
        target_vessel=VESSEL_PROFILES["small_boat"],
    )
    ctx2 = OrcaExecutionContext(
        request_id="req-2",
        user_query="test 2",
        origin_location=DEFAULT_LOCATION,
        target_vessel=VESSEL_PROFILES["trawler"],
    )
    ctx1.evidence_ledger.append(None)  # mutate ctx1 ledger
    assert len(ctx1.evidence_ledger) == 1
    assert len(ctx2.evidence_ledger) == 0  # ctx2 must remain empty


def test_planner_selective_tool_dispatch() -> None:
    """Verify planner produces intent-specific task DAGs, omitting unnecessary tools."""
    orchestrator = OrcaOrchestrator()

    # Safety-only query should NOT plan PFZ lookup or route calculation
    plan_safety = orchestrator.plan_deterministic("Is it safe tomorrow?", "safety", "small_boat")
    tool_names_safety = [t.tool_name for t in plan_safety.tasks]
    assert "tool_evaluate_vessel_risk" in tool_names_safety
    assert "tool_lookup_pfz_advisory" not in tool_names_safety
    assert "tool_calculate_safe_route" not in tool_names_safety
    assert len(plan_safety.tasks) <= MAX_TASKS

    # Worst-zone query should rank zones but NOT calculate route
    plan_worst = orchestrator.plan_deterministic("Which zone is worst?", "worst", "small_boat")
    tool_names_worst = [t.tool_name for t in plan_worst.tasks]
    assert "tool_lookup_pfz_advisory" in tool_names_worst
    assert "tool_rank_fishing_zones" in tool_names_worst
    assert "tool_calculate_safe_route" not in tool_names_worst

    # Full recommendation query should include routing
    plan_full = orchestrator.plan_deterministic("Where should I fish today?", "recommendation", "small_boat")
    tool_names_full = [t.tool_name for t in plan_full.tasks]
    assert "tool_lookup_pfz_advisory" in tool_names_full
    assert "tool_calculate_safe_route" in tool_names_full


def test_task_and_tool_call_limits() -> None:
    """Verify that MAX_TASKS and MAX_TOOL_CALLS are strictly enforced."""
    orchestrator = OrcaOrchestrator()

    # Create a plan with more than MAX_TOOL_CALLS tasks
    tasks = [
        PlannedTask(
            task_id=f"t_{i}",
            agent_role="test",
            tool_name="tool_resolve_coastal_entity",
            arguments={"query_text": "Mumbai"},
        )
        for i in range(12)
    ]
    overloaded_plan = ExecutionPlan(intent="test", tasks=tasks)

    ctx = OrcaExecutionContext(
        request_id="req-limits",
        user_query="test",
        origin_location=DEFAULT_LOCATION,
        target_vessel=VESSEL_PROFILES["small_boat"],
    )

    orchestrator.dispatch_plan(ctx, overloaded_plan)
    assert len(ctx.executed_tools) <= MAX_TOOL_CALLS


def test_unregistered_tool_rejection() -> None:
    """Verify that attempting to execute an unknown or unwhitelisted tool fails safely."""
    orchestrator = OrcaOrchestrator()

    plan = ExecutionPlan(
        intent="malicious_intent",
        tasks=[
            PlannedTask(
                task_id="bad_task",
                agent_role="attacker",
                tool_name="tool_arbitrary_shell_exec",
                arguments={"cmd": "rm -rf /"},
            )
        ],
    )

    ctx = OrcaExecutionContext(
        request_id="req-bad",
        user_query="malicious query",
        origin_location=DEFAULT_LOCATION,
        target_vessel=VESSEL_PROFILES["small_boat"],
    )

    orchestrator.dispatch_plan(ctx, plan)
    assert plan.tasks[0].status == TaskStatus.FAILED
    assert "Unknown tool" in plan.tasks[0].error
    assert any("rejected" in line.lower() for line in ctx.operational_trace)


def test_safety_gate_enforcement() -> None:
    """Verify safety gate marks status BLOCKED when wave height exceeds vessel limit."""
    orchestrator = OrcaOrchestrator()
    res = orchestrator.run(
        message="Find best fishing zone near Mumbai",
        location=DEFAULT_LOCATION,
        vessel_type="small_boat",  # 1.5m max wave, cache has 2.18m wave
        use_live_data=False,
    )

    assert res["safety"]["departure_allowed"] is False
    assert "exceed" in res["safety"]["reason"].lower()


def test_operational_trace_and_evidence() -> None:
    """Verify machine-readable operational trace and typed evidence ledger generation."""
    orchestrator = OrcaOrchestrator()
    res = orchestrator.run(
        message="Is sea safe for trawler?",
        location=DEFAULT_LOCATION,
        vessel_type="trawler",
        use_live_data=False,
    )

    assert len(res["trace"]) >= 3
    assert any("Planner:" in line for line in res["trace"])
    assert any("Marine data agent:" in line or "Risk engine:" in line for line in res["trace"])
    assert len(res["evidence"]) >= 1


def test_api_chat_orchestrator_integration() -> None:
    """Verify /api/v1/chat endpoint delegates cleanly to orchestrator."""
    response = client.post("/api/v1/chat", json={
        "message": "Where is the best safe fishing spot today near Ratnagiri?",
        "location": {"lat": 18.95, "lon": 72.85},
        "vessel_type": "small_boat",
        "language": "en",
    })
    assert response.status_code == 200
    data = response.json()
    assert "answer" in data
    assert "trace" in data
    assert "evidence" in data
    assert "recommendation" in data
    assert "Ratnagiri" in data["origin"]["name"]
    assert "metrics" in data
    assert "planner_provider" in data["metrics"]


def test_gemini_structured_plan_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify valid Gemini-generated structured plan is accepted, validated, and executed."""
    orchestrator = OrcaOrchestrator()

    mock_plan = {
        "intent": "safety",
        "location_query": "Ratnagiri",
        "vessel_type": "small_boat",
        "tasks": [
            {
                "task_id": "task_1",
                "agent_role": "planner",
                "tool_name": "tool_resolve_coastal_entity",
                "arguments": {"query_text": "Is Ratnagiri safe?"},
                "dependencies": [],
            },
            {
                "task_id": "task_2",
                "agent_role": "hazard",
                "tool_name": "tool_fetch_ocean_telemetry",
                "arguments": {"use_live_data": False},
                "dependencies": ["task_1"],
            },
            {
                "task_id": "task_3",
                "agent_role": "hazard",
                "tool_name": "tool_evaluate_vessel_risk",
                "arguments": {"vessel_type": "small_boat"},
                "dependencies": ["task_2"],
            },
        ],
        "rationale": "Selective safety evaluation for small boat in Ratnagiri",
    }

    monkeypatch.setattr("api.agents.orchestrator.generate_structured_plan", lambda *args, **kwargs: mock_plan)

    plan, provider, duration_ms, calls = orchestrator.plan(
        query="Is Ratnagiri safe?",
        intent="safety",
        vessel_type="small_boat",
        api_key="valid-mock-key",
    )

    assert provider == "GEMINI NEURAL PLANNER"
    assert len(plan.tasks) == 3
    assert plan.tasks[1].tool_name == "tool_fetch_ocean_telemetry"
    assert calls == 1
    assert duration_ms >= 0.0


def test_malformed_gemini_plan_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify malformed JSON/schema output from Gemini falls back safely to deterministic planner."""
    orchestrator = OrcaOrchestrator()

    # Simulate invalid plan schema (e.g. string instead of task list)
    monkeypatch.setattr("api.agents.orchestrator.generate_structured_plan", lambda *args, **kwargs: {"invalid": "structure"})

    plan, provider, duration_ms, calls = orchestrator.plan(
        query="Where to fish near Mumbai?",
        intent="recommendation",
        vessel_type="small_boat",
        api_key="valid-mock-key",
    )

    assert provider == "DETERMINISTIC RULE PLANNER"
    assert len(plan.tasks) > 0
    assert any(t.tool_name == "tool_lookup_pfz_advisory" for t in plan.tasks)


def test_cyclic_dependency_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify planner detects and rejects cyclic task DAGs, triggering deterministic fallback."""
    orchestrator = OrcaOrchestrator()

    # Create a cyclic plan: task_1 depends on task_2 and task_2 depends on task_1
    cyclic_plan = {
        "intent": "recommendation",
        "tasks": [
            {
                "task_id": "task_1",
                "agent_role": "planner",
                "tool_name": "tool_resolve_coastal_entity",
                "dependencies": ["task_2"],
            },
            {
                "task_id": "task_2",
                "agent_role": "hazard",
                "tool_name": "tool_fetch_ocean_telemetry",
                "dependencies": ["task_1"],
            },
        ],
    }

    monkeypatch.setattr("api.agents.orchestrator.generate_structured_plan", lambda *args, **kwargs: cyclic_plan)

    plan, provider, duration_ms, calls = orchestrator.plan(
        query="Find route",
        intent="recommendation",
        vessel_type="small_boat",
        api_key="valid-mock-key",
    )

    # Must reject cyclic graph and fallback cleanly
    assert provider == "DETERMINISTIC RULE PLANNER"


def test_excessive_task_plan_rejection(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify plans exceeding MAX_TASKS are rejected and fall back to deterministic plan."""
    orchestrator = OrcaOrchestrator()

    excessive_plan = {
        "intent": "recommendation",
        "tasks": [
            {
                "task_id": f"t_{i}",
                "agent_role": "marine",
                "tool_name": "tool_fetch_ocean_telemetry",
                "dependencies": [],
            }
            for i in range(10)  # Exceeds MAX_TASKS = 6
        ],
    }

    monkeypatch.setattr("api.agents.orchestrator.generate_structured_plan", lambda *args, **kwargs: excessive_plan)

    plan, provider, duration_ms, calls = orchestrator.plan(
        query="Find fish",
        intent="recommendation",
        vessel_type="small_boat",
        api_key="valid-mock-key",
    )

    assert provider == "DETERMINISTIC RULE PLANNER"
    assert len(plan.tasks) <= MAX_TASKS


def test_unknown_tool_in_plan_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    """Verify plans requesting unregistered tools fall back to deterministic plan."""
    orchestrator = OrcaOrchestrator()

    bad_tool_plan = {
        "intent": "safety",
        "tasks": [
            {
                "task_id": "t_1",
                "agent_role": "hazard",
                "tool_name": "tool_non_existent_exploit",
                "dependencies": [],
            }
        ],
    }

    monkeypatch.setattr("api.agents.orchestrator.generate_structured_plan", lambda *args, **kwargs: bad_tool_plan)

    plan, provider, duration_ms, calls = orchestrator.plan(
        query="Check safety",
        intent="safety",
        vessel_type="small_boat",
        api_key="valid-mock-key",
    )

    assert provider == "DETERMINISTIC RULE PLANNER"


def test_performance_metrics_isolation() -> None:
    """Verify separate latency tracking and call metrics in execution payload."""
    orchestrator = OrcaOrchestrator()
    res = orchestrator.run(
        message="Is sea safe near Ratnagiri?",
        location=DEFAULT_LOCATION,
        vessel_type="small_boat",
        use_live_data=False,
    )

    assert "metrics" in res
    metrics = res["metrics"]
    assert "planner_provider" in metrics
    assert "planner_duration_ms" in metrics
    assert "synthesis_duration_ms" in metrics
    assert "gemini_calls_count" in metrics
    assert "total_duration_ms" in metrics
    assert metrics["planner_provider"] == "DETERMINISTIC RULE PLANNER"
    assert metrics["gemini_calls_count"] == 0
