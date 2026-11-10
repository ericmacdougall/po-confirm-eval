"""Recommended replay: immutable original experiment AND separate corrected accounting.

No model inference. The original replay writes only into an owned temporary copy.
"""
import hashlib
import json
import subprocess
import sys
import tempfile
import zipfile
from accounting.original import ROOT, ARCHIVE, verify


def main():
    receipt = verify()
    work = ROOT / "accounting/work"
    work.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="original-08f8afc-", dir=work) as tmp:
        with zipfile.ZipFile(ARCHIVE) as z:
            z.extractall(tmp)  # exact SHA-bound archive; member paths checked by verify()
        subprocess.run([sys.executable, "src/reproduce.py"], cwd=tmp, check=True)
        output = open(tmp + "/results/reproduction.json", "rb").read()
        receipt.update(original_replay="PASS", replay_output_sha256=hashlib.sha256(output).hexdigest())
    subprocess.run([sys.executable, "-m", "accounting.reconcile"], cwd=ROOT, check=True)
    verify()  # the original records in this checkout must still be untouched
    (ROOT / "accounting/results/original-replay-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print("RERUN PASS: historical replay + corrected post-opening accounting; no original files overwritten.")


if __name__ == "__main__":
    main()
