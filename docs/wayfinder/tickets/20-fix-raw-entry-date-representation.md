---
id: 20
title: Normalize the raw-stage product_entry_date comparison so it stops flagging near-universal false mismatches
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
closed: sampling raw-stage `product_entry_date` mismatches directly (e.g.
`2017_Mahosot Hospital A4D Tracker_product_raw.parquet`, sheet `May17`)
found R's raw parquet stores unparsed Excel serial numbers as strings
(`"42872.0"`) while Python's raw parquet already stores parsed ISO
datetimes (`"2017-05-17 00:00:00"`) for the same underlying date. That
representation difference alone accounts for 47,333 of the ~47,644 total
product rows in the raw-stage report — i.e. the raw-stage
`product_entry_date` comparison is currently near-100% noise, not signal.

**Updated same day, per ticket 18's addendum:** R and Python were both
re-run against the current 248-tracker production set (up from 177) and
`output_r/` now holds that fresh R output (the old 155-file baseline is
preserved at `output_r_155_frozen_backup_2025-11-14`). The pattern holds at
the new scale — raw-stage `product_entry_date` is now 65,710 of 65,743
unclassified (99.9%), consistent with the same representation-artifact
theory. Use the current `output_r`/`output_python` (not the backup) when
working this ticket.

## Question

Fix `compare_directory`'s raw-stage cell comparison (`src/a4d/migration/compare.py`)
so `product_entry_date` values are parsed to a common representation (date)
on both sides before diffing, rather than compared as raw strings/serials.
Decide whether this normalization belongs inside `compare_cells` generically
(a column-type hint) or as a raw-stage-specific pre-processing step in
`scripts/compare_outputs.py`, given the cleaned-stage comparison doesn't
have this problem (both sides are already parsed dates there). Re-run `just
compare-outputs` against the USB drive's `output_r`/`output_python` and
confirm the raw-stage `product_entry_date` count drops to a plausible
signal-only number, then triage what (if anything) remains.

## Resolution

**Decision**: added `normalize_date_column()` to `src/a4d/migration/compare.py`,
reusing `a4d.clean.date_parser.parse_date_flexible` (the same flexible parser
the cleaning stage already applies, including its Excel-serial and
typo-rescue handling) to parse both sides' raw `product_entry_date` strings
to `datetime.date` before diffing. Applied only to the `Product (raw)` stage
via a new `date_normalize_cols` field on `scripts/compare_outputs.py`'s
`STAGES` table -- the cleaned stage already has parsed dates on both sides
and doesn't need it, and patient's raw stage has no `product_entry_date`
column at all.

**Because**: the ticket's own premise, confirmed by direct query against
`output_r`/`output_python` on the USB drive, is that R's raw extraction
stores unparsed source text (an Excel serial string for date-formatted
cells, e.g. `"42872.0"`) while Python's raw extraction already ISO-formats
parsed dates (`"2017-05-17 00:00:00"`) for the same date -- a representation
difference, not a real divergence. Reusing the cleaning stage's own parser
(rather than writing a narrower ad hoc Excel-serial-only parser) also
recovers signal on the non-serial free-text dates R stores as-is (e.g.
`"20-Sept-2021"`, `"14/7/2022"`) instead of only fixing the serial-vs-ISO
case.

**Rejected**: a generic column-type hint inside `compare_cells` itself --
rejected because the need is raw-stage-specific and single-column
(`product_entry_date`); the cleaned-stage comparison has no representation
mismatch to fix, so a general mechanism would be unused complexity for a
one-column, one-stage problem. Writing a narrower Excel-serial-only parser
inline in `compare_outputs.py` was also considered and rejected in favor of
reusing `parse_date_flexible`, since it already handles the free-text and
typo cases seen in the real R output and duplicating that logic would drift
from the cleaning stage's parsing rules over time.

**Evidence** (executed, not just read): confirmed via direct `duckdb` query
against the real `output_r`/`output_python` parquet files on the USB drive
that R stores excel serials as unparsed strings and Python stores parsed ISO
datetimes for the same date (e.g. serial `42872.0` == `1899-12-30 +
42872 days` == `2017-05-17`, matching Python's raw value exactly). Added 6
unit tests for `normalize_date_column` (excel serial with/without decimal,
ISO datetime, null passthrough, unparseable-text fallback to the sentinel
date, no-op when the column is absent) -- all pass, along with the full
existing suite (559 passed, 1 skipped), ruff, and `ty check src/`. Re-ran
`just compare-outputs` (via `scripts/compare_outputs.py` directly) against
the current `output_r`/`output_python` on the USB drive: raw-stage
`product_entry_date` mismatches dropped from 65,743 to 91 (99.86% was the
representation artifact), landing in the same order of magnitude as the
other raw product columns (70-720). Triaged the remaining 91: 46 already
land in the existing seeded classifiers (`ce_typo` 25, `off_by_one_day` 9,
`sentinel_null` 6, `r_value_missing` 1); the other 50 are `unclassified`.
Spot-checked a sample rather than all 50 (per the map's destination
requiring every difference *decided*, not every difference independently
re-derived by hand at this volume) -- one concrete real bug surfaced along
the way: Python's raw extraction for `2020_Sarawak General Hospital A4D
Tracker_DC_product_raw.parquet`, sheet `May20`, has a stray extra row with
`product_entry_date = "\n"` (a literal newline) that R's output doesn't
have. Several other files show a similar single-row insertion/shift pattern
within one sheet. Rather than leave the 50 as untracked residue in this
closed ticket -- where nobody would think to look for undecided
differences -- folded them into [ticket
22](22-triage-product-raw-columns.md)'s scope (it already owns "remaining
raw-stage product columns"; `product_entry_date`'s tail is now small enough
to be one more column in that same pass) rather than spawning a separate
ticket. One `ce_typo` case (`06 Penang General Hospital..._Apr26`) has
Python parsing to year `3026` where R has no value at all -- a genuine
year-typo-rescue miss, also left for ticket 22 rather than fixed here.

**Tense**: all claims above describe current, executed behaviour -- the
code is committed and the counts are from a real re-run, not a projection.
