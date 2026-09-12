# Product Requirements Document: Family Wardrobe & Lifestyle Planner

**Version:** 0.1  
**Status:** Draft for review  
**Prototype submission:** September 12  
**Final demonstration:** September 16

## 1. Product summary

The Family Wardrobe & Lifestyle Planner is an AI assistant that plans clothing decisions across a family's upcoming calendar. It combines the family's existing wardrobe, member preferences, event requirements, and contextual guidance to build practical outfit plans. When a suitable outfit cannot be made from owned items, it identifies the smallest wardrobe gap and recommends a reusable purchase within budget.

The prototype focuses on one household with multiple family members. It demonstrates an end-to-end planning experience across several events rather than trying to support every fashion, shopping, travel, and calendar feature in the broader vision.

**Core principle:** “Dress for your life, not just the next event.”

## 2. Problem statement

Families make clothing decisions repeatedly across work, school, celebrations, travel, and cultural events. Existing styling tools generally optimize for one person or one occasion. They do not account for what the household already owns, whether an item is available, how often it has been worn, how several family members should coordinate, or whether a proposed purchase will be useful again.

This creates four problems:

1. Planning each occasion independently takes time and produces inconsistent decisions.
2. Useful clothes are overlooked because the family cannot easily recall or combine everything it owns.
3. Last-minute purchases are often expensive, redundant, or useful for only one event.
4. Preferences learned during one interaction are lost before the next planning session.

## 3. Product goal

Help one family prepare for multiple upcoming events by producing complete, constraint-aware outfit plans that prioritize owned clothes, remember personal preferences, explain their recommendations, and adapt when circumstances change.

### Prototype hypothesis

If the assistant considers the family's wardrobe and calendar together, it can reduce decision effort and unnecessary purchases while producing plans that remain useful when events, weather, or item availability change.

## 4. Target user and demo household

### Primary user

A household organizer who coordinates clothing decisions for themselves and other family members. They want practical recommendations and care about time, budget, comfort, appropriateness, and reuse.

### Demo household

The seeded demonstration uses one fictional household:

- Two adults and one child.
- Approximately 25–30 wardrobe items across clothing, footwear, and accessories.
- Individual sizes, style preferences, disliked items, and comfort needs.
- Three upcoming events with different dress codes and conditions.
- A household purchase budget of $100 for the planning period.

The data model should support changing the family members without changing the planning logic.

## 5. Core user story

> As a household organizer, I want the assistant to plan outfits for my family across our upcoming events using clothes we already own, so that everyone is appropriately dressed and I avoid unnecessary last-minute purchases.

### Supporting user stories

- As a user, I can view and edit each family member's wardrobe and preferences.
- As a user, I can add events with date, location, participants, activities, and dress expectations.
- As a user, I can request one coordinated plan covering several events.
- As a user, I can see which owned items are used and why each outfit was selected.
- As a user, I can state a durable preference and have it applied in a later session.
- As a user, I can change an event or mark an item unavailable and receive a repaired plan.
- As a user, I can see a purchase recommendation only when the owned wardrobe leaves a meaningful gap.

## 6. Demo scenario

The household asks:

> “Plan outfits for our family for a school celebration, a festive dinner, and a weekend outdoor outing. Use what we own first, coordinate our looks without making us identical, and keep any suggested purchases under $100 total.”

The system retrieves relevant family preferences, wardrobe items, event details, and styling guidance. It creates a complete plan, validates it, and presents explanations and any wardrobe gaps.

The user then says:

> “Remember that Maya prefers flats whenever an event involves a lot of walking.”

In a later planning interaction, the assistant recalls that preference. Finally, the user marks a selected jacket unavailable or changes the outdoor forecast to rain. The assistant replans the affected outfit without violating the other constraints.

## 7. Scope

### September 12 prototype

- One household with multiple member profiles.
- Seeded, editable wardrobe data with manually supplied item attributes and images.
- Three manually entered or seeded events.
- Outfit planning across all selected events.
- Retrieval-augmented generation over a small, reviewed style and dress-code knowledge base.
- Model-driven tool calls for wardrobe, event, preference, and guidance retrieval.
- Deterministic validation of ownership, participant, availability, and explicit preference constraints.
- A visible explanation of each recommendation and the evidence used.
- A small evaluation dataset with automated results.
- A locally runnable user interface and documented setup in GitHub.

### September 16 final demonstration

- Cross-session preference storage and retrieval using Mem0.
- Replanning after an event, weather, preference, or item-availability change.
- Budget validation and basic purchase-gap ranking against a curated sample catalog.
- Improved family coordination and wardrobe-reuse scoring.
- Expanded evaluation coverage, including memory isolation and replanning.
- Polished interface, reliable demo data, and a rehearsed fallback path.

### Out of scope for this version

- Multiple household accounts, authentication, and permissions.
- Live calendar integration.
- Live retailer search, checkout, or affiliate links.
- Fully automatic wardrobe recognition from photographs.
- Image generation or virtual try-on.
- Background monitoring and proactive notifications.
- Detailed hairstyle, makeup, jewelry, or grooming generation.
- Laundry-cycle tracking and real-time item location.
- Production security, scale, and multi-tenant deployment.

## 8. Functional requirements

### FR-1: Household profiles

The system shall maintain a profile for each family member containing a name or pseudonym, age group, sizes, preferred colors, avoided colors or styles, comfort needs, cultural or modesty preferences, and willingness to repeat outfits.

### FR-2: Wardrobe inventory

The system shall store wardrobe items with a stable item ID, owner, category, color, formality, season, warmth, occasion tags, availability, and optional image. The user shall be able to inspect and edit these attributes.

### FR-3: Event management

The system shall store events with a stable event ID, date, location, participating family members, event type, dress code, indoor or outdoor setting, planned activities, and optional notes.

### FR-4: Context retrieval

For a planning request, the system shall retrieve:

- Relevant household members and their authoritative profile constraints.
- Available wardrobe candidates belonging to each participant.
- Relevant remembered preferences scoped to the correct family member.
- Relevant style or dress-code guidance from the knowledge base.

The interface shall expose enough retrieval evidence to demonstrate that RAG occurred.

### FR-5: Multi-event outfit planning

The system shall create an outfit for every participating family member at every selected event. An outfit shall contain item IDs grouped into applicable categories and a concise rationale.

The planner shall consider all selected events together so that it can balance suitability, repetition, coordination, reuse, and purchase value across the calendar.

### FR-6: Constraint validation and repair

Before showing a plan as valid, deterministic checks shall verify:

- Every referenced owned item exists.
- The item belongs to the intended family member.
- The item is available.
- Each event participant has an outfit.
- Explicitly prohibited items or attributes are absent.
- Proposed purchases remain within the stated budget.

If validation fails, the system shall provide the errors to the planner and allow a limited number of repair attempts. If no valid solution is found, it shall state the unresolved conflict instead of inventing an item or silently relaxing a constraint.

### FR-7: Recommendation explanations

For each outfit, the system shall explain its suitability using concrete facts from the event, member profile, wardrobe, remembered preferences, or retrieved guidance. It shall distinguish owned items from proposed purchases.

### FR-8: Preference memory

The user shall be able to save an enduring preference for a specific family member. In a later session, the system shall retrieve relevant memories and use them during planning.

Current user instructions and authoritative profile constraints shall take precedence over retrieved memories. Memories must be isolated by household member and be correctable or removable.

### FR-9: Replanning

When an event detail, preference, or item availability changes, the system shall identify the affected portion of the plan and generate a valid replacement. Unaffected outfits should remain stable when possible.

### FR-10: Purchase-gap recommendation

If no valid owned outfit can be produced, the system may recommend an item from a curated sample catalog. The recommendation shall include price, compatibility with owned items, events supported, and a reuse rationale. The system shall prefer the smallest set of purchases that resolves the most important gaps within budget.

### FR-11: Plan persistence

The user shall be able to save and reopen the latest generated plan for the household.

## 9. Agent behavior: workflow and autonomy

The product uses a hybrid design so the demonstration clearly distinguishes dependable workflow from bounded autonomy.

### Deterministic workflow

1. Parse the request and selected events.
2. Load authoritative household and event data.
3. Retrieve relevant memories and knowledge-base passages.
4. Ask the planning model to select tools or produce candidate outfits.
5. Validate candidates with deterministic rules.
6. Repair invalid candidates within a fixed retry limit.
7. Rank valid plans and present the best plan with evidence.
8. Save the plan after user action.

### Bounded autonomous decisions

Within the workflow, the planning agent may decide:

- Which available tool to call next.
- Which family memories and guidance queries are relevant.
- Whether the available context is sufficient to plan.
- Which wardrobe combinations to propose.
- Whether a wardrobe gap justifies searching the sample catalog.
- How to repair a candidate after receiving validation errors.

The agent may not silently change a hard constraint, invent owned items, exceed the tool-call or repair budget, make a purchase, or write a durable memory that the user did not express.

## 10. Planned tools

| Tool | Purpose | Data source |
|---|---|---|
| `get_family_profiles` | Load participating members and explicit constraints | SQLite |
| `get_events` | Load selected event details | SQLite |
| `search_wardrobe` | Find eligible owned items using filters | SQLite |
| `search_style_guidance` | Retrieve relevant contextual guidance | Pinecone |
| `search_memories` | Retrieve member-specific learned preferences | Mem0 |
| `save_preference` | Store a user-expressed durable preference | Mem0 |
| `get_weather` | Return seeded or live conditions for an event | Weather adapter |
| `search_sample_catalog` | Find gap-filling products within constraints | Local catalog |
| `save_plan` | Persist a validated plan | SQLite |

For a repeatable video and live demonstration, the weather adapter must support deterministic seeded responses even if an external service is unavailable.

## 11. RAG and memory boundaries

RAG and memory solve different problems in this product:

- **Pinecone RAG** retrieves general contextual knowledge such as dress-code interpretation, layering guidance, and coordination principles. Retrieved passages have source IDs and can support explanations.
- **Mem0** retrieves personal facts learned from prior interactions, such as comfort and style preferences. Memories are scoped to a specific family member.
- **SQLite** remains the source of truth for inventory, events, availability, prices, budget, and explicit profile constraints.

No retrieved passage or memory may override a current explicit instruction or an authoritative stored constraint.

## 12. Recommendation policy

Candidate plans are evaluated in this order:

1. Satisfy ownership, availability, participation, dress-code, cultural, comfort, and budget constraints.
2. Prefer owned items over purchases.
3. Match event conditions and retrieved guidance.
4. Respect personal preferences and outfit-repeat tolerance.
5. Coordinate the family through complementary formality or colors without requiring identical outfits.
6. Reuse versatile items across the planning horizon where practical.
7. If a purchase is necessary, prefer the item that closes the most gaps and works with the most owned items.

## 13. Data model

The minimum entities are:

- `Household`: household ID, name, planning budget.
- `FamilyMember`: member ID, household ID, profile attributes and explicit constraints.
- `WardrobeItem`: item ID, owner ID, descriptive attributes, availability, image reference.
- `Event`: event ID, date, location, participants, dress code, activities, contextual conditions.
- `KnowledgeDocument`: document ID, source, text, tags, embedding reference.
- `Memory`: managed by Mem0 and scoped by member ID, with category and timestamps.
- `Plan`: plan ID, selected events, generated outfits, purchases, evidence, validation status.
- `PlanItem`: plan ID, event ID, member ID, item ID or catalog product ID, role in outfit.

## 14. Non-functional requirements

- A seeded demo plan should complete within 30 seconds under normal provider conditions.
- Tool calls, retrieved evidence, validation outcomes, and model latency should be traceable.
- The same seeded scenario should succeed repeatedly without manual database correction.
- External-service failures should produce a clear message and preserve the existing saved plan.
- Secrets shall be read from environment variables and excluded from version control.
- The application shall use pseudonymous demo data and no real child information.
- The interface shall clearly label sample catalog data and simulated weather when used.

## 15. Evaluation plan

The prototype shall include a version-controlled dataset of at least 12 cases. Each case contains the request, relevant household state, expected constraints, and evaluators.

### Deterministic evaluators

- `item_exists`: all owned item IDs exist.
- `correct_owner`: every item belongs to the assigned member.
- `item_available`: unavailable items are never selected.
- `participant_coverage`: every event participant receives an outfit.
- `hard_preference_compliance`: prohibited attributes are absent.
- `budget_compliance`: total purchase cost is within budget.
- `schema_validity`: the output matches the defined plan schema.
- `memory_isolation`: a preference stored for one member is not applied as another member's fact.
- `replanning_consistency`: a changed item is replaced and unaffected valid selections are preserved where possible.

### Retrieval and qualitative evaluators

- Relevant guidance appears in the retrieved context.
- The rationale is supported by retrieved or structured evidence.
- The plan is appropriate for the event and weather.
- Family coordination is coherent without being overly matched.
- A proposed purchase has credible reuse value across the selected events.

Qualitative criteria may use a documented human rubric for the prototype. Model-based grading is optional and must not be presented as objective ground truth.

### Baseline comparison

Compare multi-event planning with independently planning each event. Record:

- Number and total cost of proposed purchases.
- Constraint violations.
- Number of owned wardrobe items utilized.
- Human-rated coherence and usefulness.

## 16. Success metrics

### September 12 acceptance criteria

- The application completes the seeded request from input to displayed plan.
- At least three events and three family members are included.
- The model makes observable tool calls rather than receiving all context in one prompt.
- At least one recommendation uses retrieved knowledge with a visible source reference.
- All displayed plans pass ownership, availability, participant, and schema checks.
- At least 10 evaluation cases run from a documented command, with results included in the repository.
- The repository contains setup instructions, architecture, sample data, known limitations, and a short demo video link or file reference.

### September 16 acceptance criteria

- A preference saved in one session is correctly recalled in a later session.
- Memories remain isolated between family members.
- The system repairs a plan after an item or event condition changes.
- A purchase suggestion, when triggered, remains within budget and includes reuse evidence.
- At least 12 evaluation cases cover RAG, tool use, memory, hard constraints, and replanning.
- The main demonstration can be completed reliably, with a recorded fallback available.

## 17. Product risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| The model invents wardrobe items | Breaks trust | Require stable IDs and deterministic validation |
| Too many service integrations fail during demo | Incomplete flow | Use adapters, seeded fallbacks, and test each integration independently |
| Memory stores a temporary statement as permanent | Bad personalization | Save only explicit durable preferences and allow correction/deletion |
| Preferences leak between members | Incorrect or sensitive result | Scope every memory query and eval by member ID |
| “Good style” is subjective | Weak evaluation claims | Separate objective constraints from a documented human rubric |
| RAG exists only cosmetically | Fails course objective | Show retrieved passages and evaluate retrieval relevance |
| Broad scope prevents an end-to-end build | Missed submission | Protect the September 12 acceptance criteria and defer stretch features |

## 18. Implementation assumptions

- Python and Streamlit will be used for the prototype interface.
- LangGraph will orchestrate the workflow and bounded agent loop.
- Nebius Token Factory will provide access to an open-weight instruction model; the exact model will be selected after tool-calling and structured-output tests.
- SQLite will store authoritative application data.
- Pinecone will provide vector retrieval for the knowledge base.
- Mem0 managed service will provide cross-session preference memory.
- LangSmith will capture traces and evaluation runs.
- Sample product and weather data are acceptable for the prototype when clearly labeled.

## 19. Open decisions

The following decisions should be resolved during architecture design:

1. Which Nebius-hosted model provides the best balance of tool-call reliability, structured output, speed, and cost?
2. Should the September 12 interface support editing all seed data, or only the fields needed for the demo?
3. Which weather source will be used live, and what seeded response format will provide the fallback?
4. What reviewed documents will make up the initial RAG knowledge base, and how will source attribution appear in the interface?
5. Which family coordination rules should be deterministic and which should remain part of the qualitative rubric?
