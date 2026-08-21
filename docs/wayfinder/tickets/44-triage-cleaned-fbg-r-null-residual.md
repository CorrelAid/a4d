---
id: 44
title: Classify the cleaned-stage FBG cells where R has nothing and Python has a corrected reading
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: null
claimed_at: 2026-08-21
resolution: decided
evidence: executed
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

## Resolution

**Decision.** Option 1, as the user chose -- but measurement moved where it
pays off, and the population turned out to be one mechanism rather than the
two the ticket describes.

The cleaned-stage `fbg_updated_mmol` residual is **2,935 cells, 99.3% of the
whole cleaned-stage unclassified population** (the ticket's 2,842 was measured
on 2026-08-16 and had drifted). Every one of them -- **not one exception** --
sits beside an `fbg_updated_mg` cell on the same row that is *itself* a
mismatch with an already-named cause. Neither pipeline reads the mmol column
from the workbook: both derive it from the mg cell (`convert_glucose_units`,
clean/patient.py; `fix_fbg`'s `fbg/18` in R). So the mmol divergence is the
arithmetic shadow of a decision already taken next door, in three shapes:

| n | shape | mg sibling's cause |
|---|---|---|
| 2,797 | R null, Python has the reading | `python_glucose_unit_corrected` / `r_fbg_text_category_invention` |
| 110 | **Python null, R has a value** | `r_fbg_text_category_invention` (80), `python_glucose_unit_corrected` (30) |
| 28 | R null, Python has the reading, no swap in the file | `python_recovers_glucose_r_rejected` |

The 110 is not in the ticket at all -- it is the *opposite* direction, and it
is where R does the damage. Every one is exactly `mg_r / 18`: R divides a
number `fix_fbg` manufactured out of text (140 from "Lost follow up") or one
far beyond the analytical ceiling (2013 mg/dL) and publishes the quotient as a
measurement. `2023_CDA` gets **111.8 mmol/L** that way -- above the level A4D's
medical advisor called outright impossible. Python is the correct side in all
three shapes.

Two changes, both following the existing precedent that `compare_cells`
precomputes a fact onto `CellMismatch` and the classifier judges it
(`row_order_candidate`, `row_has_bare_year_date`):

1. **`mg_sibling`** carries the row's `(r, py)` mg pair to the mmol cell.
   `mmol_derived_from_mg_sibling` (`PATIENT_GLUCOSE_CASCADE_CLASSIFIERS`)
   fires only when the mg sibling itself disagrees **and** each side's mmol
   value is either absent or exactly its own mg cell over 18. That arithmetic
   identity is the bound: an mmol cell carrying a reading its mg sibling
   cannot account for is left alone.
2. **`column_unit_swapped`** carries the file-level fact -- read back from the
   run's own `glucose_unit_swapped` error records via
   `load_glucose_unit_swaps`, keyed through each frame's `file_name` column
   rather than by string surgery on parquet names, so a pipeline threshold
   change reaches the comparison without a second edit.
   `_is_python_glucose_unit_corrected` now picks its analytical bound on that
   evidence instead of on whether the column's name ends `_mg`.

**Measured against the real 254-tracker drive data** (`output/comparison/
2026-08-21T215325Z` vs the `...T212441Z` baseline):

- `fbg_updated_mmol` unclassified **2,935 -> 2**
- `fbg_baseline_mg` unclassified **6 -> 0** -- change 2 closes the standing fog
  patch *"Whether a column-level finding can be classified at all"*, the six
  2020 Kantha Bopha cells round 10 could only write out in prose
- **cleaned-stage unclassified overall: 2,955 -> 16**
- `per_column` counts are **byte-identical**, and the patient raw, product raw
  and product cleaned snapshots are identical -- nothing was suppressed, only
  named
- Full suite 905 passed / 1 skipped; ruff and `ty check src/` clean

**The remaining 16 are all already owned by fog, and none is a glucose
question**: 11 `insulin_subtype` + 2 `remote_followup` are the standing
null-vs-`Undefined` patch (round 10 counted these 13 exactly), 1 `bmi_date` is
ticket 39's slash-separated-month patch, and the last 2 `fbg_updated_mmol` are
R-null against Python's `999999` -- **neither side published a reading**, so
this is the numeric-absence fog patch (`999999` making the same false claim
`9999-09-09` made on dates), not a cascade. The classifier declines them
deliberately.

**Because.** The ticket framed the obstacle as file-level and the answer as a
choice about error bounds. Scanning the whole population first -- per the map's
own standing preference -- showed the decisive fact is row-level and stronger
than any file-level rule: the mg sibling's value *is* the evidence, so no error
bound has to be accepted at all. Option 1's file-level context still earned its
place, just on the six cells the fog patch named rather than on the 2,794.

**Rejected.**

- **Option 2** (narrow the cell rule, accept a stated error bound): the exact
  shape ticket 42, [ticket 31](31-triage-patient-raw-residual-2.md) and round
  10 each declined. Measurement priced it honestly -- the bound is 28 cells,
  not the ticket's estimated ~193 -- and those 28 turn out to be a *real,
  separate* mechanism (2018 CDA's `148 mg/dl   (Mar-18)` cells), so option 2
  would have mislabelled the one population that had never been looked at.
- **Option 3** (triage the 28 first, then judge option 2): its measuring half
  was done and is what produced the answer; its conclusion -- that a measured
  bound licenses option 2 -- does not follow, since a bound prices a rule it
  does not make correct.
- **Reordering the registry** so `PATIENT_FBG_TEXT_CLASSIFIERS` precedes the
  glucose ones, to stop the widened mmol bound claiming five
  `r_fbg_text_category_invention` cells (140 exceeds 45): rejected because
  `r_unit_suffix_not_stripped` rides in the same registry and is broad enough
  to steal the 28 cells' mg sibling from `python_recovers_glucose_r_rejected`.
  Guarding the range test against R's manufactured constants instead is local
  and says the true thing -- a number `fix_fbg` invented is not a reading, so
  no range has anything to say about it. Caught by re-running: the first pass
  moved those 5 cells and the snapshot diff showed it.
- **A classifier keyed on "the mg sibling is a mismatch" alone**, without the
  ÷18 identity: it would swallow any genuine mmol divergence that happened to
  sit beside a diverging mg cell, which is precisely the over-claiming the
  standing bar forbids.

**Evidence.** **Executed** throughout: the population split, the sibling
pairing and the "no exceptions" claim are duckdb queries over the run's own
`cell_mismatches` sheet and `table_errors.parquet`; the before/after numbers
are two full `just compare-outputs` runs against the real drive data, compared
snapshot-to-snapshot. R's `fix_fbg` behaviour and the analytical limits are
**read** -- inherited from rounds 8/10 and ticket 42, not re-derived here.

**Tense.** All numbers describe current behaviour after this session's changes,
except the baseline column of each before/after pair.

**Spawned nothing.** The residual is fully absorbed by fog patches that already
exist.
