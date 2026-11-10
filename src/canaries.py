"""Controls that MUST fail (and one that must pass). They write run files in the same format as real systems.

python src/canaries.py --split dev
  canary-always_confirm : rubber stamp, repeats the ERP PO back as the supplier's claims
  canary-always_human   : never automates
  canary-price_drift    : oracle extraction but every unit price multiplied by 1.02 (subtle numeric bug)
  canary-drop_last_line : oracle extraction but the last line of multi-line POs is dropped
  canary-shuffled       : oracle claims from a different case (labels decoupled from the email)
  control-oracle        : the gold claims; the gate must SHIP it (non-regression control)
"""
import argparse
import copy
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, SEED, jl_read, jl_write, DATA  # noqa: E402
import extractors as X  # noqa: E402


def claims_from_po(po):
    return dict(po_number=po["po_num"], intent="confirm", conditions=False, ship_date=None,
                lines=[dict(line=i + 1, desc=l["desc"], qty=l["qty"], unit_price=l["unit_cost"]) for i, l in enumerate(po["lines"])])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", required=True)
    ap.add_argument("--open-heldout")
    a = ap.parse_args()
    from run_system import guard_heldout
    guard_heldout(a.split, a.open_heldout)
    cases = [c for c in jl_read(os.path.join(DATA, "cases.jsonl"))
             if c["split"] == a.split]
    have = {e["id"] for e in jl_read(os.path.join(DATA, "emails.jsonl"))}
    cases = [c for c in cases if c["id"] in have]
    rng = random.Random(SEED)
    others = [c["claims"] for c in cases]
    rng.shuffle(others)
    makers = {
        "canary-always_confirm": lambda c, i: claims_from_po(c["po"]),
        "canary-always_human": lambda c, i: dict(X.ABSTAIN),
        "canary-price_drift": lambda c, i: _drift(c["claims"]),
        "canary-drop_last_line": lambda c, i: _droplast(c["claims"]),
        "canary-shuffled": lambda c, i: others[i],
        "control-oracle": lambda c, i: copy.deepcopy(c["claims"]),
    }
    os.makedirs(os.path.join(ROOT, "runs"), exist_ok=True)
    for tag, mk in makers.items():
        rows = [dict(id=c["id"], system=tag, model="canary", claims=mk(c, i), raw="", attempts=0, latency_s=0, completion_tokens=0)
                for i, c in enumerate(cases)]
        jl_write(os.path.join(ROOT, "runs", f"{tag}_{a.split}.shard0.jsonl"), rows)
        print("wrote", tag, len(rows))


def _drift(cl):
    c = copy.deepcopy(cl)
    for l in c["lines"]:
        l["unit_price"] = round(l["unit_price"] * 1.02, 2)
    return c


def _droplast(cl):
    c = copy.deepcopy(cl)
    if len(c["lines"]) > 1:
        c["lines"] = c["lines"][:-1]
    return c


if __name__ == "__main__":
    main()
