---
id: 22
title: Triage the remaining product raw-stage column mismatches
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12
claimed_at: 2026-08-12
resolution: decided
evidence: executed
closed_by: null
spawned_by: 18
---

## Premise

Rests on [Triage every flagged R/Python difference for both arms, and
resolve the 189-vs-155-tracker discrepancy](18-triage-comparison-flagged-differences.md),
closed: `product_entry_date`'s raw-stage report was found to be ~99%
representation-artifact noise (R stores unparsed Excel serials, Python
stores parsed dates), split into [ticket
20](20-fix-raw-entry-date-representation.md). The other raw-stage product
columns from that session's run are untouched: `product_balance` (2,397),
`product_received_from` (94), `product_released_to` (70), `product_remarks`
(65), `product_units_received` (269), `product_units_returned` (1), and
`product` (685).

Not blocked on ticket 20: these are different columns, and there's no
evidence yet they share entry_date's serial-vs-parsed problem (most are
numeric or plain string columns, not dates) — check each independently
before assuming the same representation issue applies.

**Updated after ticket 20 closed:** normalization dropped raw-stage
`product_entry_date` mismatches from 65,743 to 91, but didn't triage the
residual — 46 already land in ticket 18's existing seeded classifiers
(`ce_typo`, `off_by_one_day`, `sentinel_null`, `r_value_missing`), leaving
50 `unclassified` and undecided, per the destination's "every difference
documented and explicitly decided" bar. Folded into this ticket's scope
rather than spawning a separate one, now that it's down to a small tail
alongside the other raw columns. One concrete finding already surfaced
while triaging (not chased further): Python's raw extraction for
`2020_Sarawak General Hospital A4D Tracker_DC_product_raw.parquet`, sheet
`May20`, has a stray extra row with `product_entry_date = "\n"` (a literal
newline) that R's output doesn't have — a real extraction bug, not a
representation or ordering artifact. Several other files in the residual
(same tracker across other months, `2020_Sultanah Bahiyah Hospital...`,
`2024_CDA A4D Tracker..._Dec24`, `2019_Vietnam National Children's
Hospital..._Oct19`) show a similar single-row insertion/shift pattern
within one sheet — worth checking whether they share the same cause before
assuming each is independent.

**Updated same day, per ticket 18's addendum:** R and Python were both
re-run against the current 248-tracker production set (up from 177) and
`output_r/` now holds that fresh R output (old baseline preserved at
`output_r_155_frozen_backup_2025-11-14`). Refreshed raw-stage counts (same
run, `output/comparison/2026-08-11T232419Z/`): `product_balance` 712 (was
2,397), `product_received_from` 133 (was 94), `product_released_to` 70
(unchanged), `product_remarks` 83 (was 65), `product_units_received` 109
(was 269), `product_units_returned` 1 (unchanged), `product` 721 (was 685).
Use the current `output_r`/`output_python`, not the backup.

## Question

For each remaining raw-stage product column — including `product_entry_date`'s
50 residual `unclassified` rows now that ticket 20 has cleared the
representation-artifact bulk of it — pull the flagged mismatch rows and
determine whether the divergence is a real R/Python content difference
(worth a named classifier and, if it points at a Python bug, a fix) or
another comparison-tool artifact like ticket 20's (worth a normalization
fix instead). Fall back to the real source Excel trackers as the arbiter
per the map's standing preference. If any raw-stage finding turns out to
also explain part of the corresponding cleaned-stage divergence from
[ticket 21](21-triage-remaining-product-columns.md), note the connection
there rather than re-deriving it.

## Resolution

**Decision:** three distinct causes triaged and resolved for six of the eight
remaining raw-stage columns; the residual (105 rows across
`product_units_received`, `product_units_released`, `product_received_from`)
didn't converge to a single cause and is split off into [ticket
24](24-triage-remaining-raw-column-residual.md).

**Because**, in order of investigation:

1. **Real Python bug, fixed**: `remove_header_rows` (`src/a4d/extract/product.py`)
   dropped rows where every column was `None`, but a formula-emptied Excel
   cell can surface via openpyxl as `""` rather than `None` -- so a row with
   one stray `""` cell (everything else genuinely `None`) survived
   extraction when R's `is.na()`-based check (`read_product_data.R` step
   1.6/1.7) drops it. Confirmed directly: Python's raw parquet for
   `2019_Vietnam National Children's Hospital..._Oct19` had 815 rows against
   R's 814, with the extra row isolated to one blank row inserted before a
   totals-like row. Fixed by treating a stripped-empty string as blank too,
   the same way the rest of the row's `None`s already are. This is the same
   mechanism as the Sarawak `"\n"`-dated row ticket 20 flagged but didn't
   chase -- re-verified after the fix: that row is gone too (191/191 rows,
   was 191/192). Regression test added
   (`test_remove_header_rows_drops_row_of_empty_strings`). This was the root
   cause of the "single-row insertion/shift pattern" this ticket's premise
   flagged across several files -- fixing it collapsed a whole cascade of
   downstream cell mismatches (`product_entry_date`, `product_released_to`,
   `product_units_received`, `product_received_from`, `product_units_released`,
   `product` all shifted together for an affected file's rows after the
   blank row).
2. **Comparison-tool artifact, normalized**: `product_balance`'s 712
   mismatches were R's and Python's own float-to-string conversions
   rounding a binary float's trailing digits differently (e.g.
   `"9.300000000000001"` vs `"9.3"`, numerically identical to 1e-9).
   `normalize_numeric_column()` (`src/a4d/migration/compare.py`) parses both
   sides back to `float` before comparing, so the existing float-tolerance
   in `_values_differ` applies instead of a raw string diff. Verified: 0
   `product_balance` mismatches remain against the real drive data.
3. **Comparison-tool artifact, normalized**: the large majority of
   `product`, `product_remarks`, `product_released_to`, and
   `product_units_returned`'s mismatches were whitespace/line-ending
   representation, not content -- two distinct readxl defaults: (a)
   `trim_ws = TRUE` strips leading/trailing whitespace R-side, which
   openpyxl-based Python extraction preserves as-is, including reducing a
   whitespace-only cell to `""` that R's trim reduces further to `NA`; (b)
   readxl represents an embedded line break as `\r\n`, openpyxl normalizes
   it to `\n` alone -- confirmed byte-for-byte on a `product` mismatch that
   looked identical in `repr()` but wasn't (`\r\n` vs `\n`) until this was
   found. `normalize_whitespace_column()` handles both. Verified: `product`,
   `product_remarks`, `product_released_to`, and `product_units_returned`
   all dropped to 0 mismatches against the real drive data.

Combined effect, verified end-to-end against the real `output_r`/
`output_python` on the USB drive (248-tracker production set, same run
ticket 18's addendum re-ran R and Python against): raw-stage product
mismatches (all 9 columns) dropped from 2,007 to 105 -- a 95% reduction.
`product_entry_date`'s own residual (91, carried over from ticket 20) is now
fully classified into existing seeded causes (`ce_typo` 25,
`off_by_one_day` 2, `sentinel_null` 6 = 33 total, 0 `unclassified`) --
`r_value_missing`'s single case and 50 `unclassified` rows both resolved by
the blank-row fix above, since they were downstream of the same row-shift.

**Rejected**: extending `normalize_whitespace_column`/
`normalize_numeric_column` speculatively to the residual columns
(`product_units_received`, `product_units_released`,
`product_received_from`) without first understanding their pattern --
a first look showed at least two more distinct causes there (an
openpyxl date/time auto-coercion leak, and an unexplained value-shift
in `product_units_released` that isn't the same row-shift bug already
fixed), not one. Per the map's "split rather than sprawl" rule, chasing
those inline would have pushed this ticket well past its one-session
scope; ticket 24 carries them instead.

**Evidence**: executed throughout -- the blank-row fix was verified via a
regression test and a live re-run of `a4d run product` against the full
248-tracker USB-drive dataset (not just unit tests), and both
normalizations were verified against `just compare-outputs` run against the
real `output_r`/`output_python` before-and-after. Full suite (571 passed, 1
skipped), ruff, `ty check src/` all pass.

**Tense**: all claims above describe current, executed behavior -- not a
proposed design.

**Incidental fix**: a prior run of this session accidentally wrote a
Python-output run to `a4dphase2_upload/output_python/` (a relative
`A4D_OUTPUT_DIR` combined with `data_root`) instead of the drive's
top-level `output_python/` that `output_r/` and prior sessions' runs live
next to; caught mid-session and removed, no lasting effect on the drive.
