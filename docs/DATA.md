# Data and licences

| Dataset | Use | Licence | Source |
|---|---|---|---|
| Legacy Purchase Orders, City of Baton Rouge and Parish of East Baton Rouge | the ERP side of ~85% of cases: real PO numbers, vendors, line descriptions, quantities, unit costs, order dates | Public Domain (as stated by the publisher on the Socrata view metadata) | https://data.brla.gov/resource/54bn-2sqf |
| Lottery Contracts - Multi-Year Report, Oregon Lottery | the ERP side of ~15% of cases (a distribution-shift slice: different vendors, services-heavy descriptions, PO numbers prefixed `OR` by us) | Public Domain U.S. Government (usa.gov/government-works) | https://data.oregon.gov/resource/rkhh-35im |
| Enron email corpus, CMU release of the FERC-published mailboxes (2015-05-07) | the REAL-email slice (`real`): real emails that mention a purchase order | Public record released by FERC; widely used for research, no formal licence file | https://www.cs.cmu.edu/~enron/ |

## What is real and what is synthetic

* ERP purchase orders: real public records (vendor names are businesses; vendor contact persons were never read into the cases).
* **Supplier emails in the main evaluation are SYNTHETIC.** No labelled public corpus of supplier PO-confirmation emails exists.
  Each email was written by the `claude` CLI (Sonnet, subscription, no API key) from a spec whose facts are the gold claims, then
  checked programmatically (every stated number, PO number and date must appear in the text) and audited by a second model
  (see `docs/LABEL_AUDIT.md`).
* The real-email slice is real text, labelled by two independent annotators (see `docs/REAL_SLICE.md`) and is reported separately
  to show how far synthetic results transfer.
* Enron mailbox owner names and email headers are not kept; only subject and body text, keyed by a hash.
