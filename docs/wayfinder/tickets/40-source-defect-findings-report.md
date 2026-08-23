---
id: 40
title: Produce one Excel of every source-tracker defect, so the trackers themselves can be corrected
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 30
---

## Premise

Rests on [Triage the patient pipeline's raw-stage column-existence
divergence](30-triage-patient-raw-column-divergence.md), closed, where the user
set the principle this ticket exists to serve: where a divergence comes from a
human error in the source workbook, **the right fix is the source tracker, not
inference in the pipeline** -- cheaper, safer, and permanent. That only works
if every such finding is written down somewhere a person can act on.

Rests also on the map's standing preference that triage means deciding: across
tickets 18-38 this map has accumulated a large body of confirmed
source-data defects, each currently recorded only in prose on its own ticket,
or as a row in a per-run comparison report that will disappear when R is
retired ([ticket 12](12-retire-r-workspace.md)).

Concrete findings already waiting for such a report, all source-verified:

- **26 trackers with headerless columns holding data** (ticket 30), 4,572
  values, of which the clearest is `2021_Kantha Bopha`, sheets `Mar21`/`Apr21`,
  column Q -- 194 insulin-regimen values lost because the header cell is empty.
  Now emitted at runtime under the `blank_header_with_data` error code.
- **37 trackers that change shape mid-year**, 284 column positions
  (`tracker_layout_changed`, ticket 30) -- a tracker is one workbook for one
  clinic-year and should hold one layout throughout. Includes `2018_CDA`, whose
  April sheet is missing the `Insulin Regimen` column outright, and `2020_CDA`,
  whose June header edit relabels `Baseline FBG` from `mmol/dL` to `mg/dL` over
  unchanged values -- costing that clinic five months of baseline FBG (the
  `mmol/dL` spelling maps to nothing) and mis-filing five months of updated FBG
  under `fbg_updated_mmol`.
- **A corrupt tracker**: one 2022-named, 2022-sheeted tracker whose Patient
  List holds 2023 diagnosis dates for all 43 patients ([ticket
  38](38-triage-patient-cleaned-date-family.md)).
- **Buddhist-Era years typed into Gregorian date cells** ([ticket
  27](27-triage-patient-raw-residual.md)). **Superseded as a defect by [ticket
  61](61-decide-buddhist-era-date-conversion.md)**: a BE year is the calendar a
  Thai clinic uses, and the cleaned stage now converts it (375 patient cells,
  22 product rows). What remains reportable is only the era years that decode
  to nothing -- see the two below.
- **Excel formula errors cached in source cells** (`r_formula_error`, ticket 27).
- **Stray date/time-formatted cells in numeric columns** ([ticket
  24](24-triage-remaining-raw-column-residual.md)).
- **23 patients listed twice on the same monthly sheet** ([ticket
  45](45-patient-row-alignment-duplicate-keys.md)), with different data in each
  copy: 21 on `2024_Vietnam National Children`'s `Jul24` (two lists spliced
  together -- the numbered column runs 1..78 while the IDs repeat), one on
  `2023_Vietnam National Children's` `Jun23` (`VN_VC026`), one on `2018_Penang
  General Hospital_DC` `Oct18` (`MY_PN004`). Derived from the pipeline's own
  raw output, so this one is already machine-derivable per file, sheet and
  `patient_id`.
- **Two trackers whose R output carries `patient_id = "#REF!"`** -- 98 rows in
  `2026_Preah Kossamak` `May26`, 5 in `2026_Quirino` `Jan26` (ticket 45). A
  broken Excel reference in the source, visible because R preserves it where
  Python drops the rows.
- **Numeric entries typed into date-formatted cells** ([ticket
  46](46-triage-patient-raw-residual-4.md)), 26 patient cells: `2025_Hat Yai`
  `Annual!H` (12 sheets x systolic 120), `2025_YGH` (systolic 80),
  `2020_Mahosot` (`testing_frequency` 2). Excel stored each as a 1900 date, so
  the cell displays a date where a reading belongs -- the format is what needs
  correcting, not the value. The pipeline now recovers the number, so this is
  a workbook-tidiness finding rather than data loss.
- **Dates typed into numeric columns** ([ticket
  46](46-triage-patient-raw-residual-4.md)): `2023_Chiang Mai Maharaj Nakorn`,
  `Patient List!H` for `TH_CP005`, "Age at Diagnosis" holds a
  Buddhist-formatted date (Excel serial 20668) against a D.O.B. of 2009 -- 16
  rows. Neither pipeline can recover an age from it; the cell needs a human.
  `2020_Mahosot` and `2022_Mahosot` `blood_pressure_mmhg` carry the same shape.
- **Rich-text cells whose space sits in its own formatting run** ([ticket
  46](46-triage-patient-raw-residual-4.md)): `2017_Yangon`'s
  `hba1c_updated`/`fbg_updated_mg` ("8.8 (20.9.16)") and `2022_Mahosot`'s
  `observations`. Python reads them correctly, so this is cosmetic for the
  pipeline -- but it is also why the same value exists in two forms in one
  column, which is worth flagging to whoever maintains the workbooks.
- **More dates typed into numeric columns** ([ticket
  50](50-triage-patient-raw-residual-6.md)), extending the ticket-46 entry
  above with the two cells that finished the raw stage: `2023_Yangon General`
  `Patient List!H76` for `MM_YC043_YG`, "Age at Diagnosis" holding a
  `d-mmm-yyyy`-formatted 2017-05-04 (4 rows); `2021_Khon Kaen` `Mar21!P60` for
  `TH_KN008`, "Testing Frequency (per day)" holding a `d-mmm`-formatted
  2021-02-01 (1 row). Same verdict as the ticket-46 cases: no number is
  recoverable, the cell needs a human.
- **A clinical note typed into a date column** ([ticket
  50](50-triage-patient-raw-residual-6.md)): `2022_Kantha Bopha`,
  `May'22!Y161` and `Jun'22!Y161` for `KH_KB089`, the hospitalisation Date
  column holding the text "on stamlor 5mg" -- a medication note, not a date.
  Both pipelines carry the text through the raw stage unchanged.
- **A Buddhist-Era year in a date cell that decodes to a plausible Gregorian
  date** ([ticket 50](50-triage-patient-raw-residual-6.md)): `2022_Hat Yai`
  `Patient List!G25` for `TH_HY013` holds 2560-01-01 in a `d-mmm-yyyy` cell.
  The patient's own D.O.B. (2013-03-17), recruitment (2017-06-01) and age at
  diagnosis (4) all agree the intended date is 2017. **[Ticket
  61](61-decide-buddhist-era-date-conversion.md) now recovers it**: the band
  test converts 2560 to 2017 without being told, matching the answer this
  report had derived by hand. Still worth reporting so the workbook is
  corrected, but no longer data the pipeline loses.
- **Three more header defects Python works around and R does not** ([ticket
  50](50-triage-patient-raw-residual-6.md)), each costing R real data and each
  worth correcting at source: `2022_Kantha Bopha`'s month sheets open the
  hospitalisation header (`X71`) with thirteen leading spaces; `2019_Preah
  Kossamak`'s `Jul19` and `Aug19` sheets have lost every header merge the other
  ten sheets still carry, leaving "Date" sub-headers unqualified (and a stray
  `3` typed into `L63`); `2025_LWCH` leaves the current-month clinic-visit
  column (`D`) unheaded in both header rows.
- **113 product groups across 21 files where the computed closing balance
  contradicts the tracker's own recorded total** (`balance_reconciliation`,
  [ticket 36](36-triage-product-cleaned-unclassified-residual.md)).

## Question

Decide what this report is and build it. The user's stated shape: **one Excel,
every finding, with tracker file, sheet, `patient_id`, row and the exact
finding**, so the data team can go and correct the source workbooks.

Points to settle before building:

1. **Source of truth.** Derive it from the pipeline's own error log / errors
   table (which already carries error codes, file and sheet) rather than
   hand-collecting from ticket prose -- otherwise it is a hand-maintained list
   that drifts. Check what the existing `errors`/`logs` tables already capture
   per finding and what is missing (row number and `patient_id` in particular).
2. **Which findings belong.** Every error code, or only the ones a human can
   act on in the workbook? A type-conversion failure on a cell a clinician
   mistyped is actionable; an internal pipeline warning is not.
3. **Where it lives and when it runs.** A new `a4d` CLI command (this outlives
   R, unlike `scripts/compare_outputs.py`), part of `create tables`, or a
   separate report step.
4. **Whether it supersedes anything.** [Ticket
   16](16-log-analyzer-drill-down.md) asks for a drill-down view into one
   tracker's errors; these two may be the same deliverable seen from two
   angles, or complementary (per-file interactive vs. whole-set actionable).
   Decide that rather than building both blind.

## Standing bar

Per the map's **triage means deciding, not labelling** preference and the
destination's "every difference explicitly decided": a finding in this report
must be precise enough that someone can open the named workbook, find the named
cell, and see the problem -- not a category label.

## Findings added by session-2026-08-19 ([round 4](51-triage-patient-cleaned-residual-4.md))

Two more source defects, both verified in the workbook and both already
producing a pipeline error the report can derive from:

- **2022 Vietnam National Children's Hospital: the whole `Date of T1D
  Diagnosis` column is a year out.** Every cell in `Patient List!G` holds a
  2023 date -- `G13` = 2023-07-16 for VN_VC001, who was born 2013-03 and
  recruited 2017-07 -- in a tracker filled in during 2022. The patients are
  recorded as diagnosed a year after the tracker was written and five years
  after they were recruited for having the disease. Python's `_validate_dates`
  already logs each one as `invalid_value`; 530 cleaned-stage cells.
- **Misspelled month names inside otherwise well-formed dates.** `9-Dce-20`
  (2021 Mahosot, 81 cells), `25-Ma4-2025` (18), `4-Okt-2023` (3), plus
  malformed separators `26/102022` (5) and `19-Jan_2023` (5). Python refuses
  them and stamps the date sentinel, logging `invalid_value`; R guesses and
  gets them wrong (it reads `9-Dce-20` as 2020-09-01, dropping the misspelled
  month and promoting the day into the month slot). The intended dates are
  legible to a human, which is exactly why the fix belongs in the workbook.

Also worth carrying, though it is a *province* rather than a date: five VNCH
trackers write `Thái Nguyễn` where the allowed list has `Thái Nguyên`, and two
more spellings (`Thai Nguyen`, `Thai nguyen`) that **neither** pipeline
recovers -- those rows are "Undefined" in both, so the comparison never flags
them but the data is lost all the same.

## Findings added 2026-08-19c (from [round 6](53-triage-patient-cleaned-residual-6.md))

Two more source-workbook defects, both found while triaging the patient cleaned
stage and both deliberately left uncorrected in the pipeline:

- **A date typed into the diagnosis-age column.** 2023 Chiang Mai Maharaj
  Nakorn records `1956-08-01` in `t1d_diagnosis_age`; R carries the Excel
  serial (20668) through into the age, Python nulls it. The cell needs a number
  of years, not a date.
- **A date broken by a stray space inside it.** `26-05- 2007` is legible to a
  human as 26 May 2007 but parses as neither pipeline's answer — R and the old
  Python both produced a wrong date, and Python now produces the error
  sentinel. Round 6 rejected normalizing whitespace around date separators as
  an untested third change in one session, so the workbook is the fix.

## Findings added 2026-08-19d (from [round 7](54-triage-patient-cleaned-residual-7.md))

Round 6 already logged 2023 Chiang Mai's date-in-the-age-column above. Round 7
confirmed it against the workbook itself and found the wider defect behind it,
plus a second clinic with the same shape:

- **2023 Chiang Mai's `Date of T1D Diagnosis` column is empty for every
  patient**, which is why its formula-derived `Age at Diagnosis*` column reads
  `#NUM!` throughout and why TH_CP005's stray `1956-08-01` had nothing to be
  computed from. Fixing the one cell without filling the diagnosis-date column
  leaves the whole column broken.
- **2023 Yangon General records a diagnosis a year before the birth.**
  MM_YC043_YG has D.O.B. 2008-01-01 and `Date of T1D Diagnosis` 2007-06-01,
  with `2017-05-04` typed into the age column on top. R carries that date's
  Excel serial (42859) into the age; Python nulls it. Two defects in one row.
- **Heights that are not heights.** 2025/2026 Señor Sto. Niño, 2021-2023 Likas
  and 2019 Mahosot record `6.9`, `2.52`, `2.43`, `2.72`, `13.0` in the height
  column. R sentinels them; Python converts them to metres and emits `0.069`,
  `0.0252`. Whether these are a mis-keyed unit or plain data entry errors is
  [round 8](55-triage-patient-cleaned-residual-8.md)'s question, but no reading
  of them is a plausible height.

## Findings added 2026-08-20 (from [round 10](57-triage-patient-cleaned-residual-10.md))

Round 10's whole residual is source defects: 37 of its 72 remaining cells are a
date cell damaged past reading, and every one of them is a workbook fix rather
than something either pipeline can infer.

- **`25-Ma4-2025` in a `Date Lost to Follow Up` cell.** 2025 Taunggyi, 18 cells
  (one value, repeated down the months). "Ma4" is Mar or May and nothing in the
  workbook decides which; R reads the embedded `4` as the month and publishes
  2025-04-25, a third answer neither spelling supports, and Python declines.
  The same row also carries `status = Active` while holding a lost-date at all,
  so two cells need attention.
- **Dates with a separator swallowed or a digit group glued.** `26/102022`
  (2022/2023 Sunprasitthiprasong), `8/1023` (2023 Yangon General), `10/1023`,
  `3/10.23` (2023 North Okkalapa), `10-Oct-2-24`, `13-Mar-0202` (2023 Penang
  General). Where the missing separator belongs is a guess: R's frozen output
  reads `10/1023` as 2010-10-23 while running R's own parser over that string
  in isolation returns 2023-10-10 -- the same input, two answers, so R's number
  is not evidence of the clinic's intent either.
- **The tracker template's own example text left in a patient row.** 2018
  Penang General DC, MY_PN001, `e.g. xxx (mth-18)` in both the HbA1c and FBG
  measurement cells across Jul18/Aug18/Sep18. R turns it into 2018-01-01.
- **A fasting-glucose reading typed into the HbA1c column.** 240 and 125, plus
  299 at 2024 Preah Kossamak (KH_KB050, Jun24-Aug24). R has no range check on
  this column and publishes them as HbA1c percentages; Python rejects them
  against the declared 0-25 bound. The numbers look real -- they are in the
  wrong column.
- **A date typed into `testing_frequency`.** 2021 Khon Kaen, TH_KN008, Mar21
  holds 2021-02-01 where a tests-per-day count belongs. R publishes the Excel
  serial 44228 as the frequency.
- **Two baseline-FBG readings that cannot be read in the unit their column
  turned out to hold.** 2020 Kantha Bopha's `Baseline FBG` column is 90.1%
  sub-30, so the pipeline reads the whole column as mmol/L (ticket 42) -- and
  KH_KB056's 47.8 and KH_KB062's 53.8 are then past the analytical ceiling and
  are rejected. Read as mg/dL they would be ordinary. Either those two cells
  are mg/dL in an otherwise-mmol column, or they are mis-keyed; the workbook is
  the only place that can say.
- **Patient IDs that do not match the template's `XX_YY###` format**, found
  while closing [ticket 47](47-patient-ids-merged-at-cleaning.md). These are
  identity defects, not measurement defects, so they are worth listing first in
  the report: an unrepairable one costs the clinic a whole patient's history.
  - `2023_NPH A4D Tracker`, sheet `Sep23`, rows 128-131: `KH_NPH026`,
    `KH_NPH027`, `KH_NPH028`, `KH_NPH029` carry a stray `H`. The same
    workbook's `Patient List`, `Oct23`, `Nov23` and `Dec23` sheets all spell
    the same four patients `KH_NP026`-`KH_NP029`. The pipeline now recovers
    these, so the data is not lost -- but the workbook should be corrected so
    it stops relying on recovery.
  - `2026_NOGH T1D Tracker_June_26`: `MM_NO97`, `MM_NO98`, `MM_NO99` are
    7 characters where the template wants 8, in the `Patient List` **and**
    every month sheet. The workbook has `MM_NO090`-`MM_NO096` and no
    `MM_NO097`, so nothing in it says whether the intended IDs are `MM_NO097`
    -`MM_NO099` or something else. **Unrepairable in the pipeline**: three
    distinct patients, 18 rows, all published as `Undefined` today. This one
    needs a human at the clinic.
  - `2026_YGH T1D Tracker_June_26`: `MM_NO55_MW_YG` reduces to `MM_NO55`,
    again 7 characters. One patient, 3 rows, published as `Undefined`. Same
    situation as above.
  - `2021_Mahosot Hospital A4D Tracker_DC`: `LA-MH056`, `LA-MH057`,
    `LA-MH058` on the Jun-Nov sheets vs `LA_MH056`-`LA_MH058` on `Dec21` --
    the same three patients spelled two ways inside one workbook. The pipeline
    merges them correctly; the workbook should still be made consistent.
  - `2026_Surat Thani Hospital A4D Tracker_Jun_26`: `TH-ST029` and `TH_ST029`
    both appear on `May26`, so that patient ends up with two rows for one
    month once the spellings are normalized. Likely a duplicated entry.

## Findings added by [ticket 39](39-recover-dates-embedded-in-free-text.md) (2026-08-21)

All four sit in `hospitalisation_date` and were measured on the real
254-tracker set. None is repairable in the pipeline; each needs the workbook
changed.

- **The template's own instruction text saved as data, ~170 cells.**
  `Insert Date` (65), `Insert Date or NA` (60), `NA or Hospitalisation Date`
  (44), `DKA - <insert date>` (1). The pipeline nulls them (ticket 38), so
  nothing is published wrongly -- but a data row holding the form's own
  placeholder means the cell was never filled in, and the clinics should be
  told which rows those are.
- **Buddhist-Era years in a Gregorian date field, inside a note naming a date
  *range***: `18-19/11/2567`, `19-22/5/2568`. Two cells, both
  `hospitalisation_date`. [Ticket
  61](61-decide-buddhist-era-date-conversion.md) settled that a BE year is
  converted, not refused -- but these carry a range as well, and picking one of
  two admission days is a convention [ticket
  39](39-recover-dates-embedded-in-free-text.md) declined and this decision did
  not overturn. Left unconverted on the range, not on the calendar; the fix is
  the clinic writing one Gregorian date.
- **Era years that decode to no plausible date**, 6 cells, both
  `fbg_updated_date` ([ticket
  61](61-decide-buddhist-era-date-conversion.md)): `2025_CDA` `3035-03-01`
  (1 cell, `KH_CD016`) and `2025_Surat Thani` `5025-05-19` (5 cells,
  `TH_ST003`). Subtracting 543 gives 2492 and 4482, still years in the future,
  so neither is a Buddhist-era date the band can recover. Both stay sentinelled
  and are logged `invalid_value`; the cells need a human.
- **A stay written with no separators at all**: `25Jul-2Aug2022`, 1 cell.
  Neither pipeline reads it correctly -- R gives 2022-02-25, Python takes the
  discharge day 2022-08-02 -- because with the separator missing the opening
  `25Jul` cannot be told from a token whose year is unreadable.
- **Two impossible dates that a plausible-looking reading nearly hid**:
  `39 Aug 2022` (2022 CDA) and `DKA Jul'29` (2021 Mahosot), 7 cells. Both
  recover to a date past their own tracker year (2039, 2029) and are then
  sentinelled by the beyond-tracker-year guard, so nothing wrong is published.
  `39 Aug` is a day that does not exist; `Jul'29` is almost certainly `'19`
  or `'20` mistyped.

## Findings added by [the classifier re-audit](32-audit-classifiers-against-decision-bar.md) (2026-08-22)

All three are product-side, all measured on the real 254-tracker set, and all
now emit a pipeline error record this report can derive from.

- **Corrupt Excel serials in entry-date cells**, `implausible_era_date`, 3 cells.
  `2024_Chiang Mai Maharaj Nakorn`, `Aug24`: serial **1,339,576**, which reads as
  `5567-08-19`. `2026_Penang General Hospital_Jun_26`, `Apr26`: serial
  **411,384**, reading as `3026-04-30`. `2025_Hat Yai Hospital`, `Oct25`:
  `2525-10-02`, where the Buddhist year for 2025 is 2568 -- so this one is a
  mistyped BE year rather than a serial. In each case the day and month match
  the sheet, so the intended date is legible to a human; the year is not
  recoverable by inference, which is why the pipeline now sentinels them.
- **Entry dates from the following year in a December sheet**, 78 cells across
  26 files, the largest being `2023_Sarawak General Hospital`'s `Dec23` sheet
  (25 cells, running 2024-12-01 to 2024-12-28). Python's beyond-tracker-year
  guard already flags each one under `invalid_value`. Either the rows belong in
  the next year's tracker or the year was mistyped; the workbook is the only
  place that says which.
- **Entry dates decades before the tracker**, 29 cells, logged by the same
  guard's year-floor branch and deliberately preserved in output.
  `2023_Surat Thani` holds `0202-06-20` and `2025_Quirino` `0205-12-02` -- year
  202 and 205 -- alongside `1935-04-30` (2025 NOGH), seven `2009-12-04` (2019
  Mahosot) and four `2004-05-08` (2024 Sarawak).

**One finding about this report's own source of truth, now fixed.** Point 1 of
the Question above assumes the errors table carries every finding. It did not:
`a4d run` published an errors table holding the **patient arm only**, because
the patient arm writes it from inside `run_patient_pipeline` and nothing wrote
the product arm's. Measured before the fix: 63,295 records with zero
`balance_reconciliation` (116 exist) and zero `implausible_era_date`. So the 113
product balance-reconciliation groups this ticket already lists were never
actually reachable from the table. `run` now writes it once after both arms:
63,295 -> 97,326 records.

## Findings added by [rows that pair with nothing](59-triage-unmatched-row-keys.md) (2026-08-24)

- **Patient ID cells holding a broken formula, 120 rows across 9 trackers**,
  now emitted under the new `excel_error_patient_id` code. Every one of these
  rows is discarded -- the patient cannot be identified -- so the clinic's
  measurements for that row never reach BigQuery. Two trackers hold nearly all
  of it: `2026_Preah Kossamak Hospital`'s `May26` sheet is **98 rows, the entire
  month**, and they are not empty rows (50 carry an age and an updated FBG, 47 a
  baseline HbA1c, weight, height and BMI, 45 an insulin regimen); and
  `2026_Quirino Memorial`'s `Jan26` sheet is 5 rows carrying baseline HbA1c and
  BMI. The remaining 17 are spread over `2025_Kantha Bopha II` (4),
  `2024_Likas Women & Children's` (4), `2024_Sultanah Bahiyah` (3),
  `2022_Mandalay Children's` (3), `2025_Phattalung` (2) and
  `2025_Mandalay Children's` (1). The ID column formula needs repointing in each
  workbook; until then the measurements are unrecoverable, since nothing else in
  the row names the patient (the name column reads `#REF!` too).

- **A patient ID that is two clinic codes spliced together.** `2026_YGH`
  records `MM_NO55_MW_YG` in `Apr26`, `May26` and `June26` -- a transfer between
  clinics written into the ID -- where every other patient in that tracker reads
  `MM_YY###_YG`. It fails the template's format and no well-formed ID in the
  tracker sits an edit away, so the pipeline sentinels it to `Undefined` per
  [ticket 47](47-patient-ids-merged-at-cleaning.md) and the patient's three
  months are unattributable. Only the clinic can say which ID is intended.

- **A cleared patient row number, `2022_Children's Hospital 2`, `Oct22`, cell
  A70.** The number was deleted but the cell kept a space, which is invisible in
  Excel. Harmless to the pipeline as of this session (`find_data_start_row` now
  reads through it), and listed only because the same residue in row 1 of eleven
  `2024_Mandalay Children's` sheets is what makes R drop that tracker's first
  patient -- a clinician cannot see the difference between an empty cell and one
  holding a space, so it is worth knowing the shape exists.
