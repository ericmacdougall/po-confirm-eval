"""Shared helpers and the deterministic decision policy (the 'checker').

The policy is the product spec: it turns what a supplier email CLAIMS plus the
ERP purchase order into confirm / reject / needs-human. The gold label of every
case is policy(gold_claims, erp_po); extraction systems are scored on how well
their claims reproduce that.
"""
import hashlib
import json
import os
import re
import math
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
RESULTS = os.path.join(ROOT, "results")
SEED = 20261110

PRICE_TOL = 0.01      # relative unit-price tolerance
DATE_WINDOW_DAYS = 30  # ship date may be at most this far after the PO date
LABELS = ("confirm", "reject", "needs-human")


def jl_read(path):
    with open(path) as f:
        return [json.loads(x) for x in f if x.strip()]


def jl_write(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, sort_keys=True) + "\n")


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def bucket(key, mod=1000):
    return int(hashlib.sha256(key.encode()).hexdigest()[:12], 16) % mod


_TOK = re.compile(r"[a-z0-9]+")


def toks(s):
    return set(_TOK.findall((s or "").lower()))


def match_lines(po_lines, claimed):
    """Align claimed lines to ERP lines: explicit line number first, then best score of token overlap plus a
    price hint, then order when counts agree and nothing is numbered. Returns {erp_idx(1-based): claimed or None}.
    (v1 used overlap only and wrongly rejected paraphrased descriptions: run log R04.)"""
    out = {i: None for i in range(1, len(po_lines) + 1)}
    used = set()
    for i in out:
        for j, c in enumerate(claimed):
            if j not in used and c.get("line") == i:
                out[i] = c
                used.add(j)
                break
    for i, pl in enumerate(po_lines, 1):
        if out[i] is not None:
            continue
        pt = toks(pl["desc"])
        best, bj = 0.0, None
        for j, c in enumerate(claimed):
            if j in used or c.get("line") not in (None, 0):
                continue
            ct = toks(c.get("desc", ""))
            ov = len(pt & ct) / max(1, len(pt | ct)) if pt and ct else 0.0
            p = _num(c.get("unit_price"))
            hint = 0.5 if p is not None and abs(p - pl["unit_cost"]) <= PRICE_TOL * pl["unit_cost"] + 1e-9 else 0.0
            if ov + hint > best:
                best, bj = ov + hint, j
        if bj is not None and best >= 0.25:
            out[i] = claimed[bj]
            used.add(bj)
    if all(c.get("line") in (None, 0) for c in claimed) and len(claimed) == len(po_lines):
        free = [j for j in range(len(claimed)) if j not in used]
        for i in out:
            if out[i] is None and free:
                out[i] = claimed[free.pop(0)]
    return out


def _num(x):
    if isinstance(x, bool):
        return None
    try:
        value = float(x)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def policy(claims, po):
    """claims: {po_number, intent, lines:[{line,desc,qty,unit_price}], ship_date, conditions}
    po: ERP record. Returns (label, reason)."""
    if not isinstance(claims, dict):
        return "needs-human", "no_claims"
    if not isinstance(claims.get("po_number"), str) or claims["po_number"].strip().upper() != po["po_num"].upper():
        return "needs-human", "po_number_mismatch_or_missing"
    intent = claims.get("intent")
    if intent == "reject":
        return "reject", "supplier_declines"
    if intent != "confirm":
        return "needs-human", "not_a_confirmation"
    if claims.get("conditions"):
        return "needs-human", "conditions"
    lines = claims.get("lines")
    if not isinstance(lines, list) or len(lines) != len(po["lines"]) or not all(isinstance(c, dict) for c in lines):
        return "needs-human", "line_count_mismatch"
    m = match_lines(po["lines"], lines)
    for i, pl in enumerate(po["lines"], 1):
        c = m[i]
        if c is None:
            return "needs-human", "line_not_confirmed"
        q, p = _num(c.get("qty")), _num(c.get("unit_price"))
        if q is None or abs(q - pl["qty"]) > 1e-9:
            return "needs-human", "qty_mismatch"
        if p is None or abs(p - pl["unit_cost"]) > PRICE_TOL * pl["unit_cost"] + 1e-9:
            return "needs-human", "price_mismatch"
    sd = claims.get("ship_date")
    if sd:
        try:
            d = date.fromisoformat(sd)
            if d > date.fromisoformat(po["order_date"]) + timedelta(days=DATE_WINDOW_DAYS):
                return "needs-human", "ship_date_late"
        except ValueError:
            return "needs-human", "bad_date"
    return "confirm", "all_checks_pass"
