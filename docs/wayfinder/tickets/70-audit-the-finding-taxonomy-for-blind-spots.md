---
id: 70
title: What can go wrong in a tracker that the pipeline never reports at all?
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-26
claimed_at: 2026-08-26
resolution: decided
evidence: executed
closed_by: null
spawned_by: 16
---


> **Partly answered, and re-scoped (2026-08-26).** [The finding taxonomy
> rework](69-miscategorised-and-duplicated-findings.md) settled this ticket's
> point 4: the taxonomy is now keyed on the **outcome**, `invalid_value`'s
> twelve emitters and `invalid_tracker`'s five became specific codes, and 21
> codes became 37. `tests/test_finding_taxonomy_guard.py` now pins the
> code-to-emitter map, so a code silently acquiring a second, differently-shaped
> emit site fails CI.
>
> **What is left is this ticket's real question and it is untouched**: nothing
> has checked the taxonomy *from the defect rather than from the code*. Two new
> instances were added by that session, both found by measuring rather than by
> reading the codes -- a negative calculated age was publishing as a recovery
> (now fixed), and the pipeline was reading its own report as a tracker (see
> [ticket 71](71-pipeline-ingests-its-own-output-as-a-tracker.md), also fixed),
> neither of which any channel would have reported. That is two more arguments
> for the outside-in audit, not fewer.

## Premise

Rests on [Unify the two separate channels that report data-quality
findings](66-unify-finding-channels.md), closed 2026-08-25, which made
`report_finding` the single way to record a finding and declared the 21-code
`ErrorCode` taxonomy. It proved the taxonomy is **internally** consistent --
tests keep `FINDING_CATEGORY` exhaustive in both directions, so no code ships
uncategorised. Nothing checks it against the **outside**: whether the 21 codes
cover what actually goes wrong in a tracker.

Rests on [the findings report](16-log-analyzer-drill-down.md), closed
2026-08-25, which turned the table into something a person reads, so a blind
spot in the taxonomy is now a blind spot in A4D's view of its own data rather
than a gap in an internal table.

Rests on [the classifier re-audit](32-audit-classifiers-against-decision-bar.md),
closed, which is this ticket's precedent and its warning: it re-examined every
existing cause classifier against the bar "is Python actually right, or was the
diff merely labelled?" and found several that were labelled rather than
understood. The same question now applies one level up, to the codes themselves.

**Sequencing, not a block.** [Ticket
69](69-miscategorised-and-duplicated-findings.md) fixes three *known* defects
in the taxonomy and should run first, so this audit surveys a set whose known
faults are already corrected. It is not wired as `blocked_by` because this
ticket's main work -- finding what is never reported -- does not depend on
those fixes.

### Why this is not paranoia: the map already has four instances

1. **A silent sentinel with zero current instances.** `standardize_gender`
   (`clean/transformers.py:115`) turns any value outside its synonym lists into
   `Undefined` with no finding emitted. Measured on the 255-tracker run: `sex`
   holds only `F` (1,073), `M` (711) and null (44), so nothing is being lost
   **today** -- but a clinic writing `F/M` or a typo would lose the value and
   nothing anywhere would say so. A blind spot with no current instances is
   still a blind spot.
2. **Three populations found only by measuring workbooks directly**, each
   invisible to the R/Python comparison because both sides agreed, and each
   discovered by hand rather than by any channel: [ticket
   59](59-triage-unmatched-row-keys.md)'s rows that pair with nothing, [ticket
   42](42-fbg-unit-headers-and-implausible-values.md)'s unit swap, and [ticket
   63](63-name-the-cleaned-stage-static-join-divergence.md)'s static-join
   misses. The comparison tool is retired; whatever it was accidentally
   covering is now covered by nothing.
3. **A code whose reported population is 5% of the catalogued one** --
   `blank_header_with_data`, 217 findings against ticket 30's 4,572, which is
   [ticket 68](68-blank-header-emitter-vs-catalogue.md). That ticket is one
   instance of this ticket's general question.
4. **One code doing twelve jobs.** `invalid_value` carries 24,805 findings
   from 12 distinct emitters ([ticket
   69](69-miscategorised-and-duplicated-findings.md)), which is what made a
   malformed patient ID -- arguably the most consequential defect the pipeline
   finds -- impossible to filter for.

Sixty `report_finding` call sites resolve to 21 codes. Nobody has ever checked
that mapping from the direction that matters: **from the defect, not from the
code.**

## Question

Audit the taxonomy against reality and report where it fails. **This ticket
produces an inventory and a set of named gaps; it does not redesign the
taxonomy** -- decisions that follow are spawned as their own tickets, so this
stays one session's work.

1. **Derive the inventory, do not write it.** One list, generated from the
   tree: every `report_finding` call site, its code, its category, the
   condition that triggers it, and what the pipeline does with the value
   (publishes it, sentinels it, drops the row, drops the column). A
   hand-written version drifts the first time a call site moves -- the map's
   standing rule.
2. **Find the silent paths.** Everywhere the pipeline discards or sentinels
   data **without** emitting a finding: every use of `error_val_numeric` /
   `error_val_character` / `error_val_date`, every `drop`/`filter` that removes
   rows or columns, every `otherwise(...)` fallback. `clean/transformers.py`
   sentinels in 8 places and reports in 2; `tables/product.py` sentinels twice
   and reports through the functions it calls. For each, say whether silence is
   correct.
3. **Come at it from the defect, not the code.** Take the source-defect
   catalogue this map accumulated over tickets 18-63 -- and the current tracker
   template -- and ask of each defect kind: which code fires, on how many
   trackers, and does the count match what triage found? Ticket 68 is one
   worked example of this and it disagreed by a factor of twenty.
4. **Judge the codes as names.** Is each one distinguishable from its
   neighbours by someone reading the report? `invalid_value` at twelve
   emitters is the clear failure; `missing_value`, `missing_column` and
   `missing_required_field` are three codes whose names do not tell a reader
   which is which, and only one of them means what it says.
5. **Say what would have to be true for the taxonomy to be complete**, and
   whether that is achievable or whether "complete" is the wrong goal --
   an open-ended set of clinic mistakes may be better served by a catch-all
   with good detail than by chasing exhaustiveness. That is a real possible
   answer, not a failure to converge.

## Standing bar

Per the map's **triage means deciding, not labelling** preference and its
2026-08-13 refinement: the bar is a clear *understanding* of each gap, measured
against the real 255-tracker run or the source workbooks -- not a tidiness
review of the code list. And per [ticket
32](32-audit-classifiers-against-decision-bar.md)'s hard-won lesson: finding
evidence that fits the existing frame is the most reliable way an audit gets
abandoned halfway. A code that looks right is the one to check hardest.

## Resolution (2026-08-26)

**Decision. The taxonomy's blind spots are structural, not lexical: what the
pipeline fails to report is not a defect kind it lacks a word for, but a
*decision it makes silently* -- a sheet it does not open, a value it replaces,
a mismatch it logs instead of reporting.** Four gaps are named and measured
below. The audit did not redesign anything; each gap that needs a decision left
as its own ticket.

**Two derived artifacts, both kept, neither hand-written:**

- [`scripts/finding_inventory.py`](../../../scripts/finding_inventory.py) --
  walks the AST for every `report_finding` call site and prints its code,
  category, glossary line, governing condition and stage, joined against a
  run's measured counts. **51 call sites -> 35 codes, against 37 declared.**
  `--silent` is the second mode: 86 discard/sentinel sites in functions that
  emit nothing, narrowed to **60 that actually lose a value** by splitting
  `otherwise(pl.col(x))` (the "everything else is fine" branch) from
  `otherwise(pl.lit(...))` (a replacement). Without that split the survey is
  noise and the real sites do not stand out.
- [`scripts/finding_blind_spots.py`](../../../scripts/finding_blind_spots.py)
  -- five probes, one per suspected gap, each printing its own evidence
  against the real tracker set.

### The four gaps

**1. A sheet the name matcher does not recognise is skipped in total silence.**
`sheet_skipped` has ten call sites and **fired zero times** on the 255-tracker
run -- every one of them reports a sheet that was *found and unusable*, never
one that was never considered. 517 sheets are never opened (16 distinct names,
mostly `Lookup List` / `Inventory` / `INV`). One is a real loss: `Annual_2026`
in the 2026 VNCH tracker, **76 rows with `VN_VC###` IDs**, missed because the
static-sheet test is the exact string `"Annual"`. Now [ticket
72](72-sheets-the-pipeline-never-opens.md).

**2. Three defects the pipeline detects, acts on, and never reports.** A
diagnosis date before the date of birth (**8 patients, 7 trackers, 58 rows** --
`MY_PJ025` is diagnosed seven years before birth), stock released to a patient
ID that tracker does not contain (**14 rows, 2 trackers**, DEBUG log only), and
an unrecognised sex value sentinelled to `Undefined` (**1 row**, source cell
`§`). Now [ticket 73](73-three-defects-detected-but-never-reported.md).

**3. The table mixes units and no field says which.**
`validate_allowed_values` iterates `col_values.unique()`, so it emits one
finding per *distinct value* per tracker: 1,170 `province` findings across 124
trackers against **26,124 rows carrying the `Undefined` province sentinel in
those same trackers**. `type_conversion` is per *row* -- 3,579 findings against
3,692 `hba1c_baseline` sentinels, 8,122 against 8,486 `fbg_baseline_mg`. Both
are correct emitters; the table cannot tell them apart, and the Summary sheet
ranks trackers by a count that silently weights one above the other. Recorded
on [ticket 67](67-findings-must-name-sheet-year-month.md), whose `scope` field
is the same field.

**4. [Ticket 68](68-blank-header-emitter-vs-catalogue.md) is probably an
instance of gap 3, but only half of it.** If `blank_header_with_data` counts
columns where ticket 30 counted values, 217-vs-4,572 is ~21 values per column
-- the right order for a sheet. That is a hypothesis recorded on 68, not a
finding: it was not checked, and it does not explain why the code never fires
on ticket 30's headline example or outside 2022.

### Because

The four instances the ticket was written on all pointed at codes. Deriving the
inventory showed the codes are in reasonable shape after [ticket
69](69-miscategorised-and-duplicated-findings.md) -- 37 codes, 35 firing, none
doing twelve jobs any more, names that distinguish. What is *not* in reasonable
shape is everything upstream of a code: selection, replacement and
cross-checking all make decisions that never become findings. That is why
"which defect kind is missing a word" was the wrong question to keep asking,
and it is the answer to the ticket's point 5 (below).

### Rejected

- **Adding codes for the gaps in this session.** The ticket scoped itself to an
  inventory and named gaps, and each gap turns out to carry a real decision --
  what unit to report a skipped sheet in, whether a one-instance defect earns a
  permanent glossary entry, whether to keep publishing an age the workbook's
  own dates contradict. Deciding those inside an audit is how an audit becomes
  a redesign nobody reviewed.
- **"The taxonomy should be complete" (point 5).** Rejected for the value space
  and accepted for the structural space. Clinic mistakes are open-ended -- no
  finite code list covers what a person can type into a cell -- so chasing
  exhaustiveness there buys a longer glossary and no more coverage; a catch-all
  with good detail is the better trade, which is what `type_conversion` and
  `value_not_in_allowed_list` already are. But the set of places the pipeline
  *decides* something is finite, enumerable from the tree, and now enumerated:
  **every point where the pipeline declines to look at data, or replaces a
  value with a sentinel, should emit a finding or be able to say why not.**
  That rule is testable the same way ticket 69's emitter map is -- the
  `--silent` mode is the derivation, and a guard test over it would keep the
  answer true rather than leaving it as this session's snapshot. Not built
  here: it needs the three tickets' decisions first, or it pins today's
  silences as correct.
- **The `INV`/`Inventory` hypothesis.** 112 `INV` and 133 `Inventory` sheets
  are never opened and the product arm reads month sheets only, so a tracker
  keeping stock on a dedicated sheet would lose all of it silently. Measured
  and killed: every tracker with such a sheet still produced product rows, and
  the four `empty_product_data` trackers have no `INV` sheet at all, so that
  code's message is accurate. Recorded because the next person will have the
  same idea.
- **"760 static-sheet rows are dropped without an ID."** The first measurement
  said so; qualifying it killed it. All 760 resolve to sub-header rows (the
  units row: `(dd-mmm-yyyy)`, `Y OR N`, `%`), all-zero template rows, or the
  Annual sheet's second header row. **Zero carry real patient data on the
  current set.** The code path is real -- `read_all_patient_sheets` filters
  null and `#`-prefixed IDs out of the static sheets while the month-sheet path
  reports the identical defects as `missing_required_field` and
  `excel_error_patient_id` -- but it has no current population, so it is
  recorded as an assumption on the map rather than ticketed.
- **A per-site "what happens to the value" column in the inventory.** It is
  judgement, not derivable, and a hand-annotated column keyed to call sites
  drifts the first time one moves. The condition and the category are derived;
  the judgement lives in this resolution and in the spawned tickets.

### Evidence

**Executed.** Every count above comes from the 255-tracker run on the data
drive (`table_findings.parquet`, the per-tracker cleaned and raw parquets) or
from opening the source workbooks with openpyxl -- the sheet census, the 76
`Annual_2026` rows, the eight diagnosis-before-birth patients, the two
unmatched product recipients, the `§` in `2019_Preah Kossamak`, the province
and `type_conversion` unit comparisons, and the `INV` and static-row
hypotheses that died. The one **read** claim is gap 4, explicitly flagged as a
hypothesis on ticket 68.

**Tense.** All counts describe **current behaviour** on the 2026-08-25 run.
Nothing in this session changed the pipeline; the two scripts are new and read
only. `uv run pytest -m "not slow"`: 1,198 passed, 1 skipped.
