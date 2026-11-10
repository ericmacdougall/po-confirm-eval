import sys, tarfile, email, re
sys.path.insert(0, "src")
from build_real_slice import PO_RE, body_of
n = files = big = small = po = okbody = 0
with tarfile.open("data/raw/enron.tar.gz", "r|gz") as tf:
    for m in tf:
        n += 1
        if not m.isfile():
            continue
        files += 1
        if m.size > 20000: big += 1; continue
        if m.size < 300: small += 1; continue
        raw = tf.extractfile(m).read()
        msg = email.message_from_bytes(raw)
        t = (msg.get("Subject") or "") + "\n" + body_of(msg)
        if PO_RE.search(t):
            po += 1
            if 150 <= len(body_of(msg)) <= 3500: okbody += 1
print(n, files, big, small, po, okbody)
