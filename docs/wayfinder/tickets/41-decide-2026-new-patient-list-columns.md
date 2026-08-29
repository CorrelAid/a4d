---
id: 41
title: Decide whether the 2026 template's five new Patient List fields enter the pipeline
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-28b
claimed_at: 2026-08-28
resolution: decided
evidence: executed
closed_by: null
spawned_by: 30
---

## Premise

Rests on [Triage the patient pipeline's raw-stage column-existence
divergence](30-triage-patient-raw-column-divergence.md), closed, which found
these columns while accounting for the only-in-Python divergences, and on the
user's rule stated in that session: **the current tracker template is the
golden rule** -- a column present in today's template is the kind that matters,
where one that appeared for a single year and vanished is very likely a test
that did not survive. These five are the former case, which is why they are
ticketed rather than ruled out.

Verified against the source workbook
(`2026_Preah Kossamak Hospital A4D Tracker_Jun_26.xlsx`, `Patient List` sheet,
header row 8): the 2026 template carries five columns with no entry in
`reference_data/synonyms/synonyms_patient.yaml` and no home in the 83-column
cleaned schema:

| Col | Header | Populated |
|---|---|---|
| 17 | `Phone Number` | |
| 18 | `Insurance Card Status` | |
| 19 | `Current Insulin Regimen` | 213 rows |
| 20 | `BGM A4D` | 213 rows |
| 21 | `Insulin A4D` | 213 rows |

Python's raw stage passes them through under their literal header text (its
`ColumnMapper` runs non-strict); the cleaning stage drops them, since the
schema has no such columns. R does the same thing under sanitized names
(`currentinsulinregimen`, `bgma4d`, ...), so neither pipeline carries them
forward -- this is a **new-field question, not a Python defect**.

**`Current Insulin Regimen` is not the monthly `Insulin Regimen`.** Measured on
the same file: both columns exist, 191 rows have both populated, and they
**disagree on 39** of those. Mapping the Patient-List column onto
`insulin_regimen` would corrupt data. It is a patient-level field beside the
month-by-month one.

## Question

The user said they need to look at the new 2026 trackers themselves before
deciding -- so this ticket waits on that inspection, and the decision is
theirs.

For each of the five: does it enter the pipeline as a new cleaned-schema
column, or stay a raw-stage passthrough that is deliberately dropped?

Things the decision turns on, worth having ready when it is taken:

1. **How widely each column is actually used** -- only one clinic's 2026
   tracker is in the current set. Check the 2026/2025 master template rather
   than this single file before concluding it is standard.
2. **Blast radius of saying yes.** A new cleaned-schema column means
   `clean/schema.py`, the synonym file, the patient tables, and the BigQuery
   schema -- and a BigQuery schema change touches the production load path
   ([ticket 5](05-production-verification-run.md)'s territory).
3. **Whether `Current Insulin Regimen` needs a distinct name** to keep it from
   ever colliding with the monthly `insulin_regimen` -- the 39 disagreeing rows
   are the evidence that it would.
4. **Whether this belongs to this map at all**, or to the post-promotion
   backlog. The destination is "close out the R-to-Python migration"; adding
   fields R never had is arguably new development, not migration. Deciding that
   is part of this ticket.


---

**Update from [ticket 76](76-columns-dropped-by-the-fixed-output-shape.md),
2026-08-28.** All five columns now appear in the findings report. They did not
before, and the reason was a bug rather than a design choice: the `Patient
List` and `Annual` sheets were put through the unrecognised-heading check
without being told which sheet they came from, and the check switches itself
off when it is not told. Both call sites now pass the sheet name, so the five
columns produce one finding each (`unrecognised_column`, scope `sheet_column`)
against the 2026 Preah Kossamak tracker.

Ticket 76 also settled that these five are the **only** current-template
columns the pipeline reads and drops -- every other dropped column it found
was last recorded in 2023 or earlier. So this ticket is the whole of the
remaining publish-or-not question, not a sample of it.


---

## Resolution (2026-08-29, session-2026-08-28b)

**Decision.** None of the five enters the pipeline. They stay raw-stage
passthroughs, dropped at cleaning, and reported as `unrecognised_column`
findings against the one workbook that carries them. **No code change** -- the
pipeline already does exactly this, and this session verified it by execution
rather than by reading. The question is answered, not deferred: if the charity
adopts any of these fields into the template, that is a fresh schema change
with its own ticket, not a resumption of this one.

**Because the ticket's premise was false.** It was written believing these were
*current-template* columns, which is the one category the user's 2026-08-15
golden-rule decision protects. They are not. Measured across the whole corpus:

| | trackers carrying the five |
|---|---|
| 2026 trackers | **1 of 48** (Preah Kossamak, Cambodia) |
| 2025 trackers | **0 of 47** |

The 2026 `Patient List` sheet is **identical in all 48 workbooks** -- the same
thirteen headers, no exceptions -- and the five appear appended past column 16
in the single Cambodian file. They are one clinic's local edit to their own
copy, not a template change. Under the golden rule that is the *weaker* case
than the one already ruled out of scope by
[ticket 77](77-per-test-screening-completion-months.md) (a column family present
in one year and no other): one workbook out of 48 is narrower than one year out
of ten. The user confirmed the decision on this measurement.

**The ticket's populate counts were also wrong.** It recorded 213 rows for three
of the five. The sheet holds 114 patient IDs, and the real fill is:

| Header | Populated (of 114) | Distinct |
|---|---|---|
| `Phone Number` | **0** | -- |
| `Insurance Card Status` | **0** | -- |
| `Current Insulin Regimen` | 47 | 7 |
| `BGM A4D` | 43 | 2 (`Y`/`N`) |
| `Insulin A4D` | 43 | 2 (`Y`/`N`) |

Two of the five have never been filled in at all. And `Current Insulin Regimen`
is not a clean field even where it is used: alongside 43 real regimens
(`Self-mixed BD` 27, `Basal-bolus MDI` 11, `Premixed 30/70 BD` 5) sit three
free-text notes to self -- `Sarin contacted. Confirmed will come`,
`Name changed to Chann Kongcheyvannly`, `Remark from contacting`. The column is
being used partly as a scratchpad, which is a further argument against
publishing it as a typed field.

**Rejected.**

- *Publish the two charity-supply columns only* (`BGM A4D`, `Insulin A4D`) --
  the strongest of the alternatives, since both are clean `Y`/`N` and the
  charity plausibly wants to know which patients it supplies. Killed on
  population: 43 answers from one clinic is a note, not a field, and saying yes
  commits `clean/schema.py`, the synonym file, the patient tables and the
  BigQuery schema -- a warehouse change on the production load path -- to one
  workbook's local habit.
- *Map `Current Insulin Regimen` onto the monthly `insulin_regimen`* -- ruled
  out on the ticket's own evidence, kept here so it is not re-proposed: both
  columns exist in that file, 191 rows have both, and they **disagree on 39**.
  They are different fields (patient-level vs month-by-month); merging them
  would corrupt data.
- *Hold the ticket and ask the charity whether the five are a coming template
  change* -- offered to the user and declined. Their instruction:
  ignore them until the schema is officially changed. That is what makes this
  `decided` rather than parked; the `unrecognised_column` findings are the
  standing detector if other clinics start adopting them.

**What the chosen route gives up.** 133 filled-in cells at one clinic
(47 + 43 + 43) stay out of the published tables. They remain in the source
workbook and in the raw stage, so nothing is destroyed, and the report names
each column every run.

**Evidence: executed.**

- Corpus scan of all 48 2026 and 47 2025 workbooks, reading the `Patient List`
  header row of each and counting populated cells -- this produced the 1-of-48
  and 0-of-47 figures and the "13 identical headers" result.
- Value profile of the Cambodian workbook's five columns (counts and distinct
  values above).
- `extract_patient_data` + `harmonize_patient_data_columns` run against the real
  workbook inside a `findings_collected` block: all five emit
  `unrecognised_column` naming `sheet_name='Patient List'`, and all five survive
  into the raw frame under their literal header and reach no cleaned column.
  This confirms [ticket 76](76-columns-dropped-by-the-fixed-output-shape.md)'s
  claim by execution; the earlier claim was code-reading only.
- Grep confirming none of the five appears in
  `reference_data/synonyms/synonyms_patient.yaml`, `clean/schema.py`, or
  anywhere else in `src/`, `reference_data/` or `tests/`.

**Tense.** Every claim above describes current behaviour on `dev` at commit
`a98cce6`, not a consequence of a proposed design.

**Spawned.** Running the extraction against the real workbook to verify the
findings surfaced an unrelated defect: the sheet holds 114 patient IDs and
extraction returns 100. A second patient block below a `PENDING TRANSFER KBH`
banner row -- 14 real patients, rows 114-128, with the row counter restarting
at 1 -- is dropped in silence, because `read_patient_rows` stops at the first
fully blank row. Measured across all 2,573 patient sheets in the corpus: **4
sheets, 48 rows**, three of them this same workbook (so those 14 patients lose
their monthly records too) and 2 rows at Mukdahan. Not this ticket's question;
ticketed as [ticket 78](78-blank-row-ends-the-patient-block.md).
