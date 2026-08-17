---
id: 45
title: Give the patient comparison an ordinal row key, so duplicated patient IDs stop faking mismatches
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-17c
claimed_at: 2026-08-17
resolution: decided
evidence: executed
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

## Resolution

**Decision.** Patient keeps `patient_id` + `sheet_name` as its row-alignment
key and gains an ordinal *within* that key as a tie-breaker -- not product's
unconditional positional key. The tie is broken by **content, not position**,
because within one patient-and-sheet group the row order carries no meaning
and the cleaned stage demonstrably reorders. Applied to both patient stages,
raw and cleaned. Patient raw-stage unclassified fell **1,409 -> 601 (-57%)**
and cleaned-stage **9,392 -> 8,383 (-11%)**, measured against baseline run
`output/comparison/2026-08-17T192144Z`; the new baseline is
`output/comparison/2026-08-17T202809Z`.

**1. How widely: identity everywhere, position never.** The user set the rule
directly -- `patient_id` is the main key, and if it does not match something is
very wrong; `sheet_name` stays because monthly is the granularity of the data.
So `add_row_ordinal` is grouped by the identity key itself rather than by a
whole sheet: in the 250+ files whose key is unique every ordinal is 0 and
behaviour is unchanged, and the ordinal only does work where a sheet lists a
patient twice. Product's `(clinic_id, product_sheet_name)` grouping is
untouched.

The two strategies are now named rather than inferred: `RowAlignment.IDENTITY`
vs `RowAlignment.POSITIONAL` on a new `Stage` dataclass
(`scripts/compare_outputs.py`), replacing a 9-field positional tuple in which
the alignment key was one unlabelled slot. `detect_row_order_divergence` --
ticket 21's `order_group_cols` diagnostic, which asks whether a mismatched
value appears elsewhere in its group -- is derived from the alignment rather
than set per stage, and is off for patient: under IDENTITY a group is one
patient on one sheet, where that test would label noise as understood.

**2. The three-file list was right for raw and incomplete for cleaned.**
Measured per file across both output directories rather than taken on trust
(the ticket's list came from one run): at the **raw** stage exactly the three
named files have a two-sided duplicate key -- `2024_Vietnam National Children`
(21 keys, 42 excess pairings), `2023_Vietnam National Children's` (1) and
`2018_Penang General Hospital_DC` (1). At the **cleaned** stage there are
**five**: those three plus `2023_NPH` (one key repeated 4 times) and
`2026_Surat Thani`. Two further files (`2026_Preah Kossamak`, 98 rows;
`2026_Quirino`, 5) have R-side rows keyed `patient_id = "#REF!"` with no
Python counterpart -- unmatched, never fanned out, and unaffected by this
change.

**3. Position is the wrong tie-break at the cleaned stage -- measured, not
assumed.** Before wiring anything, both pairings were brute-forced over every
two-sided duplicate group in the real data. At raw, occurrence order is already
the mismatch-minimising pairing in all 23 groups (256 differing cells either
way) -- both pipelines emit the rows in source order. At cleaned it is not: in
9 groups R and Python emit the copies the other way round, and `2024_Vietnam
National Children` alone scores 340 differing cells under positional pairing
against 27 under the best pairing. `align_duplicate_rows`
(`src/a4d/migration/compare.py`) therefore pairs a duplicate group by minimum
differing cells, brute-forced (groups are at most 4 rows; bounded at 6), and
keeps positional order unless another pairing is *strictly* better.

**Why this is not just minimising the count.** Raw is the control: there,
positional order is verifiable ground truth, and content matching reproduced it
exactly, changing nothing (26,697 mismatches before and after). The most the
tie-break can be hiding is the cleaned stage's 351-cell difference between the
two pairings, inside groups that are the same patient on the same sheet by
construction.

**4. The rows now compared are the rows that should be compared.**
`row_key_overlap` is byte-identical before and after on both stages (raw
82,653 matched / 118 R-unmatched / 12 Python-unmatched; cleaned 81,738 / 121 /
15). No pairing was gained or lost -- only *which* row pairs with which inside
a duplicate group changed. Per file, raw unclassified went 770 -> 0, 22 -> 0
and 16 -> 0 in the three files; cleaned went 789 -> 7 (VNC 2024), 146 -> 2
(NPH), 73 -> 32 (Surat Thani), 39 -> 17 and 148 -> 128. Product is a
regression check and is unchanged to the cell (cleaned 22,716 mismatches, raw
112, row-key divergence 0).

**5. Residual after realignment.** Raw: **601 unclassified**, the long tail
[ticket 46](46-triage-patient-raw-residual-4.md) owns; nothing left in the
three duplicate-key files. Cleaned: **8,383 unclassified**, no ticket's scope
yet -- the remaining 7 in VNC 2024 are `hba1c_updated_date` (5) and
`fbg_updated_date` (2).

**6. Handed over, not absorbed.** The duplicated IDs are a source defect: 21
patients listed twice on `2024_Vietnam National Children`'s `Jul24`, one on
`2023_Vietnam National Children's` `Jun23`, one on `2018_Penang General
Hospital_DC` `Oct18` -- derived from Python's raw output, not from the ticket's
prose. Recorded on [ticket 40](40-source-defect-findings-report.md).

Chasing why the cleaned stage has *two extra* duplicate files surfaced
something else: in `2023_NPH`, four distinct raw identities (`KH_NPH026`,
`KH_NPH027`, `KH_NPH028`, `KH_NPH029`) arrive at the cleaned stage as one
`KH_NPH02`. Across all 254 trackers, 4 files lose 9 identities this way. R does
the same thing on the same file, so it is not a Python regression and not an
R/Python divergence -- which is exactly why no comparison-based ticket would
ever have found it. Split into [ticket
47](47-patient-ids-merged-at-cleaning.md) rather than chased here.

**Because.** The ticket's open question was how widely to adopt positional
alignment, and the answer is nowhere: product needed a positional key because
it had no usable natural key, whereas patient's key is unique in 249 of 254
files, so the only thing missing was a tie-break. Grouping the existing
`add_row_ordinal` by the identity key gives that tie-break using the exact
mechanism ticket 17 already validated, without trading an identity check for a
positional one anywhere.

**Rejected.**
- *Product's unconditional positional key for patient.* Would discard
  `patient_id` from the alignment in 249 files that do not need it, and import
  product's cascade failure mode (ticket 21's `row_order_divergence`), where a
  single row-membership difference shifts every later row in the group.
- *Switching strategy per file where the key is ambiguous.* Needs a file list
  -- derivable, but still machinery -- and buys nothing: grouping by the
  identity key already degenerates to today's behaviour wherever the key is
  unique.
- *Occurrence-order tie-breaking (the ticket's own proposal).* Correct at raw,
  measurably wrong at cleaned: 9 groups pair the wrong two copies, leaving 351
  false mismatches. Kept as the fallback for uneven or oversized groups.
- *Applying this to raw only, as the ticket's title scopes it.* The defect and
  the key are shared by both stages, and the cleaned stage held the larger
  share. It does move counts on a stage other tickets closed against -- flagged
  below.
- *Chasing the `KH_NPH02` identity merge here.* A production data-correctness
  bug in cleaning, not a comparison-alignment question, and not an R/Python
  divergence at all.

**Evidence.** All **executed**. Duplicate-key incidence and fan-out counted per
file with duckdb directly against `output_r`/`output_python` on the USB drive
(245 R files, 254 Python); both pairings brute-forced over every two-sided
duplicate group in the real parquets; a full `just compare-outputs`-equivalent
run before and after each of the two designs, with per-file and per-column
counts read from the resulting workbooks; `row_key_overlap` compared before and
after; the `KH_NPH02` collapse confirmed in both R's and Python's own cleaned
output and traced to 4 files / 9 identities across the whole set. TDD: 8 new
tests written before the implementation (`TestPatientOccurrenceOrdinalKey`,
`TestStageWiring`). Full suite 727 passed, 1 skipped; ruff check, ruff format
and `ty check src/` clean. One **read**-only claim: `clean/patient.py`'s
`patient_id` normalization regex was read but *not* confirmed to be the cause
of the `KH_NPH02` merge -- it does not obviously produce it, which is why
ticket 47 exists rather than a fix.

**Tense.** Every count describes current behaviour after the change, except the
1,409 / 9,392 / 27,510 / 114,473 starting figures, which describe baseline run
`2026-08-17T192144Z`.

**Note for the tickets that measured the cleaned stage.** Tickets 28, 29, 37
and 38 recorded cleaned-stage counts taken under the old key. Their causes are
unaffected (nothing they diagnosed lives in a duplicate-key group), but their
numbers no longer reproduce; [ticket
44](44-triage-cleaned-fbg-r-null-residual.md) should re-measure against
`2026-08-17T202809Z` rather than the figures in its premise.

Commit: see branch `migration`.
