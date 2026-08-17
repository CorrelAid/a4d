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
  27](27-triage-patient-raw-residual.md)).
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
