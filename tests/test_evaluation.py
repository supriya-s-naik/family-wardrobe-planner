from pathlib import Path

from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.evaluation import load_eval_cases, run_evaluation

ROOT = Path(__file__).resolve().parents[1]


def test_versioned_evaluation_suite_has_twelve_passing_cases() -> None:
    cases = load_eval_cases(ROOT / "evals" / "cases.json")

    report = run_evaluation(load_seed_dataset(ROOT / "data" / "seed"), cases)

    assert len(cases) >= 12
    assert report.total_cases == len(cases)
    assert report.passed_cases == report.total_cases
    assert report.pass_rate == 1
