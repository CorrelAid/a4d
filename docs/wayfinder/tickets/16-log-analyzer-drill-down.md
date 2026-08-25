---
id: 16
title: Build a drill-down log analyzer for admins to inspect a specific tracker file's errors/logs
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-25c
claimed_at: 2026-08-25
resolution: decided
evidence: executed
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
current pipeline logs via loguru into the `logs` BigQuery table and the
findings table instead, so any Python equivalent needs a different shape.

**Both of those figures were wrong and are corrected here.** The logs table is
not 1M+ rows: measured on the real 254-tracker set it is ~215,000 operational
rows, and one tracker's entire detail is a few hundred. Both tables answer any
question in under a second in `duckdb`, which is what killed the dashboard
framing during this ticket's own grilling session and settled the deliverable
as an Excel workbook.

**And `table_errors` no longer exists.** [Ticket
66](66-unify-finding-channels.md) closed 2026-08-25: there is now one channel.
Every data-quality finding lives in `table_findings` -- 118,175 on the
254-tracker run, both arms, one schema, `file_name` the bare tracker stem, so
it joins against `table_logs` and `tracker_metadata` on all 254 files. Each
finding carries a `category` (`fix_workbook` / `recovered` / `data_lost`) that
says whether anyone has to act. `table_logs` is now operational only --
timings, progress, exceptions -- with no `error_code` column at all.

**So this ticket's two data sources are no longer "logs plus errors" but
"findings for what is wrong with the workbook, logs for what the pipeline
did".** That is the split the drill-down should present, and it is the reason
ticket 66 had to land first.

## Question

Design and build a tool (CLI subcommand, small TUI, or lightweight
dashboard — open which) that lets an admin/developer pick one tracker file
from a run and see everything relevant to it: every log line (from
`table_logs`), every data-quality finding (from `table_findings`: column,
original value, error code, category), and the exception detail for an outright
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
rather than sprawled. `blocked_by` gained **66**
([unify the finding channels](66-unify-finding-channels.md)), which carried
every measurement taken here. **That blocker closed 2026-08-25 and this ticket
is unblocked**: the unified `table_findings` is exactly the shape the workbook
needs, and its `category` column is the ranking key the summary sheet asks
for.

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

## Resolution (2026-08-25, session-2026-08-25c)

**Decision: one workbook, one command, both audiences.** `a4d report findings`
writes a three-sheet `.xlsx` from `table_findings` -- Summary (one row per
tracker, ranked by `fix_workbook` count), Findings (every row, autofiltered,
frozen header), Glossary (all 21 error codes, what each means and what to do).
`--tracker <substring>` is the drill-down: it filters the Summary and Findings
sheets to one workbook and leaves the Glossary whole. `--from-bigquery` reads
the published table instead of the local parquet; local is the default so a
developer debugging a run needs no GCP credentials.

**Because** the user chose option (a) when this ticket's overlap with [the
source-defect report](40-source-defect-findings-report.md) was put to them:
the `fix_workbook` rows *are* that report, the other two categories are the
drill-down's extra, and one artifact means the person correcting workbooks and
the person debugging a run look at the same evidence with the same glossary.

**Rejected.**
- *Two workbooks from one derivation* (a staff-facing `fix_workbook`-only file
  and a full one) -- rejected as the user's call; it costs little to build but
  forces every reader to first work out which file they are holding.
- *Two separate deliverables* -- rejected: the audiences want the same rows,
  filtered differently, not different things.
- *A TUI or dashboard* -- already killed by this ticket's previous session on
  measurement (`duckdb` answers any question on this table in under a second).
- *One sheet per tracker* -- 254 tabs is unnavigable and cannot answer
  cross-tracker questions; the autofilter gives the same view.
- *Folding it into `a4d create tables`* so every run emits it -- rejected: most
  runs do not need the file, and a separate command is where an operator
  already looks.
- *Generating the glossary by parsing the `#` comments beside `ErrorCode`* --
  rejected for a `FINDING_GLOSSARY` dict kept exhaustive in both directions by
  tests, mirroring `FINDING_CATEGORY`. Comments are not data.
- *Hand-rolling the workbook on `openpyxl`* (already a dependency) -- rejected
  for adding `xlsxwriter`, which the user approved: autofilter, frozen panes
  and typed writes are one call each.
- *Filling `tracker_year`* -- deliberately **not** done here; see below.

**Evidence: executed.** Every number is from a full `a4d run` over the real
255-tracker set on the data drive (download included -- the user confirmed new
trackers had landed), plus the full test suite (1,159 passed, 1 skipped), ruff
and `ty`. Nothing here is read or inferred.

### What the session found that the ticket did not ask about

**`a4d run` wrote no product table at all, and reported success.** Found on the
first verification run: `tables/` held every patient table and no
`product_data.parquet`. `create_table_product_data` calls `fix_patient_id` and
`safe_convert_column` at the table-aggregation stage -- over a frame spanning
every tracker, outside any tracker's context -- so `report_finding` raised
`NoFindingContextError`, and `run_product_pipeline`'s `except Exception:
logger.exception(...)` swallowed it. A regression from [ticket
66](66-unify-finding-channels.md), whose own resolution names these two call
sites as the hard ones and whose code comment at the site describes findings
being "returned to the caller" that nothing returned. **The test suite could
not catch it**: `tests/conftest.py`'s autouse `_findings_context` fixture binds
a context around every test, so this path only fails in production. Fixed by
opening `findings_collected(arm="product")` inside
`create_table_product_data` -- inside, not at each of the three call sites
(`run`, `run product`, `create tables`), because a caller that forgets gets no
product table. Measured: `product_data.parquet` **absent -> 75,169 rows**.

**`findings_collected(arm=...)` was silently ignored unless `file_name` was
also passed.** It bound the tracker context only alongside a file name, so a
caller whose findings name their own workbooks -- exactly the product table
stage -- had every finding filed under the default arm `patient`. Now bound
unconditionally; a `None` file name still raises at emit time if the call
carries none.

Together these two returned findings the run was losing: **119,588 ->
122,590**.

### Measured against the source-defect report's catalogue

The coverage check that decides whether [ticket
40](40-source-defect-findings-report.md) closes as delivered. All 21 error
codes fire on the real run (`fix_workbook` 49,034 / `data_lost` 71,566 /
`recovered` 1,990). Its two headline populations check out --
`excel_error_patient_id` is 120 rows over **8** trackers, matching the ticket's
row count against its claim of 9; the malformed 7-character NOGH/YGH IDs are
all present. **But three gaps mean ticket 40 does not close here**, and each is
measured, not suspected:

1. **`sheet_name` is empty on 120,088 of 122,590 findings (98%)**, and
   `patient_id` on 54,027. Ticket 40's stated bar is that someone can "open the
   named workbook, find the named cell"; with twelve month sheets and no sheet
   name, they cannot.
2. **`blank_header_with_data` fires 217 times across 24 trackers**, all of them
   2022, against ticket 40's catalogued 4,572 values across 26. It never fires
   on that ticket's clearest example -- `2021_Kantha Bopha`, sheets
   `Mar21`/`Apr21`, column Q, 194 lost insulin-regimen values. The catalogue's
   figure came from the comparison tool's analysis; the runtime emitter is a
   different and much narrower population, and nobody had held the two numbers
   against each other.
3. **`tracker_year` and `tracker_month` are populated on 0 of 122,590 rows.**
   Both `tracker_context` call sites in `pipeline/tracker.py` omit them. The
   Summary sheet therefore does **not** carry a `tracker_year` column -- a blank
   column in the deliverable is worse than none, and the year is legible off
   `file_name`, which is the first column. Filling the field is ticket 40's.

Also confirmed absent: no error code covers the 23 patients listed twice on one
monthly sheet ([ticket 45](45-patient-row-alignment-duplicate-keys.md)), the
rich-text formatting-run cells, or the unaccented-province loss -- so those
catalogue entries reach no row today.

**Tense.** Every count above is current behaviour of the code as committed this
session, measured after the fixes. The three gaps describe current behaviour
too; nothing here is a consequence of a proposed design.
