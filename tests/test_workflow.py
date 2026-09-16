import json
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
    assert result["workflow_metrics"]["tool_calls"] <= 9
    assert {trace["tool"] for trace in state["tool_trace"]} >= {
        "search_wardrobe",
        "get_weather",
        "search_style_guidance",
        "search_sample_catalog",
        "search_memories",
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


def test_validator_rejects_festive_items_for_a_casual_outing() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    state = run_demo_workflow(dataset)
    result = deepcopy(state["final_result"])
    result.pop("validation_errors")
    result.pop("workflow_metrics")
    coastal_maya = next(
        outfit
        for outfit in result["outfits"]
        if outfit["event_id"] == "event_coastal_outing" and outfit["member_id"] == "member_maya"
    )
    coastal_maya["item_ids"][0] = "maya_top_02"

    errors = validate_plan(
        OutfitPlan.model_validate(result),
        dataset,
        dataset.demo_request.event_ids,
    )

    assert any("Formality mismatch" in error for error in errors)


def test_validator_rejects_guidance_that_was_not_retrieved() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    state = run_demo_workflow(dataset)
    result = deepcopy(state["final_result"])
    result.pop("validation_errors")
    result.pop("workflow_metrics")
    result["outfits"][0]["guidance_ids"] = ["guide_not_retrieved"]

    errors = validate_plan(
        OutfitPlan.model_validate(result),
        dataset,
        dataset.demo_request.event_ids,
        retrieved_guidance_ids={document.id for document in dataset.guidance_documents},
    )

    assert any("was not retrieved" in error for error in errors)


def test_validator_rejects_missing_required_wardrobe_item() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    dataset.demo_request.event_ids = ["event_school_celebration"]
    state = run_demo_workflow(dataset)
    result = deepcopy(state["final_result"])
    result.pop("validation_errors")
    result.pop("workflow_metrics")

    errors = validate_plan(
        OutfitPlan.model_validate(result),
        dataset,
        dataset.demo_request.event_ids,
        required_item_ids={"maya_top_03"},
    )

    assert any("Required wardrobe item maya_top_03 missing" in error for error in errors)


def test_validator_requires_affordable_rain_protection_for_each_participant() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    dataset.demo_request.event_ids = ["event_coastal_outing"]
    state = run_demo_workflow(dataset)
    result = deepcopy(state["final_result"])
    result.pop("validation_errors")
    result.pop("workflow_metrics")
    result["purchases"] = [
        purchase
        for purchase in result["purchases"]
        if purchase["member_id"] != "member_maya"
    ]
    result["total_purchase_cost"] = 38

    errors = validate_plan(
        OutfitPlan.model_validate(result),
        dataset,
        dataset.demo_request.event_ids,
    )

    assert any(
        "Missing rain protection for event_coastal_outing/member_maya" in error
        and "catalog_01" in error
        for error in errors
    )


def test_local_planner_honors_required_wardrobe_item() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    dataset.demo_request.event_ids = ["event_coastal_outing"]
    dataset.demo_request.required_item_ids = ["maya_top_03"]

    state = run_demo_workflow(dataset)
    result = state["final_result"]
    maya_outfit = next(
        outfit for outfit in result["outfits"] if outfit["member_id"] == "member_maya"
    )

    assert result["status"] == "valid"
    assert "maya_top_03" in maya_outfit["item_ids"]
    assert "required wardrobe item" in maya_outfit["rationale"]


def test_memory_search_is_member_scoped_and_changes_local_footwear() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    dataset.demo_request.event_ids = ["event_coastal_outing"]
    searched_member_ids = []

    def search_memory(member_id: str, query: str, limit: int):
        searched_member_ids.append(member_id)
        assert "Santa Cruz Coastal Outing" in query
        assert limit == 5
        if member_id == "member_maya":
            return [
                {
                    "id": "memory_maya_flats",
                    "member_id": member_id,
                    "text": "Maya prefers flats when an event involves extensive walking",
                    "category": "footwear",
                    "provider": "mem0",
                }
            ]
        return []

    graph = build_planning_graph(
        dataset,
        memory_search=search_memory,
    )
    state = graph.invoke({"request": dataset.demo_request.model_dump(mode="json")})
    maya_outfit = next(
        outfit
        for outfit in state["final_result"]["outfits"]
        if outfit["member_id"] == "member_maya"
    )

    assert set(searched_member_ids) == {
        "member_maya",
        "member_arjun",
        "member_anaya",
    }
    assert "maya_shoe_01" in maya_outfit["item_ids"]
    assert "Applies remembered preference" in maya_outfit["rationale"]
    memory_result = next(
        result for result in state["tool_results"] if result["name"] == "search_memories"
    )["result"]
    assert memory_result["memories_by_member"]["member_arjun"] == []
    assert memory_result["retrieval_metadata"]["provider"] == "mem0"


def test_nebius_agent_backend_drives_the_same_graph_contract() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    local_state = run_demo_workflow(dataset)
    expected_plan = deepcopy(local_state["final_result"])
    expected_plan.pop("validation_errors")
    expected_plan.pop("workflow_metrics")
    expected_plan["status"] = "needs_review"

    captured = {}

    class FakeNebiusModel:
        def generate_via_tool(self, **kwargs: object):
            captured.update(kwargs)
            return OutfitPlan.model_validate(expected_plan)

    graph = build_planning_graph(dataset, NebiusPlanningAgent(FakeNebiusModel()))

    state = graph.invoke({"request": dataset.demo_request.model_dump(mode="json")})

    assert state["final_result"]["status"] == "valid"
    assert state["final_result"]["workflow_metrics"]["agent_backend"] == "nebius"
    assert state["final_result"]["workflow_metrics"]["tool_calls"] == 2
    assert state["tool_trace"][0]["tool"] == "prepare_planning_context"
    assert state["tool_trace"][0]["actor"] == "workflow"
    assert state["tool_trace"][1]["tool"] == "search_memories"
    prompt_payload = json.loads(captured["user_message"])
    assert "maya_outer_02" not in prompt_payload["allowed_wardrobe_ids_by_member"]["member_maya"]
    assert "maya_outer_01" in prompt_payload["allowed_wardrobe_ids_by_member"]["member_maya"]
    assert "opaque identifiers" in captured["system_prompt"]


def test_workflow_repairs_an_unambiguous_weather_gap_without_another_model_call() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    dataset.demo_request.event_ids = ["event_coastal_outing"]
    local_state = run_demo_workflow(dataset)
    incomplete_plan = deepcopy(local_state["final_result"])
    incomplete_plan.pop("validation_errors")
    incomplete_plan.pop("workflow_metrics")
    incomplete_plan["status"] = "needs_review"
    incomplete_plan["purchases"] = [
        purchase
        for purchase in incomplete_plan["purchases"]
        if purchase["member_id"] != "member_maya"
    ]
    incomplete_plan["total_purchase_cost"] = 38

    class IncompleteNebiusModel:
        calls = 0

        def generate_via_tool(self, **kwargs: object):
            self.calls += 1
            return OutfitPlan.model_validate(incomplete_plan)

    model = IncompleteNebiusModel()
    graph = build_planning_graph(dataset, NebiusPlanningAgent(model))
    state = graph.invoke({"request": dataset.demo_request.model_dump(mode="json")})
    result = state["final_result"]

    assert result["status"] == "valid"
    assert result["validation_errors"] == []
    assert result["total_purchase_cost"] == 96
    assert any(
        purchase["member_id"] == "member_maya"
        and purchase["catalog_item_id"] == "catalog_01"
        and purchase["supports_event_ids"] == ["event_coastal_outing"]
        for purchase in result["purchases"]
    )
    assert model.calls == 1
    assert result["workflow_metrics"]["repair_attempts"] == 0
    assert result["workflow_metrics"]["policy_repairs"] == 1
    assert state["tool_trace"][-1]["tool"] == "apply_weather_policy_repair"
    assert state["tool_trace"][-1]["actor"] == "workflow"
