---
id: 16
title: Build a drill-down log analyzer for admins to inspect a specific tracker file's errors/logs
labels: [wayfinder:grilling]
status: open
blocked_by: []
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
