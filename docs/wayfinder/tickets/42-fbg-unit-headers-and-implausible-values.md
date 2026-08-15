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
- **The mmol-mapped columns hold physiologically implausible values.** Normal
  fasting glucose is ~4-7 mmol/L and severe DKA rarely exceeds ~50:

  | Header | Values | Median | Max | > 35 mmol/L |
  |---|---|---|---|---|
  | `Baseline FBG (mmol/L)` | 2,787 | 21.8 | 71.5 | 386 (13.9%) |
  | `Baseline FBG* mmol/L` | 1,293 | 16.6 | 81.9 | 129 (10.0%) |
  | `Baseline FBG mmol/L` | 449 | 11.1 | 53.8 | 40 (8.9%) |
  | `Updated FBG mmol/L` | 11,108 | 8.0 | 516.8 | 66 (0.6%) |

  The baseline columns are 10-14% implausible where the updated ones are 0.6%,
  which points at mixed units *within* a single column rather than scattered
  typos.

Nothing in `reference_data/synonyms/synonyms_patient.yaml` was changed while
closing ticket 30: resolving a unit needs clinical input, not a code decision.

## Question

The user will put the clinical half to A4D's medical advisor. This ticket
carries the decision once that answer is in.

1. **What ceiling is physiologically credible for FBG in mmol/L**, and is a
   *baseline* median of 21.8 plausible for newly-diagnosed T1D patients (it may
   genuinely be high at diagnosis) or evidence of mixed units?
2. **What should the pipeline do with an out-of-range value** -- flag it via
   `ErrorCollector` and keep it, convert it on the assumption it is mg/dL
   (`mmol/L = mg/dL / 18.0182`), or sentinel it? Converting is a data-altering
   guess and should not be done on a heuristic alone.
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
