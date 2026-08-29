---
id: 78
title: A blank row ends the patient block, so anything written below it is never read
labels: [wayfinder:grilling]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
