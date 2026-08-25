---
id: 70
title: What can go wrong in a tracker that the pipeline never reports at all?
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 16
---

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
