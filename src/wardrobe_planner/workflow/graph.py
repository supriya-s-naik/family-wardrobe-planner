from __future__ import annotations

import json
from typing import Any, Literal

from langgraph.graph import END, START, StateGraph
from openai import OpenAIError
from pydantic import ValidationError

from wardrobe_planner.adapters.local import LocalPlanningData
from wardrobe_planner.adapters.pinecone_rag import PineconeGuidanceRAG
from wardrobe_planner.domain.models import DemoRequest, SeedDataset
from wardrobe_planner.domain.plans import OutfitPlan
from wardrobe_planner.workflow.agent import PlanningAgent
from wardrobe_planner.workflow.local_agent import LocalPlanningAgent
from wardrobe_planner.workflow.nebius_agent import NebiusPlanningAgent
from wardrobe_planner.workflow.state import PlanningState
from wardrobe_planner.workflow.tools import ToolExecutor
from wardrobe_planner.workflow.validator import validate_plan

MAX_TOOL_CALLS = 8
MAX_REPAIR_ATTEMPTS = 2


def build_planning_graph(
    dataset: SeedDataset,
    agent: PlanningAgent | None = None,
    guidance_search=None,
):
    data = LocalPlanningData(dataset)
    tools = ToolExecutor(data, guidance_search=guidance_search)
    planning_agent = agent or LocalPlanningAgent()

    def load_context(state: PlanningState) -> dict[str, Any]:
        request = DemoRequest.model_validate(state["request"])
        events = data.get_events(request.event_ids)
        participant_ids = list(
            dict.fromkeys(member_id for event in events for member_id in event.participant_ids)
        )
        members = data.get_family_profiles(participant_ids)
        return {
            "household_context": {
                "household": dataset.household.model_dump(mode="json"),
                "members": [member.model_dump(mode="json") for member in members],
                "events": [event.model_dump(mode="json") for event in events],
            },
            "tool_results": [],
            "tool_trace": [],
            "validation_errors": [],
            "retry_count": 0,
            "tool_call_count": 0,
            "terminal_error": None,
            "candidate_plan": None,
            "final_result": None,
            "pending_tool_calls": [],
        }

    def agent_node(state: PlanningState) -> dict[str, Any]:
        try:
            calls = planning_agent.next_tool_calls(state)
        except (OpenAIError, RuntimeError, TypeError, ValueError, ValidationError) as exc:
            return {
                "pending_tool_calls": [],
                "terminal_error": (
                    f"{planning_agent.backend_name.title()} tool selection failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        if calls:
            remaining = MAX_TOOL_CALLS - state.get("tool_call_count", 0)
            if len(calls) > remaining:
                return {
                    "pending_tool_calls": [],
                    "terminal_error": (
                        f"Agent requested {len(calls)} tools with only {remaining} of "
                        f"{MAX_TOOL_CALLS} calls remaining."
                    ),
                }
            completed_signatures = {
                (result["name"], _canonical_arguments(result["arguments"]))
                for result in state.get("tool_results", [])
            }
            new_signatures = [
                (call["name"], _canonical_arguments(call["arguments"])) for call in calls
            ]
            if len(new_signatures) != len(set(new_signatures)) or any(
                signature in completed_signatures for signature in new_signatures
            ):
                return {
                    "pending_tool_calls": [],
                    "terminal_error": "Agent requested a duplicate tool call.",
                }
            return {"pending_tool_calls": calls}
        try:
            plan = planning_agent.compose_plan(state)
        except (OpenAIError, RuntimeError, TypeError, ValueError, ValidationError) as exc:
            return {
                "pending_tool_calls": [],
                "terminal_error": (
                    f"{planning_agent.backend_name.title()} plan generation failed: "
                    f"{type(exc).__name__}: {exc}"
                ),
            }
        return {"pending_tool_calls": [], "candidate_plan": plan.model_dump(mode="json")}

    def execute_tool(state: PlanningState) -> dict[str, Any]:
        calls = state.get("pending_tool_calls", [])
        if not calls:
            return {"terminal_error": "Tool node received no pending tool call."}
        records = []
        trace_records = []
        first_step = state.get("tool_call_count", 0) + 1
        for offset, call in enumerate(calls):
            try:
                result = tools.execute(call["name"], call["arguments"])
            except (KeyError, TypeError, ValueError) as exc:
                return {
                    "pending_tool_calls": [],
                    "terminal_error": f"Tool {call.get('name', '<unknown>')} failed: {exc}",
                }
            records.append(
                {
                    "name": call["name"],
                    "arguments": call["arguments"],
                    "result": result,
                }
            )
            trace_records.append(
                {
                    "step": first_step + offset,
                    "tool": call["name"],
                    "reason": call["reason"],
                    "actor": call.get("actor", "agent"),
                    "arguments": call["arguments"],
                    "result_count": len(result) if isinstance(result, list) else 1,
                    "batch_size": len(calls),
                }
            )
        return {
            "tool_results": [*state.get("tool_results", []), *records],
            "tool_trace": [*state.get("tool_trace", []), *trace_records],
            "tool_call_count": state.get("tool_call_count", 0) + len(calls),
            "pending_tool_calls": [],
        }

    def validate_node(state: PlanningState) -> dict[str, Any]:
        candidate = state.get("candidate_plan")
        if candidate is None:
            return {"validation_errors": ["Planner produced no candidate plan."]}
        plan = OutfitPlan.model_validate(candidate)
        errors = validate_plan(plan, dataset, state["request"]["event_ids"])
        return {"validation_errors": errors}

    def repair_node(state: PlanningState) -> dict[str, Any]:
        return {
            "candidate_plan": None,
            "retry_count": state.get("retry_count", 0) + 1,
        }

    def finalize_node(state: PlanningState) -> dict[str, Any]:
        if state.get("terminal_error"):
            return {
                "final_result": {
                    "status": "failed",
                    "error": state["terminal_error"],
                    "validation_errors": state.get("validation_errors", []),
                }
            }
        candidate = state.get("candidate_plan")
        if candidate is None:
            return {
                "final_result": {
                    "status": "failed",
                    "error": "No plan was produced.",
                    "validation_errors": state.get("validation_errors", []),
                }
            }
        plan = OutfitPlan.model_validate(candidate)
        if state.get("validation_errors"):
            plan.status = "needs_review"
        else:
            plan.status = "valid"
        result = plan.model_dump(mode="json")
        result["validation_errors"] = state.get("validation_errors", [])
        result["workflow_metrics"] = {
            "agent_backend": planning_agent.backend_name,
            "tool_calls": state.get("tool_call_count", 0),
            "repair_attempts": state.get("retry_count", 0),
        }
        return {"final_result": result}

    def route_after_agent(state: PlanningState) -> Literal["execute_tool", "validate", "finalize"]:
        if state.get("terminal_error"):
            return "finalize"
        if state.get("pending_tool_calls"):
            return "execute_tool"
        return "validate"

    def route_after_validation(state: PlanningState) -> Literal["repair", "finalize"]:
        if state.get("validation_errors") and state.get("retry_count", 0) < MAX_REPAIR_ATTEMPTS:
            return "repair"
        return "finalize"

    graph = StateGraph(PlanningState)
    graph.add_node("load_context", load_context)
    graph.add_node("agent", agent_node)
    graph.add_node("execute_tool", execute_tool)
    graph.add_node("validate", validate_node)
    graph.add_node("repair", repair_node)
    graph.add_node("finalize", finalize_node)
    graph.add_edge(START, "load_context")
    graph.add_edge("load_context", "agent")
    graph.add_conditional_edges("agent", route_after_agent)
    graph.add_edge("execute_tool", "agent")
    graph.add_conditional_edges("validate", route_after_validation)
    graph.add_edge("repair", "agent")
    graph.add_edge("finalize", END)
    return graph.compile()


def run_demo_workflow(dataset: SeedDataset) -> PlanningState:
    graph = build_planning_graph(dataset, LocalPlanningAgent())
    return graph.invoke({"request": dataset.demo_request.model_dump(mode="json")})


def run_nebius_workflow(dataset: SeedDataset) -> PlanningState:
    try:
        guidance_search = PineconeGuidanceRAG.from_env().search_guidance
    except RuntimeError:
        guidance_search = None
    graph = build_planning_graph(
        dataset,
        NebiusPlanningAgent(),
        guidance_search=guidance_search,
    )
    return graph.invoke({"request": dataset.demo_request.model_dump(mode="json")})


def _canonical_arguments(arguments: dict[str, Any]) -> str:
    return json.dumps(arguments, sort_keys=True, separators=(",", ":"))
