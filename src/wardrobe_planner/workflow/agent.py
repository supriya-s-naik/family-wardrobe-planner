from __future__ import annotations

from typing import Any, Protocol

from wardrobe_planner.domain.plans import OutfitPlan


class PlanningAgent(Protocol):
    backend_name: str

    def next_tool_calls(self, state: dict[str, Any]) -> list[dict[str, Any]]: ...

    def compose_plan(self, state: dict[str, Any]) -> OutfitPlan: ...
