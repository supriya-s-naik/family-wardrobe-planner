from pathlib import Path

from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.workflow.graph import run_demo_workflow
from wardrobe_planner.workflow.refinement import PlanFeedbackIntent, refine_plan

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


def coastal_plan():
    dataset = load_seed_dataset(SEED_DIR)
    dataset.demo_request.event_ids = ["event_coastal_outing"]
    return dataset, run_demo_workflow(dataset)


def test_refinement_replaces_only_mayas_denim_with_owned_shorts():
    dataset, state = coastal_plan()
    before = {
        (outfit["event_id"], outfit["member_id"]): list(outfit["item_ids"])
        for outfit in state["final_result"]["outfits"]
    }

    outcome = refine_plan(
        dataset,
        state,
        "I would rather wear shorts at the beach than denim jeans.",
        "event_coastal_outing",
        "member_maya",
    )

    assert outcome["status"] == "applied"
    revised_state = outcome["planning_state"]
    assert revised_state["final_result"]["status"] == "valid"
    maya_outfit = next(
        outfit
        for outfit in revised_state["final_result"]["outfits"]
        if outfit["member_id"] == "member_maya"
    )
    assert "maya_bottom_04" in maya_outfit["item_ids"]
    assert "maya_bottom_03" not in maya_outfit["item_ids"]
    assert revised_state["refinement"]["accepted"] is False
    assert revised_state["refinement"]["interpreter"] == "local"
    for outfit in revised_state["final_result"]["outfits"]:
        if outfit["member_id"] != "member_maya":
            assert outfit["item_ids"] == before[(outfit["event_id"], outfit["member_id"])]


def test_refinement_explains_when_no_owned_or_catalog_alternative_exists():
    dataset, state = coastal_plan()

    outcome = refine_plan(
        dataset,
        state,
        "Replace the jeans with a skirt.",
        "event_coastal_outing",
        "member_arjun",
    )

    assert outcome["status"] == "needs_input"
    assert outcome["planning_state"] is None
    assert "no available wardrobe or affordable catalog match" in outcome["message"]


def test_nebius_can_interpret_feedback_before_deterministic_revision():
    dataset, state = coastal_plan()

    class FakeNebiusModel:
        def generate_structured(self, **kwargs):
            return PlanFeedbackIntent(
                action="replace_item",
                target_category="bottom",
                desired_terms=["shorts"],
                avoided_terms=["denim", "jeans"],
                interpretation="Replace denim jeans with shorts.",
                memory_text="Maya prefers shorts instead of denim for beach outings.",
            )

    outcome = refine_plan(
        dataset,
        state,
        "I want shorts, not denim jeans.",
        "event_coastal_outing",
        "member_maya",
        backend="nebius",
        model=FakeNebiusModel(),
    )

    assert outcome["status"] == "applied"
    assert outcome["interpreter"] == "nebius"
    assert outcome["planning_state"]["final_result"]["workflow_metrics"][
        "refinement_interpreter"
    ] == "nebius"
