"""Preflight only: no SDK, credentials, model request or listener. Exit 2 = NO-GO."""
import json
import sys

from damon_offline import Sandbox


def main():
    if len(sys.argv) != 1:
        raise SystemExit("preflight_accepts_no_arguments")
    with Sandbox() as sandbox:
        (sandbox.root / "data").mkdir()
        from app.services.damon_ai.real_gate import REFERENCE_ENDPOINT, SmokeBudget, evaluate

        report = evaluate(endpoint=REFERENCE_ENDPOINT, budget=SmokeBudget())
        result = report.to_dict()
    result.update({"REAL-MODEL-GATE": "CLOSED", "REAL MODEL SMOKE": "NO-GO",
                   "cleanup_complete": not sandbox.root.exists()})
    print(json.dumps(result))
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
