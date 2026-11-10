"""Extraction systems. Each returns claims {po_number,intent,conditions,ship_date,lines[]} from email text only.

S0  rules        : regex and keyword rules, no model.
S1  llm_zero     : local open-weight LLM (llama.cpp, Qwen2.5-3B-Instruct Q4_K_M), zero-shot, naive parse.
S2  llm_valid    : S1 + validators (schema, grounding of every number in the email text, intent/lines
                   consistency), one retry with the validator's complaint, then abstain (intent=other).
S3  llm_fewshot  : S2 + k retrieved worked examples from the labelled pool (TF-IDF nearest neighbours).
S4  claude_ref   : same prompt as S2 but through the claude CLI (subscription), a stronger reference.
"""
import json
import re
import math
from datetime import date

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
PO_TOKEN = re.compile(r"\b((?:PO|OR|P)\d{5,8})\b")
MONEY = re.compile(r"\$\s?([0-9][0-9,]*\.?[0-9]*)")


def text_of(subject, body):
    return f"Subject: {subject}\n\n{body}"


def supplier_reply(text):
    """Conservative reply-on-top boundary; buyer quotes are not supplier evidence."""
    return re.split(r"\n\s*(?:-{2,}\s*(?:Original|Forwarded)|On .{5,120} wrote:|>\s)",
                    text, maxsplit=1, flags=re.I)[0]


# ---------------------------------------------------------------- dates
def parse_dates(t):
    out = []
    for m in re.finditer(r"\b(20\d\d)-(\d\d)-(\d\d)\b", t):
        out.append((m.start(), m.group(0)))
    for m in re.finditer(r"\b([A-Za-z]{3,9})\.?\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", t):
        mo = MONTHS.get(m.group(1)[:3].lower())
        if mo:
            try:
                out.append((m.start(), date(int(m.group(3)), mo, int(m.group(2))).isoformat()))
            except ValueError:
                pass
    for m in re.finditer(r"\b(\d{1,2})[ -]([A-Za-z]{3,9})\.?,?[ -](20\d\d)\b", t):
        mo = MONTHS.get(m.group(2)[:3].lower())
        if mo:
            try:
                out.append((m.start(), date(int(m.group(3)), mo, int(m.group(1))).isoformat()))
            except ValueError:
                pass
    for m in re.finditer(r"\b(\d{1,2})/(\d{1,2})/(20\d\d)\b", t):
        try:
            out.append((m.start(), date(int(m.group(3)), int(m.group(1)), int(m.group(2))).isoformat()))
        except ValueError:
            pass
    return sorted(out)


# ---------------------------------------------------------------- S0 rules
REJECT = re.compile(r"unable to (fill|fulfil|supply|ship)|cannot (fill|fulfil|supply|ship|accept)|can't (fill|fulfil|supply)|"
                    r"decline|regret|cancel|discontinued|no longer (offer|available|carry|in business)|out of business|"
                    r"not able to|will not be able|won't be able|reject", re.I)
CONFIRM = re.compile(r"confirm|acknowledg|accept|will ship|shipping|ships|scheduled to ship|processed", re.I)
COND = re.compile(r"back-?order|substitut|in place of|instead of|replac(e|ing|ement)|partial|remainder|remaining|split ship|"
                  r"ships now|ship now|balance (will|to)", re.I)


def rules_extract(subject, body):
    t = text_of(subject, body)
    # reply on top: cut at quoted original so rules look only at the new message
    cut = re.split(r"\n\s*(?:-{2,}\s*(?:Original|Forwarded)|On .{5,80} wrote:|>\s)", t, maxsplit=1)[0]
    pos = PO_TOKEN.findall(cut)
    po = pos[0] if pos else None
    intent = "other"
    if REJECT.search(cut) and not re.search(r"\bconfirm", cut, re.I):
        intent = "reject"
    elif REJECT.search(cut) and re.search(r"unable|cannot|can't|decline|regret|cancel", cut, re.I):
        intent = "reject"
    elif CONFIRM.search(cut) and (MONEY.search(cut) or po):
        intent = "confirm" if MONEY.search(cut) or re.search(r"\bqty|quantity", cut, re.I) else "other"
    lines = []
    if intent == "confirm":
        # table-like or prose: pair each money amount with the nearest preceding quantity
        for m in MONEY.finditer(cut):
            price = float(m.group(1).replace(",", "").rstrip(".") or 0)
            window = cut[max(0, m.start() - 90):m.start()]
            q = re.findall(r"(?:qty|quantity)[:\s]*([0-9][0-9,]*)|\b([0-9][0-9,]*)\s*(?:x|units?|ea|each|pcs|pieces)\b", window, re.I)
            qty = None
            if q:
                g = q[-1]
                qty = float((g[0] or g[1]).replace(",", ""))
            else:
                nums = re.findall(r"(?<![\d.$])([0-9]{1,5})(?![\d.]|\s*[%/-])", window)
                if nums:
                    qty = float(nums[-1])
            if qty is not None and price > 0:
                lines.append(dict(line=None, desc=window.strip().split("\n")[-1][-70:], qty=qty, unit_price=price))
    ds = parse_dates(cut)
    return dict(po_number=po, intent=intent, conditions=bool(COND.search(cut)),
                ship_date=ds[0][1] if ds else None, lines=lines)


# ---------------------------------------------------------------- LLM prompts
SCHEMA = ('{"po_number": string or null, "intent": "confirm" | "reject" | "other", '
          '"conditions": boolean, "ship_date": "YYYY-MM-DD" or null, '
          '"lines": [{"line": integer or null, "desc": string, "qty": number, "unit_price": number}]}')

PROMPTS = {
    "v1": ("You read a supplier email about a purchase order and extract structured data.\n"
           "Return JSON with this shape: " + SCHEMA + "\n"
           "intent is confirm if the supplier confirms the order, reject if they decline or cancel it, otherwise other. "
           "conditions is true for partial shipment, backorder, substitution or other conditions.\n\n"
           "EMAIL:\n{email}\n\nJSON:"),
    # v2 written after dev error analysis (see docs/RUNLOG.md): quoted text trap, only stated values, no guessing
    "v2": ("You read a supplier email about a purchase order and extract structured data.\n"
           "Return ONLY a JSON object with this shape: " + SCHEMA + "\n"
           "Rules:\n"
           "- Use only what the supplier states in their own new message. Ignore quoted earlier messages (lines starting with '>' "
           "or after 'Original Message' or 'wrote:'); those are the buyer's text, not the supplier's claims.\n"
           "- po_number: the PO number the supplier cites, exactly as written; null if none.\n"
           "- intent: confirm only if the supplier is confirming/accepting this order; reject if they decline or cancel; "
           "other for acknowledgements without terms, questions, newsletters, auto-replies or anything else.\n"
           "- conditions: true if any part is partial, backordered, substituted or conditional.\n"
           "- lines: one entry per line the supplier states, with qty and unit_price exactly as stated (numbers only, no $ or commas). "
           "If a line number is given use it, else null. Do not invent lines, quantities, prices or dates.\n"
           "- ship_date as YYYY-MM-DD if the supplier states one, else null.\n\n"
           "{demos}EMAIL:\n{email}\n\nJSON:"),
}


def extract_json(txt):
    """Decode the first JSON object, respecting braces inside quoted strings."""
    s = txt.find("{")
    if s < 0:
        return None
    try:
        return json.JSONDecoder().raw_decode(txt[s:])[0]
    except ValueError:
        return None


def normalise(c):
    """Coerce an LLM JSON into the claims schema; returns None when it is not an object."""
    if not isinstance(c, dict):
        return None

    def num(x):
        if isinstance(x, bool):
            return None
        if isinstance(x, (int, float)):
            return float(x) if math.isfinite(x) else None
        if isinstance(x, str):
            try:
                value = float(x.replace("$", "").replace(",", "").strip())
                return value if math.isfinite(value) else None
            except ValueError:
                return None
        return None
    lines = []
    raw_lines = c.get("lines") or []
    if not isinstance(raw_lines, list):
        return None
    for l in raw_lines:
        if isinstance(l, dict):
            ln = l.get("line")
            lines.append(dict(line=ln if isinstance(ln, int) else None, desc=str(l.get("desc") or ""),
                              qty=num(l.get("qty")), unit_price=num(l.get("unit_price"))))
    po = c.get("po_number")
    return dict(po_number=str(po).strip() if po not in (None, "", "null") else None,
                intent=c.get("intent") if c.get("intent") in ("confirm", "reject", "other") else "other",
                conditions=bool(c.get("conditions")), ship_date=c.get("ship_date") if isinstance(c.get("ship_date"), str) else None,
                lines=lines)


def validate(claims, text):
    """S2 validators. Returns None when fine else a short complaint to feed back to the model."""
    if claims is None:
        return "Your reply was not a single valid JSON object. Return only the JSON."
    nums_in_text = set(re.findall(r"\d[\d,]*\.?\d*", text))
    flat = {n.replace(",", "").rstrip(".") for n in nums_in_text}
    flat |= {str(float(n)).rstrip("0").rstrip(".") for n in flat if re.fullmatch(r"\d+\.?\d*", n)}

    def present(v):
        if v is None:
            return False
        for f in (f"{v:.2f}", f"{v:g}", str(int(v)) if v == int(v) else f"{v:g}"):
            if f in flat:
                return True
        return False
    if claims["po_number"] and claims["po_number"] not in text:
        return f"po_number {claims['po_number']} does not appear in the email. Copy it exactly or use null."
    for l in claims["lines"]:
        if not present(l["qty"]):
            return f"qty {l['qty']} does not appear in the email text. Use only stated numbers."
        if not present(l["unit_price"]):
            return f"unit_price {l['unit_price']} does not appear in the email text. Use only stated numbers."
    if claims["ship_date"]:
        try:
            d = date.fromisoformat(claims["ship_date"])
        except ValueError:
            return "ship_date is not YYYY-MM-DD."
        if claims["ship_date"] not in {d for _, d in parse_dates(text)}:
            return "ship_date does not match any date written in the email."
    if claims["intent"] == "confirm" and not claims["lines"]:
        return "intent is confirm but no lines were extracted. Extract the stated lines or set intent to other."
    return None


ABSTAIN = dict(po_number=None, intent="other", conditions=False, ship_date=None, lines=[])
