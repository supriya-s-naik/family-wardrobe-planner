from __future__ import annotations

import json
import time
from pathlib import Path

from pydantic import BaseModel, Field

from wardrobe_planner.adapters.nebius import NebiusModel
from wardrobe_planner.config import Settings
from wardrobe_planner.data.seed_loader import load_seed_dataset

ROOT = Path(__file__).resolve().parents[1]


class MiniOutfit(BaseModel):
    member_id: str
    event_id: str
    item_ids: list[str] = Field(min_length=2)
    rationale: str


def wardrobe_tool_schema() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "search_wardrobe",
            "description": "Find owned wardrobe items for one family member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {
                        "type": "string",
                        "description": "Stable family-member ID",
                    },
                    "categories": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                    "must_be_available": {"type": "boolean"},
                },
                "required": ["member_id", "categories", "must_be_available"],
                "additionalProperties": False,
            },
        },
    }


def weather_tool_schema() -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather for an event using its weather key.",
            "parameters": {
                "type": "object",
                "properties": {"weather_key": {"type": "string"}},
                "required": ["weather_key"],
                "additionalProperties": False,
            },
        },
    }


def main() -> None:
    settings = Settings.from_env()
    model = NebiusModel(settings)
    dataset = load_seed_dataset(ROOT / "data" / "seed")

    print(f"Model: {settings.nebius_model}")

    started = time.perf_counter()
    tool_result = model.choose_tool(
        user_message=(
            "Find Maya's available footwear. Her stable member ID is member_maya."
        ),
        tools=[wardrobe_tool_schema(), weather_tool_schema()],
        expected_tool="search_wardrobe",
    )
    tool_seconds = time.perf_counter() - started
    if tool_result.actual_tool != tool_result.expected_tool:
        raise RuntimeError(
            f"Wrong tool: expected {tool_result.expected_tool}, got {tool_result.actual_tool}"
        )
    if tool_result.arguments.get("member_id") != "member_maya":
        raise RuntimeError(f"Wrong member ID: {tool_result.arguments}")
    print(f"Tool calling: PASS ({tool_seconds:.2f}s)")
    print("Tool arguments:", json.dumps(tool_result.arguments, sort_keys=True))

    maya_items = [
        item.model_dump(mode="json")
        for item in dataset.wardrobe_items
        if item.member_id == "member_maya" and item.available
    ]
    event = next(event for event in dataset.events if event.id == "event_school_celebration")

    started = time.perf_counter()
    structured = model.generate_structured(
        system_prompt=(
            "Create one outfit using only the supplied stable item IDs. "
            "Return output that follows the supplied JSON schema exactly."
        ),
        user_message=json.dumps(
            {
                "member_id": "member_maya",
                "event": event.model_dump(mode="json"),
                "available_items": maya_items,
            }
        ),
        response_model=MiniOutfit,
        schema_name="mini_outfit",
    )
    structured_seconds = time.perf_counter() - started

    valid_ids = {item["id"] for item in maya_items}
    unknown_ids = sorted(set(structured.item_ids) - valid_ids)
    if unknown_ids:
        raise RuntimeError(f"Structured output invented item IDs: {unknown_ids}")
    if structured.member_id != "member_maya" or structured.event_id != event.id:
        raise RuntimeError("Structured output changed the member or event ID")

    print(f"Structured output: PASS ({structured_seconds:.2f}s)")
    print(structured.model_dump_json(indent=2))


if __name__ == "__main__":
    main()

