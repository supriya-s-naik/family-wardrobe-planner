from pathlib import Path

from wardrobe_planner.adapters.sqlite_store import SQLiteApplicationStore
from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.domain.models import Event, WardrobeItem, WeatherSnapshot
from wardrobe_planner.workflow.graph import run_demo_workflow

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


def initialized_store(tmp_path):
    seed = load_seed_dataset(SEED_DIR)
    store = SQLiteApplicationStore(tmp_path / "wardrobe.db")
    store.initialize(seed)
    return store, seed


def test_seed_data_is_loaded_idempotently(tmp_path):
    store, seed = initialized_store(tmp_path)

    store.initialize(seed)
    dataset = store.load_dataset(seed)

    assert len(dataset.wardrobe_items) == 31
    assert len(dataset.events) == 3
    assert len(dataset.weather) == 3


def test_added_item_and_image_survive_a_new_store_instance(tmp_path):
    store, seed = initialized_store(tmp_path)
    item = WardrobeItem(
        id="added_floral_dress",
        member_id="member_maya",
        name="Coral floral dress",
        category="one_piece",
        color="coral",
        formality="smart_casual",
        seasons=["spring", "summer"],
        warmth="light",
        occasion_tags=["outing", "brunch"],
        image_path="sqlite_upload",
    )
    image_bytes = b"example-image"
    store.save_wardrobe_item(
        item,
        image_bytes=image_bytes,
        image_media_type="image/png",
    )

    restarted_store = SQLiteApplicationStore(store.database_path)
    restarted_store.initialize(seed)
    restarted_dataset = restarted_store.load_dataset(seed)

    assert next(row for row in restarted_dataset.wardrobe_items if row.id == item.id) == item
    assert restarted_store.get_wardrobe_image(item.id) == image_bytes


def test_availability_change_survives_seed_reinitialization(tmp_path):
    store, seed = initialized_store(tmp_path)

    updated = store.set_wardrobe_item_availability("maya_shoe_02", False)
    store.initialize(seed)
    dataset = store.load_dataset(seed)

    assert updated.available is False
    assert next(item for item in dataset.wardrobe_items if item.id == "maya_shoe_02").available is False


def test_added_event_and_weather_survive_a_new_store_instance(tmp_path):
    store, seed = initialized_store(tmp_path)
    weather = WeatherSnapshot(
        key="weather_added_event",
        condition="mild and dry",
        high_f=72,
        low_f=55,
        precipitation_probability=5,
        wind_mph=7,
    )
    event = Event(
        id="added_event",
        household_id=seed.household.id,
        name="Family birthday dinner",
        date="2026-11-02",
        location="San Jose, California",
        participant_ids=[member.id for member in seed.family_members],
        event_type="birthday dinner",
        dress_code="smart_casual",
        setting="indoor",
        activities=["dinner", "photos"],
        weather_key=weather.key,
    )
    store.save_event(event, weather)

    restarted_store = SQLiteApplicationStore(store.database_path)
    restarted_store.initialize(seed)
    restarted_dataset = restarted_store.load_dataset(seed)

    assert next(row for row in restarted_dataset.events if row.id == event.id) == event
    assert next(row for row in restarted_dataset.weather if row.key == weather.key) == weather


def test_saved_plan_survives_restart_and_can_be_found_by_item(tmp_path):
    store, seed = initialized_store(tmp_path)
    seed.demo_request.event_ids = ["event_coastal_outing"]
    planning_state = run_demo_workflow(seed)

    saved_plan = store.save_plan(seed.household.id, planning_state)
    restarted_store = SQLiteApplicationStore(store.database_path)
    restarted_store.initialize(seed)

    loaded_plan = restarted_store.get_saved_plan(saved_plan.id)
    saved_plans = restarted_store.list_saved_plans(seed.household.id)
    affected_plan = restarted_store.find_latest_plan_using_item(
        seed.household.id, "maya_shoe_02"
    )

    assert loaded_plan is not None
    assert loaded_plan.event_ids == ["event_coastal_outing"]
    assert loaded_plan.planning_state["final_result"]["status"] == "valid"
    assert saved_plans[0].id == saved_plan.id
    assert affected_plan is not None
    assert affected_plan.id == saved_plan.id


def test_saved_plan_can_be_deleted_without_deleting_its_replan(tmp_path):
    store, seed = initialized_store(tmp_path)
    seed.demo_request.event_ids = ["event_coastal_outing"]
    planning_state = run_demo_workflow(seed)
    original = store.save_plan(seed.household.id, planning_state)
    replan = store.save_plan(
        seed.household.id,
        planning_state,
        source_plan_id=original.id,
    )

    assert store.delete_saved_plan(seed.household.id, original.id) is True

    assert store.get_saved_plan(original.id) is None
    remaining_replan = store.get_saved_plan(replan.id)
    assert remaining_replan is not None
    assert remaining_replan.source_plan_id is None
    assert store.delete_saved_plan(seed.household.id, original.id) is False


def test_saved_plan_keeps_compact_refinement_provenance_without_chat_history(tmp_path):
    store, seed = initialized_store(tmp_path)
    seed.demo_request.event_ids = ["event_coastal_outing"]
    planning_state = run_demo_workflow(seed)
    planning_state["refinement_history"] = [
        {"user": "Use shorts", "assistant": "Replaced jeans with shorts."}
    ]
    planning_state["refinement"] = {
        "accepted": True,
        "feedback": "Use shorts",
        "event_id": "event_coastal_outing",
        "member_id": "member_maya",
        "removed_item_ids": ["maya_bottom_03"],
        "replacement_item_id": "maya_bottom_04",
        "interpreter": "local",
        "memory_scope": "Similar occasions",
    }

    saved_plan = store.save_plan(seed.household.id, planning_state)
    reopened = store.get_saved_plan(saved_plan.id)

    assert reopened is not None
    assert "refinement_history" not in reopened.planning_state
    assert "refinement" not in reopened.planning_state
    assert reopened.planning_state["refinement_summary"] == {
        "event_id": "event_coastal_outing",
        "member_id": "member_maya",
        "removed_item_ids": ["maya_bottom_03"],
        "replacement_item_id": "maya_bottom_04",
        "interpreter": "local",
        "memory_scope": "Similar occasions",
    }
