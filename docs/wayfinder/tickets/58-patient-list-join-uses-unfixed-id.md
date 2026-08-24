---
id: 58
title: Monthly rows with a misspelled ID silently lose their Patient List demographics
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-24d
claimed_at: 2026-08-24T20:00:00+02:00
resolution: decided
evidence: executed
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

## Resolution

**Decision.** Both whole-tracker joins in `extract/patient.py` -- the
`Patient List` demographics and the `Annual` sheet -- now key on a **derived
normalized ID** (`join_static_sheet`), not the raw one. The normalization rule
is the one cleaning already applied (fold `-` to `_`, drop any transfer-clinic
suffix), lifted out of `clean/patient.py::_apply_preprocessing` into
`extract/common.py::normalize_patient_id_expr` so the two layers cannot drift
into disagreeing about what one patient's identity is.

The key is derived **for the join only**. `patient_id` in the raw parquet is
still the spelling the month sheet used, which is what the raw layer promises
and what the comparison's patient row-alignment key depends on -- so this
change creates no row-key divergence at all (raw row-key divergence held at
4 files / 115 rows, cleaned at 6 / 129).

The user chose this over the two alternatives after seeing the measurement.

**1. The blast radius is 100x the ticket's known case, and it is one clinic.**
Derived across all 254 real trackers by extracting each workbook's own
`Patient List` with the pipeline's own extractor and diffing its ID set
against that tracker's raw monthly IDs -- the join-miss measure the ticket
asked for, rather than the null-`dob` proxy it warned off.

| File | Rows | What the month sheets write vs the Patient List |
|---|---|---|
| `2024_Mahosot Hospital A4D Tracker` | 397 | `LA-MH056`..`LA-MH093` (38 patients) vs `LA_MH0xx` |
| `2023_Mahosot Hospital A4D Tracker` | 275 | `LA-MH056`..`LA-MH082` (27 patients) vs `LA_MH0xx` |
| `2024_Mandalay General Hospital A4D Tracker` | 11 | `MM_YG013_MG`, absent from that Patient List entirely |
| `2024_CDA A4D Tracker` | 6 | `KH-CD016/017` vs `KH_CD0xx` |
| `2023_NPH A4D Tracker` | 4 | ticket 47's stray `H` |
| `2026_Surat Thani Hospital A4D Tracker_Jun_26` | 2 | `TH-ST029` vs `TH_ST029` |

**695 rows in 6 files; 680 recoverable by normalization, carrying 6,863
Patient List cells** across 12-13 columns -- `hba1c_baseline`,
`recruitment_date`, `patient_consent`, `lost_date`, `status_out` and the
diagnosis block, not just the four the ticket named. The boundary is exact:
`LA_MH055` had all 12 months of `dob`/`sex`/`province`/`t1d_diagnosis_date`,
`LA_MH056` had none of them.

**2. A second join had the identical defect and the ticket did not know about
it.** The `Annual` sheet join (same function, ~40 lines later) also keyed on
the raw ID. Measured the same way over the 131 trackers that have an Annual
sheet: **132 miss rows, 19 recoverable, 40 cells** (8 rows carrying data; the
other 11 are `VN_VC070`, whose Annual row is blank). Small, but leaving one
join on the raw key while the other used the normalized one is exactly the
drift the shared helper exists to prevent, so both were fixed together. The
remaining 113 misses name a patient the Annual sheet does not list at all --
a source fact, not a key mismatch.

**3. R has the identical gap, and the comparison was structurally blind to
it.** R's own frozen cleaned `2024_Mahosot` shows the same null block starting
at `LA_MH056`. Both sides null means no cell mismatch, so this never appeared
in `cell_mismatches` -- the same shape as [ticket
59](59-triage-unmatched-row-keys.md)'s unmatched rows and [ticket
42](42-fbg-unit-headers-and-implausible-values.md)'s unit swap. It is a
divergence the tool cannot report, found only by measuring the workbooks
directly. That answers question 3: R is **not** matching these rows, so this
was never being reported as ordinary cell divergence.

**4. The safety check that made the choice cheap.** Normalizing the key can
only hurt by fan-out -- two static entries folding to one key would silently
duplicate a patient's month rows. Measured across all 192 Patient-List-bearing
trackers: **zero** colliding keys, and zero Patient Lists with exact duplicate
IDs. The Annual sheet showed 20 files with apparent collisions, all of which
turned out to be junk rows (`'0'`, `'NEW'`) that already collide on the *exact*
key. `join_static_sheet` still dedupes and logs, as a guard against a future
workbook rather than a current one.

**Rejected.**
- *Also run `fix_patient_id`'s edit-distance recovery at join time*, which
  would have caught NPH's 4 rows too. Rejected: it pulls cleaning's fuzzy
  identity recovery into the raw layer, where [ticket
  47](47-patient-ids-merged-at-cleaning.md) deliberately kept it out, to gain
  4 rows. Those 4, plus Mandalay General's 11, are **source defects** and go to
  [ticket 40](40-source-defect-findings-report.md).
- *Join a second time after cleaning.* Rejected: the Patient List rows do not
  survive into the cleaned stage, so this means re-reading each workbook or
  persisting a second parquet -- much larger machinery for the same result.
- *Rewrite the raw `patient_id` itself instead of deriving a key.* Rejected:
  the comparison aligns patient rows on it, and the raw layer's promise
  (ticket 27) is that it records what the source cell actually contained.
- *Wire the new cause to every patient column and let its own gate bound it.*
  Tried and **measured**, not reasoned about -- it over-claimed on the three
  columns the month sheets also carry (`t1d_diagnosis_age` 1,069 rows against
  a join-miss population of 679, `bmi` 144, `age` 1), where R's null is not
  necessarily the join's fault. Backed out to an explicit column list.

**5. The divergence the fix creates is named.** New cause
`r_static_join_misses_respelled_id` (`migration/compare.py`): R null, Python
present, and the row's own ID still carrying the hyphen or transfer-clinic
suffix. It fires on **5,959 raw-stage cells across 16 columns**, every
per-column count matching the measured delta exactly, and **raw-stage
`unclassified` is now zero** (was 3,577 immediately after the fix, 0 before
it).

It is deliberately **raw-stage only**. The discriminator is the unnormalized
spelling, which is exactly what cleaning removes -- by the cleaned stage both
pipelines publish `LA_MH056` and the cause cannot tell itself apart from
`r_extraction_gap`'s column-naming failures. Cleaned-stage `unclassified` is
therefore **16 -> 3,593**, and that residue is [ticket
63](63-name-the-cleaned-stage-static-join-divergence.md).

One trap worth carrying forward: the classifier silently never fired on its
first run, because `add_row_ordinal` renames every key column to
`__key_<col>` and a bare `m.key.get("patient_id")` finds nothing.
`_sheet_year` documents the same trap. There is now a regression test for it.

**Evidence: executed.** Every number above is from a run, not a reading. The
blast radius and the collision check are corpus-wide scans of the real 254
trackers on the USB drive; the Patient List contents were read from
`Laos/MHS/2024_Mahosot Hospital A4D Tracker.xlsx` itself (`LA_MH056`:
Vientiane Capital, M, D.O.B. 2014-02-22, recruited 2021-06-22, all present);
the recovery was verified by re-running `a4d run patient` over all 254
trackers and re-counting. R's matching gap was read from R's own frozen
cleaned parquet. Full suite 958 passed / 1 skipped, `ruff check`,
`ruff format --check` and `ty check src/` clean; 22 new tests across
`test_extract/test_common.py`, `test_extract/test_patient_helpers.py` and
`test_migration/test_compare.py`.

Comparison totals, before this session -> after: patient raw cell divergence
**26,171 -> 33,488**, patient cleaned **114,306 -> 121,742**. Product is
byte-identical ("no change from the previous run" on both stages). Every one
of those new cells is Python publishing a value the source workbook carries
and R does not.

**Tense.** Everything describes current behaviour on this branch after the
change, except the R descriptions, which are of `r-archive/` and `output_r/`
as frozen.

## Spawned

- [Name the cleaned-stage half of the static-join divergence](63-name-the-cleaned-stage-static-join-divergence.md)
  -- 3,593 cleaned-stage cells with no cause, plus the three columns the
  corpus-wide wiring over-claimed on.

## Reported to ticket 40

- `2023_Mahosot Hospital A4D Tracker` and `2024_Mahosot Hospital A4D Tracker`:
  every month sheet writes `LA-MH056` and up with a **hyphen**, while the
  `Patient List` in the same workbook writes `LA_MH056` with an underscore --
  38 patients in 2024, 27 in 2023. Both pipelines lost every demographic for
  those patients; Python now recovers them, but the workbooks should be made
  consistent.
- `2024_CDA A4D Tracker`: `KH-CD016` and `KH-CD017` on the month sheets
  against `KH_CD016`/`KH_CD017` in the Patient List.
- `2024_Mandalay General Hospital A4D Tracker`: the month sheets carry
  `MM_YG013_MG` for 11 rows, but that workbook's `Patient List` has no such
  entry -- it lists `MM_MG013` and `MM_YG064_MG`. One of those is presumably
  meant; the pipeline cannot tell which, so the patient has no demographics.
