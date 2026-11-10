import copy
import math
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "src"))
from common import policy
from gate import gate
from metrics import paired_bootstrap, wilson
from extractors import extract_json, normalise, supplier_reply, validate


class PolicySafety(unittest.TestCase):
    def setUp(self):
        self.po = {"po_num": "PO12345", "order_date": "2026-01-01",
                   "lines": [{"desc": "steel bolts", "qty": 10, "unit_cost": 5.0}]}
        self.claims = {"po_number": "PO12345", "intent": "confirm", "conditions": False,
                       "ship_date": None, "lines": [{"line": 1, "desc": "steel bolts", "qty": 10, "unit_price": 5.0}]}

    def test_valid_confirmation(self):
        self.assertEqual(policy(self.claims, self.po)[0], "confirm")

    def test_nonfinite_or_bool_numbers_cannot_confirm(self):
        for field in ("qty", "unit_price"):
            for value in (float("nan"), float("inf"), -float("inf"), True, "NaN"):
                with self.subTest(field=field, value=str(value)):
                    c = copy.deepcopy(self.claims)
                    c["lines"][0][field] = value
                    self.assertEqual(policy(c, self.po)[0], "needs-human")

    def test_extra_or_duplicate_supplier_lines_need_human(self):
        c = copy.deepcopy(self.claims)
        c["lines"].append(dict(c["lines"][0]))
        self.assertEqual(policy(c, self.po)[0], "needs-human")

    def test_refusal_for_wrong_order_cannot_reject_this_order(self):
        c = dict(self.claims, po_number="PO99999", intent="reject")
        self.assertEqual(policy(c, self.po)[0], "needs-human")


class EvaluationSafety(unittest.TestCase):
    def test_json_braces_inside_strings_are_valid(self):
        self.assertEqual(extract_json('text {"desc":"a } bracket","lines":[]}')['desc'], 'a } bracket')

    def test_supplier_reply_does_not_include_buyer_numbers(self):
        reply = supplier_reply('Received. We will revert.\n-----Original Message-----\nQty 25 at $50.00')
        self.assertNotIn('50.00', reply)
        claims = {"po_number": None, "intent": "confirm", "conditions": False,
                  "ship_date": None, "lines": [{"line": 1, "desc": "bolts", "qty": 5, "unit_price": 5}]}
        self.assertIsNotNone(validate(claims, 'PO12345 quantity 150 at $150.00'))

    def test_nonfinite_extraction_values_are_missing(self):
        cl = normalise({"intent": "confirm", "lines": [{"qty": "NaN", "unit_price": True}]})
        self.assertIsNone(cl['lines'][0]['qty'])
        self.assertIsNone(cl['lines'][0]['unit_price'])

    def test_supplier_refusal_needs_no_unstated_prices(self):
        cl = normalise({"po_number": "PO12345", "intent": "reject", "lines": [
            {"line": 1, "desc": "bolts", "qty": None, "unit_price": None}]})
        self.assertIsNone(validate(cl, 'We cannot fill PO12345. The bolts are discontinued.'))

    def test_no_observations_is_not_zero_risk(self):
        self.assertEqual(wilson(0, 0), (0.0, 0.0, 1.0))

    def test_bad_denominators_rejected(self):
        for k, n in ((1, 0), (-1, 10), (11, 10)):
            with self.assertRaises(ValueError):
                wilson(k, n)

    def test_bootstrap_requires_paired_nonempty_samples(self):
        for a, b in (([], []), ([1], [1, 0])):
            with self.assertRaises(ValueError):
                paired_bootstrap(a, b, B=50)

    def test_empty_gate_blocks_without_crashing(self):
        r = {"ok_vector": {}, "false_confirm_rate": wilson(0, 0), "parse_fail_rate": 0,
             "automation_recall": wilson(0, 0), "slices": {"behaviour": {}}}
        spec = {"max_false_confirm_upper": .06, "max_parse_fail": .05,
                "max_regression": .01, "max_automation_drop": .03,
                "slice_min_n": 20, "slice_drop": .1, "min_n": 400}
        result = gate(r, r, spec, B=50)
        self.assertEqual(result["verdict"], "BLOCK")
        self.assertTrue(any("coverage" in f for f in result["failures"]))


if __name__ == "__main__":
    unittest.main()
