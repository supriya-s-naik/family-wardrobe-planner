from pathlib import Path

from wardrobe_planner.adapters.local import LocalPlanningData
from wardrobe_planner.data.seed_loader import load_seed_dataset

SEED_DIR = Path(__file__).resolve().parents[1] / "data" / "seed"


def test_seed_dataset_has_demo_scope() -> None:
    dataset = load_seed_dataset(SEED_DIR)

    assert len(dataset.family_members) == 3
    assert len(dataset.wardrobe_items) == 31
    assert len(dataset.events) == 3
    assert set(dataset.demo_request.event_ids) == {event.id for event in dataset.events}


def test_local_wardrobe_search_is_scoped_and_available() -> None:
    adapter = LocalPlanningData(load_seed_dataset(SEED_DIR))

    results = adapter.search_wardrobe("member_maya", categories=["footwear"])

    assert results
    assert all(item.member_id == "member_maya" for item in results)
    assert all(item.category == "footwear" for item in results)
    assert all(item.available for item in results)


def test_every_event_has_seeded_weather() -> None:
    dataset = load_seed_dataset(SEED_DIR)
    adapter = LocalPlanningData(dataset)

    snapshots = [adapter.get_weather(event.weather_key) for event in dataset.events]

    assert len(snapshots) == len(dataset.events)
    assert all(snapshot.source == "seeded" for snapshot in snapshots)
