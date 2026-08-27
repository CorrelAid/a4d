---
id: 75
title: Which screenings a patient had, and what they found, is read from every workbook and never published
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-27b
claimed_at: 2026-08-27T12:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 68
---

## Premise

Rests on [The pipeline reports 217 headerless-column defects where the triage
found 4,572](68-blank-header-emitter-vs-catalogue.md), closed 2026-08-27, which
established that a column sitting under a merged header is named by that merge
and is no longer reported as a headerless data column. Splitting the 193
suppressed findings by what the merge names showed they are two unrelated
populations, not one:

- **`Insulin Regimen`** -- 103 findings, 3,659 values, 10 trackers, of which
  **2,910 values are byte-identical to the column the merge anchors**. Stale
  content buried under a merge, invisible in Excel. Correctly dropped.
- **the complication-screening block** -- 90 findings, **226 values across 12
  trackers**, of which **zero** duplicate the anchor column. These are
  additional screening results, one per column, and the pipeline keeps only the
  first.

Rests on [Python drops complication-screening results and dates where a merged
header spans them](48-putrajaya-screening-columns-lost.md), closed, which found
the same shape on `2021_Putrajaya` and deliberately did not fix it: both
pipelines keep only the first selection, so the R/Python comparison stays silent
and it is a shared limitation rather than a divergence.

**This was the map's "multi-select screening block" fog patch**, which said it
was not sharp enough to ticket "until someone has measured how many trackers lay
a block out this way". Ticket 68 measured it: **12 trackers, 226 values**.

**What would void this ticket rather than rewrite it**: if ticket 68's
merge-coverage classification is wrong -- that is, if these columns are not
under a merged header at all -- the population disappears and there is nothing
to decide. Ticket 68's own reversal, were it overturned, would only change how
these are *reported*, not whether they are dropped.

## Question

A clinic records several complication screenings for one patient in one month --
`Foot Examination (Nerves)`, `Lipid profile`, `TSH` -- by putting each in its own
column under a single merged "Complication Screening" header. The pipeline
publishes the first and discards the rest.

Until ticket 68 this was at least *visible*, though under a message
(`blank_header_with_data`, "fix the header in the source tracker") that
described it wrongly -- the header is not missing, and there is nothing for the
clinic to fix. Ticket 68 removed that message, so as of now these 226 values are
dropped in **total silence**. That is the state this ticket has to resolve, and
it is a step backwards taken knowingly.

1. **Are the extra selections wanted downstream?** The published patient tables
   carry one screening column. Answering "yes" means a schema question, not just
   an extraction one: several results per patient-month have to land somewhere.
   Ask the consumer (the internal tool and the dashboard) before designing.
2. **If they are wanted, what shape?** A delimited list in the existing column,
   one row per screening, or additional columns -- and what that does to
   consumers already reading the single-value column.
3. **If they are not wanted, they must still be reported.** Silently discarding
   226 clinical results is what the map's blind-spot audit exists to prevent.
   A code naming what actually happened ("this patient-month recorded 3
   screenings, 2 were dropped") is a different statement from "your header is
   missing", and is the minimum outcome of this ticket.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: naming the
class is not the decision. Ticket 27's precedent applies directly -- what looked
like a labelling job was extraction silently discarding data, and a classifier
would have cemented the bug as "explained".

Measure before designing: the 226 values are known, but how many are *distinct*
per patient-month, how many patient-months carry more than one, and which
trackers and years, are not.

## Resolution

**Decision.** The screening selection and its outcome are published. Two columns
join the cleaned output shape -- `complication_screening` and
`complication_screening_results` -- and both appear in `patient_data_monthly`.
Where a merged header covers several columns and the leftmost is the screening
selection, the others are given the anchor's header so
`merge_duplicate_columns_data` comma-joins them into one cell. Which merged
blocks are multi-select is a declared frozenset (`MULTI_SELECT_MERGED_BLOCKS`,
`extract/patient.py`), not a property inferred from the values.

The 2023 template's seven per-test "Complication Screening Completed <test>"
columns are **removed from the `complication_screening` synonym list**. They do
not record which screenings were done; each records the *month* one test was
completed, and five of them mapped onto the selection column and comma-joined
there. They are now reported as unrecognised columns -- which two of the seven
(TSH, tTG-IgA) already were -- and their proper home is
[ticket 77](77-per-test-screening-completion-months.md).

**Because.** The ticket's own premise was false and the measurement is what
found it. The pipeline did not publish the first selection and drop the rest: it
published **none of them**. `apply_schema` selects the schema's keys, and neither
column was on the list, so both were read out of every workbook and discarded
with no finding raised -- 4,031 selections and 3,349 outcomes across the corpus.
The 227 extras this ticket was written about were a rounding error beside the
whole field going unpublished. Publishing the field makes the 227 arrive for
free, since the join happens before the shape is applied.

Publishing the 2023 columns as they stood was not an option: they produced
`MAR,MAR` on 1,393 patient-months, and would have made one published column mean
"which screenings" for 2021/2022 and "which month, five times over" for 2023.
Unmapping them loses nothing -- none of those 3,638 cells reached any table
before this session either -- and trades a `duplicate_source_columns` finding
that described a fusion for an `unrecognised_column` finding that says plainly
the pipeline has no home for the column.

**Rejected.**
- *Deduplicate the joined 2023 value* (`MAR,MAR` -> `MAR`). Truthful about the
  month but silently drops which tests, and is ambiguous the moment two tests
  differ (`MAR,APR`). One column would still carry two meanings by year.
- *Infer multi-select from the values* -- join a shadow column when its values
  do not duplicate the anchor. It reproduces today's populations correctly but
  makes a workbook layout question depend on the data in the cells, so a year
  where a clinic happened to repeat a value would silently change behaviour.
- *One published row per screening per patient-month.* The wider shape the
  question offered. Rejected with the user: 133 patient-months is not enough to
  rebuild consumers around, and the joined cell loses nothing.
- *Map the 2023 per-test columns onto the existing per-test date columns.* The
  right end state, probably, but a bare `MAR` has no year, the month recorded
  need not be the sheet's month, and there is no column at all for blood
  pressure or tTG-IgA. That is a decision, not a mapping -- ticket 77.
- *Report the drop instead of publishing* (the ticket's option 3). Superseded by
  the user choosing to publish.

**Evidence: executed.**
- The 227 extras were measured by running the extraction functions over all 254
  workbooks: **227 values, 13 trackers** (2021 Putrajaya + twelve 2022), 45
  sheets, **133 patient-months, 81 patients**; 74 patient-months carry one
  extra, 31 two, 21 three, 7 four; **none duplicates the anchor**. Ticket 68's
  226/90/12 was one finding low.
- The silent drop was confirmed by reading `apply_schema` (it is a `select` of
  the schema keys, with no reporting) and then by running one 2023 workbook end
  to end on current code: 33 selections and 33 outcomes in the raw parquet, both
  columns absent from the cleaned parquet, no finding.
- Full local both-arm run, before and after, over the same 254 workbooks:

  | | baseline | after |
  |---|---|---|
  | findings | 103,407 | 104,820 |
  | codes firing | 40 | 40 |
  | selections published | 0 | **395** |
  | outcomes published | 0 | **3,349** |
  | patient-months with >1 screening | 0 | **133** |

  The baseline reproduces ticket 68's recorded 103,407 exactly. Only three codes
  moved: `unrecognised_column` +1,765 and `duplicate_source_columns` -353 (the
  same seven columns, reported differently), and `tracker_layout_changed` +1 --
  2021 Putrajaya, whose month sheets genuinely disagree, now shows one more
  column disagreeing because it too carries a screening selection in some
  months. `patient_data_static` (1,828), `patient_data_monthly` (86,360),
  `patient_data_annual` (4,520) and `product_data` (75,169) are unchanged, so no
  existing published data moved.
- Suite green: **1,332 passed, 1 skipped**. Four new tests: the multi-select
  join, the named-column exemption, the insulin block staying single-select, and
  a reference-data test pinning the 2023 columns out of the selection column.

**The title was corrected on closing.** It read "a screening block records
several results per patient and the pipeline keeps only the first", which is the
false premise the measurement overturned -- nothing was kept. The file name is
unchanged so the links from [ticket 68](68-blank-header-emitter-vs-catalogue.md)
and the map still resolve.

**Tense.** Every number above is measured current behaviour after the change,
against a measured baseline of the behaviour before it. The claim that the 2023
per-test columns *should* live somewhere else is a proposal, and is ticket 77's
to settle.

**Consumers see a schema change.** BigQuery tables are deleted and recreated on
each production run, so `patient_data_monthly` gains two columns on the next
one.
