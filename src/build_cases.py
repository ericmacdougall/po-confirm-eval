"""Build ERP purchase orders from public data and assign each a supplier-behaviour case.

Sources (both public record, licence in docs/DATA.md):
  - Baton Rouge Legacy Purchase Orders (Public Domain)
  - Oregon Lottery contracts / purchase orders (Public Domain U.S. Government)
Usage: python src/build_cases.py   (reads data/raw/*.json, writes data/cases.jsonl)
Emails are NOT here: gen_emails.py writes them (synthetic, from the spec below).
"""
import json
import os
import random
import re
from collections import defaultdict
from datetime import date, timedelta

from common import DATA, SEED, policy, jl_write

RAW = os.path.join(DATA, "raw")
SPLIT_SIZES = [("pool", 300), ("dev", 600), ("h1", 450), ("h2", 450), ("fb", 360)]
BEHAVIOURS = [  # (name, weight)
    ("exact", .22), ("tol_price", .06), ("exact_nodate", .08),
    ("qty_diff", .10), ("price_diff", .10), ("date_late", .06), ("substitution", .06),
    ("partial", .06), ("unknown_po", .05), ("ambiguous", .06), ("offtopic", .05),
    ("reject", .10),
]
STYLES = [("terse", .2), ("formal", .2), ("forwarded_thread", .15), ("table", .15),
          ("chatty_typos", .15), ("line_by_line", .15)]


def clean_desc(s):
    s = re.sub(r"\s{2,}", " | ", (s or "").strip())
    s = s.split(" | ")[0].strip()
    return s[:70]


def load_brla():
    rows = json.load(open(os.path.join(RAW, "brla_legacy_po.json")))
    pos = defaultdict(lambda: None)
    lines = defaultdict(list)
    for r in rows:
        if r["rec_type"] != "D":
            continue
        try:
            q, c = float(r["dt_qty_ord"]), float(r["dt_unit_cost"])
        except (KeyError, ValueError):
            continue
        d = clean_desc(r.get("dt_stock_desc"))
        um = (r.get("dt_um_desc") or "").strip()
        if q < 1 or q != int(q) or not (0.5 <= c <= 50000) or len(d) < 8 or d[0] in "*#-=" \
                or um.upper() in ("JOB", "LUMP SUM", "") or r.get("po_stat_desc") == "CANCELLED":
            continue
        pos[r["po_num"]] = dict(po_num=r["po_num"], source="brla", vendor=(r.get("vend_name_1") or "").strip().title(),
                                city=(r.get("vend_city") or "").strip().title(), order_date=r["po_in_date"][:10])
        lines[r["po_num"]].append(dict(desc=d, qty=int(q), uom=um.lower(), unit_cost=round(c, 2)))
    out = []
    for k, p in pos.items():
        ls = lines[k]
        if 1 <= len(ls) <= 4 and len(set(l["desc"] for l in ls)) == len(ls):
            p["lines"] = ls
            out.append(p)
    return out


def load_oregon():
    rows = json.load(open(os.path.join(RAW, "oregon_lottery_po.json")))
    pos, lines = {}, defaultdict(list)
    for r in rows:
        try:
            q, c = float(r["quantity"]), float(r["unit_price"])
        except (KeyError, ValueError):
            continue
        d = (r.get("line_item_description") or "").strip()[:70]
        if q < 1 or q != int(q) or c <= 1 or len(d) < 6 or not r.get("vendor") or not r.get("purchase_order") \
                or not r.get("created"):
            continue
        po = "OR" + r["purchase_order"]
        pos[po] = dict(po_num=po, source="oregon", vendor=r["vendor"].strip().title(), city=(r.get("city") or "").title(),
                       order_date=r["created"][:10])
        lines[po].append(dict(desc=d, qty=int(q), uom="each", unit_cost=round(c, 2)))
    out = []
    for k, p in pos.items():
        ls = lines[k]
        if 1 <= len(ls) <= 4 and len(set(l["desc"] for l in ls)) == len(ls):
            p["lines"] = ls
            out.append(p)
    return out


def wchoice(rng, pairs):
    names, w = zip(*pairs)
    return rng.choices(names, w)[0]


def make_case(po, rng):
    """Pick a behaviour, derive the gold claims and generator facts."""
    n = len(po["lines"])
    beh = wchoice(rng, BEHAVIOURS)
    for _ in range(10):
        if beh == "partial" and not any(l["qty"] >= 2 for l in po["lines"]):
            beh = "qty_diff"
        if beh == "qty_diff" and False:
            pass
        break
    od = date.fromisoformat(po["order_date"])
    claims = dict(po_number=po["po_num"], intent="confirm", ship_date=None, conditions=False,
                  lines=[dict(line=i + 1, desc=l["desc"], qty=l["qty"], unit_price=l["unit_cost"])
                         for i, l in enumerate(po["lines"])])
    note = ""
    idx = rng.randrange(n)
    if beh in ("exact", "tol_price", "unknown_po", "substitution", "partial", "qty_diff", "price_diff"):
        claims["ship_date"] = (od + timedelta(days=rng.randint(3, 25))).isoformat()
    if beh == "exact_nodate":
        pass
    elif beh == "tol_price":
        l = claims["lines"][idx]
        for _ in range(20):
            p = round(l["unit_price"] * (1 + rng.choice([-1, 1]) * rng.uniform(0.001, 0.008)), 2)
            if p != l["unit_price"] and abs(p - l["unit_price"]) <= 0.01 * l["unit_price"]:
                l["unit_price"] = p
                break
        if l["unit_price"] == po["lines"][idx]["unit_cost"]:
            beh = "exact"  # price too small for a sub-1-percent change at 2 decimals
        else:
            note = "unit price differs by under 1 percent from the PO (rounding)"
    elif beh == "qty_diff":
        l = claims["lines"][idx]
        q = l["qty"]
        l["qty"] = max(1, q + rng.choice([-1, 1]) * rng.randint(1, max(1, q // 2))) if q > 1 else q + rng.randint(1, 3)
        if l["qty"] == q:
            l["qty"] = q + 1
        note = "supplier states a different quantity"
    elif beh == "price_diff":
        l = claims["lines"][idx]
        l["unit_price"] = round(l["unit_price"] * (1 + rng.choice([-1, 1]) * rng.uniform(0.04, 0.3)), 2)
        note = "supplier states a different unit price"
    elif beh == "date_late":
        claims["ship_date"] = (od + timedelta(days=rng.randint(45, 120))).isoformat()
        note = "ship date is far later than the PO date"
    elif beh == "substitution":
        claims["conditions"] = True
        note = "supplier substitutes a different item/model on one line (invent a plausible one)"
        claims["lines"][idx]["subst"] = True
    elif beh == "partial":
        cand = [i for i, l in enumerate(po["lines"]) if l["qty"] >= 2]
        idx = rng.choice(cand)
        l = claims["lines"][idx]
        l["qty"] = rng.randint(1, l["qty"] - 1)
        claims["conditions"] = True
        note = "only part of this line ships now, the remainder is backordered"
    elif beh == "unknown_po":
        s = po["po_num"]
        digs = [i for i, ch in enumerate(s) if ch.isdigit()]
        i = rng.choice(digs[-3:])
        wrong = s[:i] + str((int(s[i]) + rng.randint(1, 8)) % 10) + s[i + 1:]
        claims["po_number"] = wrong
        note = "the PO number the supplier cites is not the buyer's PO number"
    elif beh == "reject":
        claims = dict(po_number=po["po_num"], intent="reject", ship_date=None, conditions=False, lines=[])
        note = "supplier declines or cancels the order (cannot supply, discontinued, out of business, etc.)"
    elif beh == "ambiguous":
        claims = dict(po_number=po["po_num"] if rng.random() < .6 else None, intent="other", ship_date=None,
                      conditions=False, lines=[])
        note = "supplier acknowledges receipt only, states no quantities or prices, says they will revert"
    elif beh == "offtopic":
        claims = dict(po_number=None, intent="other", ship_date=None, conditions=False, lines=[])
        note = rng.choice(["an out-of-office auto-reply", "a marketing newsletter from the supplier",
                           "a request for payment status on an old invoice", "a question about payment terms or a W-9"])
    label, reason = policy(claims, po)
    return dict(behaviour=beh, claims=claims, note=note, label=label, reason=reason)


def main():
    rng = random.Random(SEED)
    brla, ore = load_brla(), load_oregon()
    print("eligible POs: brla", len(brla), "oregon", len(ore))
    total = sum(n for _, n in SPLIT_SIZES)
    n_or = int(total * 0.15)
    rng.shuffle(brla)
    rng.shuffle(ore)
    chosen = brla[: total - n_or] + ore[:n_or]
    rng.shuffle(chosen)
    cases, k = [], 0
    for split, size in SPLIT_SIZES:
        for po in chosen[k:k + size]:
            g = make_case(po, rng)
            cases.append(dict(id=f"{split}-{len(cases):05d}", split=split, po=po, style=wchoice(rng, STYLES), **g))
        k += size
    jl_write(os.path.join(DATA, "cases.jsonl"), cases)
    from collections import Counter
    print(Counter(c["split"] for c in cases))
    print(Counter(c["label"] for c in cases))
    print(Counter(c["behaviour"] for c in cases))
    # consistency: behaviour -> label must be the documented mapping
    exp = {"exact": "confirm", "tol_price": "confirm", "exact_nodate": "confirm", "reject": "reject"}
    bad = [c["id"] for c in cases if c["label"] != exp.get(c["behaviour"], "needs-human")]
    assert not bad, bad[:5]
    print("behaviour/label consistency ok for", len(cases))


if __name__ == "__main__":
    main()
