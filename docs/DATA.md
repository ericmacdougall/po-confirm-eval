# Data and licences

| Dataset | Use | Licence | Source |
|---|---|---|---|
| Legacy Purchase Orders, City of Baton Rouge and Parish of East Baton Rouge | the ERP side of ~85% of cases: real PO numbers, vendors, line descriptions, quantities, unit costs, order dates | Public Domain (as stated by the publisher on the Socrata view metadata) | https://data.brla.gov/resource/54bn-2sqf |
| Lottery Contracts - Multi-Year Report, Oregon Lottery | the ERP side of ~15% of cases (a distribution-shift slice: different vendors, services-heavy descriptions, PO numbers prefixed `OR` by us) | Public Domain U.S. Government (usa.gov/government-works) | https://data.oregon.gov/resource/rkhh-35im |
| Enron email corpus, CMU release of the FERC-published mailboxes (2015-05-07) | the REAL-email slice (`real`): real emails that mention a purchase order | Public record released by FERC; widely used for research, no formal licence file | https://www.cs.cmu.edu/~enron/ |

## What is real and what is synthetic

* ERP purchase orders: real public records (vendor names are businesses; vendor contact persons were never read into the cases).
* **Supplier emails in the main evaluation are SYNTHETIC.** This experiment did not obtain a suitable public corpus pairing supplier-confirmation emails with ERP orders and gold labels.
  Each email was written by the `claude` CLI (Sonnet, subscription, no API key) from a spec whose facts are the gold claims, then
  checked programmatically (every stated number, PO number and date must appear in the text) and audited by a second model
  (see `docs/LABEL_AUDIT.md`).
* The real-email slice contains real text and a partial model-versus-regex PO-number annotation. It is an exploratory, off-domain stress test, reported separately; it does not establish confirmation accuracy on actual supplier/ERP pairs.
* Enron source text can contain personal details even after headers are dropped. The corpus and extracted subject/body text remain untracked; only aggregate results and retrieval recipes may be published. The CMU distributor asks users to respect the privacy of those involved.

Publisher metadata was rechecked on 2026-11-10: Baton Rouge `licenseId=PUBLIC_DOMAIN`; Oregon `licenseId=USGOV_WORKS`, with its own terms link to usa.gov/government-works. The Oregon label is the publisher's assertion, not a deduction from state ownership. These snapshots describe what the publishers claimed at acquisition.

The 2,160 PO cases are split by distinct source/order identifier: pool300, dev600, H1450, H2450, feedback360. Eight generated emails failed construction checks and were dropped: published email counts pool299, dev595, H1450, H2449, feedback359. The cases are sampled for this experiment; vendor and description overlap across splits limits claims about unseen suppliers. Synthetic sender names/signatures were invented by the generator.
