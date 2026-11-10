"""python src/score.py --split dev --tags s0-v1,s1-v1 [--baseline s0-v1] [--out results/dev_x.json]"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from metrics import evaluate, load_cases, paired_bootstrap  # noqa: E402


def fmt(w):
    return f"{w[0]:.3f} [{w[1]:.3f},{w[2]:.3f}]"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--tags", required=True)
    ap.add_argument("--baseline", default=None)
    ap.add_argument("--out", default=None)
    ap.add_argument("--slices", action="store_true")
    a = ap.parse_args()
    cases = load_cases()
    tags = a.tags.split(",")
    res = {t: evaluate(t, a.split, cases) for t in tags}
    common = set.intersection(*[set(r["ok_vector"]) for r in res.values()])
    print(f"split={a.split}  items common to all systems: {len(common)}")
    print(f"{'system':16} {'n':>4} {'doc acc [95% CI]':24} {'false-confirm [CI]':24} {'auto-recall [CI]':24} {'macroF1':>7} {'lat s':>6} {'abst':>5}")
    for t, r in res.items():
        print(f"{t:16} {r['n']:4d} {fmt(r['accuracy']):24} {fmt(r['false_confirm_rate']):24} {fmt(r['automation_recall']):24} "
              f"{r['macro_f1']:7.3f} {r['latency_s_mean']:6.1f} {r['abstain_rate']:5.2f}")
    if a.baseline:
        ids = sorted(common)
        b = [res[a.baseline]["ok_vector"][i] for i in ids]
        for t in tags:
            if t == a.baseline:
                continue
            d = paired_bootstrap(b, [res[t]["ok_vector"][i] for i in ids])
            print(f"paired bootstrap {t} - {a.baseline}: diff={d[0]:+.3f} 95% CI [{d[1]:+.3f},{d[2]:+.3f}]  P(diff<=0)={d[3]:.4f}  n={len(ids)}")
    for t, r in res.items():
        print(f"\n== {t} fields:", {k: fmt(v) + f" n={v[3]}" for k, v in r["fields"].items()})
        print("   confusion gold->pred:", {k: v for k, v in r["confusion"].items() if v})
        if a.slices:
            for dim, d in r["slices"].items():
                print(f"   slice {dim}:", {k: f"{v[0]:.2f}(n={v[3]})" for k, v in d.items()})
    if a.out:
        os.makedirs(os.path.dirname(os.path.abspath(a.out)), exist_ok=True)
        json.dump({t: {k: v for k, v in r.items() if k not in ("ok_vector", "cluster_ids")} for t, r in res.items()}, open(a.out, "w"), indent=1)


if __name__ == "__main__":
    main()
