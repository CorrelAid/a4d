---
id: 44
title: Classify the cleaned-stage FBG cells where R has nothing and Python has a corrected reading
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 42
---

## Premise

Rests on [Decide how FBG unit headers are resolved, and what to do about
physiologically implausible mmol values](42-fbg-unit-headers-and-implausible-values.md),
closed: on A4D's medical advisor's answer of 2026-08-17, the pipeline now
resolves glucose readings recorded under the wrong unit's header
(`src/a4d/clean/glucose.py`). Where a whole column labelled mg/dL holds mmol/L
readings, its values move to the mmol sibling and the mg column is rescaled by
18 -- 29 columns across 21 files. R has no unit resolution at all, so every
correction is a deliberate divergence.

`python_glucose_unit_corrected` (`PATIENT_GLUCOSE_UNIT_CLASSIFIERS`,
`src/a4d/migration/compare.py`) explains 11,189 of them, on the three shapes the
correction provably produces. It deliberately does **not** fire where R is null,
because that rule would also swallow a pre-existing population on the same
column that has nothing to do with this change.

Also rests on the map's assumption in force about which baseline-FBG copy Python
keeps (from [ticket 29](29-triage-patient-cleaned-residual.md)) -- R's Patient
List join suffixes both sides and loses the unsuffixed column, which is the
other reason an FBG cell can be R-null. Read it before measuring; the two
populations sit on adjacent columns and are easy to conflate.

If ticket 42's correction were reverted, this ticket would be void rather than
in need of rewriting.

## Question

Classify or decide the **2,842 cleaned-stage `fbg_updated_mmol` cells** where R
is null and Python has a value (baseline run
`output/comparison/2026-08-16T231826Z`; cleaned-stage unclassified is 9,427,
of which this is the dominant share).

What is already measured, and should not be re-derived:

- **2,794 of the 2,842 (98.3%) are in files whose column was swapped** by
  ticket 42's correction, so the mechanism is understood: Python populated a
  column R never had. The largest are `2025_Kantha Bopha II` (953),
  `2022_Kantha Bopha` (648), `2019_Vietnam National Children` (430),
  `2021_Kantha Bopha` (419).
- **48 sit in files with no swap at all**, spread thin (`2018_CDA` 26,
  `2024_Vietnam National Children` 18, then singletons). These are a different
  question and have never been looked at.
- The column carried only 193 mismatches in total before ticket 42, so the
  population that predates the correction is small and bounded.

The real question is how to record the 2,794 without labelling the rest. The
obstacle is structural: `classify` sees one cell at a time and has no file
context, so it cannot ask "was this file's column swapped?". Options worth
weighing rather than assuming:

1. Give the classifier the file-level context it needs -- e.g. have the
   comparison read the run's own `glucose_unit_swapped` error records, or have
   `compare_cells` pass the file through. Most faithful, most invasive.
2. Narrow the cell-level rule enough to be safe on its own terms (mmol column,
   R null, Python present and within the analytical range) and accept a stated
   error bound of at most ~193 cells.
3. Decide the 48 no-swap cells individually against source, then judge whether
   option 2's bound is acceptable once the genuinely unrelated population is
   known.

Option 3 first looks cheapest -- 48 cells is a morning, and it turns the error
bound from an estimate into a measured number.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: a classifier
that fires on a shape it has not established is not a decision. Ticket 42
declined to stretch this exact rule for this exact reason, and [ticket
31](31-triage-patient-raw-residual-2.md) declined the same shape on
`insulin_regimen`; both are worth reading before choosing option 2.
