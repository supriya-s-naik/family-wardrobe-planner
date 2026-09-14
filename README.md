# Family Wardrobe & Lifestyle Planner

An agentic AI prototype that plans outfits across a family's real-life calendar. It prioritizes clothes the family already owns, retrieves relevant styling guidance, remembers preferences, validates hard constraints, and repairs plans when circumstances change.

> Dress for your life, not just the next event.

## Current milestone

The repository currently contains the product requirements, architecture, a runnable Streamlit planning experience, typed domain models, a bounded LangGraph workflow, local service adapters, and deterministic validation for one fictional household.

- [Product requirements](docs/PRD.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Architecture infographic](docs/assets/wardrobe-planner-architecture-user-flow-v2.png)
- [Nebius model spike](docs/MODEL_SPIKE.md)
- [Multimodal wardrobe intake](docs/MULTIMODAL_INTAKE.md)
- [Evaluation approach](docs/EVALUATION.md)
- [Latest evaluation results](evals/results/latest.md)
- [LangSmith evaluation evidence](evals/results/langsmith.md)
- [Advisory model-judge result](evals/results/model-judge-coastal.json)

## Demo household

The Rivera household contains two adults and one child, 30 wardrobe items, three events, explicit preferences, seeded weather, a small product catalog, and reviewed guidance records for later RAG ingestion.

All data is fictional.

## Run locally

Python 3.11 or newer and `uv` are recommended.

```powershell
uv sync --extra dev
uv run python scripts/validate_seed.py
uv run python scripts/index_guidance.py
uv run python scripts/smoke_test_nebius.py
uv run python scripts/smoke_test_vision.py path\to\garment.jpg
uv run --offline python scripts/run_evals.py
uv run --offline python scripts/run_langsmith_evals.py
uv run --offline python scripts/run_model_judge.py --case coastal_standard
uv run streamlit run app.py
```

Copy `.env.example` to `.env` before connecting managed services. The current data browser runs without external credentials.

The interface opens on an occasion-focused overview with family preference cards. Browse
the visual wardrobe by person and category, or use an event's planning action to preselect
it. In **Plan outfits**, select events and a purchase budget, then generate the plan.
Choose **Demo-safe local** under **Planning options** for an offline run. Seeded clothing
uses category/color illustrations. In **Wardrobe**, an uploaded item photo can be analyzed
by the Nebius Gemma vision model; the resulting metadata remains editable before saving,
and the uploaded photo appears on the new item card. Each wardrobe card also offers
**Style this item**: **Use if suitable** treats the garment as a preference, while
**Must use** makes its inclusion a validator-enforced requirement for the selected events.
Theme settings live in
`.streamlit/config.toml` and layout styles in `assets/app.css`.

The Nebius smoke test makes two small live calls: one tool-selection check and one strict structured-output check. It never prints the API key. The evaluation command runs 12 deterministic regression cases and writes machine-readable and Markdown reports under `evals/results/`.

## Project structure

```text
app.py                         Streamlit prototype shell
data/seed/                     Fictional household and demo scenario
docs/                          PRD, architecture, and presentation assets
scripts/validate_seed.py       Fast deterministic seed check
scripts/run_evals.py           Local and Nebius evaluation runner
scripts/run_langsmith_evals.py Hosted LangSmith dataset and experiment runner
evals/                         Versioned cases, human rubric, and results
src/wardrobe_planner/
  adapters/local.py            Credential-free local adapters
  data/seed_loader.py          Seed loading and reference validation
  domain/models.py             Pydantic domain contracts
  workflow/                    LangGraph, tools, planner, and validator
tests/test_seed_data.py        Seed and adapter regression checks
tests/test_evaluation.py       Evaluation-suite regression check
```

## Planned integrations

- Nebius Token Factory for open-weight planning and wardrobe-image understanding
- LangGraph for the bounded tool-calling workflow
- Pinecone for styling-guidance RAG
- Mem0 for cross-session family-member preferences
- LangSmith for tracing and evaluations

Exact inventory, ownership, availability, events, budget, and saved plans remain authoritative application data. Retrieved guidance and remembered preferences provide context but cannot override current hard constraints.

## Workflow implemented

The interface offers two backends. **Nebius live** is the primary path: LangGraph gathers the authoritative planning context through one aggregate typed tool, retrieves semantically relevant reviewed guidance from Pinecone, then makes one Nebius request in which the model builds and submits the complete plan through the typed `submit_outfit_plan` tool. Planning details display the retrieval query, provider, relevance scores, sources, and passages. If Pinecone is unavailable, the run is visibly labeled as a local-keyword fallback. **Demo-safe local** follows the same graph and validation rules without network access and retains the granular tool trace for demonstration. Both paths validate ownership, availability, coverage, preferences, purchase references, and budget, and permit at most two repair attempts.
