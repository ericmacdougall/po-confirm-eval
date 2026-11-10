"""Summarise the label audit: agreement between the gold label and the independent Opus re-extraction.
Writes data/audit_disagreements.jsonl (for human adjudication) and prints rates with Wilson CIs."""
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, jl_read, jl_write  # noqa: E402
from metrics import wilson  # noqa: E402

cases = {c["id"]: c for c in jl_read(os.path.join(DATA, "cases.jsonl"))}
rows = {r["id"]: r for r in jl_read(os.path.join(DATA, "audit.jsonl"))}
by = {}
for i, r in rows.items():
    by.setdefault(cases[i]["split"], []).append(r)
dis = []
for s, rs in sorted(by.items()):
    valid = [r for r in rs if r["audit_label"]]
    agree = [r for r in valid if r["audit_label"] == r["gold_label"]]
    print(f"{s}: audited={len(rs)} parsed={len(valid)} label-agree={len(agree)} rate={wilson(len(agree), len(valid))}")
    for r in valid:
        if r["audit_label"] != r["gold_label"]:
            c = cases[r["id"]]
            dis.append(dict(id=r["id"], split=s, behaviour=c["behaviour"], gold=r["gold_label"], audit=r["audit_label"],
                            gold_claims=c["claims"], audit_claims=r["claims"]))
print("disagreements:", len(dis), Counter((d["gold"], d["audit"]) for d in dis).most_common(6))
print("by behaviour:", Counter(d["behaviour"] for d in dis).most_common(8))
jl_write(os.path.join(DATA, "audit_disagreements.jsonl"), dis)
