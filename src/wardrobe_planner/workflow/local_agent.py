from __future__ import annotations

from typing import Any

from wardrobe_planner.domain.models import CatalogItem, Event, FamilyMember, WardrobeItem
from wardrobe_planner.domain.plans import OutfitPlan, OutfitSelection, PurchaseRecommendation


class LocalPlanningAgent:
    """Deterministic agent substitute for a reliable, credential-free demo path."""

    backend_name = "local"

    def next_tool_calls(self, state: dict[str, Any]) -> list[dict[str, Any]]:
        call = self._next_tool_call(state)
        return [call] if call is not None else []

    def _next_tool_call(self, state: dict[str, Any]) -> dict[str, Any] | None:
        context = state["household_context"]
        results = state.get("tool_results", [])

        searched_members = {
            result["arguments"]["member_id"]
            for result in results
            if result["name"] == "search_wardrobe"
        }
        for member in context["members"]:
            if member["id"] not in searched_members:
                return {
                    "name": "search_wardrobe",
                    "arguments": {
                        "member_id": member["id"],
                        "categories": [],
                        "must_be_available": True,
                        "limit": 30,
                    },
                    "reason": f"Retrieve available owned items for {member['name']}.",
                }

        searched_weather = {
            result["arguments"]["weather_key"]
            for result in results
            if result["name"] == "get_weather"
        }
        for event in context["events"]:
            if event["weather_key"] not in searched_weather:
                return {
                    "name": "get_weather",
                    "arguments": {"weather_key": event["weather_key"]},
                    "reason": f"Check conditions for {event['name']}.",
                }

        if not any(result["name"] == "search_style_guidance" for result in results):
            terms = [
                term
                for event in context["events"]
                for term in (event["event_type"], event["dress_code"])
            ]
            return {
                "name": "search_style_guidance",
                "arguments": {"query_terms": terms, "limit": 6},
                "reason": "Retrieve guidance for the selected event types and dress codes.",
            }

        if self._needs_rain_purchase(context, results) and not any(
            result["name"] == "search_sample_catalog" for result in results
        ):
            return {
                "name": "search_sample_catalog",
                "arguments": {"max_price": state["request"]["purchase_budget"], "limit": 10},
                "reason": "Fill missing rain-protection gaps within the household budget.",
            }

        return None

    def compose_plan(self, state: dict[str, Any]) -> OutfitPlan:
        context = state["household_context"]
        members = [FamilyMember.model_validate(row) for row in context["members"]]
        events = [Event.model_validate(row) for row in context["events"]]
        wardrobe = self._wardrobe_by_member(state["tool_results"])
        weather = self._weather_by_key(state["tool_results"])
        guidance = self._guidance(state["tool_results"])
        catalog = self._catalog(state["tool_results"])
        excluded_ids = self._excluded_item_ids(state.get("validation_errors", []))
        preferred_ids = set(state["request"].get("preferred_item_ids", []))
        required_ids = set(state["request"].get("required_item_ids", []))

        outfits: list[OutfitSelection] = []
        purchases: list[PurchaseRecommendation] = []
        purchase_ids: set[tuple[str, str]] = set()

        for event in events:
            snapshot = weather[event.weather_key]
            for member in members:
                items = [item for item in wardrobe[member.id] if item.id not in excluded_ids]
                required_item = next((item for item in items if item.id in required_ids), None)
                preferred_item = next((item for item in items if item.id in preferred_ids), None)
                preferred_is_suitable = False
                preference_reason = ""
                if preferred_item is not None:
                    preferred_is_suitable, preference_reason = self._preferred_item_fit(
                        preferred_item, event, snapshot
                    )
                featured_item = required_item or (
                    preferred_item if preferred_is_suitable else None
                )
                selected = self._select_owned_items(items, event, featured_item)
                rationale_parts = [
                    f"Uses {len(selected)} available owned items for {event.dress_code.replace('_', ' ')} conditions."
                ]
                if required_item is not None:
                    rationale_parts.append(
                        f"Includes the required wardrobe item {required_item.name}."
                    )
                elif preferred_item is not None:
                    if preferred_is_suitable:
                        rationale_parts.append(
                            f"Uses the preferred wardrobe item {preferred_item.name}; "
                            f"{preference_reason}."
                        )
                    else:
                        rationale_parts.append(
                            f"Considered {preferred_item.name} but skipped it because "
                            f"{preference_reason}."
                        )

                if (
                    event.setting in {"outdoor", "mixed"}
                    and snapshot["precipitation_probability"] >= 40
                    and not any("rain" in item.occasion_tags for item in selected)
                ):
                    product = self._select_rain_product(catalog, member)
                    if product is not None:
                        key = (product.id, member.id)
                        if key not in purchase_ids:
                            purchases.append(
                                PurchaseRecommendation(
                                    catalog_item_id=product.id,
                                    member_id=member.id,
                                    supports_event_ids=[event.id],
                                    rationale=(
                                        "Adds missing rain protection and coordinates with owned casual pieces."
                                    ),
                                )
                            )
                            purchase_ids.add(key)
                        rationale_parts.append(f"Adds {product.name} for possible showers.")

                matching_guidance = [
                    document["id"]
                    for document in guidance
                    if event.event_type in document["event_types"]
                    or event.dress_code in document["dress_codes"]
                ][:2]
                outfits.append(
                    OutfitSelection(
                        event_id=event.id,
                        member_id=member.id,
                        item_ids=[item.id for item in selected],
                        rationale=" ".join(rationale_parts),
                        guidance_ids=matching_guidance,
                    )
                )

        catalog_by_id = {item.id: item for item in catalog}
        total = sum(catalog_by_id[p.catalog_item_id].price for p in purchases)
        return OutfitPlan(
            household_id=state["request"]["household_id"],
            status="needs_review",
            outfits=outfits,
            purchases=purchases,
            total_purchase_cost=total,
            summary=(
                "A coordinated three-event plan that prioritizes owned pieces and fills only "
                "the rain-protection gaps."
            ),
        )

    def _needs_rain_purchase(self, context: dict[str, Any], results: list[dict[str, Any]]) -> bool:
        weather = self._weather_by_key(results)
        wardrobe = self._wardrobe_by_member(results)
        rainy_events = [
            event
            for event in context["events"]
            if weather.get(event["weather_key"], {}).get("precipitation_probability", 0) >= 40
        ]
        if not rainy_events:
            return False
        return any(
            not any("rain" in item.occasion_tags for item in wardrobe.get(member["id"], []))
            for member in context["members"]
        )

    @staticmethod
    def _wardrobe_by_member(results: list[dict[str, Any]]) -> dict[str, list[WardrobeItem]]:
        return {
            result["arguments"]["member_id"]: [
                WardrobeItem.model_validate(row) for row in result["result"]
            ]
            for result in results
            if result["name"] == "search_wardrobe"
        }

    @staticmethod
    def _weather_by_key(results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {
            result["arguments"]["weather_key"]: result["result"]
            for result in results
            if result["name"] == "get_weather"
        }

    @staticmethod
    def _guidance(results: list[dict[str, Any]]) -> list[dict[str, Any]]:
        for result in results:
            if result["name"] == "search_style_guidance":
                return result["result"]
        return []

    @staticmethod
    def _catalog(results: list[dict[str, Any]]) -> list[CatalogItem]:
        for result in results:
            if result["name"] == "search_sample_catalog":
                return [CatalogItem.model_validate(row) for row in result["result"]]
        return []

    @staticmethod
    def _excluded_item_ids(errors: list[str]) -> set[str]:
        return {
            token
            for error in errors
            for token in error.replace(":", " ").replace(",", " ").split()
            if token.startswith(("maya_", "arjun_", "anaya_"))
        }

    @staticmethod
    def _select_owned_items(
        items: list[WardrobeItem],
        event: Event,
        featured_item: WardrobeItem | None = None,
    ) -> list[WardrobeItem]:
        def first(category: str, formalities: tuple[str, ...]) -> WardrobeItem | None:
            for formality in formalities:
                for item in items:
                    if item.category == category and item.formality == formality:
                        return item
            return None

        if event.dress_code == "festive":
            priorities = ("festive", "smart_casual")
        elif event.dress_code == "smart_casual":
            priorities = ("smart_casual", "formal", "casual")
        else:
            priorities = ("casual", "smart_casual")

        selected: list[WardrobeItem] = []

        def add(item: WardrobeItem | None) -> None:
            if item is not None and item.id not in {selected_item.id for selected_item in selected}:
                selected.append(item)

        if featured_item is not None and featured_item.category == "one_piece":
            add(featured_item)
        elif featured_item is not None and featured_item.category in {"top", "bottom"}:
            add(featured_item)
            counterpart = "bottom" if featured_item.category == "top" else "top"
            add(first(counterpart, priorities))
        else:
            one_piece = first("one_piece", priorities)
            if one_piece:
                add(one_piece)
            else:
                for category in ("top", "bottom"):
                    add(first(category, priorities))

        if featured_item is not None and featured_item.category == "footwear":
            add(featured_item)
        else:
            add(first("footwear", priorities))

        if event.dress_code == "festive":
            add(first("accessory", priorities))
        elif event.dress_code == "smart_casual":
            add(first("outerwear", priorities))
        elif event.setting in {"outdoor", "mixed"}:
            rainy_outerwear = next(
                (
                    item
                    for item in items
                    if item.category == "outerwear" and "rain" in item.occasion_tags
                ),
                None,
            )
            add(rainy_outerwear)

        if featured_item is not None and featured_item.category in {"outerwear", "accessory"}:
            add(featured_item)

        return selected

    @staticmethod
    def _preferred_item_fit(
        item: WardrobeItem,
        event: Event,
        weather: dict[str, Any],
    ) -> tuple[bool, str]:
        if event.dress_code != "festive" and item.formality == "festive":
            return False, f"its festive style does not match the {event.dress_code} dress code"
        month_to_season = {
            1: "winter",
            2: "winter",
            3: "spring",
            4: "spring",
            5: "spring",
            6: "summer",
            7: "summer",
            8: "summer",
            9: "fall",
            10: "fall",
            11: "fall",
            12: "winter",
        }
        expected_season = month_to_season[event.date.month]
        high_f = int(weather.get("high_f", 70))
        if high_f >= 78:
            expected_season = "summer"
        elif high_f <= 48:
            expected_season = "winter"
        if expected_season not in item.seasons:
            seasons = "/".join(item.seasons)
            return False, f"its {seasons} season profile does not match {expected_season} conditions"
        return True, f"it matches the {event.dress_code} dress code and {expected_season} conditions"

    @staticmethod
    def _select_rain_product(
        catalog: list[CatalogItem], member: FamilyMember
    ) -> CatalogItem | None:
        for item in catalog:
            if "rain" in item.occasion_tags and item.intended_age_group in {
                member.age_group,
                "any",
            }:
                return item
        return None
