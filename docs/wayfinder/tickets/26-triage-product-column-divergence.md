---
id: 26
title: Triage the product pipeline's column-existence and dtype divergence (Column divergence)
labels: [wayfinder:task]
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

Rests on [Build and run the R/Python output comparison script, then triage
every flagged difference](15-build-and-run-comparison-script.md), closed:
`compare_columns` (`src/a4d/migration/compare.py`) — column existence
(only-in-R / only-in-Python) plus dtype mismatches on common columns — was
built as one of the comparison tool's four structural layers and has been
computed and shown in the CLI summary table (`Column divergence`) on every
`just compare-outputs` run since. It was never triaged: every subsequent
triage ticket ([17](17-fix-product-row-alignment-and-triage.md),
[18](18-triage-comparison-flagged-differences.md),
[20](20-fix-raw-entry-date-representation.md),
[21](21-triage-remaining-product-columns.md),
[22](22-triage-product-raw-columns.md)) worked exclusively off the
`cell_mismatches` sheet (per-value diffs), not this structural layer — a gap
against the destination's "every Python/R difference documented and
explicitly decided" bar, not a deliberate scope decision.

Surfaced while closing ticket 21 (a user question about the CLI's `Column
divergence` count), on the current 248-tracker `output_r`/`output_python`
pair. Cleaned-stage `product_data_cleaned` shows 4 divergences in every one
of 229 files, plus a 5th in 103 of them:

- `orig_product_released_to` present only in Python's output (229/229) — a
  Python-only helper column (`clean/product.py`, holds the pre-cleaning
  `product_released_to` value) that R never emits.
- `product_table_month`: R `Float64` vs Python `Int32` (229/229)
- `product_table_year`: R `Float64` vs Python `Int32` (229/229)
- `product_unit_capacity`: R `Float64` vs Python `Int32` (229/229)
- `product_remarks`: R `Boolean` vs Python `String` (103/229) — only in
  files where the column is entirely null for that tracker; a likely
  all-null-column dtype-inference artifact of R's parquet writer, not
  wired into any normalizer.

Raw-stage `product_data_raw` shows a smaller, different set (51 files
missing `product_returned_by`, 25 missing `product_units_returned`, plus a
handful of one-off `product_released_to`/`product_remarks`/
`product_units_released` — all only-in-Python, no dtype mismatches), not
yet looked at either. Patient's own column divergence (if any) hasn't been
checked at all.

## Question

For both product stages (and patient, if it turns out to have any): is each
column-existence or dtype divergence a genuine content gap, or a
representation/schema artifact (following `normalize_date_column`/
`normalize_numeric_column`/`normalize_whitespace_column`'s precedent) that
should be normalized or simply documented as expected? In particular:
confirm whether `product_table_month`/`product_table_year`/
`product_unit_capacity`'s Float64-vs-Int32 split is purely R's lack of a
native integer type (harmless) or hides an actual value difference (e.g.
truncation/rounding); confirm `orig_product_released_to`'s absence from R is
expected (a Python-only helper column, not something R should ever have
had) rather than a naming/step gap; and root-cause the raw-stage
only-in-Python columns (`product_returned_by`, `product_units_returned`,
etc.) — are these real R-side columns R simply never populates for these
files, or a genuine extraction gap. Add findings to `compare_columns`'
report output (currently CLI-only, not written to any report sheet) if
that's the fix, or to the classifier/normalization layer if it's a
representation issue.
