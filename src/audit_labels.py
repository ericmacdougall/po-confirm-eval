"""Label-noise audit: a DIFFERENT model (Opus via the claude CLI) blindly re-extracts the claims of each email.
It never sees the gold claims or the label. Disagreements with gold are queued for human adjudication.

python src/audit_labels.py --splits h1,h2,dev --per-split dev=150 --out data/audit.jsonl
"""
import argparse
import json
import os
import random
import re
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import ROOT, DATA, SEED, jl_read, policy  # noqa: E402
import extractors as X  # noqa: E402

HEAD = ("You audit labels for a purchase-order email dataset. For EACH email below, extract what the supplier states in their own "
        "new message (ignore quoted earlier messages). Return ONLY a JSON array with one object per email: "
        '{"id": "<id>", "claims": ' + X.SCHEMA + "}.\n"
        "intent: confirm only if the supplier confirms/accepts this order; reject if they decline/cancel; other for acknowledgements "
        "without terms, questions, auto-replies, newsletters, anything else. conditions: true if partial, backordered, substituted or conditional. "
        "Numbers only (no $ or commas). Do not invent values.\n\n")


def call(prompt, model):
    r = subprocess.run(["claude", "-p", "--model", model, "--tools", "", "--no-session-persistence", "--disable-slash-commands",
                        ], input=prompt, capture_output=True, text=True, timeout=600,
                       cwd=os.environ.get("LABE_NEUTRAL_CWD", ROOT))
    return r.stdout


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--splits", default="h1,h2")
    ap.add_argument("--per-split", default="")
    ap.add_argument("--out", required=True)
    ap.add_argument("--model", default="opus")
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--batch", type=int, default=8)
    a = ap.parse_args()
    caps = dict(x.split("=") for x in a.per_split.split(",") if x)
    cases = {c["id"]: c for c in jl_read(os.path.join(DATA, "cases.jsonl"))}
    emails = {e["id"]: e for e in jl_read(os.path.join(DATA, "emails.jsonl"))}
    done = {r["id"] for r in jl_read(a.out)} if os.path.exists(a.out) else set()
    ids = []
    rng = random.Random(SEED)
    for s in a.splits.split(","):
        pool = sorted(i for i in emails if cases[i]["split"] == s)
        if s in caps:
            pool = rng.sample(pool, int(caps[s]))
        ids += pool
    ids = [i for i in ids if i not in done]
    lock = threading.Lock()

    def work(b):
        txt = HEAD + "\n\n".join(f"### id: {i}\n{X.text_of(emails[i]['subject'], emails[i]['body'])}" for i in b)
        try:
            m = re.search(r"\[.*\]", call(txt, a.model), re.S)
            got = {e["id"]: e["claims"] for e in json.loads(m.group(0))} if m else {}
        except Exception as ex:  # noqa: BLE001
            print("err", repr(ex)[:100], file=sys.stderr)
            got = {}
        with lock, open(a.out, "a") as f:
            for i in b:
                cl = X.normalise(got.get(i)) if got.get(i) else None
                lab = policy(cl, cases[i]["po"])[0] if cl else None
                f.write(json.dumps(dict(id=i, audit_model=a.model, claims=cl, audit_label=lab, gold_label=cases[i]["label"]),
                                   sort_keys=True) + "\n")
            print(len(b), "done", flush=True)

    batches = [ids[i:i + a.batch] for i in range(0, len(ids), a.batch)]
    with ThreadPoolExecutor(a.workers) as ex:
        list(ex.map(work, batches))


if __name__ == "__main__":
    main()
