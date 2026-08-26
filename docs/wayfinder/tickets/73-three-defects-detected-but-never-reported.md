---
id: 73
title: Three workbook defects the pipeline detects, acts on, and never reports
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
