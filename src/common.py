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
    """Align claimed lines to ERP lines: by explicit line number, else by best token overlap.
    Returns {erp_idx(1-based): claimed_line or None}."""
    out = {}
    used = set()
    for i, pl in enumerate(po_lines, 1):
        hit = None
        for j, c in enumerate(claimed):
            if j in used:
                continue
            if c.get("line") == i:
                hit = j
                break
        if hit is None:
            best, bj = 0.0, None
            pt = toks(pl["desc"])
            for j, c in enumerate(claimed):
                if j in used or c.get("line") not in (None, 0):
                    continue
                ct = toks(c.get("desc", ""))
                if not pt or not ct:
                    continue
                ov = len(pt & ct) / max(1, len(pt | ct))
                if ov > best:
                    best, bj = ov, j
            if bj is not None and best >= 0.25:
                hit = bj
        if hit is not None:
            used.add(hit)
            out[i] = claimed[hit]
        else:
            out[i] = None
    return out


def _num(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def policy(claims, po):
    """claims: {po_number, intent, lines:[{line,desc,qty,unit_price}], ship_date, conditions}
    po: ERP record. Returns (label, reason)."""
    if not isinstance(claims, dict):
        return "needs-human", "no_claims"
    intent = claims.get("intent")
    if intent == "reject":
        return "reject", "supplier_declines"
    if intent != "confirm":
        return "needs-human", "not_a_confirmation"
    if (claims.get("po_number") or "").strip().upper() != po["po_num"].upper():
        return "needs-human", "po_number_mismatch_or_missing"
    if claims.get("conditions"):
        return "needs-human", "conditions"
    m = match_lines(po["lines"], claims.get("lines") or [])
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
