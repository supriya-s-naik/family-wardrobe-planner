from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class OutfitSelection(BaseModel):
    event_id: str
    member_id: str
    item_ids: list[str] = Field(min_length=1)
    rationale: str
    guidance_ids: list[str] = Field(default_factory=list)


class PurchaseRecommendation(BaseModel):
    catalog_item_id: str
    member_id: str
    supports_event_ids: list[str] = Field(min_length=1)
    rationale: str


class OutfitPlan(BaseModel):
    household_id: str
    status: Literal["valid", "needs_review"]
    outfits: list[OutfitSelection] = Field(min_length=1)
    purchases: list[PurchaseRecommendation] = Field(default_factory=list)
    total_purchase_cost: float = Field(ge=0)
    summary: str


class SavedPlan(BaseModel):
    id: str
    household_id: str
    event_ids: list[str] = Field(min_length=1)
    purchase_budget: float = Field(ge=0)
    planning_state: dict[str, Any]
    created_at: datetime
    source_plan_id: str | None = None


class ToolSmokeResult(BaseModel):
    expected_tool: str
    actual_tool: str
    arguments: dict[str, object]
