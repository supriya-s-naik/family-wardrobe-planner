from __future__ import annotations

from wardrobe_planner.domain.models import (
    CatalogItem,
    Event,
    FamilyMember,
    GuidanceDocument,
    SeedDataset,
    WardrobeItem,
    WeatherSnapshot,
)


class LocalPlanningData:
    """Credential-free adapter used by the first prototype and tests."""

    def __init__(self, dataset: SeedDataset) -> None:
        self.dataset = dataset

    def get_family_profiles(self, member_ids: list[str] | None = None) -> list[FamilyMember]:
        if member_ids is None:
            return self.dataset.family_members
        selected = set(member_ids)
        return [member for member in self.dataset.family_members if member.id in selected]

    def get_events(self, event_ids: list[str]) -> list[Event]:
        selected = set(event_ids)
        return [event for event in self.dataset.events if event.id in selected]

    def search_wardrobe(
        self,
        member_id: str,
        categories: list[str] | None = None,
        must_be_available: bool = True,
        limit: int = 20,
    ) -> list[WardrobeItem]:
        category_set = set(categories or [])
        results = [
            item
            for item in self.dataset.wardrobe_items
            if item.member_id == member_id
            and (not category_set or item.category in category_set)
            and (not must_be_available or item.available)
        ]
        return results[:limit]

    def get_weather(self, weather_key: str) -> WeatherSnapshot:
        for snapshot in self.dataset.weather:
            if snapshot.key == weather_key:
                return snapshot
        raise KeyError(f"Unknown weather key: {weather_key}")

    def search_catalog(self, max_price: float, limit: int = 10) -> list[CatalogItem]:
        return [item for item in self.dataset.catalog_items if item.price <= max_price][:limit]

    def search_guidance(self, query_terms: list[str], limit: int = 4) -> list[GuidanceDocument]:
        terms = {term.lower() for term in query_terms}

        def score(document: GuidanceDocument) -> int:
            haystack = " ".join(
                [
                    document.title,
                    document.text,
                    *document.event_types,
                    *document.dress_codes,
                    *document.season_tags,
                    *document.audience_tags,
                ]
            ).lower()
            return sum(term in haystack for term in terms)

        ranked = sorted(self.dataset.guidance_documents, key=score, reverse=True)
        return [document for document in ranked if score(document) > 0][:limit]

