from __future__ import annotations

import json
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path

from wardrobe_planner.data.seed_loader import load_seed_dataset
from wardrobe_planner.workflow.graph import run_demo_workflow
from wardrobe_planner.workflow.refinement import refine_plan

ROOT = Path(__file__).resolve().parents[1]
CASES_PATH = ROOT / "evals" / "refinement_cases.json"
RESULTS_JSON = ROOT / "evals" / "results" / "latest-refinement.json"
RESULTS_MD = ROOT / "evals" / "results" / "latest-refinement.md"


def main() -> None:
    cases = json.loads(CASES_PATH.read_text(encoding="utf-8"))
    results = [evaluate_case(case) for case in cases]
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "backend": "local",
        "passed_cases": sum(result["passed"] for result in results),
        "total_cases": len(results),
        "results": results,
    }
    report["pass_rate"] = round(report["passed_cases"] / report["total_cases"], 4)
    RESULTS_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    RESULTS_MD.write_text(markdown_report(report), encoding="utf-8")
    print(
        f"refinement evaluation: {report['passed_cases']}/{report['total_cases']} cases passed "
        f"({report['pass_rate']:.0%})"
    )
    for result in results:
        print(f"[{'PASS' if result['passed'] else 'FAIL'}] {result['case_id']}")
    if report["passed_cases"] != report["total_cases"]:
        raise SystemExit(1)


def evaluate_case(case: dict) -> dict:
    dataset = load_seed_dataset(ROOT / "data" / "seed")
    dataset.demo_request.event_ids = [case["event_id"]]
    original_state = run_demo_workflow(dataset)
    original_outfits = {
        (outfit["event_id"], outfit["member_id"]): list(outfit["item_ids"])
        for outfit in original_state["final_result"]["outfits"]
    }
    outcome = refine_plan(
        dataset,
        deepcopy(original_state),
        case["feedback"],
        case["event_id"],
        case["member_id"],
    )
    checks = {"expected_status": outcome["status"] == case["expected_status"]}
    if case["expected_status"] == "applied":
        revised = outcome["planning_state"]
        target = next(
            outfit
            for outfit in revised["final_result"]["outfits"]
            if outfit["event_id"] == case["event_id"]
            and outfit["member_id"] == case["member_id"]
        )
        checks.update(
            {
                "plan_valid": revised["final_result"]["status"] == "valid",
                "expected_item_used": case["expected_item_id"] in target["item_ids"],
                "forbidden_item_removed": case["forbidden_item_id"] not in target["item_ids"],
                "other_outfits_preserved": all(
                    outfit["item_ids"]
                    == original_outfits[(outfit["event_id"], outfit["member_id"])]
                    for outfit in revised["final_result"]["outfits"]
                    if outfit["member_id"] != case["member_id"]
                    or outfit["event_id"] != case["event_id"]
                ),
            }
        )
    else:
        checks["original_plan_preserved"] = outcome["planning_state"] is None
    return {
        "case_id": case["id"],
        "feedback": case["feedback"],
        "passed": all(checks.values()),
        "checks": checks,
        "message": outcome["message"],
    }


def markdown_report(report: dict) -> str:
    rows = [
        "# Plan-refinement evaluation results",
        "",
        f"- Backend: `{report['backend']}`",
        f"- Cases passed: **{report['passed_cases']}/{report['total_cases']}**",
        f"- Pass rate: **{report['pass_rate']:.0%}**",
        "",
        "| Case | Result | Status | Minimal change |",
        "|---|---:|---:|---:|",
    ]
    for result in report["results"]:
        checks = result["checks"]
        minimal_change = checks.get("other_outfits_preserved", checks.get("original_plan_preserved"))
        rows.append(
            f"| `{result['case_id']}` | {'PASS' if result['passed'] else 'FAIL'} | "
            f"{'PASS' if checks['expected_status'] else 'FAIL'} | "
            f"{'PASS' if minimal_change else 'FAIL'} |"
        )
    rows.extend(
        [
            "",
            (
                "Applied cases check intent handling, expected replacement, forbidden-item "
                "removal, full-plan validity, and preservation of every unaffected outfit. "
                "No-match cases verify that the original valid plan remains unchanged."
            ),
            "",
        ]
    )
    return "\n".join(rows)


if __name__ == "__main__":
    main()
