from __future__ import annotations

import argparse
import json
import os
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from dotenv import load_dotenv

from wardrobe_planner.adapters.nebius import NebiusModel
from wardrobe_planner.config import Settings
from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.evaluation import judge_plan_quality, load_eval_cases
from wardrobe_planner.workflow.graph import run_demo_workflow, run_nebius_workflow

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an advisory model-graded style evaluation.")
    parser.add_argument("--case", default="coastal_standard")
    parser.add_argument("--planner-backend", choices=["local", "nebius"], default="local")
    parser.add_argument("--output-name", default="model-judge-coastal")
    args = parser.parse_args()

    load_dotenv(ROOT / ".env")
    cases = {case.id: case for case in load_eval_cases(ROOT / "evals" / "cases.json")}
    if args.case not in cases:
        raise SystemExit(f"Unknown evaluation case: {args.case}")
    case = cases[args.case]

    dataset = load_seed_dataset(ROOT / "data" / "seed")
    dataset.demo_request.event_ids = case.event_ids
    dataset.demo_request.purchase_budget = case.purchase_budget
    runner = run_demo_workflow if args.planner_backend == "local" else run_nebius_workflow
    state = runner(dataset)

    planner_model = Settings.from_env()
    judge_model_name = os.getenv("NEBIUS_JUDGE_MODEL", planner_model.nebius_model)
    judge_model = NebiusModel(replace(planner_model, nebius_model=judge_model_name))
    judgment = judge_plan_quality(dataset, case, state, judge_model)
    output = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_id": case.id,
        "planner_backend": args.planner_backend,
        "judge_model": judge_model_name,
        "same_model_family_warning": (
            "The configured judge may share biases with the planner; treat these scores as advisory."
        ),
        "judgment": judgment.model_dump(mode="json"),
    }
    output_path = ROOT / "evals" / "results" / f"{args.output_name}.json"
    output_path.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"Model judge: {case.id} scored {judgment.overall_score:.1f}/5")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()
