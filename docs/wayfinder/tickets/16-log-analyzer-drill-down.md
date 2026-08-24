---
id: 16
title: Build a drill-down log analyzer for admins to inspect a specific tracker file's errors/logs
labels: [wayfinder:grilling]
status: open
blocked_by: [66]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 11
---

## Premise

Rests on [Decide what CLI/TUI UX and error-log observability improvements
admins/developers need before rollout](11-cli-ux-observability.md), closed:
the user distinguished two separate concerns under that ticket's "error-log
observability" question — a high-level per-run summary (now built into
`run-pipeline`'s combined summary: both-arms-ok / patient-only-failed /
product-only-failed / lost-entirely counts, plus a merged per-file error
count) versus a drill-down view into one specific file's full detail. The
summary is done; this ticket is explicitly the drill-down half, deferred
because it's a separate, larger deliverable rather than an extension of the
existing summary tables.

Also rests on [Retire R from the workspace once the pipeline is fully
verified Python-only](12-retire-r-workspace.md)'s premise material: prior
art is `tools/LogViewerA4D`, an R Shiny dashboard (deleted once ticket 12
closes) that read local tab-separated `.log` files and offered a per-tracker
log table + Sankey diagram, a cross-tracker regex-filterable overview, and a
reference-data validation tab (missing/duplicate `clinic_id`). Read before
building, not to be ported as-is — its design assumes local log files; the
current pipeline logs via loguru into the `logs` BigQuery table (1M+ rows)
and `table_errors.parquet` instead, so any Python equivalent needs a
different shape.

## Question

Design and build a tool (CLI subcommand, small TUI, or lightweight
dashboard — open which) that lets an admin/developer pick one tracker file
from a run and see everything relevant to it: every log line (from
`table_logs`), every data-quality error row (from `table_errors`: column,
original value, error code), and the exception detail for an outright
processing failure — without hand-querying BigQuery or grepping JSON.

Concrete use case to design against: the combined run summary (ticket 11)
tells an admin *that* `2024_Clinic_B.xlsx` had 4 errors or failed outright;
this tool answers *what exactly went wrong*, row by row.

Questions to resolve:
- Where does it live — a new `a4d.cli` subcommand reading local
  parquet/BigQuery, a separate small script/TUI, or something else?
- Does it need BigQuery access (for a deployed run) or only local
  output/tables (for a local run), or both?
- Which of `LogViewerA4D`'s three views (per-tracker detail, cross-tracker
  overview, reference-data validation) are worth carrying forward given the
  new data shape, and which don't translate?
- Scope: is this genuinely needed before `migration` promotes to `dev`
  (this map's destination), or is "good enough to operate day to day"
  already met by the combined run summary alone, making this a nice-to-have
  outside the promotion path?

## Re-scoped (session-2026-08-24i)

This ticket was worked, not resolved: the grilling established that the tool it
asks for cannot be built well on the data as it stands, so the session split
rather than sprawled. `blocked_by` gains **66**
([unify the finding channels](66-unify-finding-channels.md)), which carries
every measurement taken here.

**What this ticket is now:** build the report -- and it is an **Excel workbook**,
not a TUI or a dashboard. The user's goal is to replace a Looker error dashboard
that is a lot of work to maintain, and to answer two questions: how to address
data-quality issues, and what to tell A4D staff about their trackers.

Shape, agreed with the user:

- **A summary sheet** ranked by the *workbook is wrong* category, so the first
  thing visible is "these trackers need a human", not 103,000 rows.
- **One findings sheet** with autofilter, over `table_findings`. Explicitly
  **not one sheet per tracker**: 254 tabs is unnavigable, and filtering
  `file_name` gives the same view while also allowing cross-tracker questions a
  tab cannot answer.
- **A glossary sheet** -- each `error_code`, what it means, what to do about it.

**Two premise corrections from this session.** The ticket claimed the `logs`
table is "1M+ rows" and that a Python equivalent therefore "needs a different
shape"; it is **216,871** rows over 254 trackers, and one tracker's entire
detail is a few hundred rows. This was never a big-data problem, and the premise
that pushed it toward a dashboard does not survive measurement. Its fourth
question -- whether this is needed *before* `migration` promotes to `dev` -- is
**dead**: the promotion happened on 2026-08-24, so the question cannot be asked
in that form. What survives is whether it is needed to operate day to day, and
the user's answer is yes.
