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
— that file does not exist anywhere in the repo's tracked tree. Two PDF reports
also ship on that branch (`docs/migration/Product pipeline parity presentation.pdf`,
`docs/migration/dashboarding_evaluation_report_verbose_.pdf`), unread as of this
writing. The user has stated a standing preference: no notebooks for analysis —
write scripts instead — and docs that stay in sync rather than going stale.

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
User has flagged this as lower priority than the merge/CI work, so the
resolution can scope it as a follow-up ticket rather than something to build
in this session.
