"""Immutable original snapshot and exact frozen-input checks. Never refreeze."""
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "original/experiment-08f8afc.zip"
ARCHIVE_SHA256 = "6024b164c989db8ddb6e41015f5496b7cc1c9883dbb6c7f58d0b56d697ff460f"
ORIGINAL_HEAD = "08f8afc92e2b39b987511e5d24302666bf34df7f"


def verify():
    if hashlib.sha256(ARCHIVE.read_bytes()).hexdigest() != ARCHIVE_SHA256:
        raise ValueError("Immutable original archive SHA mismatch")
    with zipfile.ZipFile(ARCHIVE) as z:
        manifest = json.loads(z.read("docs/PREREG.manifest.json"))
        expected_code = {n for n in manifest["sha256"] if n.startswith(("src/", "tests/"))}
        actual_code = {str(p.relative_to(ROOT)) for folder in ("src", "tests") for p in (ROOT / folder).glob("*.py")}
        if actual_code != expected_code:
            raise ValueError("Frozen source/test inventory changed")
        for name, sha in manifest["sha256"].items():
            if hashlib.sha256(z.read(name)).hexdigest() != sha:
                raise ValueError("Original archive frozen input mismatch: " + name)
            if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != sha:
                raise ValueError("Current frozen input changed: " + name)
        # All originally recorded outputs remain byte-for-byte immutable, too.
        protected = [n for n in z.namelist() if n.startswith(("runs/", "results/")) and not n.endswith("/")]
        protected += ["docs/PREREG.manifest.json", "docs/PREREG.sha256"]
        for name in protected:
            if (ROOT / name).read_bytes() != z.read(name):
                raise ValueError("Original record changed: " + name)
        for name in z.namelist():
            if Path(name).is_absolute() or ".." in Path(name).parts:
                raise ValueError("Unsafe archive member")
    return dict(original_head=ORIGINAL_HEAD, archive_sha256=ARCHIVE_SHA256,
                frozen_artifacts=len(manifest["sha256"]), preserved_records=len(protected))
