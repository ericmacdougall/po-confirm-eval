"""Audit final extraction outcomes from original predictions + six exact cached retries.

No network or inference. All output is separate from original runs/results.
"""
import copy
import hashlib
import json
from pathlib import Path
import sys

from accounting.original import ROOT, verify
from accounting.runner import inspect_attempt, finish, X
from accounting.scoring import evaluate_rows
from common import jl_read, policy
from gate import gate
from metrics import evaluate, load_cases, load_run

OUT = ROOT / "accounting/results"


def rules_status(row):
    return dict(row, extraction_status=dict(schema=1, parse_status="not-applicable", parse_failed=False,
                                            validation_failed=False, validation_status="not-applied"),
                attempt_evidence=[], final_raw="")


def recover_row(row, email, receipts):
    """Rebuild only already-observed attempt accounting; assert decisions/claims unchanged."""
    text = X.supplier_reply(X.text_of(email["subject"], email["body"]))
    claims, first = inspect_attempt(row["raw"], text)
    evidence = [first]
    receipt = None
    if row["attempts"] == 2:
        why = first["parse_error"] or first["validation_error"]
        if not why:
            raise ValueError("Recorded retry without first-attempt failure: " + row["id"])
        prompt = X.PROMPTS["v2"].replace("{email}", text).replace("{demos}", "")
        messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": row["raw"]},
                    {"role": "user", "content": why + " Return only the corrected JSON."}]
        key = hashlib.sha256((row["runtime_identity"] + json.dumps(messages) + "320").encode()).hexdigest()
        receipt = receipts[row["id"]]
        if receipt["cache_key"] != key or receipt["path"] != key[:2] + "/" + key + ".json":
            raise ValueError("Retry cache request binding mismatch")
        expected_file = "accounting/evidence/retries/" + key + ".json"
        if receipt["file"] != expected_file:
            raise ValueError("Unexpected retry evidence path")
        blob = (ROOT / expected_file).read_bytes()
        if hashlib.sha256(blob).hexdigest() != receipt["sha256"]:
            raise ValueError("Retry evidence SHA mismatch")
        cached = json.loads(blob)
        claims, last = inspect_attempt(cached["text"], text)
        evidence.append(last)
    elif row["attempts"] != 1:
        raise ValueError("Unexpected recorded attempt count")
    corrected = finish(claims, evidence)
    if corrected["claims"] != row["claims"] or corrected["abstained"] != row["abstained"]:
        raise ValueError("Accounting repair changed historical extraction behavior: " + row["id"])
    return dict(row, **corrected, retry_evidence_sha256=receipt["sha256"] if receipt else None)


def injection_control(rows, cases, base, spec, B=10000):
    """Break >5% final parsing on already-correct escalations; decision quality stays fixed."""
    broken = copy.deepcopy(rows)
    ids = sorted(i for i in rows if cases[i]["label"] == "needs-human"
                 and policy(rows[i]["claims"], cases[i]["po"])[0] == "needs-human"
                 and not rows[i]["extraction_status"]["parse_failed"])[:30]
    if len(ids) != 30:
        raise ValueError("Need thirty eligible correctly escalated cases")
    claims, first = inspect_attempt("constructed invalid first response", "")
    claims, final = inspect_attempt("constructed invalid final response", "")
    failure = finish(claims, [first, final])
    for i in ids:
        broken[i].update(copy.deepcopy(failure), attempts=2)
    corrected = evaluate_rows("constructed-parse-failure-control", "h1", broken, cases)
    unchanged = evaluate_rows("corrected-candidate", "h1", rows, cases)
    from unittest.mock import patch
    import metrics
    with patch.object(metrics, "load_run", return_value=broken):
        historical = metrics.evaluate("constructed-control-under-original-accounting", "h1", cases)
    fields = ("accuracy", "automation_recall", "false_confirm_rate", "confusion", "ok_vector")
    if any(corrected[f] != unchanged[f] for f in fields):
        raise ValueError("Control accidentally changed decision accuracy or automation")
    old_gate, new_gate = gate(historical, base, spec, B=B), gate(corrected, base, spec, B=B)
    if old_gate["verdict"] != "SHIP" or new_gate["verdict"] != "BLOCK":
        raise ValueError("Parse-failure control did not distinguish the two accounting versions")
    return dict(constructed_control=True, replaced_ids=ids, introduced_failures=30,
                final_parse_failures=corrected["parse_fail_count"], n=corrected["n"],
                original_parse_fail_rate=historical["parse_fail_rate"],
                corrected_parse_fail_rate=corrected["parse_fail_rate"],
                accuracy_automation_safety_decisions_unchanged=True,
                original_gate=old_gate, corrected_gate=new_gate)


def main():
    original = verify()
    cases = load_cases()
    emails = {e["id"]: e for e in jl_read(str(ROOT / "data/emails.jsonl"))}
    receipt_list = json.loads((ROOT / "accounting/evidence/retry-receipt.json").read_text())
    receipts = {r["id"]: r for r in receipt_list}
    if len(receipts) != 6 or len(receipt_list) != 6:
        raise ValueError("Expected six unique original retry records")
    spec = json.loads((ROOT / "docs/GATE.json").read_text())
    report = dict(scope="Post-opening measurement/control correction; not retuning or new confirmation",
                  inference_calls=0, original=original, splits={}, original_decisions_unchanged=True)
    OUT.mkdir(exist_ok=True)
    h1rows = None
    for split in ("h1", "h2", "fb"):
        rows = {i: recover_row(row, emails[i], receipts) for i, row in load_run("s2-7b-v3", split).items()}
        corrected = evaluate_rows("s2-7b-v3-corrected-accounting", split, rows, cases)
        historical = evaluate("s2-7b-v3", split, cases)
        for field in ("accuracy", "automation_recall", "false_confirm_rate", "confirm_precision",
                      "confusion", "fields", "ok_vector", "slices", "abstain_rate"):
            if corrected[field] != historical[field]:
                raise ValueError("Original decision/field result changed: " + field)
        (OUT / (split + "-records.jsonl")).write_text("".join(json.dumps(rows[i], sort_keys=True, allow_nan=False) + "\n" for i in sorted(rows)))
        (OUT / (split + "-metrics.json")).write_text(json.dumps(corrected, indent=2, allow_nan=False) + "\n")
        record = dict(n=corrected["n"], original_parse_fail_rate=historical["parse_fail_rate"],
                      corrected_parse_fail_count=corrected["parse_fail_count"],
                      corrected_parse_fail_rate=corrected["parse_fail_rate"],
                      validation_fail_count=corrected["validation_fail_count"],
                      final_failure_ids=[i for i, r in rows.items() if r["extraction_status"]["parse_failed"]],
                      retry_ids=[i for i, r in rows.items() if r["attempts"] == 2])
        if split != "fb":
            base = evaluate_rows("s0-v1", split, {i: rules_status(r) for i, r in load_run("s0-v1", split).items()}, cases)
            record.update(original_gate=gate(historical, base, spec), corrected_gate=gate(corrected, base, spec))
        report["splits"][split] = record
        if split == "h1":
            h1rows = rows
    report["parse_failure_control"] = injection_control(h1rows, cases, evaluate("s0-v1", "h1"), spec)
    (OUT / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    print(json.dumps({s: {k: v for k, v in r.items() if k in ("n", "corrected_parse_fail_count", "corrected_parse_fail_rate", "validation_fail_count")}
                      for s, r in report["splits"].items()}, indent=2))
    print("CORRECTED ACCOUNTING PASS: no inference; original extractions/decisions preserved; >5% parse-failure control BLOCKS.")


if __name__ == "__main__":
    main()
