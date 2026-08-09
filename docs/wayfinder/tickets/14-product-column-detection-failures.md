---
id: 14
title: Fix product pipeline's "unable to find column product" failures on 4 real trackers
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-09e
claimed_at: 2026-08-09
resolution: decided
evidence: executed
closed_by: null
spawned_by: 10
---

## Premise

Rests on [Profile the combined pipeline's performance against the R baseline
before promoting to dev](10-performance-profiling.md), closed: while running
`process-product` against the full 177-tracker set on the USB drive
(`a4dphase2_upload`) to profile performance, 4 trackers failed outright with
`unable to find column "product"; valid columns: ["index"]` —
`2020_Jayavarman VII Hospital A4D Tracker.xlsx`, `2018_Kantha Bopha Hospital
A4D Tracker.xlsx`, `2019_Kantha Bopha Hospital A4D Tracker.xlsx`,
`2020_Kantha Bopha Hospital A4D Tracker.xlsx`. This is unrelated to ticket
10's performance fix (reproduces identically before and after it) and was not
previously documented anywhere on this map. Not diagnosed further in ticket
10's session, which stayed scoped to performance — the error originates
around `find_product_section` / `extract/product.py`, not investigated
deeper.

Also rests on [Is the product pipeline (and patient's own claimed
completeness) actually complete and sound, audited against R's product logic
and patient's structure?](07-pipeline-completeness-audit.md), closed: that
audit judged R-logic coverage "essentially complete" on product without
surfacing this — these 4 files are a fresh finding from actually running
against the full real dataset, not something the completeness audit's
code-reading caught.

## Question

Why do these 4 trackers fail product extraction with "valid columns:
[\"index\"]" (this looks like `find_product_section` failing to locate the
product/stock section at all, falling back to an empty/index-only frame) —
is it a genuine structural difference in these files' layout (older/different
tracker format for these years), a synonym-mapping gap, or a real regression?
Decide: fix the extraction to handle whatever these files' actual layout is,
or confirm they're legitimately out of scope (e.g. pre-product-tracking
years) and should fail loudly rather than silently, with that decision
recorded either way. Bears on the destination's "every Python/R difference
documented and explicitly decided" bar and on ticket 6's promotion readiness.

## Resolution

**Decision:** confirmed legitimate — 2018-2020 KBH and 2020 JVM trackers
predate product/stock tracking entirely; not a synonym gap, not a
regression. Fixed a real bug in the cleaning stage that was turning that
legitimate absence into a hard tracker failure: `clean_product_data` now
returns an empty, schema-conformant (0 rows, 20 columns) DataFrame when
extraction hands it a fully columnless raw frame, instead of running the
full step sequence and crashing on a missing `"product"` column.

**Because:** direct inspection of the 4 files' sheets (`openpyxl`, on the
real trackers from the USB drive's `a4dphase2_upload`) found the literal
string "product" nowhere in any cell of any month sheet in the 2018/2019/2020
KBH trackers or the 2020 JVM tracker, and no `INV`/inventory sheet — that
sheet, and product/stock columns generally, first appear in KBH's 2021
tracker (`INV` sheet with `Product`, `Balance`, `Total Units Received`
headers). `find_product_section` (`src/a4d/extract/product.py`) correctly
returns a fully empty `pl.DataFrame()` (0 rows, 0 cols) for these — logged as
a WARNING per sheet plus one "Empty product data" warning per tracker, not a
crash. The crash traced to `clean_product_data`
(`src/a4d/clean/product.py`): step 2.5 (`_add_row_index`) adds an `"index"`
column to the columnless frame, and the later schema-conformance step
(`apply_schema`, `src/a4d/clean/schema_product.py`) calls
`df.with_columns(pl.lit(None, dtype=...))` on that 0-row/1-col-then-more
frame — with zero *original* columns to anchor the frame's height, polars'
literal broadcast invents a 1-row output instead of preserving 0 rows, and
whichever step first indexes `"product"` (`_fill_product_names_and_sort`
class of helpers, unlike `_split_multi_product_cells` which already guards
with `if "product" not in df.columns`) throws
`ColumnNotFoundError: unable to find column "product"; valid columns:
["index"]` — reproduced exactly, matching the ticket's original report
verbatim. Confirmed end-to-end via `process_tracker_product` on all 4 real
files before and after: all 4 now return `success=True` with a
`(0, 20)`-shaped cleaned parquet, matching each file's genuine absence of
product data; `read_cleaned_product_data`'s existing diagonal-concat table
stage already tolerates a 0-row schema-conformant frame (no changes needed
there). Full suite (490 tests, one new regression test added), ruff, and
`ty check src/` all pass.

**Rejected:** "fail loudly" (raise/mark the tracker as failed for having no
product data) was the ticket's other named option — rejected because these
are legitimate, expected years for these two clinics, not a data-quality
problem; treating them as failures would misrepresent real "the pipeline
broke" failures once this map starts tracking tracker success/failure counts
as a rollout-readiness signal (ticket 11's territory). No extraction-side fix
was needed or made — `find_product_section` and `read_all_product_sheets`
already do the right thing; only the cleaning stage's implicit assumption
that a raw frame always has a `"product"` column was wrong.

**Evidence:** executed — reproduced the original crash and the fix against
the real files on the USB drive (not synthetic fixtures), ran the full test
suite, ruff, and `ty check` after the change.

**Tense:** all claims above describe current, verified behaviour (post-fix),
not a proposed design.

