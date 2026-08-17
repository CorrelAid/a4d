---
id: 47
title: Four trackers where cleaning merges several patients into one patient ID
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 45
---

## Premise

Rests on [Give the patient comparison an ordinal row key](45-patient-row-alignment-duplicate-keys.md),
closed, which established that `patient_id` + `sheet_name` is patient's real
identity key and made duplicate-key groups visible per file and per stage. Two
of the five cleaned-stage duplicate groups it found have no raw-stage
counterpart, which is how this surfaced: the duplication is created *by
cleaning*, not read from the source.

Measured directly against the real 254-tracker output on the USB drive
(executed, not inferred):

- `2023_NPH A4D Tracker`, sheet `Sep23`: four distinct raw identities --
  `KH_NPH026`, `KH_NPH027`, `KH_NPH028`, `KH_NPH029` -- arrive at the cleaned
  stage as a single `KH_NPH02` with four rows. Every other patient in that file
  is keyed `KH_NP0xx`, so the four carry an odd prefix in the source.
- Across all 254 trackers, **4 files lose 9 identities** between raw and
  cleaned (distinct `patient_id` count drops). Row counts are preserved --
  nothing is dropped or invented, the identities are merged.

**R does exactly the same thing on the same file**, so this is not a Python
regression and not an R/Python divergence. That is why no comparison-based
ticket could have found it: both sides agree, and agreement is what the
comparison tool is built to stay quiet about. It also means this ticket does
not need R alive to answer -- it is a question about the Python pipeline and
the source workbooks.

`clean/patient.py`'s `_apply_preprocessing` normalizes `patient_id` by
converting hyphens to underscores and keeping `^([A-Z]+_[^_]+)` -- documented
as removing a transfer-clinic suffix (`MY_SM003_SB` -> `MY_SM003`). Ticket 45
**read** this and could not see how it produces `KH_NPH026` -> `KH_NPH02`,
since that value has only one underscore. Treat the mechanism as unlocated, not
as diagnosed.

## Question

Find out what merges these identities, and decide what the pipeline should do.

1. **Locate the mechanism.** Not the `patient_id` regex on its face -- read the
   actual value at each step (raw parquet, preprocessing, the Patient List
   join) for one of the four `2023_NPH` rows rather than reasoning from the
   code. The Patient List join is the prime suspect, since the cleaned
   identity may be coming from the Patient List rather than the monthly sheet.
2. **Decide whether the source is wrong or the pipeline is.** Open
   `2023_NPH A4D Tracker.xlsx` and see what the `Sep23` sheet and the Patient
   List actually record for these four patients. If the workbook itself
   conflates them, that is a finding for [ticket
   40](40-source-defect-findings-report.md), not a pipeline fix. If the
   pipeline is collapsing identities the workbook keeps distinct, that is
   patient data being attributed to the wrong person, and the pipeline gets
   fixed.
3. **Name the other three files.** Ticket 45 counted them (4 files, 9
   identities) without listing them; derive the list rather than assuming they
   share `2023_NPH`'s shape.

## Standing bar

Per the map's **triage means deciding, not labelling**: a named cause is not
enough -- say explicitly whether the merged identity is correct, with what was
read in the source workbook. This one carries more than a mismatch count: if
cleaning is merging distinct patients, the production `patient_data_*` tables
attribute one patient's monthly records to another.
