# Architecture: Family Wardrobe & Lifestyle Planner

**Version:** 0.1  
**Scope:** Single household prototype  
**Related document:** [Product Requirements Document](./PRD.md)

![Hand-drawn system architecture and user flow for the Family Wardrobe & Lifestyle Planner](./assets/wardrobe-planner-architecture-user-flow-v2.png)

## System architecture

```mermaid
flowchart LR
    U[Household organizer]

    subgraph APP[Wardrobe Planner application]
        UI[Streamlit interface]

        subgraph GRAPH[LangGraph orchestration]
            INTAKE[1. Intake and normalize request]
            CONTEXT[2. Gather planning context]
            PLAN[3. Outfit planning agent]
            VALIDATE[4. Deterministic validator]
            REPAIR[5. Repair invalid plan]
            PRESENT[6. Rank and present plan]

            INTAKE --> CONTEXT --> PLAN --> VALIDATE
            VALIDATE -->|Valid| PRESENT
            VALIDATE -->|Errors and retries remain| REPAIR --> PLAN
            VALIDATE -->|Retry limit reached| PRESENT
        end

        TOOLS[Typed tool layer]
        SCHEMAS[Pydantic schemas and policy rules]
    end

    subgraph AI[AI services]
        NEBIUS[Nebius Token Factory<br/>open-weight planning model]
        PINECONE[Pinecone<br/>style-guidance RAG]
        MEM0[Mem0<br/>cross-session preferences]
    end

    subgraph DATA[Authoritative and contextual data]
        SQLITE[(SQLite<br/>family, wardrobe, events, plans)]
        WEATHER[Weather adapter<br/>live or seeded]
        CATALOG[Curated sample catalog]
        DOCS[Reviewed guidance documents]
    end

    OBS[LangSmith<br/>traces and evaluations]

    U -->|Profiles, events, requests, feedback| UI
    UI -->|Planning request| INTAKE
    PRESENT -->|Outfit plan, evidence, warnings| UI
    CONTEXT <--> TOOLS
    PLAN <--> TOOLS
    PLAN <--> NEBIUS
    VALIDATE <--> SCHEMAS

    TOOLS <--> SQLITE
    TOOLS <--> PINECONE
    TOOLS <--> MEM0
    TOOLS <--> WEATHER
    TOOLS <--> CATALOG
    DOCS -->|Ingestion before demo| PINECONE

    INTAKE -.->|Run events| OBS
    VALIDATE -.->|Validation events| OBS
    TOOLS -.->|Tool traces| OBS
    NEBIUS -.->|Model traces| OBS
```

## Architectural intent

The application uses a hybrid workflow. LangGraph controls the required sequence, gathers authoritative context through the typed `prepare_planning_context` tool, validates the result, and enforces termination conditions. The Nebius model has bounded autonomy inside the planning stage: it chooses the outfit combinations, explains them, decides whether catalog purchases add value, and submits the complete result through the typed `submit_outfit_plan` tool. A live run therefore needs one provider request for each planning or repair attempt instead of one request per data lookup.

The model never becomes the source of truth for inventory, availability, events, or budget. Those facts come from SQLite through typed tools. This lets deterministic code reject hallucinated item IDs and other hard-constraint violations before a plan reaches the user.

## Component responsibilities

| Component | Responsibility | Must not be used for |
|---|---|---|
| Streamlit | Household setup, wardrobe and event views, planning request, plan display, feedback | Business-rule enforcement |
| LangGraph | State transitions, retry limits, tool loop, failure routing | Long-term authoritative storage |
| Nebius model | Contextual reasoning, outfit generation, purchase decisions, explanations, typed plan submission | Deciding whether hard constraints passed |
| Typed tool layer | Stable boundary between the agent and application services | Free-form database access by the model |
| SQLite | Source of truth for household members, wardrobe, events, budgets, plans | Semantic style guidance |
| Pinecone | Semantic retrieval of reviewed styling and dress-code guidance | Inventory, prices, or member ownership |
| Mem0 | Member-scoped preferences learned across conversations | Events, wardrobe availability, or current hard constraints |
| Validator | Schema, ownership, availability, coverage, explicit preference, and budget checks | Subjective style judgments |
| LangSmith | Trace inspection, evaluation runs, latency and failure analysis | Application storage |

## Planning request flow

```mermaid
sequenceDiagram
    actor User
    participant UI as Streamlit
    participant Graph as LangGraph
    participant DB as SQLite tools
    participant Memory as Mem0
    participant RAG as Pinecone
    participant Model as Nebius model
    participant Rules as Validator

    User->>UI: Plan three family events
    UI->>Graph: Structured request and selected event IDs
    Graph->>DB: Load events, participants, profiles, budget
    DB-->>Graph: Authoritative records
    Graph->>Memory: Search preferences by member ID
    Memory-->>Graph: Relevant personal memories
    Graph->>RAG: Search event and dress-code guidance
    RAG-->>Graph: Passages with source metadata
    Graph->>DB: Run prepare_planning_context once
    DB-->>Graph: Eligible wardrobe, weather, guidance, catalog
    Graph->>Model: Context plus required submit_outfit_plan tool
    Model-->>Graph: Complete plan as typed tool arguments
    Graph->>Rules: Validate candidate

    alt Candidate is valid
        Rules-->>Graph: Pass
    else Repairable errors and retries remain
        Rules-->>Graph: Specific violations
        Graph->>Model: Repair using validation feedback
        Model-->>Graph: Revised candidate
        Graph->>Rules: Validate again
    else No valid plan after retry limit
        Rules-->>Graph: Unresolved constraint report
    end

    Graph-->>UI: Valid plan or explicit unresolved conflict
    UI-->>User: Outfits, evidence, purchases, warnings
```

## LangGraph state

The graph passes a typed state object between nodes. The minimum state is:

```text
PlanningState
├── request
│   ├── household_id
│   ├── event_ids[]
│   ├── user_message
│   └── purchase_budget
├── household_context
│   ├── members[]
│   ├── events[]
│   └── explicit_constraints[]
├── retrieved_context
│   ├── wardrobe_candidates[]
│   ├── memories[]
│   ├── guidance_passages[]
│   └── weather_by_event
├── candidate_plan
├── validation_errors[]
├── retry_count
├── tool_call_count
└── final_result
```

Large wardrobe or guidance collections are not copied into every model message. The graph stores identifiers and selected results, while tools apply filters close to the data source.

## Graph nodes and transitions

| Node | Input | Output | Deterministic or model-driven |
|---|---|---|---|
| `intake` | User request, event selection | Normalized planning request | Deterministic parsing plus schema validation |
| `load_context` | Household and event IDs | Profiles, events, budget | Deterministic parsing and data access |
| `agent` | Planning state | Context-tool request or candidate plan | Deterministic context request; model-driven plan |
| `execute_tool` | Approved tool request | Typed planning context | Deterministic execution |
| `validate` | Candidate plan and authoritative records | Validation errors or pass | Deterministic rules |
| `repair` | Candidate and validation errors | Repair instructions for planner | Deterministic routing; model performs repair |
| `finalize` | Valid plan or terminal failure | Ranked, display-ready response | Mostly deterministic formatting |
| `save_plan` | User-selected valid plan | Persisted plan ID | Deterministic write after user action |

### Termination controls

- Maximum application tool calls per run: 8; the live path currently uses one aggregate context call.
- Maximum validation repair attempts: 2.
- A plan cannot be marked valid unless all hard checks pass.
- A tool error is returned as structured state; the model does not receive stack traces or secrets.
- When the retry limit is reached, the workflow returns the exact unresolved constraints.

These values are prototype defaults and should be configurable.

## Data ownership and precedence

When sources disagree, the application uses this precedence order:

1. The user's current request.
2. Explicit profile and event constraints in SQLite.
3. Current inventory, availability, and budget records in SQLite.
4. Relevant personal memories from Mem0.
5. General guidance retrieved from Pinecone.
6. The model's general knowledge.

The current request may intentionally override a soft preference. It may not fabricate ownership or availability. Any conflict with a hard constraint results in clarification or an unresolved-constraint response.

## Tool boundary

Every agent tool has a narrow typed contract. Example:

```json
{
  "name": "search_wardrobe",
  "arguments": {
    "member_id": "member_maya",
    "categories": ["shoes"],
    "event_id": "event_outing",
    "must_be_available": true,
    "limit": 10
  }
}
```

Tool results include stable IDs and structured attributes. User-facing explanations may use item names, but generated plans must reference IDs so the validator can verify every selection.

Write-capable tools are deliberately limited:

- `save_preference` is called only after the user clearly expresses a durable preference.
- `save_plan` is called from an explicit interface action after validation.
- No purchase or external communication tool exists in the prototype.

## RAG ingestion and retrieval

Before the demo, reviewed guidance documents are split into short topic-focused passages. Each Pinecone record contains:

- `document_id`
- `passage_id`
- `title`
- `source`
- `text`
- `event_types[]`
- `dress_codes[]`
- `season_tags[]`
- `audience_tags[]`

At planning time, the system builds retrieval queries from event type, dress code, conditions, and relevant family constraints. It returns a small number of passages with scores and source metadata. The interface shows the source title for guidance used in the explanation.

## Memory lifecycle

Mem0 stores durable preference statements such as “Maya prefers flats for events with extensive walking.” Each operation is scoped using the household member's stable ID.

Memory rules:

- Search only for members participating in selected events.
- Save only a user-expressed preference that is likely to matter later.
- Attach member ID and preference category metadata.
- Do not store raw wardrobe inventory or child-identifying information.
- Allow the user to correct or delete a remembered preference.
- Apply current instructions before recalled memories.

## Failure handling and demo resilience

| Failure | Behavior |
|---|---|
| Nebius model timeout | Stop the run and show a recoverable provider error without changing the saved plan; the user can retry explicitly |
| Invalid structured model output | Request one schema repair, then terminate with a clear error |
| Pinecone unavailable | Continue with authoritative data and label guidance retrieval unavailable |
| Mem0 unavailable | Continue without learned preferences and preserve explicit SQLite constraints |
| Weather provider unavailable | Use clearly labeled seeded demo weather |
| Catalog unavailable | Omit purchases and report unresolved wardrobe gaps |
| SQLite read failure | Stop planning because authoritative constraints cannot be verified |
| Validation failure after retry limit | Display unresolved violations; never label the plan valid |

## Deployment shape for the prototype

The first submission runs as one Python application process plus managed external services. SQLite and seeded assets remain local to the application. This keeps deployment simple while preserving real integrations for model inference, RAG, memory, and observability.

```mermaid
flowchart TB
    subgraph HOST[Prototype host]
        APP[Streamlit and LangGraph process]
        DB[(SQLite database)]
        ASSETS[Seed data and wardrobe images]
        APP <--> DB
        APP <--> ASSETS
    end

    APP -->|HTTPS| NEB[Nebius Token Factory]
    APP -->|HTTPS| PC[Pinecone]
    APP -->|HTTPS| M0[Mem0]
    APP -.->|HTTPS traces| LS[LangSmith]
```

## Security and privacy boundaries

- Provider credentials are loaded from environment variables and excluded from Git.
- Demo data uses fictional names and synthetic wardrobe information.
- The browser does not receive provider API keys.
- All external service access occurs through the application process.
- Logs and traces avoid raw secrets and unnecessary personal data.
- Production authentication and multi-household isolation remain outside this prototype's scope.

## Architecture decisions still requiring a spike

1. Select the Nebius-hosted model after testing tool-call accuracy and structured-output adherence.
2. Confirm Mem0 project access and member-scoped metadata behavior.
3. Confirm Pinecone index dimension or integrated embedding configuration.
4. Choose the live weather API while keeping the seeded adapter as the demo fallback.

The Nebius integration decision is resolved: a custom planning-agent adapter uses Nebius's OpenAI-compatible client while LangGraph retains ownership of state transitions, tool execution, validation, retries, and termination.
