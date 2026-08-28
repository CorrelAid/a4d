---
id: 76
title: Everything the pipeline reads out of a workbook and then discards to fit the fixed output shape
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-28b
claimed_at: 2026-08-28
resolution: decided
evidence: executed
closed_by: null
spawned_by: 75
---

## Premise

Rests on [A screening block records several results per patient and the pipeline
keeps only the first](75-screening-selections-under-merged-header.md), closed
2026-08-28, which found that the complication-screening selection and its result
were read out of every workbook and then dropped, because the cleaned output has
a fixed column list and neither was on it. Nothing reported the drop. Ticket 75
fixed those two columns by adding them to the list; it did not touch the
mechanism.

Rests on [What can go wrong in a tracker that the pipeline never reports at
all?](70-audit-the-finding-taxonomy-for-blind-spots.md), closed, which audited
the finding taxonomy for blind spots and did not reach this one -- the audit
looked at what the emitters cover, and this is a whole stage with no emitter at
all.

**What would void this ticket rather than rewrite it**: if the fixed output
shape is found to be enforced somewhere that already reports the columns it
drops. Ticket 75 read the function that applies it (`clean/schema.py`,
`apply_schema`) and it selects the schema's keys with no reporting of any kind.

## Question

Applying the fixed output shape is a `select` of the 85 named columns. Anything
else the extraction produced is discarded there, silently -- no finding, no log
line, nothing in the report a clinic or A4D staff member reads.

Measured on the 254-tracker corpus: **73 distinct column names carrying 63,790
values** are dropped this way. They are not one population:

- **Consumed, correctly dropped.** `blood_pressure_mmhg` (19,273 values, 73
  trackers) is split into systolic and diastolic before the shape is applied,
  so the source column has done its job. Several others are like this.
- **Deliberately excluded.** Phone numbers, contact numbers and insurance-card
  fields (roughly 5,000 values) look like data the output is meant not to carry.
  Nobody has confirmed that, and it is not written down anywhere.
- **Genuinely lost, nobody told.** `complication_screening` and
  `complication_screening_results` were in this group until ticket 75. What else
  is in it is not known -- candidates from the measurement include
  `est_strips_pmoth` (3,749 values, 22 trackers), `insulin_dosage` (2,533, 8),
  `meter_received_date` (1,788, 17) and `complication_screening_date` (397, 19).

The measurement above was taken from a previous run's raw parquets; re-derive it
against a current run before deciding anything on it.

The question has two halves:

1. **Which of the 73 are in the third group**, and should any of them reach the
   published tables the way ticket 75's two now do?
2. **Should the drop be reported at all**, and if so how -- one finding per
   dropped column per workbook would be noisy for the columns that are
   deliberately excluded, so a declared list of "read and discarded on purpose"
   is probably the shape, with anything outside it reported.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: sorting the
73 into three buckets is not the decision. Each column in the third group needs
a decision about whether it is published or reported, and ticket 27's precedent
applies -- a classifier that explains a drop without deciding it cements the
loss as "understood".


## Resolution

**Decision.** Nothing new is published, and the drop is now covered two ways:
the check that reports an unrecognised heading is switched on for the two
sheets it was silently skipping, and every column the pipeline recognises but
does not publish is declared in the source with its reason, pinned by a guard
test. Findings **104,820 -> 104,834**; all four published tables row-for-row
identical.

**The measurement, re-derived against the current run** (255 trackers,
post-ticket-75, the run whose 395/3,349 screening figures match this map's
record). The ticket's "73 columns / 63,790 values" was a raw-parquet proxy that
counted columns already reported elsewhere. The real silent population is
**22 columns / 42,436 values**, and it is four mechanisms, not three:

| bucket | cols | values | mechanism |
|---|---:|---:|---|
| Consumed | 1 | 19,273 | `blood_pressure_mmhg` is split into sys/dias before the shape is applied |
| Superseded duplicate | 2 | 9,953 | `fbg_baseline_{mg,mmol}.static`, the Patient List copy ticket 29 chose against |
| Recognised, no schema column | 8 | 11,093 | the synonym file names them; `get_patient_data_schema` does not |
| Unrecognised on a static sheet | 11 | 2,117 | reported nowhere, see the bug below |

**Half 1 -- which should be published? None.** Each of the 8 recognised
columns was measured for the last year any tracker carries a value:
`est_strips_pmoth` 2019, `insulin_dosage` 2018, `meter_received_date` 2023,
`insulin_required_month` 2018, `insulin_required_year` 2019,
`complication_screening_date` 2022, `family_support_scale` 2019,
`dm_complications` 2023. **Not one appears in 2024, 2025 or 2026**, so the
user's "current template is the golden rule" decision (ticket 30) already
settles them. Nine further recognised names carry no value in any tracker at
all. The only *current-template* columns dropped here are the five
[ticket 41](41-decide-2026-new-patient-list-columns.md) already owns, and this
ticket deliberately does not decide them.

**Half 2 -- the reporting. A real bug, found by asking why the deliberately-
excluded bucket was invisible.** `harmonize_patient_data_columns` reports
unrecognised headings only when told which sheet the frame came from --
`report_unrecognised_columns` switches itself off otherwise, which its
docstring justifies by "the callers that omit it are tests and tools working
on a bare frame". Two callers that are neither omitted it: the `Patient List`
and `Annual` paths in `read_all_patient_sheets`. So **every unrecognised
heading on those two sheets was dropped in total silence**, across all 255
trackers, while the same check produced 3,042 findings on month sheets. This
is why the 2026 template's five new Patient List columns produced zero
findings -- the fact ticket 41 needed and did not have.

Passing the sheet name fixes it: **+14 findings, one per column per sheet,
nothing else moved.** All five of ticket 41's columns (`Phone Number`,
`Insurance Card Status`, `Current Insulin Regimen`, `BGM A4D`, `Insulin A4D`),
plus 2024 Jayavarman's `Lost Follow Up`, 2023 Sibu's five-column DM
Hospitalisations Summary block, and 2024 Nakornping's two lipid-unit columns.
Zero merged-header noise, which was the risk.

**The eight retired columns get a declaration, not a finding.**
`UNPUBLISHED_COLUMNS` in `clean/schema.py` names all 18 recognised-but-
unpublished columns plus the two join artifacts, each with its reason and its
last-seen year. `tests/test_clean/test_schema.py` derives
`synonyms - schema - declared` from the real config and fails on anything left
over -- so a column can no longer sit in the reference list without a home in
the output and nobody noticing, which is exactly how ticket 75's two screening
columns survived unseen. A fifth test is an `ast` guard asserting every
`harmonize_patient_data_columns` call in `src/` passes `sheet_name`, so the
bug above cannot come back; same shape as ticket 67's static guard.

**Rejected.**
- *Report every discarded column* (~13,000 new findings). Rejected by the
  user: the `data_lost` bucket holds 24,164 findings and means "a real value
  nobody can get back"; adding 11,000 entries about fields A4D deliberately
  stopped collecting before 2024 would roughly halve its signal.
- *A second error code for "recognised but not published"*, splitting
  "retype your heading" from "A4D does not carry this field". Rejected as the
  same noise with better labels; it remains the right upgrade if A4D ever
  wants every discarded value visible per workbook.
- *A runtime finding when `join_static_sheet` hits an undeclared collision.*
  Rejected: an undeclared collision is a development defect, not a workbook
  defect, and findings are for workbook defects. Only two collisions exist in
  the corpus and both are declared. **What this gives up**: a *new* colliding
  column would be discarded silently, and no test can catch it from config
  alone -- the guard covers the synonym-vs-schema gap, not the join.

**Evidence.** Executed. Two full both-arm runs over the real 255-tracker set,
before and after, from a clean output directory. Before 104,820 findings / 40
codes, after 104,834 / 40; the only code that moved is `unrecognised_column`
(23,106 -> 23,120). `patient_data_monthly` (86,360), `patient_data_static`
(1,828), `patient_data_annual` (4,520) and `product_data` (75,169) are
row-for-row identical, checked with a symmetric `EXCEPT ALL` on every column.
Column populations and last-seen years come from the run's own raw parquets;
the sheet each unreported column lives on was confirmed by opening the source
workbooks. Full suite green, 1,338 passed.

**Tense.** Every number above is current behaviour after the change, except
the "before" column of each pair.
