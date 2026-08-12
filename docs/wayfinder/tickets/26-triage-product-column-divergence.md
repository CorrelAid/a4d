---
id: 26
title: Triage the product pipeline's column-existence and dtype divergence (Column divergence)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12d
claimed_at: 2026-08-12
resolution: decided
evidence: executed
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

## Resolution

**Decision:** column-existence/dtype divergence now has a dedicated
`column_divergence` sheet (one row per file/column, `only in R` / `only in
Python` / `dtype mismatch` with both dtypes) written to every stage's Excel
report by `build_mismatch_rows()` (`src/a4d/migration/compare.py`) — closing
the "CLI-only, no report sheet" gap the premise named. `compare_columns()`
itself is deliberately left unchanged: an existing test
(`test_flags_dtype_mismatch_on_common_column`) already established that even
a value-equal Int64-vs-Float64 pair must be flagged, so the structural check
stays a strict, unfiltered signal — severity/cause judgment belongs in the
report and this ticket's findings, not in the check.

Every divergence named in the premise, plus patient's (previously unchecked),
was root-caused directly against the real 248-tracker USB-drive R/Python
output pair (`output_r`/`output_python`) via `just compare-outputs`, and spot
verified against real source Excel:

- `product_table_month`/`product_table_year`/`product_unit_capacity`
  (product cleaned, R `Float64` vs Python `Int32`, 229/229 files): confirmed
  harmless — 0 non-integer values across all 198,060 R-side values checked.
  R's own `script3_create_table_product_data.R` declares these `integer`,
  but its error-substitution path assigns the *double* `ERROR_VAL_NUMERIC`
  (999999) into the integer branch on any coercion failure, which silently
  widens the whole column to double in R even when no error actually fires
  on this data — a pure representation artifact, not a value difference.
- `orig_product_released_to` (product cleaned, only-in-Python, 229/229):
  confirmed expected — 0/229 R files ever have it; it's a Python-only helper
  column (`clean/product.py`) R was never going to emit, not a gap.
- `product_remarks` (product cleaned, R `Boolean` vs Python `String`,
  103/229 files): confirmed an all-null-column dtype-inference artifact —
  every affected file's R-side column is 100% null; R's parquet writer
  infers `Boolean` for an entirely-empty column instead of the declared
  `character` type.
- `product_returned_by` (51 files) / `product_units_returned` (25 files)
  (product raw, only-in-Python): confirmed a **genuine R extraction gap**,
  not an artifact — spot-checked `2017_Mahosot Hospital A4D Tracker.xlsx`'s
  `INV` sheet directly: its header row has a literal "Units Returned"
  column, and Python's raw extraction holds 11 real non-null values for it
  (range -1 to 2) that R's raw output drops entirely for this file. R is
  wrong here, consistent with the destination's "R can be wrong" stance —
  no Python fix needed, but it's now a documented, real divergence rather
  than an assumed artifact.
- Patient cleaned stage: essentially clean — one single-file dtype mismatch
  (`testing_frequency`, R `Float64` vs Python `Int32`), same harmless
  integer-widening pattern as the product columns above.
- Patient raw stage: **did not converge** — 18,783 column_divergence rows
  across 245 files, dominated by two large, distinct patterns neither
  matching anything else on this map: hundreds of uniquely-numbered
  only-in-R junk columns (`na`, `na1`, `na2`, ... `na10064`, one file
  contributing 185 of them) that look like R's header-deduplication scheme
  for blank/duplicate Excel headers, and a large only-in-Python set of
  literal, unmapped source header text (`"Phone Number"`, `"Date"`, `"Home
  Visit"`, etc.) that Python's raw extraction passes through verbatim where
  R's apparently doesn't. Root-causing this needs its own session — split
  into [ticket 30](30-triage-patient-raw-column-divergence.md) rather than
  forcing convergence, per this map's "split rather than sprawl" rule.

**Rejected:** normalizing the dtype-mismatch numeric/boolean cases away
inside `compare_columns()` itself (e.g. treating value-equal numeric dtypes
or all-null Boolean-vs-String as a non-divergence) — rejected because an
existing test explicitly pins the opposite policy (flag every dtype
difference, unfiltered), and folding a value-equality check into a purely
structural comparison would blur that boundary for no real benefit: these
five are now fully documented and explained instead, which satisfies the
destination's "every difference explicitly decided" bar without touching
established, tested behavior.

**Evidence:** executed — every claim above was checked directly against the
real drive data (`output_r`/`output_python`, 248 trackers) or the real
source Excel (`2017_Mahosot Hospital A4D Tracker.xlsx`), not read from R
source alone. `src/a4d/migration/compare.py`'s R-source citation
(`script3_create_table_product_data.R`'s `ERROR_VAL_NUMERIC` coercion) is
read, used only to explain *why* the artifact happens, not to establish that
it does — the 0/198,060 non-integer check is what establishes that.

**Tense:** all current-behaviour, from the current 248-tracker output pair.

Full suite (584 passed, 1 skipped, incl. 1 new test), ruff, `ty check src/`
all pass.
