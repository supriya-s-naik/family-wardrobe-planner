from __future__ import annotations

from typing import Any

from wardrobe_planner.adapters.local import LocalPlanningData

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "prepare_planning_context",
            "description": (
                "Retrieve all authoritative wardrobe, event weather, style guidance, and "
                "budget-compatible catalog context required for one family plan."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "member_ids": {"type": "array", "items": {"type": "string"}},
                    "event_ids": {"type": "array", "items": {"type": "string"}},
                    "purchase_budget": {"type": "number", "minimum": 0},
                },
                "required": ["member_ids", "event_ids", "purchase_budget"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_wardrobe",
            "description": "Find available owned items for one family member.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_id": {"type": "string"},
                    "categories": {
                        "type": "array",
                        "description": "Empty means all categories.",
                        "items": {
                            "type": "string",
                            "enum": [
                                "top",
                                "bottom",
                                "one_piece",
                                "outerwear",
                                "footwear",
                                "accessory",
                            ],
                        },
                    },
                    "must_be_available": {"type": "boolean"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 30},
                },
                "required": ["member_id", "categories", "must_be_available", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_weather",
            "description": "Get weather conditions for an event using its weather key.",
            "parameters": {
                "type": "object",
                "properties": {"weather_key": {"type": "string"}},
                "required": ["weather_key"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_style_guidance",
            "description": "Retrieve relevant style and dress-code guidance.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query_terms": {"type": "array", "items": {"type": "string"}},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 6},
                },
                "required": ["query_terms", "limit"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_sample_catalog",
            "description": "Find sample products within the remaining purchase budget.",
            "parameters": {
                "type": "object",
                "properties": {
                    "max_price": {"type": "number", "minimum": 0},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 20},
                },
                "required": ["max_price", "limit"],
                "additionalProperties": False,
            },
        },
    },
]


class ToolExecutor:
    def __init__(self, data: LocalPlanningData) -> None:
        self.data = data

    def execute(self, name: str, arguments: dict[str, Any]) -> list[dict[str, Any]] | dict[str, Any]:
        if name == "prepare_planning_context":
            event_ids = [str(event_id) for event_id in arguments["event_ids"]]
            member_ids = [str(member_id) for member_id in arguments["member_ids"]]
            events = self.data.get_events(event_ids)
            if {event.id for event in events} != set(event_ids):
                raise ValueError("Planning context requested an unknown event ID")
            members = self.data.get_family_profiles(member_ids)
            if {member.id for member in members} != set(member_ids):
                raise ValueError("Planning context requested an unknown member ID")
            query_terms = [
                term for event in events for term in (event.event_type, event.dress_code)
            ]
            return {
                "wardrobe_by_member": {
                    member.id: [
                        item.model_dump(mode="json")
                        for item in self.data.search_wardrobe(member.id, limit=30)
                    ]
                    for member in members
                },
                "weather_by_event": {
                    event.id: self.data.get_weather(event.weather_key).model_dump(mode="json")
                    for event in events
                },
                "guidance": [
                    document.model_dump(mode="json")
                    for document in self.data.search_guidance(query_terms, limit=6)
                ],
                "catalog": [
                    item.model_dump(mode="json")
                    for item in self.data.search_catalog(
                        max_price=float(arguments["purchase_budget"]), limit=10
                    )
                ],
            }
        if name == "search_wardrobe":
            aliases = {"shoe": "footwear", "shoes": "footwear"}
            categories = [
                aliases.get(str(category).lower(), str(category).lower())
                for category in arguments.get("categories") or []
            ]
            results = self.data.search_wardrobe(
                member_id=str(arguments["member_id"]),
                categories=categories,
                must_be_available=bool(arguments.get("must_be_available", True)),
                limit=int(arguments.get("limit", 20)),
            )
            return [item.model_dump(mode="json") for item in results]
        if name == "get_weather":
            return self.data.get_weather(str(arguments["weather_key"])).model_dump(mode="json")
        if name == "search_style_guidance":
            results = self.data.search_guidance(
                query_terms=list(arguments["query_terms"]),
                limit=int(arguments.get("limit", 4)),
            )
            return [document.model_dump(mode="json") for document in results]
        if name == "search_sample_catalog":
            results = self.data.search_catalog(
                max_price=float(arguments["max_price"]),
                limit=int(arguments.get("limit", 10)),
            )
            return [item.model_dump(mode="json") for item in results]
        raise ValueError(f"Unknown tool: {name}")
