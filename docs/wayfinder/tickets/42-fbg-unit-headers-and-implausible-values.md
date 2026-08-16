---
id: 42
title: Decide how FBG unit headers are resolved, and what to do about physiologically implausible mmol values
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-17
claimed_at: 2026-08-17
resolution: decided
evidence: read
closed_by: null
spawned_by: 30
---

## Premise

Rests on [Triage the patient pipeline's raw-stage column-existence
divergence](30-triage-patient-raw-column-divergence.md), closed, whose
`tracker_layout_changed` flag surfaced `2020_CDA` relabelling its
`Baseline FBG` column from `mmol/dL` to `mg/dL` in June while the values stayed
identical (median 233, range 67-500 -- mg/dL on both sides). Chasing that
produced a full inventory of every FBG header spelling across the 254-tracker
set: [assets/fbg_header_inventory.md](../assets/fbg_header_inventory.md), all
23 spellings with their resolution and value distributions. (An `.xlsx` copy
was generated for the advisor conversation but is not committed -- `*.xlsx` is
gitignored repo-wide to keep tracker data out of git.)

What the inventory establishes (executed, whole-set):

- **The mg side is clean.** Ten spellings, all mapped, all mg-scale --
  including typos the synonym file already absorbs (`mg%`, `mg/%`, `m/dL`,
  `ml/dL`).
- **The malformed `mmol/dL` spelling carries two different units.**
  `Updated FBG mmol/dL` (2 files, 178 values, median 9.4) is genuinely mmol, so
  its existing alias to `fbg_updated_mmol` is correct.
  `Baseline FBG (mmol/dL)` (1 file -- 2020 CDA, 45 values, median 233) is
  mg-scale. So the same spelling cannot be blanket-aliased, and leaving it
  unmapped is the safe default rather than a gap.
- **One header offers the reader a choice of units and is unmapped**:
  `Baseline FBG (mmol/L or mg/dL)`, with an `Updated FBG` twin, drops 155
  mmol-scale values. Confirmed to be `2018_Kantha Bopha Hospital A4D Tracker`
  (verified from the local comparison report, where both sides carry the pair
  unmapped -- R under its sanitized name, Python under the literal text). Being
  a 2018 tracker, the **latest-template rule puts this at low priority**: it is
  historic, not current, and the trackers are kept if the values are ever
  wanted.
- **Exactly one column is outright mislabelled**, not two:
  `Baseline FBG (mmol/dL)` at 2020 CDA. The mixed-unit problem below is a
  different kind of defect -- individual rows in the wrong unit inside a
  correctly-labelled column, which no header fix can reach.
- **Unit confusion runs in both directions**, and is an order of magnitude
  larger in one of them. Grouping every glucose column by when it is measured
  and the unit its header states
  ([assets/glucose_readings_by_unit.md](../assets/glucose_readings_by_unit.md)):
  **9,264 readings sit in mg/dL-labelled columns but below 30 mg/dL** (3,714
  baseline + 5,550 updated), which cannot be an ambulatory reading and is
  exactly where a mmol/L number lands; **122 sit in mmol/L-labelled columns but
  above 100** (30 + 92), where a mg/dL number lands.
- **Zeros are placeholders, not hypoglycaemia**: all 244 baseline mmol/L
  readings under 3 mmol/L are exactly 0.
- **The baseline distribution is broad but continuous** -- median 19.3 mmol/L,
  p90 38.0, and **no values above 100 at all**. That is not the bimodal shape
  bulk mg/dL contamination would produce, so the high baseline may simply be
  presentation hyperglycaemia.

Two framings were tried and discarded before this one, both recorded so they
are not retried: bucketing on **35 mmol/L** (an invented threshold, replaced by
percentiles and the two physiologically impossible cut-offs above), and
comparing **mg-recording clinics against mmol-recording clinics** (unsound --
different clinics and populations, no dual recording of the same patient).

Nothing in `reference_data/synonyms/synonyms_patient.yaml` was changed while
closing ticket 30: resolving a unit needs clinical input, not a code decision.

## Status: asked, awaiting reply

**The email went to A4D's medical advisor on 2026-08-15**, with a
clinician-facing spreadsheet (the grouped table above plus a tab listing every
exact column label; no clinic names, no pipeline vocabulary, no invented
thresholds). This ticket cannot be worked until that reply lands -- there is
nothing to derive from the code or the data that would settle it, which is why
it is not simply blocked on another ticket.

The four questions asked, in the order sent:

1. Are a reading below 30 mg/dL and a reading above 100 mmol/L both impossible
   in this setting? If so, ~9,300 readings have their unit mixed up one way and
   ~120 the other.
2. What is the credible range for a fasting glucose reading, top and bottom?
3. Is a baseline median of 19.3 mmol/L (p90 38.0) what you would expect at T1D
   diagnosis in these clinics?
4. What should the pipeline do with a reading outside that range -- mark it
   suspect, convert it (mg/dL / 18), or discard it?

Plus one statement offered for correction: that readings of exactly 0 mean
"not measured".

## Question

The decision this ticket carries, once the reply is in.

1. **What credible range does the advisor give**, and does it confirm that
   below 30 mg/dL and above 100 mmol/L are impossible? That confirmation is
   what turns ~9,400 readings from "odd" into "unit mixed up at entry".
2. **What should the pipeline do with an out-of-range value** -- flag it via
   `ErrorCollector` and keep it, convert it (`mmol/L = mg/dL / 18.0182`), or
   sentinel it? Converting is a data-altering guess and should not be done on a
   heuristic alone. Note the asymmetry in scale: the mg/dL-labelled columns
   hold 9,264 suspect readings against the mmol/L columns' 122, so whatever is
   decided moves far more data in one direction than the other.
3. **Does `Baseline FBG (mmol/L or mg/dL)` get mapped**, and if so to which
   column -- or is the answer that a template should never offer an ambiguous
   header, making this a source fix rather than a synonym one? Note the
   latest-template rule likely settles this as "leave it": the only tracker
   carrying it is from 2018.
4. **Is a per-column unit check worth adding generally?** The same shape could
   apply to HbA1c and other unit-bearing columns; deciding that here avoids
   solving it once per column later.

Note that a unit rule cannot be decided from R's behaviour -- R has the same
headers and the same synonym source -- so this is a Python-forward decision,
not an R/Python divergence question, and it does not block [ticket
12](12-retire-r-workspace.md).

## Resolution (session-2026-08-17)

### Decision

**The advisor's reply did not confirm this ticket's central premise, and the
decision was rebuilt on what it did establish.** The ticket asked whether a
reading below 30 mg/dL is impossible; the answer came back as *analytical*
limits -- mg/dL readable from ~2-5 to ~720-800, mmol/L from ~0.1-0.3 to ~40-45
-- which makes 5-30 mg/dL **possible but severe, not impossible**. The
"9,264 readings with the unit mixed up" figure is therefore not, on the
advisor's word, clearly wrong-unit. What he authorised is narrower and
conditional: *"if it is clearly a wrong unit mixed up, then correct it"*, plus
*"advise the data input staff"*. Defining "clearly" was the real decision.

**"Clearly" was settled by measurement, not by a threshold.** Across 372
file-column groups and 110,007 readings, the confusion is overwhelmingly *per
column* rather than per row, and it clusters by clinic:

| share of the column below 30 mg/dL | groups | reading |
|---|---|---|
| >=90% | 29 | the column is mmol under an mg/dL header |
| 50-90% | 7 | per-patient mixing, all baseline at two clinics |
| 10-50% | 10 | mostly one clinic (Preah Kossamak) |
| <10% | 26 | scattered single rows |
| none | 300 | clean |

`2025_Kantha Bopha II`'s updated FBG is 99.8% of 951 readings below 30, which
cannot be a run of severe hypoglycaemia. A single low reading in an otherwise
ordinary column is the opposite case: a genuine severe hypo and a mis-entered
unit are indistinguishable, and converting one would multiply the clinically
most important reading in the file by 18 and hide it.

**Implemented (option B, chosen by the user):**

- `src/a4d/clean/glucose.py`, new. `resolve_glucose_units` runs as step 5.8 of
  patient cleaning -- before range validation so the limits judge corrected
  values, and before the existing mg/mmol cross-derivation so it sees a column
  whose unit matches its name.
- **Column-level correction.** Where a column has >=10 readings and >=90% sit
  below 30 mg/dL, its values move to the mmol sibling (never overwriting a
  reading already recorded there) and the mg column is rescaled by 18. Reported
  as `glucose_unit_swapped` **once per column, not once per row** -- the defect
  is the header, so the source fix is file-level. **29 columns across 21 files.**
- **Row-level flagging, no conversion.** A sub-30 reading in a column that was
  not swapped is reported as `glucose_unit_suspect` and left exactly as
  recorded. **5,673 rows across 34 files.** This is where the 50-90% and 10-50%
  bands land, per the user's instruction that the ambiguous middle goes with
  the flagged side.
- **Zero is not a reading.** It sits below the analytical floor of both units,
  so it becomes null rather than being read as profound hypoglycaemia.
- **Analytical limits enforced.** `cut_numeric_value` now bounds all four FBG
  columns at the permissive end of the advisor's ranges (mg/dL 2-800, mmol/L
  0.1-45). This replaces an inherited 0-150 mmol/L bound from R's
  `script2_process_patient_data.R` -- more than three times his ceiling -- and
  covers the three columns that had **no bound at all**. **832 readings
  rejected**, including 383 above the mg/dL ceiling (max 2,013) that nobody had
  ever looked for: the original analysis only examined the low end.

### Numbers (real 254-tracker run, comparison `2026-08-16T231826Z`)

Every FBG value now sits inside the advisor's limits: mg max 800.0 (was 2,013),
mmol max 44.9 (was 600). Medians moved as expected -- baseline mg 190 -> 216
(the mmol readings that were dragging it down have left), baseline mmol
19.3 -> 15.7 (it gained ~1,700 lower readings from the swap). Both remain
consistent with the presentation hyperglycaemia the advisor confirmed.

### Rejected

- **Converting every sub-30 reading** (~12,000). The advisor's limits do not
  make them impossible, and it would silently rewrite real severe hypos.
- **Converting nothing but the analytically impossible.** Defensible, but
  knowingly leaves 29 wholly mislabelled columns wrong in the data.
- **A row-level record for a swapped column.** The same finding repeated
  hundreds of times; the workbook fix is one header.
- **Stretching the new comparison classifier to cover R-null cells** -- see
  below. Ticket 31's precedent: a shape-matching label is not a decision.

### Evidence

**Executed** throughout: the file-column distribution, the 5-30 vs 2-5 vs 0
banding, the mg upper-limit breach, and every before/after figure come from
real pipeline and comparison runs over the 254-tracker set on the drive, not
from unit tests. The advisor's limits are **read** -- an expert statement, not
something this repo can verify -- which is what `evidence: read` records.

**One inconsistency in the reply, noted and immaterial:** he says readings
below 0.1 mmol/L are possible while his own table puts the analytical floor at
0.1-0.3. No reading in the dataset sits in that gap.

**Tense:** all figures describe behaviour after this session's commit.

### Questions 3 and 4 of the ticket's own list

- **`Baseline FBG (mmol/L or mg/dL)` stays unmapped.** The only tracker
  carrying it is from 2018, and the latest-template rule settles it: a template
  should never offer the reader a choice of unit, so this is a source defect to
  record, not a synonym to add.
- **A general per-column unit check was not built.** The mechanism here is
  specific to a column pair that exists in both units; HbA1c has no such pair.
  Revisit only if a second column turns out to need it.

### Not fixed, deliberately

The correction is a deliberate divergence from R, which has no unit resolution,
so patient cleaned-stage mismatches rose 98,274 -> 114,509, entirely in the four
FBG columns. `python_glucose_unit_corrected`
(`PATIENT_GLUCOSE_UNIT_CLASSIFIERS`) explains 11,189 of them on the three shapes
the correction provably produces: an exact 18x ratio either way, a null against
R's literal 0, and Python's sentinel against a reading outside the analytical
range.

It deliberately never fires on an R-null cell, which leaves **2,842 cells on
`fbg_updated_mmol` unclassified** -- cleaned-stage unclassified 6,587 -> 9,427.
Measured, **2,794 of those 2,842 (98.3%) are in files whose column was
swapped**, so the population is understood: the swap populated a column R never
had. It is not classified because the per-cell classifier has no file context,
and a blanket R-null rule would also swallow the ~193 cells on that column that
predate this change -- exactly the labelling-without-deciding this map forbids.
Spawned as [ticket 44](44-triage-cleaned-fbg-r-null-residual.md).
