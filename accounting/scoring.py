import sys
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import metrics

def evaluate_rows(tag, split, rows, cases=None):
    """Reuse original decision/field math, but require explicit final extraction status."""
    from collections import Counter
    with patch.object(metrics, "load_run", return_value=rows):
        result = metrics.evaluate(tag, split, cases=cases)
    counts = Counter()
    validation_failed = 0
    for i in result["ok_vector"]:
        if i not in rows:
            counts["missing"] += 1
            continue
        row = rows[i]
        status = row.get("extraction_status")
        if not isinstance(status, dict):
            raise ValueError("Missing final extraction status: " + i)
        state = status.get("parse_status")
        if state not in ("ok", "invalid-json", "invalid-schema", "not-applicable"):
            raise ValueError("Unknown final parse/schema status: " + i)
        if status.get("parse_failed") is not (state in ("invalid-json", "invalid-schema")):
            raise ValueError("Inconsistent parse status: " + i)
        if type(status.get("validation_failed")) is not bool or (status["parse_failed"] and status["validation_failed"]):
            raise ValueError("Inconsistent validation status: " + i)
        counts[state] += 1
        validation_failed += status["validation_failed"]
    failed = sum(counts[s] for s in ("invalid-json", "invalid-schema", "missing"))
    result.update(accounting_version="post-opening-parse-v1", parse_status_counts=dict(counts),
                  parse_fail_count=failed, parse_fail_rate=failed / max(1, result["n"]),
                  validation_fail_count=validation_failed,
                  validation_fail_rate=validation_failed / max(1, result["n"]))
    return result
