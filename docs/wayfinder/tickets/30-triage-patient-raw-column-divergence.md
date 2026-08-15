---
id: 30
title: Triage the patient pipeline's raw-stage column-existence divergence
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-15
claimed_at: 2026-08-15T10:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 26
---

## Premise

Rests on [Triage the product pipeline's column-existence and dtype
divergence](26-triage-product-column-divergence.md), closed: that ticket
added a `column_divergence` sheet to every stage's comparison report and
triaged product's (both stages) and patient's cleaned-stage divergences
fully — patient cleaned stage is essentially clean (one single-file dtype
mismatch). Patient's raw stage did not converge and was split off here
rather than forced.

On the current 248-tracker `output_r`/`output_python` pair
(`just compare-outputs` against the USB drive), patient raw stage's
`column_divergence` sheet has 18,783 rows across 245 common files —
two large, distinct patterns, neither yet root-caused:

- Hundreds of uniquely-numbered only-in-R columns (`na`, `na1`, `na2`, ...
  up to `na10064` in one file alone), which look like R's own
  deduplication scheme for blank or duplicate Excel header cells (R
  appends a numeric suffix to disambiguate repeated/empty column names on
  read) rather than anything Python's extraction produces.
- A large only-in-Python set of literal, unmapped source header text
  (`"Phone Number"`, `"Date"`, `"Home Visit"`, `"Home Visit 1"`, `"BGM
  A4D"`, etc.) — apparent raw passthrough of Excel headers that didn't
  match any entry in `reference_data/synonyms/synonyms_patient.yaml`,
  present in Python's raw output but not R's.

Unlike product raw's `product_returned_by`/`product_units_returned`
divergence (ticket 26, confirmed a genuine R extraction gap via direct
source-Excel spot check), neither pattern here has been spot-checked
against a real source file yet, and it isn't yet known whether they're
related to each other (e.g. R's blank-header dedup swallowing a header
Python matches to real text) or independent.

## Question

Root-cause both patterns against real source Excel and R's actual
extraction code (`r-archive/R/read_patient_data.R` or equivalent), the same
way ticket 26 did for product's raw-stage gap: for the `na`/`naN` columns,
confirm what R is actually doing on read (blank-header dedup, a fixed-width
header-row assumption, something else) and whether Python's raw extraction
is silently dropping equivalent columns or correctly has no equivalent to
drop; for the only-in-Python header-text columns, confirm whether these are
genuinely un-synonym-mapped columns Python passes through by design (raw
stage isn't schema-enforced) while R drops anything it can't map, or
whether R is failing to extract real data the same way it did for
product's "returned" columns. Decide, per file/column-family rather than
row-by-row given the volume: genuine content gap (needs a synonym-file
addition or an R-side note), or an expected raw-stage passthrough
difference (needs documenting only, per ticket 26's precedent for the
harmless cases).


## Standing bar (added 2026-08-12g, applies to this ticket)

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Noting
"Python has A where R has B" and adding a classifier is not a decision in
favour of A. Where Python turns out to be wrong or to be losing information
the source file carried, fix the pipeline rather than labelling the symptom
— see [ticket 27](27-triage-patient-raw-residual.md), where exactly that
turned a labelling job into a real extraction fix. A cause genuinely
undecidable on available evidence is recorded as an open question, not
closed with a label.

## Premise update (session-2026-08-14, ticket 37's session)

The tracker set is now 254 files and the frozen R baseline was renamed to
match a bulk `06 ... -> 2026_...` rename by the data analyst (see [ticket
37's addendum](37-triage-patient-cleaned-residual-2.md)). This ticket's
"18,783 rows across 245 common files" is measured against the old 248-file
set; the current figure is **18,235 rows across 245 files**
(`output/comparison/2026-08-14T200342Z`). The two patterns the Question
names are unchanged -- only the counts moved.

## Resolution (session-2026-08-15)

### Decision

All 18,235 patient raw-stage `column_divergence` rows are accounted for. Two
structural causes explain 95%, both R-side artifacts with no Python defect
behind them; the residual is already-decided R defects plus columns that died
out before the current template. **One real Python data loss was found on the
way** -- headerless columns carrying data -- and it is now detected and
reported rather than silent.

The two patterns the Question treats as possibly independent are one
phenomenon seen from two sides: the same source column mapped by one pipeline
and passed through under its raw name by the other. Both pipelines keep
unmapped columns (Python's `ColumnMapper` runs non-strict,
`reference/synonyms.py:185-217`; R's `harmonize_patient_data_columns` only
warns), so a mapping gap on either side shows up as a column "only in" the
other.

Breakdown, measured against `output/comparison/2026-08-14T204031Z`:

| Rows | Cause | Verdict |
|---|---|---|
| 17,132 | `r_blank_header_artifact` | R artifact; Python correct |
| 154 | `name_sanitization_only` | Representation only; both sides carry it |
| 703 | Columns last seen <= 2024 | Out of scope (latest-template rule) |
| 246 | R mapping gaps + new 2026 fields | R defects already decided, plus [ticket 41](41-decide-2026-new-patient-list-columns.md) |

**`r_blank_header_artifact` (17,132 rows, 94%)** -- traced in R's own code and
confirmed by running R. `script1_helper_read_patient_data.R:113` calls
`make.names(header_cols, unique = TRUE)`; executed,
`make.names(c("Patient ID", NA, NA), unique = TRUE)` returns
`"Patient.ID" "NA." "NA..1"`, and `is.na()` is `FALSE` on all three. So line
116's `df_patient[, !is.na(colnames(df_patient))]` -- commented "delete
columns without a header" -- never fires, and line 131's `"NA" %in% names(...)`
misses too because the name is `"NA."`. `sanitize_str` then strips the dot,
yielding `na`, `na1`, ... `na10064`. Python drops blank-header columns in
`filter_valid_columns`, so it correctly has no equivalent.

Measured, not assumed: across all 245 R raw parquets, 16,762 `na*` columns
exist, only 199 hold any value, and 189 of those are the trackers' unlabelled
row counter (1, 2, 3 ...). Only 10 hold real text.

**`name_sanitization_only` (154 rows)** -- R stores the sanitized name where
Python's raw stage keeps the literal source header
(`instantmeterreceiveddate` vs `INSTANT Meter Received Date`). Both sides have
the column.

**The 246 live rows** are: `insulin_total_units` (85, R's insulin-dedup grep --
[ticket 29](29-triage-patient-cleaned-residual.md)), `recruitment_date` (59,
paired exactly with R's `xmlspacepreservedateofrecruitmentmmmyyyy` -- R's
header text carries an `xml:space="preserve"` XML artifact so R cannot map it),
`edu_occ`/`edu_occ_updated` (4, [ticket 37](37-triage-patient-cleaned-residual-2.md)),
the 2026 template's Thai-bilingual complication-screening/blood-pressure
headers (R fails to map them, Python maps them correctly), and the five new
2026 Patient List fields split into [ticket 41](41-decide-2026-new-patient-list-columns.md).

### The real finding: headerless columns carrying data

`filter_valid_columns` drops any column whose header cell is blank. Verified
against the source workbook: in `2021_Kantha Bopha Hospital A4D Tracker.xlsx`
sheets `Mar21` and `Apr21`, column Q holds real insulin-regimen values from row
87 down and its header cell (row 85) is **empty**, where the same column in
`May21` reads "Insulin Regime". Python therefore has `insulin_regimen` null for
all 194 rows. R keeps the values but only as junk-named `na1`, so R's
`insulin_regimen` is null too -- **both pipelines lose it**, and Python
irrecoverably.

A sweep of all 254 trackers (executed) found **26 files, 4,572 values** in
headerless columns. Of those, 1,150 duplicate the column to their left, and a
further large share are the 2022 template's hidden merged-cell insulin column:
for `2022_Kantha Bopha`, measured across all 12 month sheets, the hidden column
never holds a value where the visible one is empty (0 of 1,932), agrees on
1,382 rows, and where it differs the **visible** column is richer
("Basal-bolus MDI (AN)" vs "Basal-Bolus"). R deletes this same column
deliberately (`script1_helper_read_patient_data.R:118-125`). Python losing it
is correct.

`find_dropped_data_columns` (`src/a4d/extract/patient.py`) now reports each
site under the new `blank_header_with_data` error code, naming sheet, column
letter and value count. All-numeric columns are excluded -- measured, that is
the trackers' own row counter (189 of the 199 populated ones). This makes the
defect visible in the logs/errors table instead of silent, and feeds the
source-correction report split into [ticket 40](40-source-defect-findings-report.md).

**And the data is recovered where the workbook itself settles the answer.**
`recover_blank_headers` names a headerless data column from the month sheets
that *do* label it -- a tracker's sheets share one layout, so the sibling
sheets are evidence, not inference. It abstains unless the answer is
unambiguous: the siblings must agree (2021 Putrajaya offers three candidate
names at one position, so those 12 values are left alone), a position no
sibling names is untouched (which is what puts the 2022 merged-cell column out
of reach), and a name the sheet already uses is refused -- 2017 Mahosot's
column S would otherwise collide with the `Estimated Testing Strips per month`
already sitting at column T, so its 97 values stay reported rather than
guessed.

Measured over the full 254-tracker set: **17 sheet-sites across 5 trackers
recovered, 201 sites left reported**. Three of the five recovered headers map
to real schema columns -- `Insulin Regime` -> `insulin_regimen` (the 194
Kantha Bopha rows, verified: that file's `insulin_regimen` goes 1,273 -> 1,467
non-null), `Patient Observations` -> `observations` (7), `Clinic Visit` ->
`clinic_visit` (5). The other two (`foot`, `eye`, 13 values) have no synonym
entry and remain raw-stage passthrough, dropped at cleaning as before.

### A tracker that changes shape mid-year is now flagged

Set by the user this session: **a tracker is one workbook for one clinic-year
and should not change mid-year under normal circumstances; where it does, that
should be flagged.** `find_layout_changes` compares every month sheet's headers
position by position and reports each position whose *canonical* column is not
stable, under the new `tracker_layout_changed` error code. Positions where the
spelling varies but the canonical column does not (75 of them) log at info
only, since the synonym file already handles those.

Verified against the real set: **37 trackers, 284 positions**. The output makes
the cascade legible -- `2018_CDA` flags columns P, Q, R and S in sequence,
which is one missing column in `Apr18` shifting everything right of it.

This is the mechanism behind two of the defect classes [ticket
40](40-source-defect-findings-report.md) will report, and it found a live one:
`2020_CDA`'s Jan-May baseline FBG is currently dropped and its updated FBG
currently filed under the wrong unit, both from a single bad header edit.

`collect_sheet_layouts` resolves every sheet's start row and headers once per
tracker, since recovery needs all sheets' headers before any one sheet is
final. Its results are handed back to `extract_patient_data` rather than
recomputed, which matters because `find_data_start_row` is the hot spot
[ticket 10](10-performance-profiling.md) rewrote: the first, naive version of
this change ran a second full column-A scan per sheet and cost **+74%** on a
serial 254-tracker extraction (63.5s -> 110.7s). Reusing the layout brings that
to **+15.6%** (63.5s -> 73.4s serial; the production arm runs parallel
workers). That residual is the honest price of the extra header pass.

**Per the user (this session): the current tracker template is the golden
rule.** A column that appears in one year and is gone the next was very likely
a test that did not survive; the trackers are kept if it is ever wanted. So
703 residual rows across 68 columns last seen in 2024 or earlier
(`TSH`, `tTG-IgA`, `Home Visit 1`, `Age (year)`, `INSTANT Meter Received Date`)
are ruled out of scope rather than triaged.

### Because

The Question asked for a per-column-family decision rather than row-by-row
triage, and a named cause on 95% of the rows plus an explicit verdict on the
rest achieves that. Classifying rather than filtering follows [ticket
26](26-triage-product-column-divergence.md)'s precedent, which deliberately
left `compare_columns` unfiltered and documented the harmless cases.

### Rejected

- **Rejecting cross-sheet header recovery** -- this was the session's own first
  conclusion and it was **wrong on the facts**, corrected when the user pushed
  back. The stated objection was that recovery would import the 2022 template's
  merged-cell duplicates; it cannot, because the rule only fires where a
  sibling sheet supplies a header at that position, and the 2022 hidden column
  is blank in *every* month sheet. Measured rather than argued: a sibling names
  the column for 316 of the 4,572 values and nothing at all for the other
  4,256. The rule was then implemented (see below). Recorded here because the
  reasoning, not just the conclusion, was the thing that failed: a plausible
  objection was accepted without measuring it.
- **Recovering on a majority or nearest-sheet donor.** Rejected in favour of
  requiring unanimity: 2021 Putrajaya offers three different candidate headers
  at one position, which is a guess rather than a recovery. Unanimity drops
  those 12 values and keeps the 7 that are unambiguous.
- **Deriving one header set per tracker from all its month sheets and applying
  it to every sheet** (the user's proposal, by analogy with the meta schema).
  Rejected on measurement, though the user was right about the dominant case.
  **66 of 249 trackers (27%) have at least one position their month sheets
  disagree on** (359 of 7,595 positions). Splitting those by whether the
  canonical column actually changes: **75 are pure renames** -- every spelling
  maps to the same column, exactly the short-to-descriptive drift the user
  described, and the synonym file already absorbs them -- but **284 across 37
  trackers change meaning**, and those a unified positional set would get
  silently wrong. Two verified against source:

  - `2018_CDA`: `Apr18` is 22 columns wide where the other eleven sheets are 23
    -- it has **no `Insulin Regimen` column at all**, so everything from
    position 16 rightward sits one column left (Mar18 position 16 reads
    `Insulin Regimen` with the value `Basal-bolus`; Apr18's reads
    `BASAL Insulin Dose (IU)` with the value `18`, same patient row). A unified
    header set would file that month's basal dose as the regimen, its bolus
    dose as basal, and so on across seven columns.
  - `2020_CDA`: position 13 changes from `Baseline FBG (mmol/dL)` to
    `(mg/dL)` in June while **the values do not change** (median 233, range
    67-500 on both sides, i.e. mg/dL throughout -- mmol/L would be ~3-28). So
    the header was edited over unchanged data, and `mmol/dL` is not even a real
    unit. This one already costs data today, in two different ways:
    `Baseline FBG (mmol/dL)` has **no synonym entry**, so Jan-May's baseline
    FBG is dropped entirely, while `Updated FBG mmol/dL` *does* map, to
    `fbg_updated_mmol` -- filing five months of mg/dL readings under mmol.

  The meta-schema analogy does not carry: the meta schema is a target columns
  are mapped onto **by name**, whereas a unified positional set assumes
  position -> meaning is stable within a tracker. This is also what makes the
  unanimity guard load-bearing rather than cautious -- at `2018_CDA` position
  16 the donor set has two members, so recovery abstains -- and it never
  overrides a header a sheet actually states.
- **Filtering `na*` out of `compare_columns`.** Would hide the 10 columns that
  do hold real content, which is how the data loss was found.
- **Adding synonyms for the 68 pre-2025 unmapped headers.** Over-fits the
  synonym file to columns that did not survive into the current template.

### Evidence

**Executed**: the cross-sheet recovery's effect and its cost (17 sites across 5
trackers recovered, 201 left reported, `insulin_regimen` 1,273 -> 1,467
non-null on the Kantha Bopha file, 63.5s -> 73.4s serial); the positional
agreement census behind rejecting a unified header set (66 of 249 trackers
conflict, split 75 renames / 284 meaning changes) and both source workbooks
behind it, including the 2020 CDA FBG value distributions either side of the
header edit; the `tracker_layout_changed` flag firing on 37 trackers / 284
positions; the synonym-lookup check showing `Baseline FBG (mmol/dL)` maps to
nothing while `Updated FBG mmol/dL` maps to `fbg_updated_mmol`; R's
`make.names` behaviour (ran `Rscript`); every count in the
table above (computed from the real comparison report and the 254-tracker
drive data); the `na*` content census across 245 R parquets; the 2021 Kantha
Bopha source-Excel header inspection and the 194-row loss on both sides; the
full-tracker blank-header sweep; the 2022 Kantha Bopha hidden-column
measurement; the new detection firing on exactly `Mar21`/`Apr21` column Q, 97
values each. Full suite 673 passed / 1 skipped, `ruff format --check`,
`ruff check`, `ty check src/` all pass.

**Read**: R's extraction and harmonization code, Python's `ColumnMapper`
non-strict behaviour.

**Tense**: every count describes current behaviour on the 254-tracker set. The
`blank_header_with_data` warning is new in this session and has not yet run in
production.
