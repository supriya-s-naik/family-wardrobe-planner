from __future__ import annotations

from collections.abc import Callable
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
            "name": "search_memories",
            "description": (
                "Retrieve durable clothing, style, and comfort preferences for the selected "
                "family members. Results are isolated by member ID."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "member_ids": {"type": "array", "items": {"type": "string"}},
                    "query": {"type": "string", "minLength": 1},
                    "limit_per_member": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["member_ids", "query", "limit_per_member"],
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
    def __init__(
        self,
        data: LocalPlanningData,
        guidance_search: Callable[[list[str], int, list[str] | None], list[dict[str, Any]]]
        | None = None,
        memory_search: Callable[[str, str, int], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.data = data
        self.guidance_search = guidance_search
        self.memory_search = memory_search

    def execute(
        self, name: str, arguments: dict[str, Any]
    ) -> list[dict[str, Any]] | dict[str, Any]:
        if name == "prepare_planning_context":
            event_ids = [str(event_id) for event_id in arguments["event_ids"]]
            member_ids = [str(member_id) for member_id in arguments["member_ids"]]
            events = self.data.get_events(event_ids)
            if {event.id for event in events} != set(event_ids):
                raise ValueError("Planning context requested an unknown event ID")
            members = self.data.get_family_profiles(member_ids)
            if {member.id for member in members} != set(member_ids):
                raise ValueError("Planning context requested an unknown member ID")
            weather_by_event = {
                event.id: self.data.get_weather(event.weather_key).model_dump(mode="json")
                for event in events
            }
            guidance, retrieval_metadata = self._retrieve_event_guidance(
                events,
                weather_by_event,
            )
            return {
                "wardrobe_by_member": {
                    member.id: [
                        item.model_dump(mode="json")
                        for item in self.data.search_wardrobe(member.id, limit=30)
                    ]
                    for member in members
                },
                "weather_by_event": weather_by_event,
                "guidance": guidance,
                "retrieval_metadata": retrieval_metadata,
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
        if name == "search_memories":
            member_ids = [str(member_id) for member_id in arguments["member_ids"]]
            known_member_ids = {member.id for member in self.data.dataset.family_members}
            unknown_member_ids = sorted(set(member_ids) - known_member_ids)
            if unknown_member_ids:
                raise ValueError(f"Memory search requested unknown member IDs: {unknown_member_ids}")
            query = str(arguments["query"]).strip()
            if not query:
                raise ValueError("Memory search query cannot be empty")
            limit = int(arguments.get("limit_per_member", 5))
            memories_by_member: dict[str, list[dict[str, Any]]] = {
                member_id: [] for member_id in member_ids
            }
            if self.memory_search is None:
                return {
                    "memories_by_member": memories_by_member,
                    "retrieval_metadata": {
                        "provider": "not_configured",
                        "query": query,
                        "match_count": 0,
                        "fallback_used": True,
                        "fallback_reason": "Mem0NotConfigured",
                    },
                }
            try:
                for member_id in member_ids:
                    matches = self.memory_search(member_id, query, limit)
                    memories_by_member[member_id] = [
                        {**match, "member_id": member_id} for match in matches
                    ]
            except Exception as exc:  # noqa: BLE001 -- memory must not block planning.
                return {
                    "memories_by_member": {member_id: [] for member_id in member_ids},
                    "retrieval_metadata": {
                        "provider": "unavailable",
                        "query": query,
                        "match_count": 0,
                        "fallback_used": True,
                        "fallback_reason": type(exc).__name__,
                    },
                }
            return {
                "memories_by_member": memories_by_member,
                "retrieval_metadata": {
                    "provider": "mem0",
                    "query": query,
                    "match_count": sum(len(rows) for rows in memories_by_member.values()),
                    "fallback_used": False,
                },
            }
        if name == "get_weather":
            return self.data.get_weather(str(arguments["weather_key"])).model_dump(mode="json")
        if name == "search_style_guidance":
            results, _ = self._retrieve_guidance(
                query_terms=list(arguments["query_terms"]),
                limit=int(arguments.get("limit", 4)),
            )
            return results
        if name == "search_sample_catalog":
            results = self.data.search_catalog(
                max_price=float(arguments["max_price"]),
                limit=int(arguments.get("limit", 10)),
            )
            return [item.model_dump(mode="json") for item in results]
        raise ValueError(f"Unknown tool: {name}")

    def _retrieve_guidance(
        self,
        query_terms: list[str],
        limit: int,
        dress_codes: list[str] | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        query = "Family wardrobe styling guidance for " + ", ".join(
            str(term).replace("_", " ") for term in query_terms
        )
        if self.guidance_search is not None:
            try:
                matches = self.guidance_search(query_terms, limit, dress_codes)
                return matches, {
                    "provider": "pinecone",
                    "query": query,
                    "match_count": len(matches),
                    "fallback_used": False,
                }
            except Exception as exc:  # noqa: BLE001 -- RAG has a deliberate local fallback.
                fallback_reason = type(exc).__name__
        else:
            fallback_reason = "PineconeNotConfigured"

        local_documents = self.data.search_guidance(
            query_terms,
            limit=len(self.data.dataset.guidance_documents),
        )
        if dress_codes:
            allowed_dress_codes = set(dress_codes)
            local_documents = [
                document
                for document in local_documents
                if allowed_dress_codes.intersection(document.dress_codes)
            ]

        local_matches = [
            {
                **document.model_dump(mode="json"),
                "retrieval_provider": "local_keyword",
                "retrieval_query": query,
                "retrieval_score": None,
            }
            for document in local_documents[:limit]
        ]
        return local_matches, {
            "provider": "local_keyword",
            "query": query,
            "match_count": len(local_matches),
            "fallback_used": self.guidance_search is not None,
            "fallback_reason": fallback_reason,
        }

    def _retrieve_event_guidance(
        self, events: list[Any], weather_by_event: dict[str, dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        matches_by_id: dict[str, dict[str, Any]] = {}
        query_records = []

        for event in events:
            weather = weather_by_event[event.id]
            query_terms = [
                event.name,
                event.event_type,
                event.dress_code,
                event.setting,
                *event.activities,
                event.notes or "",
                weather["condition"],
                f"{weather['high_f']} degree high",
                f"{weather['precipitation_probability']} percent chance of rain",
            ]
            matches, metadata = self._retrieve_guidance(
                query_terms,
                limit=2,
                dress_codes=[event.dress_code],
            )
            query_records.append({"event_id": event.id, **metadata})
            for match in matches:
                existing = matches_by_id.get(match["id"])
                if existing is None or (match.get("retrieval_score") or 0) > (
                    existing.get("retrieval_score") or 0
                ):
                    matches_by_id[match["id"]] = match

        if len(events) > 1:
            matches, metadata = self._retrieve_guidance(
                [
                    "multi-event planning",
                    "outfit reuse",
                    "wardrobe",
                    "gap",
                    "purchase",
                    "shopping",
                    "family",
                ],
                limit=2,
            )
            query_records.append({"event_id": "all_selected_events", **metadata})
            for match in matches:
                matches_by_id.setdefault(match["id"], match)

        providers = {record["provider"] for record in query_records}
        fallback_used = any(record["fallback_used"] for record in query_records)
        return list(matches_by_id.values()), {
            "provider": providers.pop() if len(providers) == 1 else "mixed",
            "queries": query_records,
            "match_count": len(matches_by_id),
            "fallback_used": fallback_used,
            "fallback_reason": next(
                (
                    record.get("fallback_reason")
                    for record in query_records
                    if record.get("fallback_reason")
                ),
                None,
            ),
        }
