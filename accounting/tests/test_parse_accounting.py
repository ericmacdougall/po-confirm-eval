import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import tempfile

from accounting.runner import run_one, check_future_args
from accounting.scoring import evaluate_rows
from common import policy
from gate import gate
from metrics import evaluate, load_cases, load_run


class FakeLLM:
    def __init__(self, *texts):
        self.texts = iter(texts)

    def chat(self, messages):
        return dict(text=next(self.texts), tokens=1, latency_s=0)


class ParseAccounting(unittest.TestCase):
    email = dict(subject="Reply", body="We will respond later.")

    def test_final_parse_failure_survives_nonempty_fallback(self):
        row = run_one("s2", FakeLLM("not JSON", "still not JSON"), "v2", self.email, None)
        self.assertTrue(row["claims"])
        self.assertTrue(row["abstained"])
        self.assertTrue(row["extraction_status"]["parse_failed"])
        self.assertFalse(row["extraction_status"]["validation_failed"])
        self.assertEqual(row["final_raw"], "still not JSON")
        self.assertEqual(len(row["attempt_evidence"]), 2)

    def test_successful_retry_clears_only_final_parse_failure(self):
        valid = '{"intent":"other","lines":[]}'
        row = run_one("s2", FakeLLM("not JSON", valid), "v2", self.email, None)
        self.assertFalse(row["extraction_status"]["parse_failed"])
        self.assertFalse(row["abstained"])
        self.assertEqual(row["attempt_evidence"][0]["parse_status"], "invalid-json")
        self.assertEqual(row["attempt_evidence"][1]["parse_status"], "ok")
        self.assertEqual(row["final_raw"], valid)

    def test_grounding_failure_is_not_parse_failure(self):
        raw = '{"po_number":"PO99999","intent":"other","lines":[]}'
        row = run_one("s2", FakeLLM(raw, raw), "v2", self.email, None)
        self.assertFalse(row["extraction_status"]["parse_failed"])
        self.assertTrue(row["extraction_status"]["validation_failed"])
        self.assertTrue(row["abstained"])
        self.assertIn("does not appear", row["attempt_evidence"][-1]["validation_error"])

    def test_invalid_schema_has_separate_status(self):
        raw = '{"lines":"not a list"}'
        row = run_one("s2", FakeLLM(raw, raw), "v2", self.email, None)
        self.assertTrue(row["extraction_status"]["parse_failed"])
        self.assertEqual(row["extraction_status"]["parse_status"], "invalid-schema")
        self.assertIsNone(row["attempt_evidence"][-1]["validation_error"])

    def test_missing_or_inconsistent_status_refuses_scoring(self):
        cases = load_cases()
        rows = load_run("s2-7b-v3", "h1")
        with self.assertRaises(ValueError):
            evaluate_rows("missing-status", "h1", rows, cases)
        for row in rows.values():
            row["extraction_status"] = dict(parse_status="invalid-json", parse_failed=False,
                                            validation_failed=False)
        with self.assertRaises(ValueError):
            evaluate_rows("inconsistent-status", "h1", rows, cases)

    def test_historical_outputs_and_path_escape_refused_before_model_construction(self):
        for split, tag in (("h1", "future-check"), ("h2", "future-check"), ("fb", "future-check"),
                           ("real", "future-check"), ("dev", "s2-7b-v3"),
                           ("dev", "future-../../runs/s2-7b-v3"), ("../h1", "future-check")):
            with self.subTest(split=split, tag=tag), self.assertRaises(SystemExit):
                check_future_args(["--split", split, "--tag", tag])
        self.assertEqual(check_future_args(["--split", "dev", "--tag", "future-new-dev"]).tag,
                         "future-new-dev")

    def test_immutable_original_archive_and_retry_binding(self):
        from accounting import original
        from accounting.reconcile import recover_row
        from common import jl_read
        self.assertEqual(original.verify()["frozen_artifacts"], 31)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "altered.zip"
            p.write_bytes(b"changed archive")
            with patch.object(original, "ARCHIVE", p), self.assertRaises(ValueError):
                original.verify()
        receipts = {r["id"]: r for r in json.loads((original.ROOT / "accounting/evidence/retry-receipt.json").read_text())}
        row = load_run("s2-7b-v3", "h1")["h1-01163"]
        emails = {r["id"]: r for r in jl_read(str(original.ROOT / "data/emails.jsonl"))}
        recovered = recover_row(row, emails[row["id"]], receipts)
        self.assertTrue(recovered["extraction_status"]["parse_failed"])
        self.assertEqual(recovered["claims"], row["claims"])
        altered = copy.deepcopy(receipts)
        altered[row["id"]]["cache_key"] = "0" * 64
        with self.assertRaises(ValueError):
            recover_row(row, emails[row["id"]], altered)
        altered = copy.deepcopy(receipts)
        altered[row["id"]]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            recover_row(row, emails[row["id"]], altered)

    def test_parse_failure_gate_blocks_without_accuracy_or_automation_change(self):
        cases = load_cases()
        rows = copy.deepcopy(load_run("s2-7b-v3", "h1"))
        before = evaluate("s2-7b-v3", "h1")
        failed = run_one("s2", FakeLLM("not JSON", "still not JSON"), "v2", self.email, None)
        ids = sorted(i for i in rows if cases[i]["label"] == "needs-human"
                     and policy(rows[i]["claims"], cases[i]["po"])[0] == "needs-human")[:30]
        self.assertEqual(len(ids), 30)
        for row in rows.values():
            row["extraction_status"] = dict(parse_status="ok", parse_failed=False, validation_failed=False)
        for i in ids:
            rows[i] = dict(failed, id=i)
        after = evaluate_rows("injected-parse-failure", "h1", rows, cases)
        self.assertEqual(before["accuracy"], after["accuracy"])
        self.assertEqual(before["automation_recall"], after["automation_recall"])
        self.assertGreater(after["parse_fail_rate"], .05)
        spec = json.loads((Path(__file__).resolve().parents[2] / "docs/GATE.json").read_text())
        base = evaluate("s0-v1", "h1")
        self.assertEqual(gate(after, base, spec, B=100)["verdict"], "BLOCK")


if __name__ == "__main__":
    unittest.main()
