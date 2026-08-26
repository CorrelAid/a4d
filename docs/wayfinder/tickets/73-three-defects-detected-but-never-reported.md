---
id: 73
title: Three workbook defects the pipeline detects, acts on, and never reports
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-26b
claimed_at: 2026-08-26T10:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 70
---

## Premise

Rests on [What can go wrong in a tracker that the pipeline never reports at
all?](70-audit-the-finding-taxonomy-for-blind-spots.md), closed 2026-08-26,
which derived the silent-path inventory and measured each of the three below
against the 255-tracker run.

Rests on [The finding taxonomy mis-files recoveries as data loss, duplicates
rows, and has no code for a malformed patient ID](69-miscategorised-and-duplicated-findings.md),
closed 2026-08-26, which keyed the taxonomy on the **outcome** and set the
precedent each of these follows: a defect gets a code specific enough to filter
for, and the category is derived from what happened to the value.

Sibling to [Four kinds of source defect the triage confirmed have no error
code](40-source-defect-findings-report.md), which is the same shape from a
different direction -- 40's four came from the triage catalogue, these three
came from reading the code for places that decide something and stay quiet.
Whichever runs second should check whether the other has already added a code
that fits.

Void if the pipeline stops publishing a findings table at all; merely in need
of rewriting if any of the three call sites moves.

## The three, each measured

**1. A diagnosis date that precedes the date of birth. 8 patients, 7 trackers,
58 rows. No code fires -- not one.**
`_fix_age_from_dob` reports exactly this contradiction on the *visit* age as
`age_negative_from_dob` (added by ticket 69; 1 finding on the run).
`_fix_t1d_diagnosis_age` (`clean/patient.py:891`) meets it on the *diagnosis*
age and publishes `None`. Ticket 52 chose that deliberately -- emitting the
arithmetic put impossible ages into production -- but no finding was added
beside the choice, so the workbook defect that caused it reaches nobody. Four
of the eight patients publish `NULL`; the other four keep the age the workbook
recorded, because `has_recorded_age` wins before the calculation is reached.
The starkest is `MY_PJ025` in `2024_Putrajaya Hospital A4D Tracker`: born
2021-05-05, diagnosed 2014-06-20 -- seven years before birth.

**2. Stock released to a patient ID that tracker's own patient sheets do not
contain. 14 rows, 2 trackers, 2 IDs (`KH_KB093` in 2025 Kantha Bopha II,
`LA_MH114` in 2026 Mahosot).**
`link_product_patient` (`tables/product.py:160`) finds these, groups them,
counts them, logs the aggregate at INFO and each pair at DEBUG -- and emits no
finding, so they reach neither the findings table nor the report. The *null*
recipient beside it does have a code (`released_units_without_recipient`, 2,239
findings / 239 trackers). 44,591 rows name a recipient, so the population is
small; the defect is not: it means insulin left the clinic recorded against a
patient that tracker has never heard of.

**3. A sex value the synonym lists do not recognise. 1 row.**
`fix_sex` (`clean/transformers.py:115`) sentinels anything outside its two
synonym lists to `Undefined` with no finding. On the run that is exactly one
cell: `KH_PK001`, sheet `Oct19`, in `2019_Preah Kossamak Hospital A4D Tracker`,
where the source cell holds `§` -- confirmed by reading the raw parquet, which
still carries the original character. One instance is not an argument for
urgency; it is an argument that the path works as described and nothing would
say so if a clinic wrote `F/M` down a whole column.

## Question

Decide, for each of the three, whether it gets a code -- then implement what
was decided.

1. **Do all three become findings, or only some?** The costs differ: (1) and
   (2) are consequential and rare, (3) is trivial today and unbounded
   tomorrow. "Report it" is not automatic -- a code with one instance that
   nobody filters for is noise the glossary has to carry forever.
2. **Which category does each carry, under ticket 69's outcome rule?** (1) is a
   workbook contradiction where the published value is either null or
   unverifiable -- `fix_workbook` on the ticket-69 reading, since a human can
   correct it. (2) is `fix_workbook` too. (3) loses the cell's contents with no
   way back, which is `data_lost` -- but its repair is at the clinic, and
   ticket 69's rule says `fix_workbook` wins where a value is both lost and
   correctable. Say which and why.
3. **Does (2) belong to the patient arm or the product arm?** It is discovered
   at table-aggregation time, across both arms' output, outside any tracker's
   extraction context. That is the exact shape that broke `a4d run` in ticket
   16's session -- `report_finding` raising outside a context and the
   exception being swallowed. Whatever is decided has to work at that stage,
   and the fix must be exercised outside the test suite's
   findings-context-per-test fixture.
4. **Should (1) also stop trusting the recorded age?** Four of the eight
   patients publish an age the workbook recorded while that same workbook's
   dates say the diagnosis came before birth. Reporting the contradiction
   without deciding what to publish leaves the report and the data disagreeing.

Reproduce with `uv run python scripts/finding_blind_spots.py --probe t1d-age
--probe product-recipient --probe sex`.

## Resolution

**Decision.** All three are reported. Two take new codes -- `diagnosis_age_negative_from_dob`
and `released_units_to_unknown_patient`, both `fix_workbook` -- and the third
reuses the existing `value_not_in_allowed_list` rather than taking a name of
its own. The recorded diagnosis age is **kept**, not nulled. `35 codes firing
-> 37`.

All four questions answered:

1. **All three, but not all three the same way.** (1) and (2) are consequential
   and rare, and each has a twin already coded -- `age_negative_from_dob` for
   the same contradiction on the *visit* age, `released_units_without_recipient`
   for the same stock row with no recipient at all. (3) is one cell today and
   unbounded tomorrow, which argues for reporting it and against minting a name
   for a population of one. `fix_sex` only bypasses `validate_allowed_values`
   because its synonym lists are hand-rolled; the outcome is identical to every
   other value a column does not allow, so it emits that code. The glossary
   carries two new entries, not three.
2. **`fix_workbook` for both new codes.** A human can correct one of the two
   dates, or the recipient ID; under ticket 69's tie-break `fix_workbook` wins
   over `data_lost` wherever the value is recoverable at the clinic. (3)
   inherits `data_lost` from the code it reuses. That inheritance is mildly
   against the same tie-break -- a mistyped sex *is* correctable -- but the
   whole `value_not_in_allowed_list` population (1,503) has that shape, so
   re-categorising it is a decision about that code, not about `fix_sex`. Left
   alone deliberately; noted on the map as an open question rather than
   silently changed.
3. **Product arm, and the ordering it depends on was broken.**
   `link_product_patient` now opens its own `findings_collected(arm="product")`
   -- the shape `create_product_data_table` already uses -- and returns
   `(count, findings)`. **The call sat at CLI step 3g, after the findings table
   was built at 3e**, so a finding emitted there would have been computed after
   the table that was supposed to hold it. It now runs at 3e and the table is
   built at 3f. Two tests carry `no_findings_context` so the emit-outside-a-
   tracker-scope path is exercised outside the suite's per-test fixture, which
   is the failure mode that broke `a4d run` in ticket 16's session.
4. **No -- the recorded age is published unchanged.** The user's call. The four
   recorded ages are 3, 9, 3 and 14, every one plausible on its own; what is
   not plausible is the date pair, and that is the suspect evidence. Nulling a
   clinician-typed value on the strength of two dates already believed wrong
   discards the more trustworthy record. `glucose_unit_suspect` is the
   precedent: publish as recorded, tell the operator to check the patient's
   record. Ticket 52's null stands where it applies -- the *derived* path,
   where the arithmetic itself produced the impossible number.

**Because.** Each of the three had a coded twin sitting beside it doing the
same job for a neighbouring defect, which is what made "report it" the answer
rather than a judgement call; and ticket 69's outcome rule decided the
categories without a second thought being needed. The one genuine judgement
was (4), and it went to the user.

**Rejected.**
- *A dedicated `sex_not_recognised` code* -- filterable separately, but the
  glossary would carry a name forever for a defect with one instance whose
  outcome is indistinguishable from 1,502 others. Reconsider if sex-specific
  filtering is ever wanted.
- *Nulling all eight diagnosis ages for self-consistency* -- buys a table that
  never disagrees with the dates beside it, at the cost of four real ages.
  `MY_LW004` shows the price concretely: 2022 publishes 3 and 2023 publishes
  null for the same patient with the same two dates, and nulling makes them
  agree by discarding the 3.
- *One finding per row for (1)* -- 58 rows, but the same dob/diagnosis pair
  repeated across up to 12 monthly sheets. Deduped to one per patient per
  tracker (**8**), because the contradiction is a property of the patient and
  saying it 58 times is the duplication ticket 69 spent a session collapsing.
  (2) is deliberately the other way -- **per row**, 14 -- because each product
  row is its own stock movement, matching how `released_units_without_recipient`
  counts. The asymmetry is intentional and is the distinction ticket 67's
  `scope` field would make explicit.
- *Adding the link check to `a4d create tables` as well* -- tried, measured,
  reverted. `report_finding` writes each finding to the active loguru sink
  (`main_pipeline_product.log`), which `rebuild_findings_from_logs` also
  globs, so handing them in as `extra_findings` counted each twice: **28 for 14
  real rows**. The rebuild picks them up from the run's own log lines with no
  help, which the parity check below proves.

**Evidence: executed.** Two full `a4d run` executions over the real 255-tracker
local corpus (USB drive), before and after, plus `duckdb`/polars over
`table_findings.parquet` both times. Suite **1,259 passed, 1 skipped**; ruff
and `ty check src/` clean.

| | before | after |
|---|---|---|
| findings total | 105,441 | **105,464** |
| `fix_workbook` | 63,164 | **63,186** |
| `data_lost` | 24,164 | **24,165** |
| `recovered` | 18,113 | 18,113 |
| distinct codes firing | 35 | **37** |
| `diagnosis_age_negative_from_dob` | -- | **8** |
| `released_units_to_unknown_patient` | -- | **14** |
| `value_not_in_allowed_list` | 1,502 | **1,503** |

The +23 is exactly 8 + 14 + 1. Nothing else moved.

**The rebuild path was re-proved exact**, since ticket 66's guarantee had to
survive two new codes emitted from a table-stage context: `run` **105,464**,
`rebuild_findings_from_logs` **105,464**, and the two frames are row-for-row
identical on all thirteen non-timestamp fields.

**All eight of (1)'s findings, as published:**

| tracker | patient | recorded age | dates |
|---|---|---|---|
| 2017 Yangon Children's | `MM_YC003` | 3 | diagnosed 2003-07-01, born 2004-01-03 |
| 2022 Hat Yai | `TH_HY022` | 9 | diagnosed 2013-11-01, born 2014-11-19 |
| 2022 Likas | `MY_LW004` | 3 | diagnosed 2015-05-29, born 2016-08-17 |
| 2022 Uni Med Centre | `VN_UM012` | 14 | diagnosed 2000-01-01, born 2004-01-01 |
| 2023 Likas | `MY_LW004` | NULL | same two dates as its 2022 row |
| 2023 Yangon General | `MM_YG044` | NULL | diagnosed 2008-07-20, born 2009-07-15 |
| 2023 Yangon General | `MM_YC043` | 999999 | diagnosed 2007-06-01, born 2008-01-01 |
| 2024 Putrajaya | `MY_PJ025` | NULL | diagnosed 2014-06-20, born 2021-05-05 |

`MM_YC043`'s `original_value` is the numeric error sentinel, so `has_recorded_age`
excludes it and it publishes NULL -- the finding still records what the cell
reached, which is the point of carrying `original_value`.

**Tense.** Every figure is *current behaviour* on `dev`, measured after the
change landed. The before column is the 2026-08-26 run recorded on ticket 69.

**One defect found while verifying, spawned rather than fixed here.** Both
readers of `output/logs/` glob `*.log` and read every file present, and worker
log names carry a run timestamp and pid, so nothing overwrites the previous
run's. With two runs' worker logs on disk the rebuild returned **213,921** for
a run that produced 105,464, and `create_table_logs` returned **326,092**
against a true 217,022. Production is unaffected -- each Cloud Run execution
starts from a fresh container -- but every triage number on this map was
measured on the local corpus, where it bites. That is [ticket
74](74-stale-worker-logs-inflate-rebuilt-tables.md). All figures above were
measured with `logs/` cleared first, precisely because of it.
