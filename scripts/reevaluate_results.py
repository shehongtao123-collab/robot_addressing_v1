"""Re-evaluate a saved details.json using deterministic local rules only."""

from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from evaluation.local_result_validator import validate_result


def reevaluate(report_directory: Path):
    source = report_directory / "details.json"
    raw = json.loads(source.read_text(encoding="utf-8"))
    output = deepcopy(raw)
    result_rows = []
    for row in output.get("results", []):
        if row.get("expected_text") is None:
            continue
        judgment = validate_result(row["expected_text"], row.get("actual_text"), row.get("candidate_call"))
        row.update({"result_type": judgment["result_type"], "passed": judgment["passed"],
                    "judgment": judgment, "judge_call": None,
                    "result_status": "evaluated_locally"})
        result_rows.append(row)
    output["metadata"] = {**output["metadata"], "result_validator": {
        "type": "deterministic_local", "version": 2}, "reevaluated_at": datetime.now(timezone.utc).isoformat(),
        "reevaluated_from": str(source), "judge": None, "judge_prompt_sha256": None}
    output_directory = report_directory.with_name(report_directory.name + "_local_validation")
    output_directory.mkdir(parents=True, exist_ok=True)
    destination = output_directory / "details.json"
    destination.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    types = Counter(row["result_type"] for row in result_rows)
    passed = sum(row["passed"] for row in result_rows)
    return destination, {"total": len(result_rows), "passed": passed,
        "failed": len(result_rows) - passed, "pass_rate": passed / len(result_rows) if result_rows else 0,
        "by_type": dict(types)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("report_directory", type=Path)
    args = parser.parse_args()
    destination, summary = reevaluate(args.report_directory)
    print(json.dumps({"output": str(destination), **summary}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
