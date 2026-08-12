---
id: 24
title: Triage the residual product_units_received/product_units_released/product_received_from raw-stage mismatches
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12e
claimed_at: 2026-08-12
resolution: decided
evidence: executed
closed_by: null
spawned_by: 22
---

## Premise

Rests on [Triage the remaining product raw-stage column
mismatches](22-triage-product-raw-columns.md), closed: a real blank-row
extraction bug and two comparison-tool representation artifacts (float
string formatting, whitespace/line-ending) together cut raw-stage product
mismatches from 2,007 to 105 (95%), fully resolving `product`,
`product_balance`, `product_entry_date`, `product_remarks`,
`product_released_to`, and `product_units_returned`. The 105-row residual
is what's left: `product_units_received` (75), `product_units_released`
(24), `product_received_from` (6), on the real `output_r`/`output_python`
comparison against the current 248-tracker production set
(`output/comparison/2026-08-12T074911Z/compare_report_product_data_raw.xlsx`
in the repo's `output/` directory as of this writing, or re-run `just
compare-outputs` against the drive for a fresh count).

A first look during ticket 22 found at least two more distinct,
not-yet-root-caused patterns in this residual, neither the same as any
cause ticket 22 already fixed:

1. **Possible openpyxl date/time auto-coercion leak** (majority of
   `product_units_received`'s 75, a handful of `product_received_from`'s
   6): R's raw value is a plain number or `"0"`; Python's is a
   parsed-looking date/time string (`"00:00:00"`, `"1900-03-15 00:00:00"`,
   `"2019-04-11 00:00:00"`). Distinct from ticket 20/22's date-column
   representation fix -- these aren't `product_entry_date`, they're columns
   that shouldn't hold dates at all. Working theory (not verified): the
   source Excel cell carries date/time number-formatting that openpyxl
   auto-converts to a Python `datetime`/`time` object regardless of the
   cell's logical column, while R's raw extraction doesn't. If confirmed,
   this could be a systemic raw-extraction issue (any column, any arm), not
   specific to these two.
2. **Unexplained value pattern** in `product_units_released` (24 rows,
   concentrated in Mandalay/Vietnam files): e.g. R has `"2 MM_MD023"`,
   Python has `"2 MM_MD023-1"` -- values that look like `product_released_to`
   content (a patient ID), not a unit count, appearing in the
   `product_units_released` column. Not explained by ticket 22's blank-row
   fix (row counts already match for at least one sample file checked) and
   not the wide-format cell-splitting logic in
   `src/a4d/extract/wide_format.py::handle_wide_format_cells` (that function
   only fires for 2017-2019 Mandalay files and splits `Released To`, it
   doesn't append `-1`/`-2` suffixes to `Units Released`). Needs a fresh
   look at the source Excel for one of these rows to see whether this is a
   genuine content divergence, another duplicate-ordinal-key pairing
   ambiguity (like the `product` column mismatches ticket 22 found and
   fixed via the `\r\n` normalization -- verify row order/uniqueness within
   the `add_row_ordinal` group before assuming content itself differs), or
   something else.

## Question

For `product_units_received`, `product_units_released`, and
`product_received_from`'s residual mismatches: confirm or refute the
date/time-coercion theory above (check the source Excel cell's number
format directly, not just the parquet output), and root-cause the
`product_units_released` value-shift pattern. Decide, per column, whether
each finding is a real Python bug (fix it), a comparison-tool
representation artifact (normalize it, following `normalize_date_column`/
`normalize_numeric_column`/`normalize_whitespace_column`'s precedent in
`src/a4d/migration/compare.py`), or something else. If the date/time-coercion
theory is confirmed and looks systemic (not just these two columns), flag
that explicitly rather than only patching the two columns it happens to
surface in here -- it may need its own ticket covering the raw extraction
approach more broadly (patient arm included).

## Resolution

**Decision:** All 105 residual mismatches across the three columns are now
fully explained by comparison-tool cause classifiers -- none required a
pipeline code change. `product_units_received` (75) and
`product_received_from` (5) are entirely the openpyxl date/time-coercion
pattern; `product_units_released` splits into 19 float-precision rows
(fixed by the same normalization) and 5 wide-format-parsing-ambiguity rows
(a new classifier).

**Because:**
- **Date/time coercion (80 rows, confirmed against real source Excel, not
  just the data pattern):** R's readxl infers a column's type from its
  majority values, so a lone Excel date/time-formatted cell in an
  otherwise-numeric column (a genuine, if rare, source-data anomaly -- e.g.
  someone typed a date into a "Units Received" cell) still gets coerced to
  that column's numeric type, the raw serial. Python's openpyxl reads each
  cell individually and honors its own format, returning a `datetime`/
  `time` object instead. Verified directly: Penang General Hospital 2019
  Apr19!E36 (a "Units Received" cell) is genuinely formatted `d/m/yy` and
  holds a date value; CDA/NPH/Yangon 2023 files hold `time(0, 0)`-formatted
  cells reading `"0"` on R's side. Neither side is wrong -- both faithfully
  extract what the cell holds per their own library's semantics -- so this
  is a comparison-tool classifier
  (`STRAY_DATE_CLASSIFIERS`/`_is_openpyxl_date_typed_stray_cell`,
  `src/a4d/migration/compare.py`), not a pipeline fix. It converts the
  R-side serial via openpyxl's own `from_excel` (not hand-rolled epoch
  math) specifically to replicate the Excel/Lotus 1900-leap-year bug
  (serials 59 and 60 both resolve to 1900-02-28) -- caught by a real
  flagged row (r_value 59) during verification, not anticipated up front.
  Per the ticket's own instruction, this is flagged as systemic rather than
  scoped to just these two columns: the same
  numeric-column-with-a-stray-date-cell shape could appear anywhere,
  including the patient arm. Not spawning a new ticket for it -- [ticket
  27](27-triage-patient-raw-residual.md) already covers "patient raw-stage
  residual" and is still open, so the lead (and the reusable classifier) is
  noted there instead as an addendum.
- **Float precision (20 rows, `product_units_released` 19 +
  `product_received_from` 1):** the same R/Python float-to-string rounding
  difference `normalize_numeric_column` already fixed for `product_balance`
  (ticket 22) -- just not yet wired for these three quantity columns.
  Extended `PRODUCT_RAW_NUMERIC_NORMALIZE_COLS` in
  `scripts/compare_outputs.py` to include all three.
- **Wide-format fragment truncation (5 rows, `product_units_released`
  only, 2017-2019 Mandalay files):** confirmed against real source Excel
  (`2017_Mandalay Children's Hospital A4D Tracker.xlsx` Jul17!K15,
  `2019_Mandalay Children's Hospital A4D Tracker.xlsx` Feb19!K48-49) that
  the source "Released To" cells hold messy free-text notes with embedded
  parentheses and extra hyphens
  (e.g. `"MM_MD019-2(Error-1),MM_MD043-1,..."`) that
  `handle_wide_format_cells`'s comma/hyphen split doesn't fully anticipate.
  In every flagged case R's value is a strict text prefix of Python's
  (`"2(Error"` vs `"2(Error-1)"`) -- R's equivalent step drops content
  after a second hyphen, Python's keeps the full remainder. Python is
  verified more faithful to the source text, not R -- this is a genuine R
  parsing gap on inherently messy human-entered notes, not a Python bug to
  fix, and not something to chase toward R's more-truncated answer. New
  classifier `WIDE_FORMAT_FRAGMENT_CLASSIFIERS`/
  `_is_wide_format_fragment_truncated`.

**Rejected:**
- Fixing `handle_wide_format_cells` to parse the 5 ambiguous Mandalay cells
  "correctly" -- rejected because there is no single correct answer for
  genuinely ambiguous human-entered free text (a missing comma between two
  name-qty pairs), and R's own answer for the same cells is demonstrably
  more lossy, not more correct. Classifying and documenting the divergence
  is more honest than writing brittle guessing logic for 5 rows.
- Spawning a new ticket for the date/time-coercion pattern's patient-arm
  implications -- rejected in favor of noting it as a lead on the
  already-open, already-scoped [ticket 27](27-triage-patient-raw-residual.md)
  rather than fragmenting the map further.

**Evidence:** executed. Every root cause was verified directly against the
real 248-tracker drive data and the real source Excel files (not just the
data pattern) -- see the specific cell coordinates cited above. The fix was
verified end-to-end by re-running `just compare-outputs` against the real
drive data after implementation: all 105 residual rows across the three
columns now carry a named cause (0 `unclassified`), and the `Product
(cleaned)`/`Patient (raw)`/`Patient (cleaned)` reports are confirmed
byte-identical to the prior run ("no change from the previous run"),
i.e. this ticket's changes didn't touch anything outside its raw-stage
product-column scope. Full test suite (592 passed, 1 skipped), ruff,
`ruff format --check`, and `ty check src/` all pass.

**Tense:** all claims above describe current, executed behavior (the fix
is implemented and pushed), not a proposed design.

Full change: `src/a4d/migration/compare.py` (new
`_excel_serial_to_datetime`, `STRAY_DATE_CLASSIFIERS`,
`WIDE_FORMAT_FRAGMENT_CLASSIFIERS` + their classifier functions),
`scripts/compare_outputs.py` (new `PRODUCT_RAW_NUMERIC_NORMALIZE_COLS`,
updated `CLASSIFIERS_BY_COLUMN`, reordered whitespace-before-numeric
normalization to avoid a dtype conflict), `tests/test_migration/test_compare.py`
(10 new classifier tests, including a regression test for the 1900
leap-year edge case).
