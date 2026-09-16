from __future__ import annotations

import argparse
import os
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from dotenv import load_dotenv
from langsmith import Client, evaluate

from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.evaluation import EvalCase, evaluate_case, load_eval_cases
from wardrobe_planner.workflow.graph import run_demo_workflow, run_nebius_workflow

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET_NAME = "wardrobe-planner-evals-v1"


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a hosted LangSmith evaluation experiment.")
    parser.add_argument("--backend", choices=["local", "nebius"], default="local")
    parser.add_argument("--dataset", default=DEFAULT_DATASET_NAME)
    parser.add_argument("--case", action="append", dest="case_ids")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    if not os.getenv("LANGSMITH_API_KEY"):
        raise SystemExit("LANGSMITH_API_KEY is required")

    client = Client()
    cases = load_eval_cases(ROOT / "evals" / "cases.json")
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in cases if case.id in requested]
        missing = requested - {case.id for case in cases}
        if missing:
            raise SystemExit(f"Unknown evaluation case(s): {', '.join(sorted(missing))}")
    if not client.has_dataset(dataset_name=args.dataset):
        dataset = client.create_dataset(
            args.dataset,
            description=(
                f"{len(cases)} versioned family wardrobe planning case(s) for constraints, "
                "tool use, retrieval grounding, memory, and repeatability."
            ),
        )
    else:
        dataset = client.read_dataset(dataset_name=args.dataset)

    client.create_examples(
        dataset_id=dataset.id,
        examples=[
            {
                "id": uuid5(NAMESPACE_URL, f"{args.dataset}/{case.id}"),
                "inputs": case.model_dump(mode="json"),
                "outputs": {"expected_pass": True},
                "metadata": {"case_id": case.id, "suite_version": "v1"},
            }
            for case in cases
        ],
    )

    base_dataset = load_seed_dataset(ROOT / "data" / "seed")
    runner = run_demo_workflow if args.backend == "local" else run_nebius_workflow

    def target(inputs: dict) -> dict:
        case = EvalCase.model_validate(inputs)
        return evaluate_case(base_dataset, case, runner, args.backend).model_dump(mode="json")

    def overall_pass(run, _example):
        return {"key": "overall_pass", "score": bool((run.outputs or {}).get("passed"))}

    def hard_constraints(run, _example):
        checks = (run.outputs or {}).get("checks", {})
        names = [
            "schema_validity",
            "workflow_valid",
            "item_exists",
            "correct_owner",
            "item_available",
            "hard_preference_compliance",
            "event_formality",
            "participant_coverage",
            "budget_compliance",
            "memory_isolation",
            "memory_application",
        ]
        return {"key": "hard_constraints", "score": all(checks.get(name) for name in names)}

    def rag_grounding(run, _example):
        checks = (run.outputs or {}).get("checks", {})
        return {
            "key": "rag_grounding",
            "score": bool(checks.get("retrieval_relevance") and checks.get("grounded_citations")),
        }

    def bounded_tool_use(run, _example):
        checks = (run.outputs or {}).get("checks", {})
        return {"key": "bounded_tool_use", "score": bool(checks.get("tool_use"))}

    results = evaluate(
        target,
        data=args.dataset,
        evaluators=[overall_pass, hard_constraints, rag_grounding, bounded_tool_use],
        experiment_prefix=f"wardrobe-planner-{args.backend}",
        description=(
            "Objective wardrobe-planner evaluation. Subjective styling remains in the separate "
            "human rubric."
        ),
        metadata={"backend": args.backend, "suite_version": "v1", "case_count": len(cases)},
        max_concurrency=1,
        client=client,
    )
    print(f"LangSmith experiment: {results.experiment_name}")


if __name__ == "__main__":
    main()
