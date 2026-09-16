from __future__ import annotations

import json
from typing import Any

from wardrobe_planner.adapters.nebius import NebiusModel
from wardrobe_planner.domain.plans import OutfitPlan


class NebiusPlanningAgent:
    """Nebius-backed planner that submits a typed plan for deterministic validation."""

    backend_name = "nebius"

    def __init__(self, model: NebiusModel | None = None) -> None:
        self.model = model or NebiusModel()

    def next_tool_calls(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        results = state.get("tool_results", [])
        if not any(result["name"] == "prepare_planning_context" for result in results):
            return [{
                "name": "prepare_planning_context",
                "arguments": {
                    "member_ids": [
                        member["id"] for member in state["household_context"]["members"]
                    ],
                    "event_ids": [event["id"] for event in state["household_context"]["events"]],
                    "purchase_budget": state["request"]["purchase_budget"],
                },
                "reason": (
                    "The controlled workflow gathers all authoritative context before autonomous "
                    "plan generation."
                ),
                "actor": "workflow",
            }]
        if not any(result["name"] == "search_memories" for result in results):
            events = state["household_context"]["events"]
            event_context = ", ".join(
                f"{event['name']} {event['dress_code']} {event['setting']} "
                + " ".join(event["activities"])
                for event in events
            )
            return [{
                "name": "search_memories",
                "arguments": {
                    "member_ids": [
                        member["id"] for member in state["household_context"]["members"]
                    ],
                    "query": (
                        "Relevant clothing, footwear, color, comfort, cultural, and outfit "
                        f"repeat preferences for: {event_context}"
                    ),
                    "limit_per_member": 5,
                },
                "reason": "Recall durable preferences for each participating family member.",
                "actor": "workflow",
            }]
        return []

    def compose_plan(self, state: dict[str, Any]) -> OutfitPlan:
        payload = {
            "planning_request": state["request"],
            "household_context": state["household_context"],
            "tool_results": state.get("tool_results", []),
            "validation_errors_to_repair": state.get("validation_errors", []),
        }
        result = self.model.generate_via_tool(
            system_prompt=(
                "You are a family wardrobe planning agent. Create one complete outfit for every "
                "event/participant pair. Use only stable wardrobe item IDs returned by tools. "
                "Prefer owned items. Reference a catalog item only when it was returned by the "
                "catalog tool. Match core clothing formality to each event. Never use festive "
                "items for casual or smart-casual events. For outdoor walking, prefer items "
                "tagged for outings, travel, walking, or rain and choose comfortable footwear. "
                "Treat preferred_item_ids as a soft preference: use them when suitable, and if "
                "one is skipped, explain the event-fit reason in that member's outfit rationale. "
                "Treat required_item_ids as a hard constraint: include each item in its owner's "
                "outfit for every selected event that owner attends. "
                "Apply retrieved memories only to the member_id attached to each memory. Treat "
                "them as soft preferences; the current request and authoritative constraints "
                "take precedence. Mention an applied memory in the outfit rationale. "
                "Respect member preferences, event conditions, and the total purchase budget. "
                "Follow the retrieved guidance and cite at least one retrieved guidance ID in "
                "every outfit. Use only guidance IDs that were actually retrieved. "
                "Address every supplied validation error. Call submit_outfit_plan exactly once "
                "with the complete plan. Set status to needs_review; deterministic validation "
                "sets the final status."
            ),
            user_message=json.dumps(payload, separators=(",", ":")),
            response_model=OutfitPlan,
            tool_name="submit_outfit_plan",
            tool_description=(
                "Submit the complete family outfit plan for deterministic policy validation."
            ),
        )
        return OutfitPlan.model_validate(result)
