from __future__ import annotations

from typing import Any, TypedDict


class PlanningState(TypedDict, total=False):
    request: dict[str, Any]
    household_context: dict[str, Any]
    tool_results: list[dict[str, Any]]
    tool_trace: list[dict[str, Any]]
    pending_tool_calls: list[dict[str, Any]]
    candidate_plan: dict[str, Any] | None
    validation_errors: list[str]
    retry_count: int
    tool_call_count: int
    terminal_error: str | None
    final_result: dict[str, Any] | None
