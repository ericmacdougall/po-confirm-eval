# Post-opening correction: parse failures hidden by abstention

Final PR review of08f8afc92e2b39b987511e5d24302666bf34df7f found a release-control
measurement bug on2026-11-10. After a failed retry, the original validated
extractor returned a nonempty abstention dictionary. The original scorer used
the presence of claims as its parse-success signal. A syntactically failed
extraction therefore escaped the preregistered5% parse-failure ceiling while
correctly routing the decision to a human.

The original experiment is preserved, including its defective gate accounting.
All31 files in `docs/PREREG.manifest.json`, all original `runs/` and `results/`
files, and the original replay remain unchanged. The complete08f8afc snapshot
is `original/experiment-08f8afc.zip`, SHA-256
`6024b164c989db8ddb6e41015f5496b7cc1c9883dbb6c7f58d0b56d697ff460f`.
`accounting.original.verify` checks that archive and the corresponding current
files before reconciliation. Nothing was retroactively refrozen.

The separate `accounting/` implementation records every raw attempt, final raw
response, JSON/normalization status, parse complaint and validation complaint.
It distinguishes final JSON/schema failure from a parsed extraction rejected
by grounding/semantic validation. Here "schema" means the original normalizer's
object/list acceptance rule; this correction does not add stricter schema rules
or repair either retained unsafe confirmation. A successful retry clears the
final parse-failure counter while retaining the first failure in its trace.
Nonempty fallback claims never clear a failed final parse status. Missing or
inconsistent status refuses corrected scoring.

All six original H1/H2/feedback retry responses were recovered from the owned
host's existing cache. Their exact request keys are recomputed from the frozen
runtime identity, prompt/messages and completion limit. The retained copies and
SHA receipts are in `accounting/evidence/`. No new inference, paid API, change
to extraction claims, decision policy, thresholds or labels occurred.

| Split | n | Original reported parse failures | Corrected final parse failures | Final grounding/validation failures |
|---|---:|---:|---:|---:|
| H1 |450|0|1 (0.2222%)|0|
| H2 |449|0|1 (0.2227%)|0|
| Feedback |359|0|1 (0.2786%)|0|

The final failures are h1-01163, h2-01612 and fb-01994. Each split also has one
other retry whose final extraction parses successfully. The corrected H1/H2
gates remain SHIP because the measured final failure rates are below5%. All
accuracy, field scores, automation, unsafe-confirm counts, confidence intervals
and original extraction decisions remain unchanged. Both unsafe confirmations
described in README and `results/error-analysis.json` remain defects.

A constructed regression control replaces30 already-correct gold-needs-human
extractions with two invalid responses and a human-escalation fallback. Accuracy,
automation, safety and every final decision remain unchanged. Including the
one actual H1 failure, corrected accounting observes31/450 failures (6.8889%).
The historical scorer still reports0% and its gate returns SHIP; the corrected
gate returns BLOCK specifically on parse coverage. The control is deliberately
constructed and is not an additional model experiment.

Run `python3 rerun.py` for the isolated original replay plus corrected report,
or `python3 -m accounting.reconcile` for correction-only auditing. The recommended
command never overwrites historical results. Tests in `accounting/tests/`
include the observed failing-first gate bypass, successful retry, invalid
schema, grounding failure, missing/inconsistent status, protected historical
splits and path-escape rejection. Future development runs use
`python3 -m accounting.runner`; historical H1/H2/feedback/real splits are refused.

These are corrected measurements of already-observed outputs. They are not
retuning, new statistical confirmation, production certification or a repair
of the discovered late-date/item-substitution acceptance gaps.
