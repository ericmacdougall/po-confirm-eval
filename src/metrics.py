"""Metrics: field-level, document-level, slices, Wilson and paired bootstrap intervals."""
import glob
import json
import math
import os
import random
from collections import Counter, defaultdict

from common import ROOT, DATA, LABELS, jl_read, match_lines, policy

RUNS = os.path.join(ROOT, "runs")


def wilson(k, n, z=1.96):
    if n == 0:
        return (0.0, 0.0, 0.0)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (p, max(0.0, c - h), min(1.0, c + h))


def paired_bootstrap(a, b, B=10000, seed=1):
    """a,b: per-item 0/1 (or float) vectors aligned by item. Returns (mean diff b-a, lo, hi, P(diff<=0))."""
    n = len(a)
    rng = random.Random(seed)
    d = [y - x for x, y in zip(a, b)]
    stats = []
    for _ in range(B):
        s = 0.0
        for _ in range(n):
            s += d[rng.randrange(n)]
        stats.append(s / n)
    stats.sort()
    return (sum(d) / n, stats[int(0.025 * B)], stats[int(0.975 * B) - 1], sum(1 for x in stats if x <= 0) / B)


def load_cases():
    return {c["id"]: c for c in jl_read(os.path.join(DATA, "cases.jsonl"))}


def load_run(tag, split):
    rows = {}
    for p in glob.glob(os.path.join(RUNS, f"{tag}_{split}.shard*.jsonl")):
        for r in jl_read(p):
            rows[r["id"]] = r
    return rows


def decide(run_row, case):
    claims = run_row.get("claims")
    return policy(claims, case["po"])[0] if claims else "needs-human"


def field_scores(run_row, case):
    """Per-field correctness of the extraction against the gold claims. Missing claims count as wrong."""
    g, c = case["claims"], run_row.get("claims") or {}
    out = {}
    out["intent"] = c.get("intent") == g["intent"]
    out["po_number"] = (c.get("po_number") or None) == (g["po_number"] or None)
    out["ship_date"] = (c.get("ship_date") or None) == (g["ship_date"] or None)
    out["conditions"] = bool(c.get("conditions")) == bool(g["conditions"])
    if g["lines"]:
        m = match_lines(case["po"]["lines"], c.get("lines") or [])
        q = p = 0
        for gl in g["lines"]:
            cl = m.get(gl["line"])
            q += bool(cl and cl.get("qty") is not None and abs(cl["qty"] - gl["qty"]) < 1e-9)
            p += bool(cl and cl.get("unit_price") is not None and abs(cl["unit_price"] - gl["unit_price"]) < 0.005)
        out["line_qty"] = (q, len(g["lines"]))
        out["line_price"] = (p, len(g["lines"]))
    return out


def evaluate(tag, split, cases=None, ids=None):
    cases = cases or load_cases()
    run = load_run(tag, split)
    ids = sorted(ids or run.keys())
    ids = [i for i in ids if i in run]
    res = dict(tag=tag, split=split, n=len(ids))
    ok = [int(decide(run[i], cases[i]) == cases[i]["label"]) for i in ids]
    res["accuracy"] = wilson(sum(ok), len(ids))
    preds = {i: decide(run[i], cases[i]) for i in ids}
    cm = Counter((cases[i]["label"], preds[i]) for i in ids)
    res["confusion"] = {f"{g}->{p}": cm[(g, p)] for g in LABELS for p in LABELS}
    nconf_wrong = sum(1 for i in ids if preds[i] == "confirm" and cases[i]["label"] != "confirm")
    npred_conf = sum(1 for i in ids if preds[i] == "confirm")
    ngold_notconf = sum(1 for i in ids if cases[i]["label"] != "confirm")
    ngold_conf = sum(1 for i in ids if cases[i]["label"] == "confirm")
    res["false_confirm_rate"] = wilson(nconf_wrong, ngold_notconf)  # unsafe auto-confirms among cases that must not be confirmed
    res["automation_recall"] = wilson(sum(1 for i in ids if preds[i] == "confirm" and cases[i]["label"] == "confirm"), ngold_conf)
    res["confirm_precision"] = wilson(npred_conf - nconf_wrong, npred_conf)
    res["macro_f1"] = macro_f1(cases, preds, ids)
    # field level
    fs = defaultdict(lambda: [0, 0])
    for i in ids:
        for k, v in field_scores(run[i], cases[i]).items():
            if isinstance(v, tuple):
                fs[k][0] += v[0]
                fs[k][1] += v[1]
            else:
                fs[k][0] += int(v)
                fs[k][1] += 1
    res["fields"] = {k: wilson(a, b) + (b,) for k, (a, b) in fs.items()}
    # slices
    sl = {}
    for dim in ("behaviour", "style", "source"):
        grp = defaultdict(list)
        for i, o in zip(ids, ok):
            key = cases[i]["po"]["source"] if dim == "source" else cases[i][dim]
            grp[key].append(o)
        sl[dim] = {k: wilson(sum(v), len(v)) + (len(v),) for k, v in sorted(grp.items())}
    grp = defaultdict(list)
    for i, o in zip(ids, ok):
        grp[len(cases[i]["po"]["lines"])].append(o)
    sl["n_lines"] = {str(k): wilson(sum(v), len(v)) + (len(v),) for k, v in sorted(grp.items())}
    res["slices"] = sl
    res["ok_vector"] = dict(zip(ids, ok))
    lat = [run[i].get("latency_s", 0) for i in ids]
    res["latency_s_mean"] = sum(lat) / max(1, len(lat))
    res["abstain_rate"] = sum(1 for i in ids if run[i].get("abstained")) / max(1, len(ids))
    res["parse_fail_rate"] = sum(1 for i in ids if not run[i].get("claims")) / max(1, len(ids))
    return res


def macro_f1(cases, preds, ids):
    f = []
    for lab in LABELS:
        tp = sum(1 for i in ids if preds[i] == lab and cases[i]["label"] == lab)
        fp = sum(1 for i in ids if preds[i] == lab and cases[i]["label"] != lab)
        fn = sum(1 for i in ids if preds[i] != lab and cases[i]["label"] == lab)
        f.append(0 if tp == 0 else 2 * tp / (2 * tp + fp + fn))
    return sum(f) / len(f)
