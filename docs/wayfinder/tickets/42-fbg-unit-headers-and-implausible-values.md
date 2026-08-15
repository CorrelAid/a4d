---
id: 42
title: Decide how FBG unit headers are resolved, and what to do about physiologically implausible mmol values
labels: [wayfinder:grilling]
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
