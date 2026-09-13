# Evaluation

The evaluation suite separates objective correctness from subjective styling quality.

Run the reproducible local suite:

```powershell
uv run --offline python scripts/run_evals.py
```

Run one live Nebius case when credentials and network access are available:

```powershell
uv run --offline python scripts/run_evals.py --backend nebius --case coastal_standard --output-name nebius-coastal
```

Run the optional advisory model judge on a representative plan:

```powershell
uv run --offline python scripts/run_model_judge.py --case coastal_standard
```

Publish the full local suite as a named LangSmith dataset and experiment:

```powershell
uv run --offline python scripts/run_langsmith_evals.py
```

The 12 cases in `evals/cases.json` cover single and multi-event planning, zero-budget requests, unavailable wardrobe items, retrieval relevance, grounded citations, required tool use, hard constraints, and repeatability. The local backend is the regression baseline. The live backend runs the same cases through Nebius and deterministic validation.

Each case reports these binary checks:

- Schema validity
- Valid workflow completion
- Item existence, correct ownership, and availability
- Hard preference and event-formality compliance
- Participant coverage
- Ownership, availability, preference, completeness, and formality constraints
- Budget compliance
- Required tool use and bounded tool calls
- Expected guidance retrieval
- Citations grounded in retrieved guidance
- Explicit exclusion of unavailable items
- Repeatability

`evals/results/latest.json` contains machine-readable evidence. `evals/results/latest.md` is the submission-friendly summary. Styling appropriateness remains subjective and uses `evals/HUMAN_RUBRIC.md`; human ratings are never merged into the objective pass rate.

The Nebius path intentionally exposes one controlled `prepare_planning_context` tool call. That tool performs wardrobe, weather, catalog, and Pinecone retrieval before the model composes a typed plan. The local regression backend exposes the equivalent granular calls, making the workflow-versus-agent boundary visible in both modes.

LangSmith tracing is enabled through `LANGSMITH_TRACING`, `LANGSMITH_API_KEY`, `LANGSMITH_PROJECT`, and `LANGSMITH_ENDPOINT`. The hosted experiment records four objective scores per case: overall pass, hard constraints, RAG grounding, and bounded tool use. Local JSON/Markdown reports remain available when LangSmith is offline.

## Recorded evidence

- Local regression report: 12/12 cases passed.
- Live Nebius/Pinecone report: `coastal_standard` passed with one tool call, two grounded guidance IDs, and zero validation errors.
- LangSmith dataset: `wardrobe-planner-evals-v1`.
- LangSmith experiment: `wardrobe-planner-local-087409b9`.
- Advisory model judge: `coastal_standard` received 4.8/5 with evidence for every rubric category.

The human rubric remains a separate review step. The optional model judge uses the same six qualitative categories and emits evidence with each 1–5 score. Human and model-judge scores are never included in the 100% deterministic pass rate.
