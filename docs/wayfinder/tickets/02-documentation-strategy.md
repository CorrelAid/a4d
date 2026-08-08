---
id: 2
title: Retire the PDF/notebook analysis docs for an automated, script-based report
labels: [wayfinder:grilling]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Rests on [Does product-pipeline's test suite meet the same cell-by-cell rigor
as patient's?](01-product-pipeline-test-rigor.md), closed as superseded: that
session decided R-vs-Python output comparison is an analysis activity, not a
pytest concern, and that this ticket is where it belongs. It also decided the
comparison's goal is not R-parity — Python may correctly diverge from R (R can
be wrong) — so the automated report must judge divergence against the
**original source Excel trackers** (available under `a4dphase2_upload` on the
test-data drive) as ground truth, not treat R's output as automatically
correct. A report that only flags "Python != R" without being able to say
which one is right against source doesn't meet this bar.

Facts on record: `docs/migration/PYTHON_IMPROVEMENTS.md` on `product-pipeline`
cites `Ali_internship/residual_dig.ipynb` for the date-parsing analysis (section 5)
— that file does not exist anywhere in the repo's tracked tree, and never has
(`git log --all -- "*residual_dig*"` returns nothing). Two PDF reports also
ship on that branch; both have now been read in full (via
`git show origin/product-pipeline:<path>` + `pdftotext`):

- `docs/migration/dashboarding_evaluation_report_verbose_.pdf` is **unrelated
  to this map** — it's a BI-tool comparison (Looker Studio vs. Evidence/
  Metabase/Superset/Redash) for A4D's research dashboarding, a separate
  internship deliverable with nothing to do with pipeline parity. Out of this
  ticket's (and this map's) scope; not this ticket's concern.
- `docs/migration/Product pipeline parity presentation.pdf` **is** the missing
  `residual_dig.ipynb`'s output — the only surviving record of a real R-vs-
  Python divergence analysis across 189 trackers / 61,077 rows / 20 columns:
  per-column mismatch counts (`Product_entry_date`: 559, `Product_balance`:
  480, `Product_category`: 214, `Product_sheet_name`: 201,
  `Product_received_from`: 154, `Product_units_received`: 9), with the
  entry-date mismatches further broken down by cause (typo-rescue: 408,
  CE-typo: 71, sentinel-null handling: 66, off-by-one-day: 7). Since the
  notebook itself is unrecoverable, this PDF is the ground truth this
  ticket's script needs to be checked against, not just background reading.

## Question

Decide the replacement for the current PDF/notebook-cited documentation:
what should the automated report look like (what does it check — all trackers
locally, error gathering, and where it needs to fall back to the original
source Excel trackers to judge a Python/R divergence rather than trusting R's
output — and how does it regenerate), and what happens to the existing PDFs
and the dead notebook reference (delete, replace, or keep as historical
record with a pointer to the new script)? Also decide what happens to
patient's existing `test_r_validation.py` (the current hand-written
exception-dict pattern) given it's now understood to be this ticket's kind of
artifact, not a pytest one — fold into the new report, or keep separate.

**Validation requirement, per the user:** once the comparison script this
ticket designs is built, run it and check whether it reproduces the same
per-column and per-cause mismatch numbers as the parity-presentation PDF
above (189 trackers, 61,077 rows, 20 columns, the counts listed in the
Premise) — that reproduction is the check that the new script is a faithful,
trustworthy replacement before the PDF is retired. Not required to design
that validation step in detail *now* (design happens when this ticket is
worked); recorded here so it isn't lost.

User has flagged this as lower priority than the merge/CI work, so the
resolution can scope it as a follow-up ticket rather than something to build
in this session.
