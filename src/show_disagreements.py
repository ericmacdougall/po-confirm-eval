import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import DATA, jl_read
cs = {c["id"]: c for c in jl_read(os.path.join(DATA, "cases.jsonl"))}
es = {e["id"]: e for e in jl_read(os.path.join(DATA, "emails.jsonl"))}
for d in jl_read(os.path.join(DATA, "audit_disagreements.jsonl")):
    print(d["id"], d["behaviour"], "gold", d["gold_claims"]["ship_date"], d["gold_claims"]["po_number"])
    print("audit", d["audit_claims"])
    print(es[d["id"]]["body"][:700])
    print("PO", cs[d["id"]]["po"]["po_num"], cs[d["id"]]["po"]["lines"])
    print("====")
