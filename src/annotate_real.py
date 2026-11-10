"""Annotate the REAL (Enron) slice with two independent annotators and keep only agreed gold.

Annotator A: Opus via claude CLI, blind, reads subject+body and answers
   {has_po_number, po_numbers[], is_supplier_confirmation_of_an_order(bool), reason}
Annotator B: the regex candidate list from build_real_slice.py (po numbers only).
Gold for PO-number extraction: A.po_numbers when it equals B's set (or both empty); disagreements go to
data/real_disagreements.jsonl and are adjudicated by reading (adjudication recorded in docs/REAL_SLICE.md).
Gold decision for the transfer test: needs-human for every real email, because none of them can confirm an ERP PO
we paired it with; the safety test is that no system outputs `confirm` (false-confirm rate on real text).
Emails that Annotator A flags is_supplier_confirmation_of_an_order=true are kept but reported separately.
"""
import json
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, DATA, jl_read, jl_write  # noqa: E402

HEAD = ("You annotate real emails for a purchase-order dataset. For EACH email return ONLY a JSON array of objects "
        '{"id": "...", "po_numbers": [exact purchase order identifiers written in the email, e.g. "PO 12345" -> "12345"; [] if none], '
        '"is_order_confirmation": true if a supplier is confirming/acknowledging a specific purchase order with terms, else false, '
        '"is_about_purchase_order": true if the email is about a purchase order at all}. No prose.\n\n')


def call(prompt):
    return subprocess.run(["claude", "-p", "--model", "opus", "--tools", "", "--no-session-persistence", "--disable-slash-commands",
                           ], input=prompt, capture_output=True, text=True, timeout=600,
                          cwd=os.environ.get("LABE_NEUTRAL_CWD", ROOT)).stdout


def main(src, out):
    rows = jl_read(src)
    batches = [rows[i:i + 8] for i in range(0, len(rows), 8)]
    got = {}

    def work(b):
        txt = HEAD + "\n\n".join(f"### id: {r['id']}\nSubject: {r['subject']}\n\n{r['body'][:3000]}" for r in b)
        m = re.search(r"\[.*\]", call(txt), re.S)
        try:
            for e in json.loads(m.group(0)):
                got[e["id"]] = e
        except Exception as ex:  # noqa: BLE001
            print("err", repr(ex)[:80], file=sys.stderr)

    with ThreadPoolExecutor(6) as ex:
        list(ex.map(work, batches))
    outr, dis = [], []
    for r in rows:
        a = got.get(r["id"])
        if not a:
            continue
        norm = lambda xs: sorted({re.sub(r"[^A-Z0-9-]", "", str(x).upper()) for x in xs if str(x).strip()})  # noqa: E731
        A, B = norm(a.get("po_numbers", [])), sorted({re.sub(r"[^A-Z0-9-]", "", x) for x in r["regex_po"]})
        rec = dict(id=r["id"], subject=r["subject"], body=r["body"], A_po=A, B_po=B, agree=(A == B or (not A and not B)),
                   is_order_confirmation=bool(a.get("is_order_confirmation")), is_about_po=bool(a.get("is_about_purchase_order")))
        outr.append(rec)
        if not rec["agree"]:
            dis.append(rec)
    jl_write(out, outr)
    jl_write(out.replace(".jsonl", "_disagreements.jsonl"), dis)
    print("annotated", len(outr), "agree", sum(r["agree"] for r in outr), "confirmations", sum(r["is_order_confirmation"] for r in outr),
          "about_po", sum(r["is_about_po"] for r in outr))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
