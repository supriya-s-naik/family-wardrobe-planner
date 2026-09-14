from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from wardrobe_planner.domain.models import (
    CatalogItem,
    DemoRequest,
    Event,
    FamilyMember,
    GuidanceDocument,
    Household,
    SeedDataset,
    WardrobeItem,
    WeatherSnapshot,
)


def _read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def load_seed_dataset(seed_dir: str | Path) -> SeedDataset:
    root = Path(seed_dir)
    dataset = SeedDataset(
        household=Household.model_validate(_read_json(root / "household.json")),
        family_members=[
            FamilyMember.model_validate(row) for row in _read_json(root / "family_members.json")
        ],
        wardrobe_items=[
            WardrobeItem.model_validate(row) for row in _read_json(root / "wardrobe.json")
        ],
        events=[Event.model_validate(row) for row in _read_json(root / "events.json")],
        weather=[
            WeatherSnapshot.model_validate(row) for row in _read_json(root / "weather.json")
        ],
        catalog_items=[
            CatalogItem.model_validate(row) for row in _read_json(root / "catalog.json")
        ],
        guidance_documents=[
            GuidanceDocument.model_validate(row)
            for row in _read_json(root / "guidance.json")
        ],
        demo_request=DemoRequest.model_validate(_read_json(root / "demo_request.json")),
    )
    validate_references(dataset)
    return dataset


def validate_references(dataset: SeedDataset) -> None:
    def require_unique(label: str, values: list[str]) -> None:
        duplicates = sorted({value for value in values if values.count(value) > 1})
        if duplicates:
            raise ValueError(f"Duplicate {label} IDs: {duplicates}")

    household_id = dataset.household.id
    member_ids = [member.id for member in dataset.family_members]
    item_ids = [item.id for item in dataset.wardrobe_items]
    event_ids = [event.id for event in dataset.events]
    weather_keys = [snapshot.key for snapshot in dataset.weather]

    require_unique("member", member_ids)
    require_unique("wardrobe item", item_ids)
    require_unique("event", event_ids)
    require_unique("weather", weather_keys)
    require_unique("catalog item", [item.id for item in dataset.catalog_items])
    require_unique("guidance document", [doc.id for doc in dataset.guidance_documents])

    if any(member.household_id != household_id for member in dataset.family_members):
        raise ValueError("Every family member must belong to the seeded household")

    member_id_set = set(member_ids)
    unknown_owners = sorted(
        {item.member_id for item in dataset.wardrobe_items if item.member_id not in member_id_set}
    )
    if unknown_owners:
        raise ValueError(f"Wardrobe items reference unknown members: {unknown_owners}")

    weather_key_set = set(weather_keys)
    for event in dataset.events:
        if event.household_id != household_id:
            raise ValueError(f"Event {event.id} belongs to another household")
        unknown_participants = sorted(set(event.participant_ids) - member_id_set)
        if unknown_participants:
            raise ValueError(f"Event {event.id} has unknown participants: {unknown_participants}")
        if event.weather_key not in weather_key_set:
            raise ValueError(f"Event {event.id} references missing weather: {event.weather_key}")

    if dataset.demo_request.household_id != household_id:
        raise ValueError("Demo request belongs to another household")
    unknown_events = sorted(set(dataset.demo_request.event_ids) - set(event_ids))
    if unknown_events:
        raise ValueError(f"Demo request references unknown events: {unknown_events}")
    requested_item_ids = {
        *dataset.demo_request.preferred_item_ids,
        *dataset.demo_request.required_item_ids,
    }
    unknown_requested_items = sorted(requested_item_ids - set(item_ids))
    if unknown_requested_items:
        raise ValueError(
            f"Demo request references unknown wardrobe items: {unknown_requested_items}"
        )
    overlapping_requests = sorted(
        set(dataset.demo_request.preferred_item_ids)
        & set(dataset.demo_request.required_item_ids)
    )
    if overlapping_requests:
        raise ValueError(
            f"Wardrobe items cannot be both preferred and required: {overlapping_requests}"
        )
    if dataset.demo_request.purchase_budget > dataset.household.planning_budget:
        raise ValueError("Demo request budget exceeds the household planning budget")
