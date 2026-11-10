# Label audit and its limits

The email generator used Claude Sonnet. A prior blind re-extraction used Claude
Opus on the emails alone, without the construction claims or labels in the
prompt. The extracted claims were checked against each public PO by the same
deterministic decision policy used for system scoring. This is cross-model
agreement, not independently collected real-world truth.

There are1,109 stored audits:450 H1,449 H2,150 dev and60 pool. All parsed. Original
agreement was449/450,449/449,150/150 and59/60 respectively. Two disagreement
records remain in data/audit_disagreements.jsonl. Reading them showed matching
quantities/prices and short descriptions which paraphrased long PO text. The
line-matching policy was improved before the final system evaluation; replaying
the stored independent claims through that policy gives agreement on all1,109.
Both the original observations and recomputation are in results/label-audit.json.

This audit does not remove generator bias, policy-specification errors, vendor
overlap, batch correlations or common model blind spots. The gold labels are
construction labels; test performance remains conditional on those assumptions.
