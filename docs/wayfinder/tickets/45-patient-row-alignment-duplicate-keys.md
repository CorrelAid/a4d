---
id: 45
title: Give the patient comparison an ordinal row key, so duplicated patient IDs stop faking mismatches
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 43
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches (round
3)](43-triage-patient-raw-residual-3.md), closed, which measured this: **808
of the 1,409 remaining unclassified patient raw-stage mismatches (57%) sit in
just three files**, and all three are files where the row-alignment key
`(patient_id, sheet_name)` is not unique.

Ticket 43 fixed a genuine Python defect in the worst of them -- 24 invented
rows in `2024_Vietnam National Children`'s `Jul24` -- and after that fix both
sides hold the *same* row set: `row_key_overlap` for that file reads
`matched: 903, r_unmatched: 0, py_unmatched: 0`. Yet 770 cell mismatches
remain in it. They are join fan-out: the `Jul24` sheet lists 27 patient IDs
twice (verified in the source workbook -- two lists spliced together, the
numbered column running 1..78 while the IDs repeat), so an equi-join on the
key pairs each duplicate every way round, and half those pairings compare
unrelated physical rows.

Also rests on [Fix the product comparison's row-alignment key](17-fix-product-row-alignment-and-triage.md),
closed, which solved exactly this for the product arm with `add_row_ordinal()`
-- ordinal position within a group, computed at comparison time and never
stored, because R's frozen baseline cannot be re-run to pick up a new column.
That ticket took product's cleaned-stage row-key match from near-0% to 97.2%
and is the precedent to follow rather than re-derive.

Overturning ticket 43's phantom-row fix would void this ticket rather than
require rewriting it: the fan-out measurement above was taken after that fix,
and before it the same file's row sets did not even match.

## Question

Extend the ordinal row-alignment strategy to the patient arm so duplicated
`(patient_id, sheet_name)` keys align positionally instead of fanning out.

Concretely:

- The three affected files are `2024_Vietnam National Children` (770
  unclassified), `2023_Vietnam National Children` (22) and `2018_Penang
  General Hospital` (16). Confirm that list by measurement rather than
  trusting it -- it was derived from one run.
- Decide whether patient should adopt `add_row_ordinal` as its key
  unconditionally (as product did) or only where the natural key is
  ambiguous. Product had no usable natural key at all; patient's is unique in
  all but three files, so switching everything to positional alignment trades
  a real identity check for a positional one across 250+ files that do not
  need it. Ticket 15 established patient's key *is* sound in general.
- Whatever is chosen, validate it the way ticket 17 did: by
  `RowKeyOverlap.matched` and by per-column counts moving in the direction the
  mechanism predicts, against the real drive data -- not by unit tests alone.

Note the duplicated IDs are themselves a **source defect**, not something the
pipeline should silently reconcile: `Jul24` genuinely lists patients twice
with different data. That belongs in [ticket
40](40-source-defect-findings-report.md) as a finding, and this ticket should
hand it over rather than absorb it.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: a
realignment that merely makes counts fall is not a result. Show that the rows
now being compared are the rows that should be compared, and say explicitly
what the residual after realignment is.
