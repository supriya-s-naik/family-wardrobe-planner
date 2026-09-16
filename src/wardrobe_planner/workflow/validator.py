from __future__ import annotations

from collections import Counter

from wardrobe_planner.domain.models import SeedDataset
from wardrobe_planner.domain.plans import OutfitPlan, PurchaseRecommendation


def validate_plan(
    plan: OutfitPlan,
    dataset: SeedDataset,
    event_ids: list[str],
    retrieved_guidance_ids: set[str] | None = None,
    required_item_ids: set[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    items = {item.id: item for item in dataset.wardrobe_items}
    events = {event.id: event for event in dataset.events if event.id in set(event_ids)}
    members = {member.id: member for member in dataset.family_members}
    catalog = {item.id: item for item in dataset.catalog_items}
    weather_by_key = {snapshot.key: snapshot for snapshot in dataset.weather}

    expected_pairs = {
        (event.id, member_id) for event in events.values() for member_id in event.participant_ids
    }
    actual_pairs = [(outfit.event_id, outfit.member_id) for outfit in plan.outfits]
    pair_counts = Counter(actual_pairs)

    missing = sorted(expected_pairs - set(actual_pairs))
    unexpected = sorted(set(actual_pairs) - expected_pairs)
    duplicates = sorted(pair for pair, count in pair_counts.items() if count > 1)
    if missing:
        errors.append(f"Missing event/member outfits: {missing}")
    if unexpected:
        errors.append(f"Unexpected event/member outfits: {unexpected}")
    if duplicates:
        errors.append(f"Duplicate event/member outfits: {duplicates}")

    for item_id in sorted(required_item_ids or set()):
        item = items.get(item_id)
        if item is None:
            errors.append(f"Unknown required wardrobe item: {item_id}")
            continue
        applicable_events = [
            event for event in events.values() if item.member_id in event.participant_ids
        ]
        if not applicable_events:
            errors.append(
                f"Required item {item_id} belongs to a member who is not attending selected events"
            )
            continue
        for event in applicable_events:
            matching_outfit = next(
                (
                    outfit
                    for outfit in plan.outfits
                    if outfit.event_id == event.id and outfit.member_id == item.member_id
                ),
                None,
            )
            if matching_outfit is None or item_id not in matching_outfit.item_ids:
                errors.append(
                    f"Required wardrobe item {item_id} missing from "
                    f"{event.id}/{item.member_id}"
                )

    for outfit in plan.outfits:
        selected_categories: set[str] = set()
        member = members.get(outfit.member_id)
        event = events.get(outfit.event_id)
        for item_id in outfit.item_ids:
            item = items.get(item_id)
            if item is None:
                errors.append(f"Unknown wardrobe item: {item_id}")
                continue
            selected_categories.add(item.category)
            if item.member_id != outfit.member_id:
                errors.append(f"Wrong owner for item {item_id}: expected {outfit.member_id}")
            if not item.available:
                errors.append(f"Unavailable wardrobe item: {item_id}")
            if event is not None and event.dress_code != "festive" and item.formality == "festive":
                errors.append(
                    f"Formality mismatch: festive item {item_id} used for "
                    f"{event.dress_code} event {event.id}"
                )
            if member is not None:
                searchable = f"{item.name} {item.color} {item.notes or ''}".lower()
                for avoided in [*member.avoided_colors, *member.avoided_styles]:
                    if avoided.lower() in searchable:
                        errors.append(f"Avoided preference '{avoided}' used in item {item_id}")
        if "one_piece" not in selected_categories and not {"top", "bottom"}.issubset(
            selected_categories
        ):
            errors.append(f"Incomplete clothing for {outfit.event_id}/{outfit.member_id}")
        if "footwear" not in selected_categories:
            errors.append(f"Missing footwear for {outfit.event_id}/{outfit.member_id}")
        if retrieved_guidance_ids is not None:
            if not outfit.guidance_ids:
                errors.append(f"Missing guidance citation for {outfit.event_id}/{outfit.member_id}")
            unknown_guidance = sorted(set(outfit.guidance_ids) - retrieved_guidance_ids)
            if unknown_guidance:
                errors.append(
                    f"Outfit {outfit.event_id}/{outfit.member_id} cites guidance that was not "
                    f"retrieved: {unknown_guidance}"
                )

    purchase_total = 0.0
    for purchase in plan.purchases:
        product = catalog.get(purchase.catalog_item_id)
        if product is None:
            errors.append(f"Unknown catalog item: {purchase.catalog_item_id}")
            continue
        purchase_total += product.price
        member = members.get(purchase.member_id)
        if member is None:
            errors.append(f"Unknown purchase recipient: {purchase.member_id}")
        elif product.intended_age_group not in {member.age_group, "any"}:
            errors.append(
                f"Catalog item {product.id} is not suitable for {purchase.member_id}'s age group"
            )
        unsupported_events = sorted(set(purchase.supports_event_ids) - set(events))
        if unsupported_events:
            errors.append(f"Purchase {product.id} references unknown events: {unsupported_events}")

    if round(purchase_total, 2) != round(plan.total_purchase_cost, 2):
        errors.append(
            f"Purchase total mismatch: expected {purchase_total:.2f}, got {plan.total_purchase_cost:.2f}"
        )
    budget = dataset.demo_request.purchase_budget
    if purchase_total > budget:
        errors.append(f"Purchase budget exceeded: {purchase_total:.2f} > {budget:.2f}")

    for outfit in plan.outfits:
        event = events.get(outfit.event_id)
        member = members.get(outfit.member_id)
        if event is None or member is None or event.setting not in {"outdoor", "mixed"}:
            continue
        weather = weather_by_key.get(event.weather_key)
        if weather is None or weather.precipitation_probability < 40:
            continue
        has_owned_rain_protection = any(
            item_id in items and "rain" in items[item_id].occasion_tags
            for item_id in outfit.item_ids
        )
        has_purchased_rain_protection = any(
            purchase.member_id == outfit.member_id
            and event.id in purchase.supports_event_ids
            and purchase.catalog_item_id in catalog
            and "rain" in catalog[purchase.catalog_item_id].occasion_tags
            for purchase in plan.purchases
        )
        if has_owned_rain_protection or has_purchased_rain_protection:
            continue
        affordable_rain_products = sorted(
            (
                product
                for product in catalog.values()
                if "rain" in product.occasion_tags
                and product.intended_age_group in {member.age_group, "any"}
                and purchase_total + product.price <= budget
            ),
            key=lambda product: product.price,
        )
        if affordable_rain_products:
            product = affordable_rain_products[0]
            errors.append(
                f"Missing rain protection for {event.id}/{outfit.member_id}: add an owned "
                f"rain-tagged item or purchase {product.id} ({product.price:.2f}) for this event"
            )
    if plan.household_id != dataset.household.id:
        errors.append(f"Wrong household ID: {plan.household_id}")

    return errors


def repair_affordable_weather_gaps(
    plan: OutfitPlan,
    dataset: SeedDataset,
    event_ids: list[str],
) -> tuple[OutfitPlan, list[dict[str, object]]]:
    """Apply only unambiguous, catalog-backed rain-protection repairs.

    The agent still gets the first two repair attempts. This workflow fallback is intentionally
    narrow: it can reuse or add an age-compatible rain product when the event requires it and the
    purchase stays within budget. All other validation failures remain for human review.
    """

    repaired = plan.model_copy(deep=True)
    items = {item.id: item for item in dataset.wardrobe_items}
    events = {event.id: event for event in dataset.events if event.id in set(event_ids)}
    members = {member.id: member for member in dataset.family_members}
    catalog = {item.id: item for item in dataset.catalog_items}
    weather_by_key = {snapshot.key: snapshot for snapshot in dataset.weather}
    budget = dataset.demo_request.purchase_budget
    purchase_total = sum(
        catalog[purchase.catalog_item_id].price
        for purchase in repaired.purchases
        if purchase.catalog_item_id in catalog
    )
    repairs: list[dict[str, object]] = []

    for outfit in repaired.outfits:
        event = events.get(outfit.event_id)
        member = members.get(outfit.member_id)
        if event is None or member is None or event.setting not in {"outdoor", "mixed"}:
            continue
        weather = weather_by_key.get(event.weather_key)
        if weather is None or weather.precipitation_probability < 40:
            continue
        if any(
            item_id in items and "rain" in items[item_id].occasion_tags
            for item_id in outfit.item_ids
        ):
            continue

        existing_purchase = next(
            (
                purchase
                for purchase in repaired.purchases
                if purchase.member_id == outfit.member_id
                and purchase.catalog_item_id in catalog
                and "rain" in catalog[purchase.catalog_item_id].occasion_tags
            ),
            None,
        )
        if existing_purchase is not None:
            if event.id not in existing_purchase.supports_event_ids:
                existing_purchase.supports_event_ids.append(event.id)
                repairs.append(
                    {
                        "event_id": event.id,
                        "member_id": outfit.member_id,
                        "catalog_item_id": existing_purchase.catalog_item_id,
                        "action": "reuse_purchase",
                        "added_cost": 0.0,
                    }
                )
            continue

        affordable_products = sorted(
            (
                product
                for product in catalog.values()
                if "rain" in product.occasion_tags
                and product.intended_age_group in {member.age_group, "any"}
                and purchase_total + product.price <= budget
            ),
            key=lambda product: (product.price, product.id),
        )
        if not affordable_products:
            continue

        product = affordable_products[0]
        repaired.purchases.append(
            PurchaseRecommendation(
                catalog_item_id=product.id,
                member_id=outfit.member_id,
                supports_event_ids=[event.id],
                rationale=(
                    f"Workflow policy added {product.name} after validation found missing rain "
                    "protection for this outdoor event."
                ),
            )
        )
        purchase_total += product.price
        repairs.append(
            {
                "event_id": event.id,
                "member_id": outfit.member_id,
                "catalog_item_id": product.id,
                "action": "add_purchase",
                "added_cost": product.price,
            }
        )

    repaired.total_purchase_cost = round(purchase_total, 2)
    return repaired, repairs
