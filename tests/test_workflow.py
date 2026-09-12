from copy import deepcopy
from pathlib import Path

from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.domain.plans import OutfitPlan
from wardrobe_planner.workflow.graph import build_planning_graph, run_demo_workflow
from wardrobe_planner.workflow.nebius_agent import NebiusPlanningAgent
from wardrobe_planner.workflow.validator import validate_plan

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


def test_demo_workflow_produces_a_valid_multi_event_plan() -> None:
    dataset = load_seed_dataset(SEED_DIR)

    state = run_demo_workflow(dataset)
    result = state["final_result"]

    assert result is not None
    assert result["status"] == "valid"
    assert result["validation_errors"] == []
    assert len(result["outfits"]) == 9
    assert result["workflow_metrics"]["tool_calls"] <= 8
    assert {trace["tool"] for trace in state["tool_trace"]} >= {
        "search_wardrobe",
        "get_weather",
        "search_style_guidance",
        "search_sample_catalog",
    }


def test_validator_rejects_an_item_owned_by_another_member() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    state = run_demo_workflow(dataset)
    result = deepcopy(state["final_result"])
    assert result is not None
    result.pop("validation_errors")
    result.pop("workflow_metrics")
    result["outfits"][0]["item_ids"][0] = "arjun_top_01"
    plan = OutfitPlan.model_validate(result)

    errors = validate_plan(plan, dataset, dataset.demo_request.event_ids)

    assert any("Wrong owner" in error for error in errors)


def test_nebius_agent_backend_drives_the_same_graph_contract() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    local_state = run_demo_workflow(dataset)
    expected_plan = deepcopy(local_state["final_result"])
    expected_plan.pop("validation_errors")
    expected_plan.pop("workflow_metrics")
    expected_plan["status"] = "needs_review"

    class FakeNebiusModel:
        def generate_via_tool(self, **_: object):
            return OutfitPlan.model_validate(expected_plan)

    graph = build_planning_graph(dataset, NebiusPlanningAgent(FakeNebiusModel()))

    state = graph.invoke({"request": dataset.demo_request.model_dump(mode="json")})

    assert state["final_result"]["status"] == "valid"
    assert state["final_result"]["workflow_metrics"]["agent_backend"] == "nebius"
    assert state["final_result"]["workflow_metrics"]["tool_calls"] == 1
    assert state["tool_trace"][0]["tool"] == "prepare_planning_context"
    assert state["tool_trace"][0]["actor"] == "workflow"
