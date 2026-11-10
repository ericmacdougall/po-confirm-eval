# Run log: purpose, command, observation and decision

These records distinguish the recovered development work from the final frozen
experiment. Generated emails are synthetic even though the underlying PO facts
are public observations. Commands below run from the repository root.

## R01: construct cases with explicit policy

Command: `python src/build_cases.py` after acquiring the publisher snapshots
listed in DATA.md. Outcome:2,160 distinct PO cases, assigned to pool300, dev600,
H1450, H2450, feedback360. Behavior, style and conditions are controlled
construction choices. The script checks the intended behavior-to-label mapping.
Decision: retain those immutable facts and source licenses, rather than use
invented ERP quantities.

## R02: write and audit email surface forms

Command family: `python src/gen_emails.py --cases data/cases.jsonl --out data/emails.jsonl`
using a subscription CLI, followed by `python src/audit_labels.py` on the named
splits. Outcome:2,152 usable generated emails; eight failed construction checks.
Independent Opus extraction audited1,109 cases. Two recorded disagreements
concerned paraphrased line descriptions, and are retained with the independent
claims. Later frozen line-matching recomputation agrees with all construction
labels; that is a policy interpretation, not a new human annotation.
Decision: disclose synthetic emails, audit limits and both agreement counts.

## R03: recover the7B baseline and compute safety denominators

Command: `python src/score.py --split dev --tags s0-v1,s1-7b-v1 --baseline s0-v1`
on595 completed development rows. Outcome: rules91.26%, zero-shot7B98.15%; both
made eight unsafe confirmations among370 cases which must not confirm.
Inspecting actual wrong rows found a consistent trap: quoted buyer order lines
were read as supplier acceptance. Decision: strip quoted buyer content before
validated extraction and explicitly teach the model the distinction.

## R04: compare validation and retrieved examples

Commands: `sh ops/run_shards.sh s2 dev v2 s2-7b-v2 18081 qwen2.5-7b-instruct-q4_k_m`
and `sh ops/run_shards.sh s3 dev v2 s3-3b-v2 18082 qwen2.5-3b-instruct-q4_k_m`.
The four shards are disjoint execution partitions. Outcome: validated7B had
zero unsafe confirmations but its refusal slice regressed;3B few-shot failed
safety and behavior-slice gates. Decision: reject the smaller candidate under
this policy and inspect why validation was throwing away correct refusals.

## R05: fail first on the validator defect

Command: `python3 -m unittest discover -s tests -v` after adding the supplier-
refusal fixture. Outcome before repair: the fixture fails because an unstated
quantity is required on a rejected item. After repair, missing values remain
missing for refusals; numbers which are actually asserted still need grounding.
Command: `sh ops/run_shards.sh s2 dev v2 s2-7b-v3 18081 qwen2.5-7b-instruct-q4_k_m`.
Outcome: cached dev replay completes595/595,99.50% document correctness, zero
unsafe confirmations, automation recall98.67%, all fixed development gates pass.
Decision: select this candidate once, before held-out inference.

## R06: evaluate the evaluator and runtime identity

Meaningful failing controls reproduced nonfinite-number auto-confirmation,
unmatched extra-line acceptance, wrong-order refusal, an empty-sample interval
claiming zero risk, and empty bootstrap crashes. Focused repairs reject them.
An independent inspection then found that a model tag alone did not bind cache
identity to actual weights/backend. The repaired client checks actual serving
properties before cache reads or inference. A live3B server presented under
the frozen7B tag was refused. Source/data inventory mismatch on a legacy remote
scratch mirror also refused before any held-out output; a clean source archive
passed without weakening the checks.

Command: `python3 -m unittest discover -s tests -v`. Outcome:18 focused controls
pass. The actual owned GPU host's server binaries and three GGUF files were
hashed; observed runtime metadata is retained. Decision: archive the first
pre-opening manifest, strengthen runtime binding, then freeze again with the
same candidate/data/metrics/thresholds, still before held-out predictions.

## R07: freeze and open the actual experiment

Commands: `python3 src/preregister.py --freeze --refreeze-before-open` after the
pre-opening inspection repair; `python3 src/preregister.py` confirms31 bound
artifacts. Exact source, both input files, selection, gate, model and runtime
observations are bound. The previous pre-opening manifest is retained under
`docs/freeze-history/`. All declared artifacts are included in tracked source.

The final pipeline runs unchanged rules and selected candidate on H1450, then
the same unchanged pair on H2449, followed by candidate inference on feedback359.
Each held-out call includes `--open-heldout codex-frozen-final`, and its opening
is logged. No tuning occurs between H1 and H2. Inference runs on the owned RTX3090;
clients and evaluation run on the remote48-vCPU host, not a laptop.

## R08: replay, gate controls and feedback

Command: `python3 src/reproduce.py`. It rechecks hashes, rejects incomplete
predictions, recalculates both sets, executes five deliberate broken-system
controls plus a constructed gold oracle, and regenerates feedback/leakage
artifacts. The controls are fault injection, not naturally occurring customer
incidents. A candidate BLOCK remains a reported result and is never repaired
against this held-out pair.

`results/feedback.json` records actual extraction/policy errors on the separate
feedback cases and the resulting simulated regression-fixture growth.
`results/leakage.json` contrasts a deliberately memorized H1 lookup with its
unchanged fallback on H2. The contaminated score is not an improvement claim.

## R09: observe the held-out result and preserve the remaining failures

H1:450/450 predictions for each system; rules93.33%, validated7B99.33%;
paired improvement6.00pp,95% interval3.78–8.44. Supplier-cluster sensitivity
3.71–8.29pp over272 supplier groups. H2:449/449, rules92.87%, validated7B99.11%;
paired improvement6.24pp, interval4.01–8.69; supplier sensitivity3.66–9.27pp
over271 groups. Both gates passed their fixed research thresholds.
Reproduction exit0; five bad controls BLOCK and the constructed oracle SHIP.
Feedback359 produced two decision errors and therefore two new regression
fixtures, raising the development suite size to597.

Post-test error inspection was exploratory and did not change the system.
Each test contained one unsafe confirmation. H1 omitted an explicitly stated
late date; returned-field grounding alone did not check completeness. H2 missed
an item substitution with unchanged money/quantity; the policy lacked a separate
item-identity check. Feedback exposed the latter class again. Proposed future
coverage and item-alignment repairs remain untested and need a new experiment.
The published passing research gate is not approval for autonomous purchases.

## Not run and limits

No model-weight fine-tuning, actual customer-mail benchmark, human labeling
operation, ERP write, production rollout, serving-capacity test or paid API
inference was performed. A frontier extraction reference stopped at a
subscription limit and was not replaced with invented output. Raw real-email
text and model weights are not included. Shared-GPU call timings describe
contention in this experiment and do not establish isolated capacity.
