---
id: 59
title: Rows that pair with nothing on the other side, which no ticket has ever triaged
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-24
claimed_at: 2026-08-24
resolution: decided
evidence: executed
closed_by: null
spawned_by: 47
---

## Premise

Rests on [Four trackers where cleaning merges several patients into one patient
ID](47-patient-ids-merged-at-cleaning.md), closed, whose comparison re-run
exposed this. That ticket's four recovered rows stop pairing with R, and
finding *which* rows they were required querying the parquets by hand -- so
`RowKeyOverlap` was extended to carry the unmatched keys, not just their
counts, and the report gained a `row_key_unmatched` sheet.

The sheet's first run named a population nobody had looked at. Measured
(executed) against the real 254-tracker output on the USB drive:

- **Patient cleaned: 144 unmatched rows across 7 files.** Only 8 of them are
  ticket 47's (`2023_NPH`, 4 R-only + 4 Python-only). The rest:
  `2026_Preah Kossamak…_Jun_26` 98 R-only, `2022_Children's Hospital 2` 15
  R-only, `2024_Mandalay Children's` 11 Python-only,
  `2026_Quirino Memorial…_Jun_26` 5 R-only, `2026_YGH…_June_26` 3 R-only and 3
  Python-only, `2024_Mahosot Hospital` 1 Python-only.
- **Patient raw: 130 unmatched rows.**
- **Product, both stages: 0** -- resolved by
  [ticket 17](17-fix-product-row-alignment-and-triage.md)'s ordinal key.

This population is structurally invisible to every triage ticket the map has
run. A row with no partner never reaches `compare_cells`, so it appears in no
`cell_mismatches` sheet, contributes to no per-column or per-cause count, and
cannot be classified -- the ten-round patient chain worked exclusively off
those counts. It is the same shape of gap as `compare_columns` was before
[ticket 26](26-triage-product-column-divergence.md).

**What would void this ticket rather than rewrite it:** the counts turning out
to be an artifact of the row-alignment key rather than of the data, which
[ticket 45](45-patient-row-alignment-duplicate-keys.md) settled for patient
(the key is unique in 249 of 254 files) -- so this is unlikely, but it is the
thing to check first.

## Question

1. **Is this a divergence at all, or a shape difference?** A whole tracker
   present on one side only is already reported separately as a file-level
   finding; these are *rows* inside files both sides produced. Establish
   per file whether R is holding rows Python drops, Python is producing rows R
   never had, or the two are the same rows keyed differently.
2. **Start with `2026_Preah Kossamak…_Jun_26`'s 98 R-only rows**, the largest
   single population and 68% of the patient cleaned total. 98 rows is a
   plausible whole clinic-month.
3. **Decide each, to the map's standing bar** -- for every group, whether
   Python is right, R is right, or the source workbook is defective. Ticket
   47's four rows are already decided (Python correct, recorded there) and
   should be excluded rather than re-argued.

## Standing bar

Per the map's **triage means deciding, not labelling**. Note that the usual
instrument does not work here: there is no cell mismatch to classify, so the
cause registry cannot carry the answer and the resolution comment has to.

## Resolution (session-2026-08-24)

**Decision.** The 144 cleaned / 130 raw unmatched rows are **five distinct
populations, not one**, and each is now decided. Two were pipeline defects --
one Python's, one R's -- two were already-closed decisions resurfacing under a
key the comparison could not pair, and one is a source defect with a behaviour
question the user settled. Python is the correct side of all five.

| population | rows | verdict |
|---|---|---|
| 2022 Children's Hospital 2, `Oct22` | 15 R-only | **Python defect, fixed.** Whole sheet was being dropped |
| 2026 Preah Kossamak `May26` + 2026 Quirino `Jan26` | 98 + 5 R-only | Source defect; Python's drop kept, now **reported** rather than silent |
| 2024 Mandalay Children's, `MM_MD001` | 11 Python-only | **R defect.** Python correct, no change |
| 2026 YGH, `MM_NO55_MW_YG` | 3 + 3 | Same rows keyed differently; ticket 47 already decided it. Source defect |
| 2023 NPH / 2024 Mahosot | 4+4 / 1 | Already decided by tickets 47 and 43; excluded per this ticket's own scope |

**Because.**

*Children's Hospital 2 (Python defect).* `find_data_start_row` scanned column A
for the first **numeric** value. In `Oct22` the first patient's row-number cell
(`A70`) holds a whitespace-only string -- Excel residue of a cleared number --
so Python started at row 71 and read its two header rows from 70 and 69. Row 70
*is* data, so the patient-ID header became the literal string `VN_CH001`,
harmonization found no `patient_id`, and `read_all_patient_sheets` skipped the
entire sheet. Fifteen patients' October records were lost. R's rule --
`which(!is.na(tracker_data[, 1]))`, any non-NA cell -- lands correctly.

The rule was chosen by scanning all 254 trackers first, per this map's standing
preference, and the scan **killed the obvious fix**: 28 month sheets have a
non-empty column-A cell above the first numeric one, and 14 of them (2026
Gensan, 2025/2026 VNCH) hold a stray `'m'`/`'f'`/`'n'` in row 1 -- adopting R's
rule wholesale would set those sheets' data start to row 1 and destroy them.
What Python now does instead: extend the numeric block back over a
whitespace-only cell **directly abutting** it, one row only. Measured over all
254 trackers, that moves the start on **exactly one sheet** -- this one.

*Preah Kossamak and Quirino (source defect + a behaviour decision).* Both sheets
carry `#REF!` in the patient ID *and* name columns on every row, and
`read_all_patient_sheets` dropped them via
`filter(~pl.col("patient_id").str.starts_with("#"))` with **no error record at
all** -- just an INFO line counting "invalid rows". The rows are not empty:
Preah's 98 carry 50 ages and updated FBG readings, 47 baseline HbA1c / weight /
height / BMI, 45 insulin regimens.

The user decided (2026-08-24) to **keep dropping and start reporting**. The
reasoning is about the group key, not the row: `Undefined` is a bucket rather
than an identity, so keeping these rows would pool 98 people's measurements
under one `patient_id` and quietly corrupt any per-patient grouping downstream.
That does not contradict [ticket 47](47-patient-ids-merged-at-cleaning.md),
which *keeps* a malformed ID under `Undefined`: a misspelled ID is a real
identifier a human wrote and a clinic could reconcile against its own records,
whereas `#REF!` is not an identifier at all -- the cell's content is gone, so
there is nothing to reconcile, ever. New `excel_error_patient_id` error code,
one record per dropped row. It fires on **120 rows across 9 trackers**, not the
103 this ticket could see -- the comparison only ever showed the rows R also
kept.

*Mandalay Children's (R defect, Python correct).* R hardcodes
`row_min <- row_min + 1` for 2022+ trackers
(`script1_helper_read_patient_data.R:67`) because "openxlsx always skips empty
rows at the start of the file" -- it assumes exactly **one** leading empty row.
Verified in the workbook: `Jan24`'s row 1 is genuinely empty, and every other
month sheet holds a single space in row 1. So openxlsx skips nothing on those
11 sheets, R's `+1` pushes the data window one row down, and `MM_MD001` -- a
real patient with a full clinical record every month -- falls out of 11 of 12
sheets. Exactly the same whitespace residue as the Children's Hospital 2 case,
mishandled in the opposite direction.

*YGH.* Source ID is `MM_NO55_MW_YG` (a transfer, two clinic codes spliced). R
truncates to `MM_NO55_`; Python sentinels to `Undefined` under ticket 47's rule.
Same three rows, two keys -- no data difference, and Python is right by a
decision already made. Reported to [ticket 40](40-source-defect-findings-report.md).

**Rejected.**

- *Adopt R's "first non-empty cell" data-start rule.* Killed by the 254-tracker
  scan: 14 sheets would start at row 1 on a stray letter. This is why the fix is
  the narrow abutting-cell rule and not the general one.
- *Back up over a whole run of blank-string cells rather than one.* No
  multi-row run exists in the corpus, and swallowing several would risk reading
  a header row as data -- the same class of bug in reverse.
- *Keep the `#REF!` rows under the `Undefined` sentinel* (option A as put to the
  user). The measurements are real and would be usable for clinic-level trends,
  but they would share one group key with every other unidentified patient. What
  this gives up is stated plainly: 120 rows of genuine clinical measurement are
  discarded, and only a workbook repair can bring them back.
- *Fix R's `+1` offset.* R is being retired ([ticket 12](12-retire-r-workspace.md));
  its bug is documented, not repaired.
- *Add a cause classifier for any of this.* There is no cell mismatch to
  classify -- an unmatched row never reaches `compare_cells`. The resolution
  comment is the record, as this ticket's own Standing bar anticipated.

**Evidence.** `executed` throughout.

- The ticket's numbers re-measured against the run at
  `output/comparison/2026-08-22T084333Z` before any work: 144 / 130 / 0 / 0,
  unchanged since the ticket was written.
- Every mechanism reproduced by running the code against the real workbook on
  the USB drive, not read: the `Oct22` header misread reproduced through
  `read_all_patient_sheets` and observed as its own "no 'patient_id' column,
  skipping" warning; the `#REF!` rows' contents counted column by column; the
  Mandalay row-1 space read out of all 12 sheets with `openpyxl`; R's `+1`
  offset read from its own source at line 67 and confirmed against which sheet
  keeps `MM_MD001` in R's frozen output (`Jan24`, alone).
- The abutting-cell rule scanned across **all 254 trackers** before it was
  written, and again after, to confirm it moves exactly one sheet.
- Full pipeline re-run against the real 254-tracker set and a full comparison
  against the frozen `output_r/`
  (`output/comparison/2026-08-23T225035Z`): row-key divergence **144 -> 129**
  cleaned and **130 -> 115** raw, the delta being exactly the 15 recovered rows
  at both stages. Cell mismatches moved by **+22 only** -- `t1d_diagnosis_age`
  4,800 -> 4,814 and `fbg_baseline_mg` 11,839 -> 11,847, both onto existing
  named causes -- and **`unclassified` did not move on any stage** (16 patient
  cleaned, 0 patient raw, 21 product cleaned, 0 product raw). Product untouched
  at both stages, patient raw's per-column snapshot byte-identical.
- 931 tests, `ruff format --check`, `ruff check`, `ty check src/` all pass.

**Tense.** The Children's Hospital 2 loss and the silent `#REF!` drop were
**current production behaviour** until this session; both are now fixed on
`migration`. R's `MM_MD001` loss is current behaviour of the archived R
pipeline and will not be fixed. The 120 discarded `#REF!` rows remain discarded
-- that is the decision, not a defect left open.

**What is left, and where it went.** The residual unmatched population is
**129 cleaned / 115 raw**, and every row of it is now decided: 103 are the
`#REF!` source defect, 11 are R's offset bug, 6 are YGH's spliced ID, 8 are
ticket 47's, 1 is ticket 43's. Nothing is unowned. Three source-defect findings
were written to [ticket 40](40-source-defect-findings-report.md).
