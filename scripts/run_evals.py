from __future__ import annotations

import argparse
from pathlib import Path

from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.evaluation import load_eval_cases, run_evaluation, write_report

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Run wardrobe-planner evaluation cases.")
    parser.add_argument("--backend", choices=["local", "nebius"], default="local")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--output-name", default="latest")
    parser.add_argument("--no-write", action="store_true")
    args = parser.parse_args()

    cases = load_eval_cases(ROOT / "evals" / "cases.json")
    if args.case_ids:
        requested = set(args.case_ids)
        cases = [case for case in cases if case.id in requested]
        missing = requested - {case.id for case in cases}
        if missing:
            raise SystemExit(f"Unknown evaluation case(s): {', '.join(sorted(missing))}")

    report = run_evaluation(
        load_seed_dataset(ROOT / "data" / "seed"),
        cases,
        backend=args.backend,
    )
    if not args.no_write:
        if not args.output_name.replace("-", "").replace("_", "").isalnum():
            raise SystemExit(
                "Output name may contain only letters, numbers, hyphens, and underscores"
            )
        write_report(report, ROOT / "evals" / "results", args.output_name)

    print(
        f"{report.backend} evaluation: {report.passed_cases}/{report.total_cases} "
        f"cases passed ({report.pass_rate:.0%})"
    )
    for result in report.results:
        status = "PASS" if result.passed else "FAIL"
        suffix = f" — {', '.join(result.failures)}" if result.failures else ""
        print(f"[{status}] {result.case_id}{suffix}")
    raise SystemExit(0 if report.passed_cases == report.total_cases else 1)


if __name__ == "__main__":
    main()
