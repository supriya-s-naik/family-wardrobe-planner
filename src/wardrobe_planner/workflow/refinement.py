from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal

from pydantic import BaseModel, Field

from wardrobe_planner.adapters.nebius import NebiusModel
from wardrobe_planner.domain.models import CatalogItem, Event, SeedDataset, WardrobeItem
from wardrobe_planner.domain.plans import OutfitPlan
from wardrobe_planner.workflow.validator import validate_plan

WardrobeCategory = Literal[
    "top", "bottom", "one_piece", "outerwear", "footwear", "accessory"
]


class PlanFeedbackIntent(BaseModel):
    """Structured meaning extracted from one plan-refinement message."""

    action: Literal["replace_item", "add_item", "remove_item", "unknown"]
    target_category: WardrobeCategory | None
    desired_terms: list[str] = Field(default_factory=list)
    avoided_terms: list[str] = Field(default_factory=list)
    interpretation: str
    memory_text: str


GARMENT_TERMS: dict[str, tuple[str, tuple[str, ...]]] = {
    "shorts": ("bottom", ("shorts", "short")),
    "jeans": ("bottom", ("jeans", "denim")),
    "trousers": ("bottom", ("trousers", "pants", "chinos")),
    "skirt": ("bottom", ("skirt",)),
    "dress": ("one_piece", ("dress", "gown")),
    "t-shirt": ("top", ("t-shirt", "tee", "t shirt")),
    "shirt": ("top", ("shirt", "blouse", "polo")),
    "sweater": ("top", ("sweater", "jumper")),
    "jacket": ("outerwear", ("jacket", "coat", "shell")),
    "cardigan": ("outerwear", ("cardigan",)),
    "sneakers": ("footwear", ("sneakers", "trainers", "walking shoes")),
    "flats": ("footwear", ("flats", "flat shoes")),
    "boots": ("footwear", ("boots", "boot")),
    "sandals": ("footwear", ("sandals", "sandal")),
    "scarf": ("accessory", ("scarf", "dupatta")),
}


def refine_plan(
    dataset: SeedDataset,
    planning_state: dict[str, Any],
    feedback: str,
    event_id: str,
    member_id: str,
    *,
    backend: Literal["local", "nebius"] = "local",
    model: NebiusModel | None = None,
) -> dict[str, Any]:
    """Interpret feedback and apply a validated, single-outfit revision."""

    text = feedback.strip()
    if not text:
        return _outcome("needs_input", "Describe the change you would like to make.")

    current_result = planning_state.get("final_result") or {}
    if current_result.get("status") != "valid":
        return _outcome("needs_input", "Only a valid plan can be refined.")

    event = next((row for row in dataset.events if row.id == event_id), None)
    member = next((row for row in dataset.family_members if row.id == member_id), None)
    if event is None or member is None or event_id not in planning_state["request"]["event_ids"]:
        return _outcome("needs_input", "Choose a family member and occasion from this plan.")

    current_outfit = next(
        (
            outfit
            for outfit in current_result.get("outfits", [])
            if outfit["event_id"] == event_id and outfit["member_id"] == member_id
        ),
        None,
    )
    if current_outfit is None:
        return _outcome("needs_input", "The selected person has no outfit for that occasion.")

    item_by_id = {item.id: item for item in dataset.wardrobe_items}
    current_items = [
        item_by_id[item_id] for item_id in current_outfit["item_ids"] if item_id in item_by_id
    ]
    intent, interpreter = _interpret_feedback(
        text,
        event,
        member.name,
        current_items,
        backend=backend,
        model=model,
    )
    if intent.action not in {"replace_item", "add_item"} or not intent.desired_terms:
        return _outcome(
            "needs_input",
            "I could not identify the garment you want. Try a request such as "
            "“Replace the denim jeans with shorts.”",
            intent=intent,
            interpreter=interpreter,
        )

    category = intent.target_category or _category_for_terms(intent.desired_terms)
    if category is None:
        return _outcome(
            "needs_input",
            "I understood the preference but could not map it to a wardrobe category.",
            intent=intent,
            interpreter=interpreter,
        )

    selected_ids = set(current_outfit["item_ids"])
    alternatives = [
        item
        for item in dataset.wardrobe_items
        if item.member_id == member_id
        and item.available
        and item.category == category
        and item.id not in selected_ids
        and _matches_any(item, intent.desired_terms)
        and not _matches_any(item, intent.avoided_terms)
        and not (event.dress_code != "festive" and item.formality == "festive")
    ]
    alternatives.sort(key=lambda item: _alternative_score(item, event, intent), reverse=True)

    if not alternatives:
        catalog_matches = _matching_catalog_items(
            dataset,
            member.age_group,
            category,
            intent,
            float(planning_state["request"]["purchase_budget"]),
            float(current_result.get("total_purchase_cost", 0)),
        )
        if catalog_matches:
            product = catalog_matches[0]
            message = (
                f"{member.name} has no available {', '.join(intent.desired_terms)} in the "
                f"wardrobe. The catalog has {product.name} for ${product.price:.0f}; add it to "
                "the wardrobe after purchase before replacing the current item."
            )
        else:
            message = (
                f"{member.name} has no available wardrobe or affordable catalog match for "
                f"{', '.join(intent.desired_terms)}. Add one to the wardrobe or revise the request."
            )
        return _outcome(
            "needs_input",
            message,
            intent=intent,
            interpreter=interpreter,
            catalog_suggestions=[item.model_dump(mode="json") for item in catalog_matches[:3]],
        )

    removable_items = [
        item
        for item in current_items
        if item.category == category and _matches_any(item, intent.avoided_terms)
    ]
    if not removable_items and intent.action == "replace_item":
        removable_items = [item for item in current_items if item.category == category]
    required_ids = set(planning_state["request"].get("required_item_ids", []))
    removable_items = [item for item in removable_items if item.id not in required_ids]
    if intent.action == "replace_item" and not removable_items:
        return _outcome(
            "needs_input",
            "The matching item is required by the current plan or the outfit uses a different "
            "structure. Remove that hard requirement before replacing it.",
            intent=intent,
            interpreter=interpreter,
        )

    replacement = alternatives[0]
    revised_state = deepcopy(planning_state)
    revised_result = deepcopy(current_result)
    revised_outfit = next(
        outfit
        for outfit in revised_result["outfits"]
        if outfit["event_id"] == event_id and outfit["member_id"] == member_id
    )
    removed_ids = [item.id for item in removable_items]
    if removed_ids:
        revised_outfit["item_ids"] = [
            replacement.id if item_id == removed_ids[0] else item_id
            for item_id in revised_outfit["item_ids"]
            if item_id not in set(removed_ids[1:])
        ]
    else:
        revised_outfit["item_ids"].append(replacement.id)
    removed_names = ", ".join(item.name for item in removable_items)
    revised_outfit["rationale"] = (
        revised_outfit["rationale"].rstrip()
        + " User refinement applied: "
        + (f"replaced {removed_names} with {replacement.name}." if removed_names else f"added {replacement.name}.")
        + " Other outfit pieces were preserved."
    )
    revised_result["summary"] = (
        revised_result.get("summary", "Family wardrobe plan.").rstrip(".")
        + f". Refined {member.name}'s outfit for {event.name} from explicit user feedback."
    )

    plan_payload = {
        key: value
        for key, value in revised_result.items()
        if key not in {"validation_errors", "workflow_metrics", "error"}
    }
    revised_plan = OutfitPlan.model_validate(plan_payload)
    validation_dataset = dataset.model_copy(deep=True)
    validation_dataset.demo_request.event_ids = list(planning_state["request"]["event_ids"])
    validation_dataset.demo_request.purchase_budget = float(
        planning_state["request"]["purchase_budget"]
    )
    validation_dataset.demo_request.preferred_item_ids = list(
        planning_state["request"].get("preferred_item_ids", [])
    )
    validation_dataset.demo_request.required_item_ids = list(
        planning_state["request"].get("required_item_ids", [])
    )
    validation_errors = validate_plan(
        revised_plan,
        validation_dataset,
        validation_dataset.demo_request.event_ids,
        retrieved_guidance_ids=_retrieved_guidance_ids(planning_state),
        required_item_ids=set(validation_dataset.demo_request.required_item_ids),
    )
    if validation_errors:
        return _outcome(
            "needs_input",
            "That change could not pass the plan rules: " + validation_errors[0],
            intent=intent,
            interpreter=interpreter,
        )

    revised_plan.status = "valid"
    final_result = revised_plan.model_dump(mode="json")
    final_result["validation_errors"] = []
    metrics = deepcopy(current_result.get("workflow_metrics", {}))
    metrics.update(
        {
            "refinement_interpreter": interpreter,
            "refinement_changes": 1,
            "refinement_tool_calls": 2,
        }
    )
    final_result["workflow_metrics"] = metrics
    revised_state["candidate_plan"] = revised_plan.model_dump(mode="json")
    revised_state["final_result"] = final_result
    revised_state["validation_errors"] = []
    revised_state.pop("saved_plan_id", None)
    revised_state["request"]["user_message"] = (
        revised_state["request"].get("user_message", "").rstrip()
        + f" User refinement: {text}"
    )
    first_step = max(
        (int(record.get("step", 0)) for record in revised_state.get("tool_trace", [])),
        default=0,
    ) + 1
    revised_state["tool_trace"] = [
        *revised_state.get("tool_trace", []),
        {
            "step": first_step,
            "tool": "interpret_plan_feedback",
            "actor": "agent" if interpreter == "nebius" else "workflow",
            "reason": "Convert the user's message into a typed, scoped revision intent.",
            "arguments": {"feedback": text, "event_id": event_id, "member_id": member_id},
            "result_count": 1,
            "batch_size": 1,
        },
        {
            "step": first_step + 1,
            "tool": "search_refinement_alternatives",
            "actor": "workflow",
            "reason": "Find an available owned item matching the requested garment change.",
            "arguments": {
                "member_id": member_id,
                "category": category,
                "desired_terms": intent.desired_terms,
                "avoided_terms": intent.avoided_terms,
            },
            "result_count": len(alternatives),
            "batch_size": 1,
        },
    ]
    assistant_message = (
        f"Updated {member.name}'s {event.name} outfit: "
        + (f"replaced {removed_names} with {replacement.name}." if removed_names else f"added {replacement.name}.")
    )
    weather = next((row for row in dataset.weather if row.key == event.weather_key), None)
    if weather and "shorts" in intent.desired_terms and weather.high_f < 68:
        assistant_message += (
            f" The forecast high is {weather.high_f}°F, so the existing warm and rain layers "
            "remain in the plan."
        )
    history = list(revised_state.get("refinement_history", []))
    history.append({"user": text, "assistant": assistant_message})
    revised_state["refinement_history"] = history
    revised_state["refinement"] = {
        "accepted": False,
        "feedback": text,
        "event_id": event_id,
        "member_id": member_id,
        "removed_item_ids": removed_ids,
        "replacement_item_id": replacement.id,
        "intent": intent.model_dump(mode="json"),
        "interpreter": interpreter,
        "memory_text": intent.memory_text,
        "assistant_message": assistant_message,
    }
    return _outcome(
        "applied",
        assistant_message,
        planning_state=revised_state,
        intent=intent,
        interpreter=interpreter,
    )


def _interpret_feedback(
    feedback: str,
    event: Event,
    member_name: str,
    current_items: list[WardrobeItem],
    *,
    backend: Literal["local", "nebius"],
    model: NebiusModel | None,
) -> tuple[PlanFeedbackIntent, str]:
    if backend == "nebius":
        try:
            result = (model or NebiusModel()).generate_structured(
                system_prompt=(
                    "Interpret one wardrobe-plan revision request. The family member and event are "
                    "already selected and must not be changed. Extract literal desired garment or "
                    "style terms and terms the user wants to avoid. Use replace_item when the user "
                    "prefers one garment over another. target_category must be one of the supplied "
                    "wardrobe categories or null. memory_text should be a concise, member-scoped, "
                    "event-context preference suitable for saving only if the user later approves it."
                ),
                user_message=str(
                    {
                        "feedback": feedback,
                        "member": member_name,
                        "event": event.model_dump(mode="json"),
                        "current_items": [item.model_dump(mode="json") for item in current_items],
                    }
                ),
                response_model=PlanFeedbackIntent,
                schema_name="plan_feedback_intent",
            )
            intent = PlanFeedbackIntent.model_validate(result)
            intent.desired_terms = _normalize_terms(intent.desired_terms)
            intent.avoided_terms = _normalize_terms(intent.avoided_terms)
            if intent.desired_terms:
                return intent, "nebius"
        except Exception:  # noqa: BLE001 -- Refinement has a deterministic language fallback.
            return _local_feedback_intent(feedback, event, member_name), "local_fallback"
        return _local_feedback_intent(feedback, event, member_name), "local_fallback"
    return _local_feedback_intent(feedback, event, member_name), "local"


def _local_feedback_intent(
    feedback: str, event: Event, member_name: str
) -> PlanFeedbackIntent:
    lowered = feedback.lower()
    desired_side = lowered
    avoided_side = ""
    for marker in (" instead of ", " rather than ", " than "):
        if marker in lowered:
            desired_side, avoided_side = lowered.split(marker, 1)
            break

    desired = _canonical_terms(desired_side)
    avoided = _canonical_terms(avoided_side)
    for attribute in ("denim", "formal", "festive", "heavy", "warm"):
        if attribute in avoided_side:
            avoided.append(attribute)
    desired = _normalize_terms(desired)
    avoided = _normalize_terms(avoided)
    category = _category_for_terms(desired)
    action: Literal["replace_item", "add_item", "remove_item", "unknown"] = (
        "replace_item" if desired and (avoided or "replace" in lowered or "rather" in lowered) else "add_item" if desired else "unknown"
    )
    desired_label = ", ".join(desired) or "the requested alternative"
    avoided_label = ", ".join(avoided)
    memory_text = f"{member_name} prefers {desired_label} for {event.event_type}"
    if avoided_label:
        memory_text += f" instead of {avoided_label}"
    memory_text += "."
    return PlanFeedbackIntent(
        action=action,
        target_category=category,
        desired_terms=desired,
        avoided_terms=avoided,
        interpretation=(
            f"Use {desired_label}"
            + (f" and avoid {avoided_label}" if avoided_label else "")
            + f" for {member_name}."
        ),
        memory_text=memory_text,
    )


def _canonical_terms(text: str) -> list[str]:
    return [
        canonical
        for canonical, (_, variants) in GARMENT_TERMS.items()
        if any(variant in text for variant in variants)
    ]


def _normalize_terms(terms: list[str]) -> list[str]:
    normalized: list[str] = []
    for raw_term in terms:
        term = raw_term.strip().lower()
        if not term:
            continue
        canonical_matches = [
            canonical
            for canonical, (_, variants) in GARMENT_TERMS.items()
            if term == canonical or any(variant in term for variant in variants)
        ]
        normalized.extend(canonical_matches or [term])
    return list(dict.fromkeys(normalized))


def _category_for_terms(terms: list[str]) -> WardrobeCategory | None:
    for term in terms:
        if term in GARMENT_TERMS:
            return GARMENT_TERMS[term][0]  # type: ignore[return-value]
        for canonical, (category, variants) in GARMENT_TERMS.items():
            if term == canonical or any(variant in term for variant in variants):
                return category  # type: ignore[return-value]
    return None


def _item_text(item: WardrobeItem | CatalogItem) -> str:
    garment_type = getattr(item, "garment_type", None) or ""
    notes = getattr(item, "notes", None) or ""
    return " ".join(
        [
            item.name,
            garment_type,
            item.category,
            item.color,
            item.formality,
            *item.occasion_tags,
            notes,
        ]
    ).lower()


def _matches_any(item: WardrobeItem | CatalogItem, terms: list[str]) -> bool:
    if not terms:
        return False
    searchable = _item_text(item)
    return any(term in searchable for term in terms)


def _alternative_score(
    item: WardrobeItem, event: Event, intent: PlanFeedbackIntent
) -> tuple[int, str]:
    searchable = _item_text(item)
    desired_matches = sum(term in searchable for term in intent.desired_terms)
    event_terms = set(
        f"{event.event_type} {event.setting} {' '.join(event.activities)}".lower().split()
    )
    occasion_matches = len(event_terms.intersection(item.occasion_tags))
    formality_match = int(item.formality == event.dress_code)
    season_match = int(_season_for_month(event.date.month) in item.seasons)
    return (
        desired_matches * 10 + occasion_matches * 2 + formality_match + season_match,
        item.id,
    )


def _matching_catalog_items(
    dataset: SeedDataset,
    age_group: str,
    category: str,
    intent: PlanFeedbackIntent,
    budget: float,
    existing_cost: float,
) -> list[CatalogItem]:
    matches = [
        item
        for item in dataset.catalog_items
        if item.category == category
        and item.intended_age_group in {age_group, "any"}
        and existing_cost + item.price <= budget
        and _matches_any(item, intent.desired_terms)
        and not _matches_any(item, intent.avoided_terms)
    ]
    return sorted(matches, key=lambda item: (item.price, item.id))


def _season_for_month(month: int) -> str:
    if month in {12, 1, 2}:
        return "winter"
    if month in {3, 4, 5}:
        return "spring"
    if month in {6, 7, 8}:
        return "summer"
    return "fall"


def _retrieved_guidance_ids(state: dict[str, Any]) -> set[str]:
    ids: set[str] = set()
    for record in state.get("tool_results", []):
        if record["name"] == "search_style_guidance":
            ids.update(result["id"] for result in record["result"])
        elif record["name"] == "prepare_planning_context":
            ids.update(result["id"] for result in record["result"].get("guidance", []))
    return ids


def _outcome(
    status: Literal["applied", "needs_input"],
    message: str,
    *,
    planning_state: dict[str, Any] | None = None,
    intent: PlanFeedbackIntent | None = None,
    interpreter: str | None = None,
    catalog_suggestions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "message": message,
        "planning_state": planning_state,
        "intent": intent.model_dump(mode="json") if intent else None,
        "interpreter": interpreter,
        "catalog_suggestions": catalog_suggestions or [],
    }
