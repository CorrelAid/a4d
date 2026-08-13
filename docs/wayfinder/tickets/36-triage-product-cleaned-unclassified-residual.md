---
id: 36
title: Triage the product cleaned-stage mismatches no ticket owns (product_balance, sheet_name, entry_date, units_received, file_name)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-13
claimed_at: 2026-08-13
resolution: decided
evidence: executed
closed_by: null
spawned_by: 25
---

## Premise

Rests on three closed decisions:

- [Triage the remaining product cleaned-stage column
  mismatches](21-triage-remaining-product-columns.md) — established the
  product arm's dominant cleaned-stage cause (R's row sort falls back to
  input order whenever `product_entry_date` fails to parse, while Python
  sorts chronologically on correctly parsed dates), added the
  `row_order_divergence` classifier, and explicitly left
  `product_balance`'s residual as "future work" without giving it a ticket.
- [Triage the product_units_released cleaned-stage column
  mismatches](25-triage-product-units-released-cleaned.md) — closed the last
  column that *did* have a ticket, and in doing so found that the remaining
  `unclassified` rows on the product cleaned-stage report belong to no
  ticket at all. It also established the mechanism behind `product_balance`'s
  poor classification rate: `product_balance` is *derived*, not carried —
  both pipelines recompute it as a running total
  (`balance[i] = balance[i-1] - released[i] + received[i]`, Python's step
  2.15 `_compute_running_balance`, R's iterative equivalent) — so under a
  legitimate re-sort the balance cannot travel with its row, and
  `row_order_divergence`'s "does R's value appear elsewhere in Python's
  group" membership test structurally under-detects it.
- [Triage every flagged R/Python difference for both arms](18-triage-comparison-flagged-differences.md)
  — established that per-column counts are judged by pattern, not by
  reproducing the parity-presentation PDF's numbers.

Current counts, measured against the real 248-tracker drive comparison
(`output/comparison/2026-08-12T220324Z/`, `Product (cleaned)` stage):

| Column | `unclassified` |
|---|---|
| `product_balance` | 1,976 (of 2,740; 764 already `row_order_divergence`) |
| `product_sheet_name` | 275 |
| `product_entry_date` | 169 (of 11,727) |
| `file_name` | 60 |
| `product_units_received` | 8 (of 305) |

Two of these have a documented lead but no verdict: `product_sheet_name` is
believed to be R's un-trimmed sheet names (noted in passing by [ticket
17](17-fix-product-row-alignment-and-triage.md), whose count of 201
reproduced the PDF exactly — the count is now 275 against the refreshed
baseline), and `product_units_received`'s 8 are believed to be the
Excel-date-serial-leak pattern [ticket
24](24-triage-remaining-raw-column-residual.md) confirmed for the raw stage,
reaching the cleaned stage too. Neither was ever decided under the standing
bar. `file_name` and `product_entry_date`'s residual have no lead at all.

This ticket exists because the destination requires **every** Python/R
difference documented and explicitly decided; these rows were reported as
`unclassified` on every run while each triage ticket worked only the columns
its own title named.

## Question

Explain and decide each of the five columns above. `product_balance` is the
bulk of the work and the one with a known mechanism but no adequate
detection: decide whether its residual is fully accounted for by the
already-established sort-order divergence (in which case the open question is
how to *evidence* that for a derived running total — e.g. comparing
end-of-group balances, or reconstructing R's order and re-deriving — rather
than by value membership), or whether some part of it is a genuine divergence
the sort-order story hides.

If the work does not converge in one session, split rather than sprawl.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining
a difference and naming a cause is only half the job. Each must carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Where
Python turns out to be wrong or to be losing information the source file
carried, fix the pipeline rather than labelling the symptom. A cause
genuinely undecidable on the available evidence is recorded as an open
question, not closed with a label.

## Addendum (session-2026-08-12h): the balance mechanism, measured

Follow-up investigation after ticket 25 closed, prompted by the user asking
whether `_compute_running_balance` is itself wrong. Findings are verified,
the decision is **not** made — that is still this ticket's job.

**There is no defect in `_compute_running_balance`.** It mirrors R exactly.
R's `compute_balance` (`r-archive/R/helper_product_data.R:437-481`) loops
over rows and, for every `"change"`/`"end"` row, *overwrites*
`product_balance` with `previous_balance - released + received`; Python's
step 2.15 does the same via a per-group cumsum seeded from the group's first
(`"start"`) row. **Both pipelines discard the source spreadsheet's recorded
balance on non-start rows by design** — this is the original R design, not a
migration artifact.

**What actually differs is the order the ledger accumulates in**, which is
downstream of step 2.7's sort, not of the balance step. Measured on
`2024_Mahosot Hospital`, sheet `Jul24`, `Accu-Chek Performa Test Strips
(50s/ bottle)` (43 rows), against the real source Excel:

- The source's own Balance column is internally consistent **in data-entry
  order** (322, 314, 310, 306, 302, 300, 293, 290, ... — each equals the
  previous minus that row's Units Released).
- R, accumulating in entry order, reproduces the source's balances **exactly**
  (multiset equal, row for row).
- Python, accumulating in chronological order, emits 322, 314, 306, 302,
  298, 294, ... — a self-consistent ledger whose intermediate values appear
  **nowhere in the source file** (source has 172/182/186/202...; Python has
  176/178/183/187...).
- **Both end at 139.0**, matching the source's closing balance.

Note the source's entry order here is *not* chronological (the clinician
entered 2024-07-23 before 2024-07-19), so the source's own Balance column is
a ledger in data-entry order, not a stock history over time.

**Breadth, across all 11,649 `(clinic, sheet, product)` groups:**

| Measure | Groups | Share |
|---|---|---|
| Balance multiset identical R vs Python (no divergence at all) | 11,117 | 95.4% |
| Closing (end-of-group) balance identical | 11,491 | 98.6% |
| Closing balance differs | 158 | 1.4% |

Of those 158, **153 are float-accumulation noise where Python is the cleaner
side** (R `-1.5999999999999999` vs Python `-1.6`; Python's cumsum applies
`.round(10)`, R's loop rounds nothing). The other **5 are R being corrupted
by an Excel date serial leaking into the arithmetic** — e.g. 2019 Penang
General Hospital, `Accu-Chek Performa Glucometer Set`: R's closing balance is
**43,572** where Python has **6.0** (43,572 is a 2019 date serial); same
shape for four Sultanah Bahiyah groups. This is the stray-date-typed-cell
pattern [ticket 24](24-triage-remaining-raw-column-residual.md) already
root-caused, now shown to corrupt R's *balance totals*, not just individual
cells. **Python's closing stock is correct in every group.**

**The open question this ticket must decide** is therefore not "is Python
buggy" but **what `product_balance` is supposed to mean on a non-closing
row**, given it is written per-row to BigQuery's `product_data` table and has
no consumer inside the Python codebase (verified by grep — only
`clean/product.py` and the schema reference it):

1. *Keep current behaviour* — balance accumulates in chronological order, so
   it is coherent as a stock-over-time series and the closing figure is
   right, but an individual row will not match the tracker cell a human
   opens next to it.
2. *Carry the source's recorded balance*, computing only where absent —
   maximally faithful per row, but propagates the source's own arithmetic
   mistakes and abandons R's design.
3. *Accumulate in entry order, output in chronological order* — each row
   keeps the balance the tracker recorded while rows still display
   chronologically; the balance column then reads non-monotonically down the
   output.

Whichever is chosen, consider logging a data-quality error when the
recomputed balance disagrees with the source's recorded balance: nothing
currently surfaces that, and it is the signal that would have exposed the R
date-serial corruption above from the tracker side.

### Decision on the balance question (user, 2026-08-12h) — implemented

**Option 1 chosen: keep the current recompute-after-chronological-sort
behaviour, and add a clear log warning.** The source's balance column
accumulates in data-entry order, which is not a meaningful stock history when
entries are out of order, so reverting to it would trade a coherent series
for a faithful-looking but less useful one. Python's closing stock is already
correct in every group. What was missing was any signal when the ledger and
the tracker's own total disagree.

**Implemented.** `_compute_running_balance` (`src/a4d/clean/product.py` step
2.15) now takes an optional `ErrorCollector` and, via
`_report_balance_reconciliation`, reports **per (sheet, product) group** when
the computed closing balance contradicts the balance the tracker itself
recorded. New error code `balance_reconciliation` in `src/a4d/errors.py`; it
flows into the errors/logs tables and BigQuery unchanged, since nothing
filters by code.

**Granularity was chosen by measurement, not by taste** — this is the part a
later session should not re-litigate:

| Candidate signal | Fires on real 248-tracker data | Verdict |
|---|---|---|
| Every row where computed != recorded | 15,301 rows (31.4% of recorded rows) | Noise — this is the re-sort working as designed |
| Per-group closing balance, incl. start-only groups | 781 groups (7.0%) | Still mostly false: a group whose only recorded balance is its start has no closing figure to reconcile |
| **Per-group closing balance, groups that recorded a non-start balance** | **113 groups (1.1%), 21 files** | **Chosen** — order-independent, so a disagreement is a real source problem |

Verified end-to-end: all 248 cleaned outputs re-run and confirmed
**byte-identical** to the previous run (no pipeline behaviour changed, only
reporting), and the live run produces exactly the 113 warnings predicted.
Example message:

> Closing balance mismatch for product 'NovoRapid FlexPen 3ml (singles/ 5s)'
> in sheet 'Mar26': tracker recorded 34.0, but the recorded transactions add
> up to 68.0 (difference 34.0). The stock movements and the tracker's own
> total do not agree.

Warnings concentrate rather than scatter — 54 of the 113 are in
`2021_Mahosot Hospital`, 12 in `2021_Mandalay Children's Hospital` — so they
point at specific trackers worth investigating.

**Still open for this ticket:** the five columns' classification (including
`product_balance`'s 1,976 `unclassified` rows) is untouched by the above; the
new warning is an operability improvement, not a triage verdict. Whether the
113 flagged groups are source data-entry errors or something the pipeline
mishandles has **not** been investigated.

## Progress (session-2026-08-13)

Worked small-columns-first at the user's direction. Three of the five columns
are decided and implemented; the whitespace pair awaits a user decision.

Counts are against the real 248-tracker drive pair,
`output/comparison/2026-08-13T212807Z/`, `Product (cleaned)` stage.

### `product_units_received` — 8 -> 0 `unclassified`. Python correct.

Source Excel `2019_Sultanah Bahiyah Hospital A4D Tracker_DC.xlsx`, sheet
`Aug19`: the header row reads `D=Date, E=Units Received`, and on rows 10-12
the clinician typed the entry date into **E** with **D** left empty. R's
readxl coerces the column to numeric and carries the raw serial (`43708`)
into its output — the same serials that corrupt R's closing balance in the
five groups this ticket's addendum measured. Python's `_clean_units_received`
(step 2.11) fails the float cast, emits one `type_conversion` error per row,
and zeroes the cell.

**Verdict: Python is right**, and observably so — the error is logged, not
swallowed. New `stray_date_zeroed` classifier
(`STRAY_DATE_ZEROED_CLASSIFIERS`): the cleaned-stage face of ticket 24's
`openpyxl_date_typed_stray_cell`, which could not see these because it
expects Python's side to still hold a datetime.

### `product_entry_date` — 169 -> 9 `unclassified`. Python correct.

Root cause found in source Excel `2022_Vietnam National Children_s Hospital`,
sheet `Apr22`: the "Entry Date" column holds **mixed types** — some cells are
real `datetime`, others are text (`'20/04/2022'`, `'14/04/2022'`, ...).
readxl guesses the column as date and nulls every *text* cell; Python's
`parse_date_flexible` reads both. In that one sheet-group R loses 25 real
dates, which drops it back to input-order sorting, so positional alignment
pairs R's July date against Python's April date — both non-null, so
`r_value_missing` never fires.

Three sub-causes, all decided:

| Sub-cause | Rows | Verdict |
|---|---|---|
| `row_order_divergence` (113) | 113 | R's readxl-nulled text dates drop it to input order; Python sorts on dates that really are in the file |
| `python_future_date_sentinel` (34) | 34 | Python substitutes R's own `9999-09-09` sentinel for an out-of-tracker-year date (`_validate_entry_dates`); R propagates the typo |
| `summary_residue_nulled` (13) | 13 | Python nulls end-of-block residue (`30` -> 1900-01-30); R keeps the junk date |

The future-date verdict is source-verified: for Preah Kossamak's 2023
tracker, sheet `Aug23`, **both** pipelines independently read `2029-08-29`
out of a sheet whose every other row is August 2023 — so the source really
does carry the typo. Python flags it; R passes it through.

The 9 remaining rows (8 real-vs-real dates, 1 R-date-vs-Python-null in
`2023_Taunggyi`, `Nov'23`) are positional-alignment residue where the
membership heuristic misses. Checked directly for the Taunggyi row: Python's
raw extraction holds `2023-11-30` for that group's last row, i.e. R's row
pairs against a Python row that is null — an alignment artefact, not a
content divergence. Deliberately left `unclassified` rather than given a
label that would decide nothing.

Also wired `PRODUCT_ROW_ORDER_CLASSIFIERS` onto every remaining positionally
aligned product column (`product_units_notes`, `product_units_returned`,
`product_returned_by`, `product_balance_status`, `orig_product_released_to`,
`product_unit_capacity`, `product_category`), and **replaced ticket 25's
hand-written `positional_columns` test list with one derived from
`get_product_data_schema()`** minus a new
`GROUP_INVARIANT_PRODUCT_COLUMNS` exclusion set. The hand-written list is
precisely what let `product_entry_date` sit unwired: the test written to
prevent this class of omission had itself omitted the column.

### `product_balance` — 1,976 -> 11 `unclassified`. Python correct.

The addendum above established the mechanism but not the detection. The
missing piece is that a derived running total needs *order-independent*
evidence, and the group's **closing** balance is exactly that.

New `group_endpoint_matches` diagnostic on `CellMismatch`, computed by
`compare_cells` (only for `add_row_ordinal`'s positional key), plus a
`derived_running_total_row_order` classifier keyed off it. Measured
independently of the comparison tool, straight off the parquet pair, and
then reproduced by the tool exactly:

| | Cells | Groups |
|---|---|---|
| Balance mismatches in groups whose closing balance **agrees** | 2,729 | 2,281 |
| Balance mismatches in groups whose closing balance **differs** | 11 | 2 |

Both differing groups are `2019_Sultanah Bahiyah ... DC`, sheets `Jun19` and
`Aug19` — the same stray-date-serial groups above, where R's ledger is
corrupted by `43644`/`43708` leaking out of "Units Received". **Python's
closing stock is correct in both.**

Those 11 are left `unclassified` **on purpose**: `unclassified` on
`product_balance` now means "the two ledgers disagree on closing stock",
which is a real signal worth surfacing. Absorbing them into the same label
would have been labelling, not deciding.

### `product_sheet_name` (275) + `file_name` (60) — 335 -> 0. Pipeline fixed.

All 335 are R keeping trailing whitespace Python strips: `trim(r_value) ==
py_value` for 275/275 of the sheet-name rows. The source really carries it —
the Excel tab is literally named `'Dec24 '` and the file is literally
`06 Pahol Polpayuhasena Hospital A4D Tracker_Jun_26 - final .xlsx`. R trims
only `product_released_to` (`read_product_data.R:204`); Python's step 2.16
strips every string column.

**The finding is not about R.** Python is inconsistent with itself:

| | `file_name` | `sheet_name` |
|---|---|---|
| `patient_data_cleaned` | `'... - final '` | `'Dec24 '` |
| `product_data_cleaned` | `'... - final'` | `'Dec24'` |
| `tracker_metadata` (`tracker_path.stem`) | `'... - final '` | — |

Measured across all 248 trackers: 1 `file_name` value and 9 `sheet_name`
values (`Apr26 `, `Dec24 `, `Feb21 `, `Jun19 `, `May19 `, `May20 `, `May26 `,
`Nov21 `, `Sept20 `) differ between the arms, so any BigQuery join of
`product_data` to `patient_data_*` or `tracker_metadata` on those keys
silently drops them.

**User decision:** trim everywhere. *"I see no reason why the pipeline should
not consistently trim whitespace at the end of all strings, filenames etc.
there is never a meaning in that"* — the source files should be corrected
too, but that is a human task, not the pipeline's.

**Implemented as a real pipeline change:**

- `strip_string_whitespace()` (`src/a4d/clean/transformers.py`), applied at
  **step 0.5** of `clean_patient_data` — deliberately *before* validation,
  not after, so a value is never rejected for whitespace alone. Product's
  own step 2.16 already did the equivalent and is unchanged.
- `tables/metadata.py` now strips `tracker_path.stem`, so
  `tracker_metadata.file_name` joins the cleaned outputs' own `file_name`.
  Output parquet names still carry the untrimmed stem, and the trimmed name
  remains a prefix of them, so the presence check is unaffected.
- Comparison tool: `product_sheet_name`/`file_name` added to the product
  cleaned whitespace normalization, and a patient equivalent added for both
  patient stages, **derived from `get_string_columns()`** rather than
  hand-listed. `sheet_name` is half the patient row-alignment key, so
  without this R's untrimmed `"Dec24 "` would fail to join Python's
  `"Dec24"` and silently drop those rows from the comparison rather than
  showing them as equal.

**The trim recovered real data that both pipelines were losing.** A test
written before the change (`test_whitespace_does_not_defeat_allowed_value_validation`)
predicted it and failed as expected: `sex = "F "` validated to `"Undefined"`.
Confirmed on the real dataset and against the source Excel —
`2019_Kantha Bopha Hospital`, sheet `Jan19`, patient `KH_KB023`, cell reads
literally `'F '`. R's validator rejects it and sentinels it; Python used to
copy that behaviour and now keeps the value. **72 rows across 6 trackers**,
classified as `r_validator_rejects_untrimmed` — Python recovering data, not
diverging.

Patient re-run (`a4d run patient --force`, all 248 trackers) and comparison
re-run confirm the rest is representation-only:

| Patient cleaned column | Before | After |
|---|---|---|
| `complication_screening_remarks` | 57 | 0 |
| `family_history` | 24 | 0 |
| `observations` | 360 | 327 |
| `blood_pressure_dias_mmhg` | 315 | 303 |
| `testing_frequency` | 154 | 144 |
| `sex` | 4 | 76 (72 of them the recovery above) |

Patient cleaned total: **99,478 -> 99,408**. The two numeric columns improved
because trimming lets their values parse. Patient raw is byte-unchanged
(28,033), as expected — raw deliberately preserves what the source contained.

### Where the numbers stand

Product cleaned-stage `unclassified`: **2,488 -> 20** (11 `product_balance`,
9 `product_entry_date`), every one explained with a verdict, and each
remaining as a deliberate signal rather than a label:

- the 11 mean "the two ledgers disagree on closing stock" — both are the
  2019 Sultanah Bahiyah groups where R is corrupted by a date serial;
- the 9 are positional-alignment residue.

Both are terminal conclusions of the "the source file is corrupt, a human
should look at this tracker" kind, which the user confirmed mid-session is a
valid place for triage to stop.

Full suite 629 passed / 1 skipped, `ruff check`, `ruff format --check`,
`ty check src/` all pass.
