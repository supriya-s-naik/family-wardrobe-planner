from __future__ import annotations

from collections import Counter

from wardrobe_planner.domain.models import SeedDataset
from wardrobe_planner.domain.plans import OutfitPlan


def validate_plan(plan: OutfitPlan, dataset: SeedDataset, event_ids: list[str]) -> list[str]:
    errors: list[str] = []
    items = {item.id: item for item in dataset.wardrobe_items}
    events = {event.id: event for event in dataset.events if event.id in set(event_ids)}
    members = {member.id: member for member in dataset.family_members}
    catalog = {item.id: item for item in dataset.catalog_items}

    expected_pairs = {
        (event.id, member_id)
        for event in events.values()
        for member_id in event.participant_ids
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

    for outfit in plan.outfits:
        selected_categories: set[str] = set()
        member = members.get(outfit.member_id)
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
    if plan.household_id != dataset.household.id:
        errors.append(f"Wrong household ID: {plan.household_id}")

    return errors

