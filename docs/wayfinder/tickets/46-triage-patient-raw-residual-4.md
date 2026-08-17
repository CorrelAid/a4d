---
id: 46
title: Triage the residual patient raw-stage column mismatches (round 4)
labels: [wayfinder:task]
status: closed
blocked_by: [45]
assignee: session-2026-08-17d
claimed_at: 2026-08-17T22:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 43
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
3)](43-triage-patient-raw-residual-3.md), closed, which took patient
raw-stage unclassified from 1,879 to **1,409** by settling two causes: a
float-to-string rounding artifact reaching four columns the normalize list
could not name (434 rows, comparison-tool fix), and 24 invented rows in
`2024_Vietnam National Children`'s `Jul24` that Python was reading from a
bare list of patient IDs below the data block (pipeline fix).

Blocked on [Give the patient comparison an ordinal row key](45-patient-row-alignment-duplicate-keys.md)
deliberately: 808 of the 1,409 are join fan-out in three duplicate-key files,
so triaging the tail before that lands would mean characterizing noise. What
this ticket inherits is the **~600 rows outside those three files**.

**Ticket 45 is now closed, and the inherited residual is exactly 601** --
measured on baseline run `output/comparison/2026-08-17T202809Z`, which is the
run to triage against (not `2026-08-17T192144Z`, whose numbers this ticket's
question section quotes). All three duplicate-key files now hold **zero**
unclassified raw mismatches. Patient rows are now aligned on `patient_id` +
`sheet_name` with a content-matched tie-break inside duplicate groups, so a
remaining mismatch is between two rows that genuinely describe the same patient
on the same monthly sheet.

Also rests on the map's standing scoping rule that the current tracker
template is the golden rule, and on ticket 43's own warning that early
sampling of these columns predates three extraction changes (ticket 30's
blank-header recovery, ticket 31's duplicate-source-column merge, ticket 43's
phantom-row fix) -- so re-measure rather than trusting any characterization
written before baseline run `output/comparison/2026-08-17T192144Z`.

## Question

Triage what remains once ticket 45 has realigned the duplicate-key files.
Shapes ticket 43 measured but did not close, all against the pre-45 baseline:

- **`hba1c_updated` / `fbg_updated_mg` interior space, 86 rows -- Python
  already verified right, cause not yet named.** All 86 are in `2017_Yangon
  Children's Hospital`, R holding `8.8(20.9.16)` where Python holds `8.8
  (20.9.16)`. The source cell (`Feb17`, row 62, column 12) was read directly
  and **contains the space**, so Python reproduces the workbook exactly and R
  drops it. Ticket 43 searched R's raw path for the mechanism and did not
  find it (`sanitize_str` touches only column names and validator lookups;
  the multiline-header merge touches only headers; the wide-format splitter
  is product-side). Either locate it or wire a classifier that says what was
  verified -- that Python matches source -- without claiming a mechanism.
- **`insulin_regimen` (234).** Ticket 43 did not reach this. 194 rows are
  ticket 30's source-verified blank-header recovery in `2021_Kantha Bopha`;
  the other ~40 share the shape but were never verified, which is exactly why
  ticket 31 refused to wire the column to `r_extraction_gap` wholesale.
  Verify the unverified ones against source, or split the classifier so it
  fires only where the evidence reaches.
- **`observations` (55), `observations_category` (42), `status` (43),
  `last_clinic_visit_date` (82), `fbg_updated_date` (74), `hba1c_updated`
  (87)** and ~40 more columns under 45 rows each. Expect a large share of the
  date-column entries to be the duplicate-key fan-out and to disappear with
  ticket 45 -- re-measure first, then triage what survives.
- **Cheap representation shapes worth one decision each**: R `FALSE` vs
  Python `False` (20 rows, `clinic_visit` and `remote_followup`); R `null` vs
  Python `""` (25 rows, mostly `insulin_injections`); a trailing space inside
  a merged sub-value (`"Normal ,Insulin"` vs `"Normal,Insulin"`), which
  ticket 31's merge strips and R's `unite` does not -- decide whether to
  extend `normalize_whitespace_column` to interior whitespace or classify.

Split further rather than leaving this open-ended if it does not converge.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining
a difference and naming a cause is not enough -- each needs an explicit
verdict on whether Python is right, with the evidence. Where Python is losing
information the source carried, fix the pipeline. Where the source workbook
itself is wrong, that is a legitimate conclusion and a finding for [ticket
40](40-source-defect-findings-report.md). A cause genuinely undecidable on
the available evidence is recorded as an open question, not closed with a
label.

## Resolution

**Decision.** Four of the residual's causes are settled; the rest split into
[round 5](49-triage-patient-raw-residual-5.md) and, separately, into a
newly-found Python data loss, [ticket
48](48-putrajaya-screening-columns-lost.md). Patient raw-stage unclassified
fell **601 -> 278 (-54%)**, cleaned **8,383 -> 8,148**. The new baseline run
is `output/comparison/2026-08-17T212151Z`.

1. **A number typed into a date-formatted cell -- a Python bug, fixed.**
   `read_patient_rows` (`src/a4d/extract/patient.py`) now converts a datetime
   before 1903 back to its Excel serial. Excel's epoch is 1899-12-30, so such
   a "date" is a small number that inherited a date format from a neighbouring
   cell; readxl reads the number because it guesses the column's type, while
   openpyxl honours each cell's own format and hands back a datetime, which
   the numeric conversion then rejected into the 999999 sentinel. 38 raw cells
   across 5 files; **in production this was destroying 24 real systolic
   readings** (`2025_Hat Yai` TH_HY035 and `2025_YGH` MM_YC023_YG, one per
   monthly sheet). Verdict: Python was wrong, R was right by accident.
2. **R drops a whitespace-only rich-text run -- classifier
   `r_drops_richtext_space` (89 rows).** Ticket 43 left this "verified but
   unexplained"; the mechanism was found in the workbooks' own XML. Where a
   cell carries mixed formatting, xlsx stores it as a sequence of runs, and a
   space between two differently-formatted fragments becomes a run holding
   only that space (`<t xml:space="preserve"> </t>`). openpyxl concatenates
   every run; readxl drops the whitespace-only one. Verified in two unrelated
   workbooks -- `2017_Yangon` (`8.8 (20.9.16)`, three runs) and `2022_Mahosot`
   (`Unable to contact`, the middle run recoloured). The same text also exists
   as a plain shared string elsewhere in the same column, which is why only
   some cells diverge. Python reproduces the workbook; R loses a character.
3. **Python trims each sub-value before a merge -- classifier
   `python_trims_merged_subvalue` (2 rows).** The opposite direction of the
   same shape: ticket 31's merge strips each fragment, `tidyr::unite` does
   not, so a source cell with trailing padding reaches R as `Normal ,Insulin`.
   Direction-scoped so the two classifiers cannot shadow each other.
4. **`insulin_regimen` in `2021_Kantha Bopha` -- `r_extraction_gap` (194
   rows).** Re-verified at source rather than taken from ticket 30: `Mar21`
   column Q has *both* header rows empty and holds `Self-mixed BD`. R has no
   header, so it drops the column; Python recovers the name from the sibling
   sheets that label it. All 194 of the column's residual sit in that one
   verified file, which is what ticket 31's refusal was waiting for.

**Because.** Each cause was taken to a verdict on which pipeline is right, not
to a label. The one that turned out to be a Python defect was fixed in the
pipeline; the three where Python reproduces the source became classifiers.

**Rejected.**

- *Recovering every date-typed cell in a numeric column.* This would also
  convert `2023_Chiang Mai`'s `t1d_diagnosis_age` (Excel serial 20668,
  1956-08-01, against a D.O.B. of 2009) into a bogus age of 20668 -- exactly
  what R does. Only the impossible range is recovered; a date that could
  plausibly have been typed stays a date, which is the cause the product arm
  already settled as `openpyxl_date_typed_stray_cell`.
- *A cell-count or magnitude threshold* ("recover if the number looks like a
  blood pressure"). A guess about the column's semantics; the Excel-epoch
  argument is a fact about the file format.
- *Extending `normalize_whitespace_column` to interior whitespace.* It would
  have silenced both space causes with one rule and hidden the fact that they
  run in opposite directions and have different mechanisms -- and it would
  have been applied before the mechanism was known.
- *Wiring `r_extraction_gap` across every R-null column at once.* ~125 of the
  remaining 278 share that shape, but only `insulin_regimen`'s file has been
  source-verified. That is ticket 31's precedent, kept.
- *Fixing the Putrajaya screening-column loss in the same session.* It is a
  second, unrelated header-handling bug needing its own sweep across all 254
  trackers; chasing it here would have been the sprawl the map's rule forbids.

**Evidence: executed.** The four causes were measured against the real
248-tracker drive data and verified at source: the Hat Yai systolic cell read
directly from `Annual!H` (`datetime(1900, 4, 29)`, number format
`dd-mmm-yyyy`, diastolic 74 beside it); the rich-text runs read out of
`xl/sharedStrings.xml` in both workbooks; the Kantha Bopha blank header read
from `Mar21` rows 85-87. The pipeline was re-run over all 254 trackers
(`a4d run patient --force`) and the comparison re-run twice, so every count
here is a measured before/after, not a projection. R's `sanitize_str` was
re-read to confirm independently of ticket 43 that it touches only column
names and validator lookups. Full suite 735 passed, ruff and `ty check src/`
clean.

**Tense.** Every count above describes current behaviour after this session's
changes. The 999999 systolic readings describe production output *before* the
fix; the drive's `output_python` and BigQuery's contents now differ until the
next production run.

## Addendum: what this leaves open

- The 278 remaining raw-stage cells: [ticket
  49](49-triage-patient-raw-residual-5.md).
- The Putrajaya merged-header data loss: [ticket
  48](48-putrajaya-screening-columns-lost.md).
- **Product's own sub-1903 cells were measured but deliberately not touched**:
  18 `product_units_received` and 2 `product_entry_date` cells carry the same
  impossible-date shape (e.g. `1900-03-15`, i.e. 74 units). They currently
  land on `openpyxl_date_typed_stray_cell`, whose verdict is "Python is
  faithful" -- which this session's evidence says is wrong for that sub-range.
  Product raw is separate extraction code and separate, already-closed triage
  scope, so it belongs to [ticket
  32](32-audit-classifiers-against-decision-bar.md)'s re-audit rather than
  here.
- Three new source-defect findings were added to [ticket
  40](40-source-defect-findings-report.md).
