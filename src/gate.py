"""Release gate. Thresholds live in docs/GATE.json and are hashed into docs/PREREG.sha256 BEFORE held-out is opened.

python src/gate.py --candidate s2-v2 --baseline s0-v1 --split h1 --gate docs/GATE.json [--out results/gate_x.json]
Exit code 0 = SHIP, 3 = BLOCK. Every failed rule is listed with its numbers.

Rules (all must hold; defaults are replaced by GATE.json):
  safety       : Wilson UPPER bound of false-confirm rate (cases that must NOT be confirmed) <= max_false_confirm_upper
  coverage     : candidate answered all baseline items (no silent drops) and parse failures <= max_parse_fail
  no_regress   : paired-bootstrap 95% CI LOWER bound of (candidate - baseline) doc accuracy >= -max_regression
  improvement  : (only if require_improvement) the same CI lower bound > 0
  slice_floor  : for each behaviour slice with n >= slice_min_n, candidate accuracy >= baseline accuracy - slice_drop
  automation   : candidate automation recall point estimate >= baseline recall - max_automation_drop
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import evaluate, load_cases, paired_bootstrap  # noqa: E402


def gate(cand, base, spec, B=10000):
    c, b = cand, base
    ids = sorted(set(c["ok_vector"]) & set(b["ok_vector"]))
    fails, info = [], {}
    if len(ids) < spec.get("min_n", 400) or c.get("missing_ids") or b.get("missing_ids"):
        fails.append(f"coverage: n={len(ids)} min={spec.get('min_n', 400)} missing_candidate={len(c.get('missing_ids', []))} missing_baseline={len(b.get('missing_ids', []))}")
    if not ids:
        return dict(verdict="BLOCK", failures=fails, info=info)
    fc = c["false_confirm_rate"]
    info["false_confirm"] = dict(point=fc[0], upper=fc[2])
    if fc[2] > spec["max_false_confirm_upper"]:
        fails.append(f"safety: false-confirm upper bound {fc[2]:.3f} > {spec['max_false_confirm_upper']}")
    if len(ids) < len(b["ok_vector"]) or c["parse_fail_rate"] > spec["max_parse_fail"]:
        fails.append(f"coverage: common={len(ids)}/{len(b['ok_vector'])} parse_fail={c['parse_fail_rate']:.3f}")
    d = paired_bootstrap([b["ok_vector"][i] for i in ids], [c["ok_vector"][i] for i in ids], B=B, seed=spec.get("seed", 1))
    info["accuracy_diff"] = dict(diff=d[0], lo=d[1], hi=d[2], p_le_0=d[3], n=len(ids))
    if d[1] < -spec["max_regression"]:
        fails.append(f"no_regress: diff CI lower {d[1]:+.3f} < -{spec['max_regression']}")
    if spec.get("require_improvement") and d[1] <= 0:
        fails.append(f"improvement: diff CI lower {d[1]:+.3f} <= 0")
    sl = []
    for k, v in c["slices"]["behaviour"].items():
        bv = b["slices"]["behaviour"].get(k)
        if bv and v[3] >= spec["slice_min_n"] and v[0] < bv[0] - spec["slice_drop"]:
            sl.append(f"{k}: {v[0]:.2f} vs {bv[0]:.2f} (n={v[3]})")
    info["slice_violations"] = sl
    if sl:
        fails.append("slice_floor: " + "; ".join(sl))
    ar, br = c["automation_recall"][0], b["automation_recall"][0]
    info["automation_recall"] = dict(candidate=ar, baseline=br)
    if ar < br - spec["max_automation_drop"]:
        fails.append(f"automation: recall {ar:.3f} < baseline {br:.3f} - {spec['max_automation_drop']}")
    return dict(verdict="BLOCK" if fails else "SHIP", failures=fails, info=info)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidate", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--split", required=True)
    ap.add_argument("--gate", required=True)
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    spec = json.load(open(a.gate))
    cases = load_cases()
    c, b = evaluate(a.candidate, a.split, cases), evaluate(a.baseline, a.split, cases)
    r = gate(c, b, spec)
    r.update(candidate=a.candidate, baseline=a.baseline, split=a.split, n=c["n"], gate_spec=spec)
    print(json.dumps({k: r[k] for k in ("candidate", "baseline", "split", "n", "verdict", "failures")}, indent=1))
    print(json.dumps(r["info"], indent=1))
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump(r, open(a.out, "w"), indent=1)
    sys.exit(0 if r["verdict"] == "SHIP" else 3)


if __name__ == "__main__":
    main()
