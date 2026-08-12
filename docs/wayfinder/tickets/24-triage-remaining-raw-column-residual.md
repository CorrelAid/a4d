---
id: 24
title: Triage the residual product_units_received/product_units_released/product_received_from raw-stage mismatches
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
