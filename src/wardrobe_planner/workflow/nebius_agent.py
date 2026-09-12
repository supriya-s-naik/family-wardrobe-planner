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
        if any(
            result["name"] == "prepare_planning_context"
            for result in state.get("tool_results", [])
        ):
            return []

        return [
            {
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
            },
        ]

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
                "catalog tool. Respect member preferences, event conditions, and the total "
                "purchase budget. Use guidance IDs only when those records were retrieved. "
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
