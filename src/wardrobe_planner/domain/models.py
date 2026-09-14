from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field


class Household(BaseModel):
    id: str
    name: str
    planning_budget: float = Field(ge=0)
    currency: str = "USD"


class FamilyMember(BaseModel):
    id: str
    household_id: str
    name: str
    age_group: Literal["adult", "child", "teen"]
    sizes: dict[str, str]
    preferred_colors: list[str]
    avoided_colors: list[str] = Field(default_factory=list)
    avoided_styles: list[str] = Field(default_factory=list)
    comfort_needs: list[str] = Field(default_factory=list)
    cultural_preferences: list[str] = Field(default_factory=list)
    repeat_tolerance: Literal["low", "medium", "high"] = "medium"


class WardrobeItem(BaseModel):
    id: str
    member_id: str
    name: str
    category: Literal["top", "bottom", "one_piece", "outerwear", "footwear", "accessory"]
    color: str
    formality: Literal["casual", "smart_casual", "formal", "festive"]
    seasons: list[Literal["spring", "summer", "fall", "winter"]]
    warmth: Literal["light", "medium", "warm"]
    occasion_tags: list[str]
    available: bool = True
    image_path: str | None = None
    notes: str | None = None


class WardrobeImageAnalysis(BaseModel):
    name: str
    category: Literal["top", "bottom", "one_piece", "outerwear", "footwear", "accessory"]
    color: str
    formality: Literal["casual", "smart_casual", "formal", "festive"]
    seasons: list[Literal["spring", "summer", "fall", "winter"]]
    warmth: Literal["light", "medium", "warm"]
    occasion_tags: list[str]
    description: str
    confidence: float = Field(ge=0, le=1)


class Event(BaseModel):
    id: str
    household_id: str
    name: str
    date: date
    location: str
    participant_ids: list[str] = Field(min_length=1)
    event_type: str
    dress_code: Literal["casual", "smart_casual", "formal", "festive"]
    setting: Literal["indoor", "outdoor", "mixed"]
    activities: list[str]
    weather_key: str
    notes: str | None = None


class WeatherSnapshot(BaseModel):
    key: str
    condition: str
    high_f: int
    low_f: int
    precipitation_probability: int = Field(ge=0, le=100)
    wind_mph: int = Field(ge=0)
    source: Literal["seeded", "live"] = "seeded"


class CatalogItem(BaseModel):
    id: str
    name: str
    category: str
    intended_age_group: Literal["adult", "child", "any"]
    color: str
    price: float = Field(ge=0)
    formality: Literal["casual", "smart_casual", "formal", "festive"]
    compatible_colors: list[str]
    occasion_tags: list[str]
    source: str = "sample_catalog"


class GuidanceDocument(BaseModel):
    id: str
    title: str
    source: str
    text: str
    event_types: list[str]
    dress_codes: list[str]
    season_tags: list[str]
    audience_tags: list[str]


class DemoRequest(BaseModel):
    household_id: str
    event_ids: list[str] = Field(min_length=1)
    user_message: str
    purchase_budget: float = Field(ge=0)


class SeedDataset(BaseModel):
    household: Household
    family_members: list[FamilyMember]
    wardrobe_items: list[WardrobeItem]
    events: list[Event]
    weather: list[WeatherSnapshot]
    catalog_items: list[CatalogItem]
    guidance_documents: list[GuidanceDocument]
    demo_request: DemoRequest
