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

Nothing closed yet.

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
locally, error gathering — and how does it regenerate), and what happens to the
existing PDFs and the dead notebook reference (delete, replace, or keep as
historical record with a pointer to the new script)? User has flagged this as
lower priority than the merge/CI work, so the resolution can scope it as a
follow-up ticket rather than something to build in this session.
