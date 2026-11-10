"""Bind the preregistration to exact code, data, model metadata and gate thresholds.

Freeze only after dev selection, before any held-out model result. A rerun can
verify the same frozen artifacts; changing any bound artifact requires a new
experiment and cannot silently replace this preregistration.
"""
import argparse
import json
import pathlib
from common import ROOT, sha256_file

ROOT_PATH = pathlib.Path(ROOT)
MANIFEST = ROOT_PATH / "docs/PREREG.manifest.json"


def frozen_paths():
    paths = list((ROOT_PATH / "src").glob("*.py"))
    paths += list((ROOT_PATH / "tests").glob("*.py"))
    paths += [ROOT_PATH / p for p in ("data/cases.jsonl", "data/emails.jsonl", "docs/GATE.json",
                                     "docs/PREREG.md", "docs/MODELS.json", "requirements.txt")]
    return sorted(str(p.relative_to(ROOT_PATH)) for p in paths)


def verify():
    if not MANIFEST.exists():
        raise ValueError("No frozen experiment manifest")
    manifest = json.loads(MANIFEST.read_text())
    expected = manifest["sha256"]
    if set(expected) != set(frozen_paths()):
        raise ValueError("Frozen source/data inventory changed")
    for path, sha in expected.items():
        if sha256_file(ROOT_PATH / path) != sha:
            raise ValueError("Frozen artifact changed: " + path)
    return manifest


def freeze():
    if MANIFEST.exists():
        return verify()
    # The freeze cannot be created after any held-out inference file exists.
    existing = [str(p) for split in ("h1", "h2") for p in (ROOT_PATH / "runs").glob(f"*_{split}.shard*.jsonl")]
    if existing:
        raise ValueError("Held-out output already exists; do not retroactively preregister")
    manifest = {"schema": 1, "sha256": {p: sha256_file(ROOT_PATH / p) for p in frozen_paths()}}
    MANIFEST.write_text(json.dumps(manifest, indent=2) + "\n")
    (ROOT_PATH / "docs/PREREG.sha256").write_text(sha256_file(ROOT_PATH / "docs/PREREG.md") + "  PREREG.md\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--freeze", action="store_true")
    args = parser.parse_args()
    result = freeze() if args.freeze else verify()
    print("Verified frozen artifacts:", len(result["sha256"]))
