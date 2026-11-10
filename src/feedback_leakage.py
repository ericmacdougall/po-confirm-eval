"""Feedback regression fixtures and an explicitly contaminated test-tuning demonstration.

These are research simulations. Support reports are selected from errors on the
separate feedback split, never from a production ticket stream. Test-set lookup
is an intentionally invalid model which makes its failure easy to inspect.
"""
import json
from collections import Counter
from pathlib import Path
from common import ROOT, DATA, jl_read
from metrics import evaluate, load_cases, load_run, decide, wilson


def main():
    root = Path(ROOT)
    selection = json.loads((root / "docs/SELECTION.json").read_text())
    candidate = selection["candidate"]
    cases = load_cases()
    feedback = evaluate(candidate, "fb", cases)
    if feedback["missing_ids"]:
        raise SystemExit("Feedback inference incomplete")
    run = load_run(candidate, "fb")
    errors = [i for i in run if decide(run[i], cases[i]) != cases[i]["label"]]
    # Only IDs, categories and decisions are needed in a public feedback artifact.
    tickets = [{"case_id": i, "gold": cases[i]["label"], "prediction": decide(run[i], cases[i]),
                "behaviour": cases[i]["behaviour"], "style": cases[i]["style"]} for i in sorted(errors)]
    new_categories = Counter((t["behaviour"], t["style"]) for t in tickets)
    out = {"scenario": "simulated support feedback on separate constructed email cases",
           "n_feedback_cases": feedback["n"], "n_errors": len(errors),
           "feedback_error_rate": wilson(len(errors), feedback["n"]),
           "unique_new_regression_cases": len(errors),
           "categories": {"|".join(k): v for k, v in new_categories.items()}, "tickets": tickets,
           "fixed_development_suite_n": 595, "expanded_suite_n": 595 + len(errors),
           "rule": "Add these failures to future development fixtures; H1/H2 remain frozen and cannot be retuned."}
    (root / "results/feedback.json").write_text(json.dumps(out, indent=2) + "\n")
    # Deliberately cheat by storing every H1 answer. The same lookup has no H2
    # entries, so it falls back to the untouched real candidate there.
    h1, h2 = evaluate(candidate, "h1", cases), evaluate(candidate, "h2", cases)
    if h1["missing_ids"] or h2["missing_ids"]:
        raise SystemExit("Held-out inference incomplete")
    lookup = {i: cases[i]["label"] for i in h1["ok_vector"]}
    leaked_h1 = [int(lookup[i] == cases[i]["label"]) for i in h1["ok_vector"]]
    leaked_h2 = [h2["ok_vector"][i] for i in h2["ok_vector"]]
    leakage = {"method": "deliberately invalid held-out answer lookup; constructed pedagogical contamination",
               "h1_original_accuracy": h1["accuracy"], "h1_leaked_accuracy": wilson(sum(leaked_h1), len(leaked_h1)),
               "h2_original_accuracy": h2["accuracy"], "h2_leaked_lookup_fallback_accuracy": wilson(sum(leaked_h2), len(leaked_h2)),
               "independent_confirmation": False,
               "lesson": "Perfect scores on a memorized test set establish no new extraction capability. Only untouched data can test the modified system."}
    (root / "results/leakage.json").write_text(json.dumps(leakage, indent=2) + "\n")
    print(json.dumps({"feedback_n": feedback["n"], "new_regression_fixtures": len(errors),
                      "leaked_h1_accuracy": 1.0, "h2_accuracy": h2["accuracy"]}, indent=2))


if __name__ == "__main__":
    main()
