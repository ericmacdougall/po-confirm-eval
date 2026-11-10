# Purchase-order confirmation experiment preregistration

Frozen before any H1/H2 system predictions, 2026-11-10 UTC. The prior label audit
read gold construction facts and independently extracted labels; it did not
evaluate the candidate systems on H1/H2. Its artifacts and disagreements are kept.

## Primary question and fixed candidate

Compare **s2-7b-v3** (Qwen2.5-7B Q4_K_M, prompt v2, quoted-buyer text removed,
grounding validators, one retry then abstention) against **s0-v1** (regex rules).
The validator was corrected using development errors: supplier refusals need no
unstated prices or quantities. This choice is fixed now in SELECTION.json.
The 3B retrieved-few-shot candidate failed development safety/slice rules and
will not be substituted after seeing test results. The zero-shot7B and earlier
validator experiments remain as development comparisons and dead ends.

H1 has exactly450 available emails and is the primary held-out evaluation. H2
has exactly449 available emails and is a separate confirmation with the same
unchanged systems; no H1-driven edits or selection occur between them. They use
disjoint PO records, but some vendors/descriptions occur in both. The selected
test distribution is not a representative production workload or an unseen-
supplier generalization test.

The primary estimand is paired document-accuracy difference, candidate minus
rules, on the fixed evaluation distribution. Report 10,000 paired PO-item
bootstrap draws (seed1), 95% percentile interval; additionally resample entire
supplier clusters (source plus vendor) in2,000 paired draws, reporting cluster
count and interval. Improvement is supported only if both lower bounds exceed
zero. An inconclusive or worse result is reported without replacing the test.
No candidate is required to improve for the experiment to be useful.

## Metrics, denominators and release rules

Report document correctness,3-class confusion matrix, field correctness, and
descriptive macro-F1. Wilson95% intervals accompany proportions. Unsafe-confirm
rate is false automatic confirmations divided by **all gold non-confirm cases**.
Automation recall is correct automatic confirmations divided by **gold confirm
cases**. Also report confirm precision, parse failures and abstention. A system
which abstains on every case cannot pass the automation rule.

The fixed research-package gate requires all rules in GATE.json:

- At least400 expected cases, exact expected-ID coverage with no missing rows.
- Unsafe-confirm Wilson upper bound at most0.06.
- Parse-failure proportion at most0.05.
- Both paired accuracy-difference lower bounds at least-0.01 versus rules.
- Automation recall no more than0.03 below rules.
- Each behavior slice with at least20 items may lose at most0.10 accuracy.

The slice checks are conservative engineering tripwires, not simultaneous
population confidence statements. Source, style and line-count slices are
descriptive; small cells do not establish reliable subgroup performance.
The6% safety bound is an illustrative research gate, not a business-approved
risk tolerance or permission to perform autonomous ERP writes.

Five deliberately broken controls must BLOCK: always-confirm, always-human,
2% price drift, missing last line, and shuffled gold claims. A constructed gold-
claims oracle must SHIP. The oracle is an artificial correctness control, not a
learned model. Failure of any control invalidates the gate demonstration.

## Data, label audit and feedback

There are2,160 real public PO cases: pool300, dev600, H1450, H2450, feedback360.
Supplier emails are synthetic, generated from controlled facts. Eight generation
failures were dropped before system selection; usable counts are299,595,450,
449,359 respectively. One PO identity appears in one split only. Data licenses
are recorded from publisher metadata in DATA.md. This setup measures extraction
and policy implementation on constructed emails over real records. It does not
establish performance on actual supplier/ERP pairs.

Prior independent Opus extraction audited all450 H1 and449 H2 labels,150 dev and
60 pool cases. Two original label disagreements are retained: inspection found
paraphrased line descriptions with matching amounts, not incorrect construction
labels. The current frozen line-matcher reinterprets the stored independent
claims consistently. Report original and recomputed agreement separately; do
not claim100% human-adjudicated production-label accuracy.

The359-case feedback split demonstrates simulated support errors becoming new
regression fixtures. Those errors may inform future development; they do not
alter this experiment's H1/H2 results. A separate explicitly invalid H1 answer-
lookup demonstrates test contamination; its H2 fallback stays unchanged. This
is an extreme pedagogical example, not a valid model or an independent result.

A partially annotated48-item real-email slice exists. Its full text stays
unpublished. It is exploratory and does not count toward the450/449 tests.
No actual ERP-matched real supplier-email corpus was obtained. No frontier
extraction-reference score is invented after the subscription limit stopped it.

## Reproducibility and freeze

PREREG.manifest.json binds this document, code/tests, case/email bytes, model
metadata, candidate selection, gate and dependency pins. Every held-out run
verifies those hashes, and refuses a changed inventory or artifact. Opening is
appended to runs/OPEN_LOG.jsonl; four shards are execution partitions of one
fixed experiment, not four new evaluations. Runs resume only their own IDs.
Expected IDs are determined from the frozen email/case inventory, not the
successful output rows. Missing predictions are errors and force gate BLOCK.

Inference uses llama.cpp build12242 commit3b4d6ab3f on one RTX3090 with24GiB.
Weight hashes, versions, licenses and decoding parameters are in MODELS.json.
GPU work is shared with other experiments. Call latencies describe this run
and include contention; they do not establish production capacity or cost.
No paid model API or managed-cloud inference is used. The CPU-side clients and
statistical evaluation run on a48-vCPU AMD EPYC7502 remote host.

Any implementation change after opening must be disclosed; no silent refreeze
may be used to promote exploratory tuning to held-out confirmation.
