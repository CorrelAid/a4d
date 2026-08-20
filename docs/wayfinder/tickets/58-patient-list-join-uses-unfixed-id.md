---
id: 58
title: Monthly rows with a misspelled ID silently lose their Patient List demographics
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 47
---

## Premise

Rests on [Four trackers where cleaning merges several patients into one patient
ID](47-patient-ids-merged-at-cleaning.md), closed, which established that a
malformed `patient_id` is now recovered against the tracker's own well-formed
IDs (edit distance 1, unique candidate) or sentinelled -- and that this happens
in **cleaning**, at `fix_patient_id` (`src/a4d/clean/validators.py`), step 7.

Extraction runs long before that. `extract/patient.py` (~line 1107) joins the
`Patient List` sheet onto the monthly rows with
`.join(patient_list_join, on="patient_id", how="left", suffix=".static")`,
keyed on the **raw, unfixed** ID. So a monthly row whose ID is misspelled
cannot match its own Patient List entry, and the row keeps its measurements but
loses every static column the join supplies.

Measured (executed) after ticket 47's fix, on the real 254-tracker output:
`KH_NP026`'s recovered `Sep23` row has null `dob`, `sex`, `province` and
`t1d_diagnosis_date`, where the same patient's `Oct23`, `Nov23` and `Dec23`
rows carry all four. Ticket 47 fixed the identity; it did not fix this.

Ticket 47 deliberately did not touch it: changing the join key changes matching
for every tracker, which is a different measurement from the one that ticket
made.

**What would void this ticket rather than rewrite it:** ticket 47's recovery
being reverted, since without recovery these rows have no identity to attach
demographics to in the first place.

## Question

1. **Measure the real blast radius.** The 4 NPH rows are the known case, but
   the hyphen-spelled IDs are the likely larger one: `2021_Mahosot Hospital A4D
   Tracker_DC` writes `LA-MH056/057/058` on its monthly sheets, and
   `2026_Surat Thani…_Jun_26` writes `TH-ST029` -- do those workbooks' Patient
   Lists use underscores, and are those rows missing demographics today? Derive
   the count across all 254 trackers rather than reasoning from these two.
   Note that a raw-stage null `dob` is a weak proxy (2,063 rows across 62 files
   carry one, most for unrelated reasons) -- find a measure that isolates
   *join misses* specifically.
2. **Decide where the normalization belongs.** Candidates: normalize both sides
   of the join key inside extraction; move `fix_patient_id` earlier; or join a
   second time after cleaning. Each has a different reach -- the first changes
   the raw parquet's own `patient_id`, which the comparison tool's patient
   row-alignment key depends on.
3. **Check R.** R's own join ordering may or may not have the same gap; if R
   matches these rows and Python does not, the comparison tool has been
   reporting it as ordinary cell divergence all along.

## Standing bar

Per the map's **triage means deciding, not labelling**: measure before
proposing, and say explicitly whether Python is losing data a source workbook
carries.
