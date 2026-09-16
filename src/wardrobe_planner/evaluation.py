from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import BaseModel, Field

from wardrobe_planner.adapters.nebius import NebiusModel
from wardrobe_planner.domain.models import SeedDataset
from wardrobe_planner.domain.plans import OutfitPlan
from wardrobe_planner.workflow.graph import (
    build_planning_graph,
    run_demo_workflow,
    run_nebius_workflow,
)
from wardrobe_planner.workflow.validator import validate_plan


class EvalCase(BaseModel):
    id: str
    description: str
    event_ids: list[str] = Field(min_length=1)
    purchase_budget: float = Field(ge=0)
    unavailable_item_ids: list[str] = Field(default_factory=list)
    forbidden_item_ids: list[str] = Field(default_factory=list)
    expected_outfit_count: int = Field(gt=0)
    expected_guidance_ids: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    max_tool_calls: int = Field(gt=0)
    repeat_runs: int = Field(default=1, ge=1, le=3)
    remembered_preferences: dict[str, list[str]] = Field(default_factory=dict)
    expected_memory_item_ids: dict[str, list[str]] = Field(default_factory=dict)


class EvalResult(BaseModel):
    case_id: str
    description: str
    backend: str
    passed: bool
    checks: dict[str, bool]
    measurements: dict[str, Any]
    failures: list[str]


class EvalReport(BaseModel):
    generated_at: str
    backend: str
    passed_cases: int
    total_cases: int
    pass_rate: float
    results: list[EvalResult]


class RubricScore(BaseModel):
    score: int = Field(ge=1, le=5)
    evidence: str


class QualitativeJudgment(BaseModel):
    event_fit: RubricScore
    weather_readiness: RubricScore
    personal_comfort: RubricScore
    family_coordination: RubricScore
    grounded_rationale: RubricScore
    purchase_value: RubricScore
    overall_score: float = Field(ge=1, le=5)
    summary: str
    concerns: list[str]


def load_eval_cases(path: Path) -> list[EvalCase]:
    return [EvalCase.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]


def run_evaluation(
    dataset: SeedDataset,
    cases: list[EvalCase],
    *,
    backend: Literal["local", "nebius"] = "local",
) -> EvalReport:
    runner = run_demo_workflow if backend == "local" else run_nebius_workflow
    results = [evaluate_case(dataset, case, runner, backend) for case in cases]
    passed_cases = sum(result.passed for result in results)
    return EvalReport(
        generated_at=datetime.now(UTC).isoformat(),
        backend=backend,
        passed_cases=passed_cases,
        total_cases=len(results),
        pass_rate=round(passed_cases / len(results), 4) if results else 0,
        results=results,
    )


def evaluate_case(
    base_dataset: SeedDataset,
    case: EvalCase,
    runner: Callable[[SeedDataset], dict[str, Any]],
    backend: str,
) -> EvalResult:
    dataset = deepcopy(base_dataset)
    dataset.demo_request.event_ids = case.event_ids
    dataset.demo_request.purchase_budget = case.purchase_budget
    dataset.demo_request.user_message = f"Evaluation case {case.id}: {case.description}"
    unavailable_ids = set(case.unavailable_item_ids)
    for item in dataset.wardrobe_items:
        if item.id in unavailable_ids:
            item.available = False

    started_at = perf_counter()
    if case.remembered_preferences and backend == "local":
        def fixture_memory_search(member_id: str, _query: str, limit: int):
            return [
                {
                    "id": f"eval-memory-{member_id}-{index}",
                    "member_id": member_id,
                    "text": text,
                    "category": "evaluation_fixture",
                    "provider": "mem0_fixture",
                }
                for index, text in enumerate(case.remembered_preferences.get(member_id, [])[:limit])
            ]

        def case_runner(case_dataset: SeedDataset):
            graph = build_planning_graph(case_dataset, memory_search=fixture_memory_search)
            return graph.invoke({"request": case_dataset.demo_request.model_dump(mode="json")})
    else:
        case_runner = runner

    states = [case_runner(dataset) for _ in range(case.repeat_runs)]
    elapsed_ms = round((perf_counter() - started_at) * 1000)
    state = states[0]
    final = state.get("final_result") or {}
    failures: list[str] = []

    try:
        plan_payload = {
            key: value
            for key, value in final.items()
            if key not in {"validation_errors", "workflow_metrics", "error"}
        }
        plan = OutfitPlan.model_validate(plan_payload)
        schema_valid = True
    except Exception as exc:  # noqa: BLE001 -- schema failure is an eval result.
        plan = None
        schema_valid = False
        failures.append(f"schema_validity: {type(exc).__name__}")

    selected_items = [
        (outfit, item_id)
        for outfit in (plan.outfits if plan else [])
        for item_id in outfit.item_ids
    ]
    selected_item_ids = {item_id for _, item_id in selected_items}
    item_by_id = {item.id: item for item in dataset.wardrobe_items}
    member_by_id = {member.id: member for member in dataset.family_members}
    event_by_id = {event.id: event for event in dataset.events}
    retrieved_guidance_ids = _retrieved_guidance_ids(state)
    cited_guidance_ids = {
        guidance_id
        for outfit in (plan.outfits if plan else [])
        for guidance_id in outfit.guidance_ids
    }
    actual_tools = [trace["tool"] for trace in state.get("tool_trace", [])]
    expected_pairs = {
        (event.id, member_id)
        for event in dataset.events
        if event.id in set(case.event_ids)
        for member_id in event.participant_ids
    }
    actual_pairs = {
        (outfit.event_id, outfit.member_id) for outfit in (plan.outfits if plan else [])
    }
    memories_by_member = _retrieved_memories_by_member(state)
    memory_rows_are_isolated = all(
        row.get("member_id") == member_id
        for member_id, rows in memories_by_member.items()
        for row in rows
    )
    expected_memory_texts_retrieved = all(
        set(expected_texts).issubset({row.get("text") for row in memories_by_member.get(member_id, [])})
        for member_id, expected_texts in case.remembered_preferences.items()
    )
    expected_memory_items_used = all(
        set(expected_item_ids).issubset(
            {
                item_id
                for outfit in (plan.outfits if plan else [])
                if outfit.member_id == member_id
                for item_id in outfit.item_ids
            }
        )
        for member_id, expected_item_ids in case.expected_memory_item_ids.items()
    )

    deterministic_errors = (
        validate_plan(plan, dataset, case.event_ids) if plan is not None else ["No valid plan"]
    )
    required_tools = (
        {"prepare_planning_context"} if backend == "nebius" else set(case.required_tools)
    )
    checks = {
        "schema_validity": schema_valid,
        "workflow_valid": final.get("status") == "valid",
        "item_exists": all(item_id in item_by_id for _, item_id in selected_items),
        "correct_owner": all(
            item_by_id[item_id].member_id == outfit.member_id
            for outfit, item_id in selected_items
            if item_id in item_by_id
        ),
        "item_available": all(
            item_by_id[item_id].available for _, item_id in selected_items if item_id in item_by_id
        ),
        "hard_preference_compliance": all(
            _respects_preferences(item_by_id[item_id], member_by_id[outfit.member_id])
            for outfit, item_id in selected_items
            if item_id in item_by_id and outfit.member_id in member_by_id
        ),
        "event_formality": all(
            event_by_id[outfit.event_id].dress_code == "festive"
            or item_by_id[item_id].formality != "festive"
            for outfit, item_id in selected_items
            if item_id in item_by_id and outfit.event_id in event_by_id
        ),
        "participant_coverage": actual_pairs == expected_pairs
        and len(plan.outfits if plan else []) == case.expected_outfit_count,
        "hard_constraint_compliance": not deterministic_errors,
        "budget_compliance": bool(plan and plan.total_purchase_cost <= case.purchase_budget),
        "tool_use": required_tools.issubset(actual_tools)
        and len(actual_tools) <= case.max_tool_calls,
        "retrieval_relevance": set(case.expected_guidance_ids).issubset(retrieved_guidance_ids),
        "grounded_citations": bool(plan)
        and all(outfit.guidance_ids for outfit in plan.outfits)
        and cited_guidance_ids.issubset(retrieved_guidance_ids),
        "unavailable_items_excluded": not selected_item_ids.intersection(case.forbidden_item_ids),
        "memory_isolation": memory_rows_are_isolated and expected_memory_texts_retrieved,
        "memory_application": expected_memory_items_used,
        "repeatability": _canonical_plan(states[0]) == _canonical_plan(states[-1]),
    }
    for name, passed in checks.items():
        if not passed and not any(failure.startswith(f"{name}:") for failure in failures):
            failures.append(name)

    return EvalResult(
        case_id=case.id,
        description=case.description,
        backend=backend,
        passed=all(checks.values()),
        checks=checks,
        measurements={
            "outfit_count": len(plan.outfits if plan else []),
            "purchase_cost": plan.total_purchase_cost if plan else None,
            "owned_items_used": len(selected_item_ids),
            "tool_calls": len(actual_tools),
            "latency_ms": elapsed_ms,
            "retrieved_guidance_ids": sorted(retrieved_guidance_ids),
            "cited_guidance_ids": sorted(cited_guidance_ids),
            "validation_errors": deterministic_errors,
            "retrieved_memory_count": sum(len(rows) for rows in memories_by_member.values()),
        },
        failures=failures,
    )


def write_report(report: EvalReport, output_dir: Path, stem: str = "latest") -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{stem}.json").write_text(
        report.model_dump_json(indent=2) + "\n", encoding="utf-8"
    )
    rows = [
        "# Evaluation results",
        "",
        f"- Backend: `{report.backend}`",
        f"- Cases passed: **{report.passed_cases}/{report.total_cases}**",
        f"- Pass rate: **{report.pass_rate:.0%}**",
        "",
        "| Case | Result | Outfits | Cost | Tool calls | Latency |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        rows.append(
            f"| `{result.case_id}` | {status} | {result.measurements['outfit_count']} | "
            f"${result.measurements['purchase_cost'] or 0:.0f} | "
            f"{result.measurements['tool_calls']} | {result.measurements['latency_ms']} ms |"
        )
    rows.extend(
        [
            "",
            (
                "Each case checks schema validity, workflow validity, participant coverage, hard "
                "constraints, budget, required tool calls, retrieval relevance, citation "
                "grounding, unavailable-item exclusion, member-scoped memory, memory "
                "application, and repeatability."
            ),
        ]
    )
    (output_dir / f"{stem}.md").write_text("\n".join(rows) + "\n", encoding="utf-8")


def judge_plan_quality(
    dataset: SeedDataset,
    case: EvalCase,
    state: dict[str, Any],
    model: NebiusModel | None = None,
) -> QualitativeJudgment:
    selected_events = [event for event in dataset.events if event.id in set(case.event_ids)]
    participant_ids = {
        member_id for event in selected_events for member_id in event.participant_ids
    }
    payload = {
        "case": case.model_dump(mode="json"),
        "events": [event.model_dump(mode="json") for event in selected_events],
        "members": [
            member.model_dump(mode="json")
            for member in dataset.family_members
            if member.id in participant_ids
        ],
        "plan": state.get("final_result"),
        "retrieved_guidance": _retrieved_guidance(state),
    }
    judge = model or NebiusModel()
    return judge.generate_via_tool(
        system_prompt=(
            "Act as a critical wardrobe-plan evaluator. Score each rubric category from 1 to 5. "
            "Use only the supplied event, family, plan, and retrieved guidance. Give concrete "
            "evidence, identify weaknesses, and do not assume unstated fashion facts. Event fit "
            "covers occasion and dress code. Weather readiness covers forecast and activities. "
            "Personal comfort covers stated needs. Family coordination should be coherent without "
            "identical outfits. Grounded rationale must connect choices to supplied evidence. "
            "Purchase value covers need, budget, compatibility, and reuse."
        ),
        user_message=json.dumps(payload, default=str),
        response_model=QualitativeJudgment,
        tool_name="submit_qualitative_evaluation",
        tool_description="Submit rubric scores and evidence for the supplied wardrobe plan.",
    )


def _retrieved_guidance_ids(state: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for record in state.get("tool_results", []):
        if record["name"] == "search_style_guidance":
            ids.update(document["id"] for document in record["result"])
        elif record["name"] == "prepare_planning_context":
            ids.update(document["id"] for document in record["result"].get("guidance", []))
    return ids


def _retrieved_guidance(state: dict[str, Any]) -> list[dict[str, Any]]:
    for record in state.get("tool_results", []):
        if record["name"] == "search_style_guidance":
            return record["result"]
        if record["name"] == "prepare_planning_context":
            return record["result"].get("guidance", [])
    return []


def _retrieved_memories_by_member(
    state: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    for record in state.get("tool_results", []):
        if record["name"] == "search_memories":
            return record["result"].get("memories_by_member", {})
    return {}


def _canonical_plan(state: dict[str, Any]) -> str:
    final = state.get("final_result") or {}
    payload = {
        key: value
        for key, value in final.items()
        if key not in {"workflow_metrics", "validation_errors"}
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def _respects_preferences(item: Any, member: Any) -> bool:
    searchable = f"{item.name} {item.color} {item.notes or ''}".lower()
    prohibited = [*member.avoided_colors, *member.avoided_styles]
    return all(value.lower() not in searchable for value in prohibited)
