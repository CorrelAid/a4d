---
id: 78
title: A blank row ends the patient block, so anything written below it is never read
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-29
claimed_at: 2026-08-29
resolution: decided
evidence: executed
closed_by: null
spawned_by: 41
---

## Premise

Rests on three closed decisions.

- [Do the 2026 template's five new Patient List fields enter the
  pipeline?](41-decide-2026-new-patient-list-columns.md), closed 2026-08-29,
  which found this while running the extraction against a real workbook to
  verify a reporting claim. That ticket's own answer does not depend on this
  one; this is residue, correctly framed here rather than folded in.
- [A sheet whose name the matcher does not recognise is skipped in total
  silence](72-sheets-the-pipeline-never-opens.md), closed, which established the
  standing shape for this class of defect: **report, do not widen** -- when the
  pipeline cannot read something, the first duty is to say so, and quietly
  reading more is the riskier move.
- [Everything the pipeline reads and then discards to fit the fixed output
  shape](76-columns-dropped-by-the-fixed-output-shape.md), closed, which
  established that silent loss is the defect even when the lost data turns out
  not to matter.

Overturning any of the three would leave this ticket needing a rewrite, not
void: the data is measurably lost either way.

## Question

**14 real patients at one clinic are read out of the workbook by nobody.**
`2026_Preah Kossamak Hospital A4D Tracker_Jun_26.xlsx` lists 114 patient IDs on
its `Patient List` sheet; extraction returns 100. The 14 (rows 114-128, IDs
`KH_KB114_PK`, `KH_KB048_PK`, `KH_KB145_PK`, ... -- transfers in from Kantha
Bopha) reach no table, and **no finding is raised**: the loss is completely
silent, which is the pattern tickets 72 and 76 both closed against.

**Mechanism, verified by execution.** `read_patient_rows`
(`src/a4d/extract/patient.py`) reads from the first data row and stops at the
first row where every cell is `None`:

```
if all(cell is None for cell in row):
    break
```

In this workbook the clinic left rows 110-112 empty, wrote a banner
`PENDING TRANSFER KBH` in row 113, and started a second numbered block at row
114 with its counter restarting at 1. The blank run ends the read; everything
below it is invisible. Confirmed by running `extract_patient_data` on the real
file and diffing the IDs it returns against the IDs openpyxl sees.

**The blast radius is measured across the whole corpus, and it is tiny and
concentrated.** Every `Patient List`, `Annual` and month sheet in every tracker
was walked, using the pipeline's own `find_data_start_row` so the gap between a
header and its first record is not mistaken for a break in the data. Of **2,573
sheets, 4 lose rows** -- **48 rows in total**, all in 2026:

| Sheet | Rows lost |
|---|---|
| `Patient List`, Preah Kossamak | 15 |
| `May26`, Preah Kossamak | 16 |
| `Jun26`, Preah Kossamak | 15 |
| `Feb26`, Mukdahan | 2 |

Three of the four are the same workbook, so the 14 transferred patients lose
their **monthly records as well as their roster entry** -- they are absent from
the pipeline entirely, not merely undescribed. Mukdahan's 2 rows are a separate
instance of the same shape and should be looked at before deciding.

A first, cruder sweep put this at 2,248 month sheets and 106,957 rows. That was
an artifact: it took the first row with anything in column B as the start of the
data, which on a month sheet is the header, so the "gap" it found was the blank
line between header and first record and the "lost" rows were the entire sheet.
It is recorded here so the number is not resurrected.

The decision this ticket exists to take:

1. **Report and stop there** -- raise a `fix_workbook` finding naming the sheet
   and the row where reading stopped, whenever data follows. This is ticket 72's
   precedent applied unchanged, it fixes the silence without changing what any
   table contains, and it puts the workbook right where it belongs: with the
   clinic. Costs nothing and risks nothing.
2. **Keep reading to the end of the sheet** and let the existing per-row guards
   decide. Recovers the 14 patients automatically -- but those guards
   (`_carries_data_beyond_identifier` and the row-number rule) were tuned by a
   254-tracker sweep specifically to reject junk *below* a data block, and that
   sweep assumed the block was already bounded by the blank row. Choosing this
   means re-running that sweep, not assuming it still holds.
3. **Both** -- read on *and* report the gap, so a recovered second block is
   still visible to whoever has to trust it.

Things the decision turns on:

- Whether a second block below a banner is a legitimate way for a clinic to
  write a roster, or a mistake the clinic should fix. Two workbooks in 255
  argues the latter.
- Whether Mukdahan's 2 rows are the same shape as Preah Kossamak's block or
  something else -- 2 rows could be a stray note rather than patients.
- Whether the banner row itself (`PENDING TRANSFER KBH`, no ID) would survive
  the per-row guards as a phantom patient.


## Resolution

**Decision.** Option 1, unchanged from ticket 72's precedent: **report the gap
and read no further.** A new finding code `data_below_blank_row`
(`fix_workbook`, scope `sheet`) fires from `read_patient_rows` whenever the
blank row that ends the block has, below it, at least one row the reader would
have accepted. The message names the row reading stopped at and how many rows
were left. No data-reading behaviour changed; no published table moved.

**Because.** The ticket's own headline -- "14 real patients are read out of the
workbook by nobody" -- is false, and measuring it is what settled the decision.
All fourteen `KH_KB*_PK` IDs exist as `KH_KB*` in
`2026_Kantha Bopha II Hospital A4D Tracker_Jun_26.xlsx`: on its `Patient List`,
its `Annual`, and every one of its six month sheets. Preah Kossamak has
pre-registered patients it expects to receive, under IDs it will use once the
transfer completes. Reading them in would **duplicate** fourteen patients
across two clinics.

Reading on is worse than merely redundant on the month sheets. `May26`'s block
holds `#REF!` in both identifier columns -- 16 rows keyed to a broken
spreadsheet reference. `Jun26`'s block has real IDs but its only payload is
column E, `Last Clinic Visit`, holding the date of the patient's last visit **at
Kantha Bopha**; reading it would create Preah Kossamak monthly records for
patients Preah Kossamak did not treat.

**Rejected.**
- *Keep reading to the end of the sheet* (ticket option 2): creates the
  duplicates and the `#REF!` rows above. The ticket noted its per-row guards
  were tuned by a sweep that assumed the blank row bounded the block; that
  concern is now moot -- even if the guards held, the rows should not be read.
- *Read on and also report* (option 3): same defects plus a finding.
- *Report any non-blank content below the break*: measured and rejected.
  **237 of 2,860 patient sheets** have some non-blank cell below the break
  (footers, notes, stray totals); **3** have a row that would be read as data.
  The counted rows use the reader's own acceptance test, shared as
  `_would_be_read_as_data` so the two cannot drift.

What this gives up: if a clinic ever *does* split a genuine, non-duplicated
block below a gap, the pipeline reports it rather than recovering it, and
someone has to act on the finding. That is the trade ticket 72 already made.

**Two of the ticket's own facts were wrong and are corrected here.**
- **Mukdahan is not affected.** The ticket lists `Feb26`, Mukdahan as losing 2
  rows. Running the real extraction on that sheet returns all 7 rows it holds;
  the first fully blank row is 61 and nothing follows it. The affected
  population is **one workbook, three sheets, 46 rows** -- Preah Kossamak's
  `Patient List` (15), `May26` (16), `Jun26` (15).
- **The corpus is 2,860 patient sheets, not 2,573.** The re-sweep walks every
  month sheet found by `find_month_sheets` plus `Patient List` and `Annual`,
  using `find_data_start_row` and the real header width for the column bound.
  This is the third count this ticket has carried and the first taken with the
  pipeline's own reading rules; the earlier two (106,957 rows, then 48 rows
  over 4 sheets) are both superseded.

The 15/16/15 counts include the clinic's `PENDING TRANSFER KBH` banner row,
which carries a second inline header (`Remark from contacting`) in column S and
so genuinely would be read. The message says "rows of data", not "patients",
for that reason.

**Evidence: executed.**
- Corpus sweep over all 255 workbooks / 2,860 patient sheets
  (`find_data_start_row` + `read_header_rows` + the reader's acceptance test):
  3 sheets, 46 rows, all 2026 Preah Kossamak. Loose variant (any non-blank
  cell): 237 sheets.
- The 14 transfer IDs searched for in the Kantha Bopha 2026 workbook: found on
  all 8 of its sheets that carry patients.
- Controlled before/after both-arm run on the full 255-tracker corpus:
  **104,834 -> 104,837 findings**, exactly the three new ones; distinct codes
  firing **40 -> 41**; every other published table byte-identical in row count
  (patient static/monthly/annual, product, clinic, logs, metadata).
- Full suite green: 1342 passed, 1 skipped. `ruff check`, `ruff format
  --check`, `ty check src/` clean.

**Tense.** Every claim above describes behaviour after this change, except the
two corrected facts and the Kantha Bopha cross-check, which describe the source
workbooks as they stand.
