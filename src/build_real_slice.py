"""Real-email slice from the public Enron corpus (CMU release of the FERC-published mailboxes).

Streams the tarball (no full extraction), keeps messages that mention a purchase order, and writes
data/real_candidates.jsonl. Personal names/emails in headers are NOT kept: only subject and body.
Usage: python src/build_real_slice.py data/raw/enron.tar.gz data/real_candidates.jsonl
"""
import email
import hashlib
import json
import re
import sys
import tarfile
import random

PO_RE = re.compile(r"(purchase\s+order|\bP\.?\s?O\.?\s*(?:#|no\.?|number|num)\s*[:#]?\s*[A-Z0-9-]{4,})", re.I)
NUM_RE = re.compile(r"\bP\.?\s?O\.?\s*(?:#|no\.?|number|num)?\s*[:#]?\s*([A-Z]{0,3}[0-9][A-Z0-9-]{3,})", re.I)


def body_of(msg):
    if msg.is_multipart():
        for p in msg.walk():
            if p.get_content_type() == "text/plain":
                return p.get_payload(decode=True).decode("utf-8", "replace")
        return ""
    return msg.get_payload(decode=True).decode("utf-8", "replace")


def main(tar_path, out_path, cap=6000):
    rows, seen = [], set()
    with tarfile.open(tar_path, "r|gz") as tf:
        for m in tf:
            if not m.isfile() or m.size > 60000 or m.size < 300:
                continue
            raw = tf.extractfile(m).read()
            try:
                msg = email.message_from_bytes(raw)
                subj = (msg.get("Subject") or "").strip()
                body = body_of(msg).strip()
            except Exception:  # noqa: BLE001
                continue
            if not PO_RE.search(subj + "\n" + body) or len(body) < 100 or len(body) > 8000:
                continue
            key = re.sub(r"\W+", "", body[:300].lower())
            if key in seen:
                continue
            seen.add(key)
            cand = sorted(set(x.upper() for x in NUM_RE.findall(subj + "\n" + body)))
            rows.append(dict(src_sha=hashlib.sha256(m.name.encode()).hexdigest()[:16],  # no mailbox-owner names kept
                             subject=subj[:200], body=body, regex_po=cand))
            if len(rows) >= cap:
                break
    random.Random(20261110).shuffle(rows)
    with open(out_path, "w") as f:
        for i, r in enumerate(rows):
            r["id"] = f"real-{i:05d}"
            f.write(json.dumps(r, sort_keys=True) + "\n")
    print("candidates", len(rows), "with regex po", sum(1 for r in rows if r["regex_po"]))


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
