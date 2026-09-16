# Conversational plan refinement

The refinement experience is attached to a valid outfit plan. The user selects an occasion and
family member, then describes a change in natural language. This explicit scope prevents ambiguous
messages such as “I want shorts” from changing multiple family members.

## Implemented flow

1. The Nebius backend converts feedback into `PlanFeedbackIntent`; the demo-safe path uses a local
   parser, and live interpretation falls back locally if the provider is unavailable.
2. The workflow searches available items owned by the selected member and ranks exact garment,
   occasion, formality, and season matches.
3. It replaces only the matching category in the selected outfit. Every other outfit and item is
   preserved.
4. The existing deterministic validator checks ownership, availability, outfit completeness,
   formality, guidance citations, weather readiness, required items, purchases, and budget.
5. The UI shows the existing before/after comparison. The user can accept the revision or restore
   the original plan.
6. An accepted revision can be saved as a new plan. If the source plan was saved, the new plan keeps
   its ID as `source_plan_id`.
7. Preference memory is opt-in. The user chooses whether feedback applies only to this plan, to
   similar occasions, or generally to that family member before anything is written to Mem0.

The chat transcript and acceptance controls are session-only. Saved plans retain a compact
`refinement_summary` for provenance, but reopening a completed plan presents a fresh refinement
box instead of replaying earlier messages.

## Current boundary

The first version applies one garment-category change per message. If no owned item matches, it
reports an affordable catalog match when available and leaves the current valid plan unchanged.
Shopping-backed outfit substitution can be added later by extending outfit selections to represent
catalog items that have not yet entered authoritative wardrobe inventory.

## Example

Input:

> I would rather wear shorts at the beach than denim jeans.

Typed intent:

```json
{
  "action": "replace_item",
  "target_category": "bottom",
  "desired_terms": ["shorts"],
  "avoided_terms": ["jeans", "denim"]
}
```

For the Rivera demo household, Maya's dark straight-leg jeans are replaced with her navy cotton
walking shorts. Her top, shoes, weather layers, family members' outfits, purchase recommendations,
and retrieved guidance remain unchanged.
