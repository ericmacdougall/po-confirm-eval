"""Current extraction accounting for future experiments, separate from frozen src.

The extraction/policy behavior is unchanged. Only observability is corrected.
Historical held-out splits and tags cannot be written through this entry point.
"""
import argparse
import copy
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import run_system as original
import extractors as X


def inspect_attempt(raw, text):
    decoded = X.extract_json(raw)
    claims = X.normalise(decoded)
    status = ("invalid-json" if not isinstance(decoded, dict) else
              "invalid-schema" if claims is None else "ok")
    why = X.validate(claims, text)
    return claims, dict(raw=raw, parse_status=status,
                        parse_error=why if status != "ok" else None,
                        validation_error=why if status == "ok" else None)


def finish(claims, evidence, validate=True):
    final = evidence[-1]
    parse_failed = final["parse_status"] != "ok"
    validation_failed = bool(validate and final["validation_error"])
    abstained = bool(validate and (parse_failed or validation_failed))
    status = dict(schema=1, parse_status=final["parse_status"], parse_failed=parse_failed,
                  validation_failed=validation_failed,
                  validation_status="not-applied" if not validate else "failed" if validation_failed else
                                    "not-run-parse-failed" if parse_failed else "ok")
    return dict(claims=copy.deepcopy(X.ABSTAIN) if abstained else claims,
                extraction_status=status, attempt_evidence=evidence,
                final_raw=final["raw"], abstained=abstained)


def run_one(system, llm, prompt_v, email, demos_for):
    text = X.text_of(email["subject"], email["body"])
    if system == "s0":
        row = dict(claims=X.rules_extract(email["subject"], email["body"]), raw="", attempts=0,
                   latency_s=0, completion_tokens=0)
        row.update(extraction_status=dict(schema=1, parse_status="not-applicable", parse_failed=False,
                                          validation_failed=False, validation_status="not-applied"),
                   final_raw="", attempt_evidence=[], abstained=False)
        return row
    if prompt_v == "v2":
        text = X.supplier_reply(text)
    demos = demos_for(text) if system == "s3" else ""
    prompt = X.PROMPTS[prompt_v].replace("{email}", text).replace("{demos}", demos)
    messages = [{"role": "user", "content": prompt}]
    first = llm.chat(messages)
    claims, attempt = inspect_attempt(first["text"], text)
    evidence = [attempt]
    lat, tok = first["latency_s"], first["tokens"]
    why = attempt["parse_error"] or attempt["validation_error"]
    if system != "s1" and why:
        messages += [{"role": "assistant", "content": first["text"]},
                     {"role": "user", "content": why + " Return only the corrected JSON."}]
        retry = llm.chat(messages)
        claims, attempt = inspect_attempt(retry["text"], text)
        evidence.append(attempt)
        lat += retry["latency_s"]
        tok += retry["tokens"]
    row = finish(claims, evidence, validate=system != "s1")
    row.update(raw=first["text"], attempts=len(evidence), latency_s=round(lat, 2), completion_tokens=tok)
    return row


def check_future_args(argv):
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--split", required=True)
    parser.add_argument("--tag", required=True)
    args, _ = parser.parse_known_args(argv)
    if args.split not in ("dev", "pool") or not re.fullmatch(r"future-[a-z0-9][a-z0-9_-]*", args.tag, flags=re.ASCII):
        raise SystemExit("REFUSED: corrected runner requires a future-* tag and a new development experiment; historical splits are read-only")
    root = Path(original.ROOT)
    if list((root / "runs").glob(args.tag + "_*.shard*.jsonl")):
        raise SystemExit("REFUSED: tag already exists in historical runs")
    return args


def main():
    check_future_args(sys.argv[1:])  # before constructing a model client or touching run output
    original.RUNS = str(Path(original.ROOT) / "accounting/future-runs")
    original.run_one = run_one
    original.main()


if __name__ == "__main__":
    main()
