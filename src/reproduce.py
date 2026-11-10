"""Replay frozen predictions, intervals, release gate and broken-system controls.

No model server or paid service is required: python3 src/reproduce.py.
For fresh inference (same frozen inputs), add --infer and set LABE_SERVER_URL
to a local llama.cpp server running the exact 7B weights in docs/MODELS.json.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from common import ROOT
from preregister import verify
from metrics import evaluate
from gate import gate


def run(*args):
    subprocess.run([sys.executable, str(Path(ROOT) / "src" / args[0]), *args[1:]], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--infer", action="store_true")
    args = parser.parse_args()
    verify()
    selection = json.loads((Path(ROOT) / "docs/SELECTION.json").read_text())
    candidate = selection["candidate"]
    spec = json.loads((Path(ROOT) / "docs/GATE.json").read_text())
    out = Path(ROOT) / "results"
    out.mkdir(exist_ok=True)
    summary = {}
    for split in ("h1", "h2", "fb"):
        if args.infer:
            if not os.environ.get("LABE_SERVER_URL"):
                raise SystemExit("Set LABE_SERVER_URL to a localhost server with the frozen model")
            for system, prompt, tag in (("s0", "v1", "s0-v1"),
                                        (selection["system"], selection["prompt"], candidate)):
                for shard in range(4):
                    run("run_system.py", "--system", system, "--split", split,
                        "--prompt", prompt, "--tag", tag, "--shard", str(shard), "--nshards", "4",
                        "--open-heldout", "reproduction")
        if split == "fb":
            continue
        run("score.py", "--split", split, "--tags", "s0-v1," + candidate,
            "--baseline", "s0-v1", "--out", str(out / (split + "-metrics.json")), "--slices")
        cand, base = evaluate(candidate, split), evaluate("s0-v1", split)
        result = gate(cand, base, spec)
        (out / (split + "-gate.json")).write_text(json.dumps(result, indent=2) + "\n")
        summary[split] = result
        if cand["missing_ids"] or base["missing_ids"]:
            raise SystemExit("Missing predictions; inference is incomplete")
    run("canaries.py", "--split", "h1", "--open-heldout", "reproduction-controls")
    base = evaluate("s0-v1", "h1")
    controls = {}
    for tag in ("control-oracle", "canary-always_confirm", "canary-always_human",
                "canary-price_drift", "canary-drop_last_line", "canary-shuffled"):
        controls[tag] = gate(evaluate(tag, "h1"), base, spec)
        expected = "SHIP" if tag == "control-oracle" else "BLOCK"
        if controls[tag]["verdict"] != expected:
            raise SystemExit(f"Control failed: {tag} expected {expected}")
    summary["controls"] = controls
    run("feedback_leakage.py")
    (out / "reproduction.json").write_text(json.dumps(summary, indent=2) + "\n")
    print("REPRODUCTION PASS: complete frozen predictions; all six controls behaved as specified.")
    print("Candidate gate outcomes:", {s: summary[s]["verdict"] for s in ("h1", "h2")})


if __name__ == "__main__":
    main()
