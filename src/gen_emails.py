"""Write SYNTHETIC supplier emails from the case spec using the claude CLI (subscription, no API key).

Every email is synthetic: the ERP PO rows are real public records, the email text is model-written to a
spec whose facts are the gold claims. A programmatic check confirms each stated number, PO number and
date really appears in the text; failures are regenerated (up to 2 retries), then dropped and logged.
Usage: python src/gen_emails.py --cases data/cases.jsonl --out data/emails.jsonl [--model sonnet] [--workers 6]
Resumable: ids already in --out are skipped.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, jl_read  # noqa: E402

# Run the CLI with the configured user safety settings preserved. Prompts contain public or synthetic data only.
NEUTRAL_CWD = os.environ.get("LABE_NEUTRAL_CWD", ROOT)

STYLE = {
    "terse": "very short, two to four lines, sales-desk shorthand, no greeting fluff",
    "formal": "polite formal business email with greeting and signature block",
    "forwarded_thread": "a short reply on top, followed by the quoted original purchase order message from the buyer (the quoted original lists the PO as the buyer sent it); the reply's claims are what counts",
    "table": "includes a small plain-text table or aligned list of the lines with qty and unit price columns",
    "chatty_typos": "casual, a couple of natural typos, conversational",
    "line_by_line": "goes through the lines one by one in prose, using line numbers or item names",
}


def money(v):
    return f"{v:.2f}"


def spec_for(c):
    cl, po = c["claims"], c["po"]
    buyer = "City of Baton Rouge Purchasing" if po["source"] == "brla" else "Oregon Lottery purchasing"
    out = [f"id: {c['id']}", f"supplier (the sender): {po['vendor']}", f"buyer (the recipient): {buyer}",
           f"style: {STYLE[c['style']]}"]
    out.append(f"buyer's original PO (for context, as the buyer sent it): PO number {po['po_num']}, dated {po['order_date']}, lines: " +
               "; ".join(f"line {i+1}: {l['desc']} x{l['qty']} at ${money(l['unit_cost'])} each" for i, l in enumerate(po["lines"])))
    if c["behaviour"] == "offtopic":
        out.append(f"the email is {c['note']}. It must NOT mention any PO number, quantity or price.")
    elif c["behaviour"] == "ambiguous":
        pn = f"cite PO number {cl['po_number']}" if cl["po_number"] else "do not cite any PO number"
        out.append(f"the email only acknowledges receipt of the order and says they will review and revert; {pn}; state NO quantities, prices or dates.")
    elif c["behaviour"] == "reject":
        out.append(f"the supplier declines/cancels the order (give a plausible reason); cite PO number {cl['po_number']}; state no quantities or prices.")
    else:
        out.append(f"the supplier is responding to the order. It MUST cite exactly this PO number: {cl['po_number']}.")
        for l in cl["lines"]:
            extra = ""
            if l.get("subst"):
                extra = " (the supplier ships a DIFFERENT but similar item/model instead of the PO item on this line; name it)"
            out.append(f"  must state for PO line {l['line']} ({l['desc']}): quantity exactly {l['qty']}, unit price exactly ${money(l['unit_price'])}{extra}")
        if c["behaviour"] == "partial":
            out.append("  on the line with the reduced quantity, say that this quantity ships now and the remainder is backordered")
        if cl["ship_date"]:
            d = date.fromisoformat(cl["ship_date"])
            out.append(f"  must state the ship date {d.isoformat()} in any natural human format that includes the year")
        else:
            out.append("  must NOT state any ship date")
        out.append("  the supplier is confirming the order on these terms; do not say whether it matches the buyer's PO; do not mention other numbers that look like quantities or prices")
    return "\n".join(out)


PROMPT = """You write realistic SYNTHETIC supplier emails for testing a purchase-order confirmation system.
For each case below write one email (subject and body) from the supplier to the buyer, following its spec exactly.
Facts marked 'must' must appear verbatim in the email text. Vary wording naturally; invent plausible first names for the sender; no real private data.
Output ONLY a JSON array, one object per case: {{"id": "...", "subject": "...", "body": "..."}}. No prose, no code fences.

{cases}
"""


def validate(c, e):
    body = (e.get("subject", "") + "\n" + e.get("body", ""))
    cl = c["claims"]
    if len(e.get("body", "")) < 20:
        return "empty"
    if c["behaviour"] in ("offtopic",):
        return None if not re.search(r"\b[A-Z]{1,2}\d{5,}\b", body) else "mentions_po"
    if cl["po_number"] and cl["po_number"] not in body:
        return "po_missing"
    for l in cl["lines"]:
        q = str(l["qty"])
        if not re.search(r"(?<![\d.,])" + re.escape(q) + r"(?![\d]|\.\d)", body):
            return f"qty_missing_{l['line']}"
        p = l["unit_price"]
        forms = {money(p), f"{p:,.2f}", (str(int(p)) if p == int(p) else "x__")}
        if not any(re.search(r"(?<![\d.,])" + re.escape(f) + r"(?![\d])", body) for f in forms):
            return f"price_missing_{l['line']}"
    if cl["ship_date"]:
        d = date.fromisoformat(cl["ship_date"])
        if str(d.year) not in body or not re.search(r"\b0?%d\b" % d.day, body):
            return "date_missing"
    return None


def call_claude(prompt, model):
    r = subprocess.run(["claude", "-p", "--model", model, "--tools", "", "--no-session-persistence",
                        "--disable-slash-commands"],
                       input=prompt, capture_output=True, text=True, timeout=420, cwd=NEUTRAL_CWD)
    return r.stdout


def parse(txt):
    m = re.search(r"\[.*\]", txt, re.S)
    return json.loads(m.group(0)) if m else []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="sonnet")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    cases = jl_read(a.cases)
    done = {r["id"] for r in jl_read(a.out)} if os.path.exists(a.out) else set()
    todo = [c for c in cases if c["id"] not in done]
    if a.limit:
        todo = todo[:a.limit]
    lock = threading.Lock()
    stats = {"ok": 0, "bad": 0, "calls": 0}
    pending = list(todo)

    def work(batch):
        for attempt in range(3):
            if not batch:
                return
            try:
                txt = call_claude(PROMPT.format(cases="\n\n".join(spec_for(c) for c in batch)), a.model)
                got = {e.get("id"): e for e in parse(txt) if isinstance(e, dict)}
            except Exception as ex:  # noqa: BLE001
                got = {}
                print("call error", repr(ex)[:120], file=sys.stderr)
            rest = []
            with lock:
                stats["calls"] += 1
                for c in batch:
                    e = got.get(c["id"])
                    why = validate(c, e) if e else "missing"
                    if why is None:
                        with open(a.out, "a") as f:
                            f.write(json.dumps(dict(id=c["id"], subject=e["subject"], body=e["body"], gen_model=a.model,
                                                    synthetic=True, attempts=attempt + 1), sort_keys=True) + "\n")
                        stats["ok"] += 1
                    else:
                        rest.append(c)
                        if attempt == 2:
                            stats["bad"] += 1
                            with open(a.out + ".dropped", "a") as f:
                                f.write(json.dumps(dict(id=c["id"], why=why)) + "\n")
                print(time.strftime("%H:%M:%S"), stats, flush=True)
            batch = rest

    batches = [pending[i:i + a.batch] for i in range(0, len(pending), a.batch)]
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(work, batches))
    print("FINAL", stats)


if __name__ == "__main__":
    main()
