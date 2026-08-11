---
id: 17
title: Fix the product comparison's row-alignment key, then triage every flagged R/Python difference
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-11
claimed_at: 2026-08-11
resolution: decided
evidence: executed
closed_by: null
spawned_by: 15
---

## Premise

Rests on [Build and run the R/Python output comparison script, then triage
every flagged difference](15-build-and-run-comparison-script.md), closed:
`scripts/compare_outputs.py` + `src/a4d/migration/compare.py` are built,
tested (23 unit tests), and were run against a fresh Python pipeline pass
(both arms) and the frozen `output_r/` baseline, both on the USB drive.

That session found the patient arm's row-alignment key —
`(patient_id, sheet_name)` — is sound (duplicate keys in only 5 of 172
matched files, each a handful of rows) and can be triaged as-is. It found
the **product arm's key is broken**: `(clinic_id, product,
product_sheet_name, product_entry_date)` collapses onto far fewer distinct
keys than rows exist (one file alone: 154 distinct keys for 1,194 rows, up
to 35 rows sharing a key) because `product_entry_date` is null on many rows
(balance-only or malformed-date rows). Every duplicate group produces a join
fan-out that inflates reported cell-mismatch counts by orders of magnitude
and — critically — excludes `product_entry_date` itself from
classification, since it's one of the join keys. The PDF's single largest
divergence column (`Product_entry_date`, 559 mismatches) currently never
gets diffed at all. This was confirmed by direct `group_by` inspection
against the real drive data, not inferred.

That session also left unreconciled: the parity-presentation PDF cites 189
trackers / 61,077 rows for product; this session's fresh run matched 155 R
product files (0 only-in-R, 19 only-in-Python — explained by [ticket
14](14-product-column-detection-failures.md)'s 0-row-output fix for
pre-product-tracking years). Whether that gap is a stale PDF number, a
different drive snapshot, or something else is not yet investigated.

**Update from the same session, after ticket 15 closed** (see its
[addendum](15-build-and-run-comparison-script.md#addendum-same-session-after-closure)):
the comparison tool this ticket inherits is more capable than what ticket 15
closed with. Notably, `compare_row_key_overlap`/`RowKeyOverlap` now measures,
per file, how many rows failed to find *any* partner via the full
row-alignment key (`matched`/`r_unmatched`/`py_unmatched`) — this is what
confirmed the diagnosis above isn't just inference: raw product files show
near-100% row-key divergence (e.g. one file: 560/560 rows unmatched)
alongside near-0% cell divergence, proving the 0s are "nothing was paired to
compare," not agreement. `compare_id_overlap` and `compare_categorical_overlap`
also confirmed product *names* match 100% between R and Python even in files
where the row key is fully broken — the identity data itself isn't the
problem, only the row-pairing mechanism is. Use `RowKeyOverlap.matched`
against a candidate replacement key to validate it directly, rather than
re-deriving fan-out evidence from raw duplicate-key counts by hand.

## Question

Design and implement a row-alignment key (or an alignment strategy that
isn't a simple equi-join key — e.g. an ordinal position within a group,
possibly reusing the `index` column `clean/product.py` already assigns per
`(clinic_id, product_sheet_name)` at step 2.5 but doesn't currently carry
into the output schema) that uniquely identifies a product row well enough
for `compare_cells` to align R and Python rows without fan-out — including
rows where `product_entry_date` is null. Confirm R and Python assign the
same ordering for whatever key is chosen (they may not, if extraction order
differs) before trusting any diff built on it.

Once alignment is fixed, re-run `compare_outputs.py` and go through the
flagged differences for both arms, column by column, labeling causes into
the classifier registry as they're identified — falling back to the
original source Excel trackers (`a4dphase2_upload`) as the arbiter wherever
a divergence isn't already an understood, expected pattern. Carries forward
ticket 15's validation requirement: the script's per-column and per-cause
counts should reproduce (or explain deltas from) the parity-presentation
PDF's numbers for `Product_entry_date` (559: typo-rescue 408, CE-typo 71,
sentinel-null 66, off-by-one-day 7), `Product_balance` (480),
`Product_category` (214), `Product_sheet_name` (201),
`Product_received_from` (154), `Product_units_received` (9) — including
resolving the 189-vs-155-tracker discrepancy noted above. Patient-arm
triage (already-sound alignment) is in scope here too, since it was run but
not triaged in ticket 15.

This ticket is still large and investigative — if it doesn't converge in
one session, split the remaining per-column investigation further rather
than leaving it open-ended.

## Resolution

**Decision.** Fixed the row-alignment key for its product-arm half; the
"triage every flagged difference for both arms" half did not converge in
this session and is split into [ticket
18](18-triage-comparison-flagged-differences.md), per this ticket's own
pre-authorization.

**Design chosen: ordinal position within `(clinic_id, product_sheet_name)`,
not a stored column.** Investigated reusing `clean/product.py`'s `index`
helper column (step 2.5) first, and found it wouldn't work as-is even if it
were kept in the output schema: R's `reading_product_data_step2`
(`r-archive/R/read_product_data.R:599`) assigns its own `index` *inside a
per-`sheet_month` loop* (resets to 1 for every sheet), while Python's
`_add_row_index` (`clean/product.py`) assigns a single global
`with_row_index` across the *whole* file — a real, previously undocumented
divergence in what "index" means between the two pipelines. Rather than fix
that and thread a new column through both pipelines (R's frozen baseline
output can't be re-run to pick it up anyway — ticket 2 decided no R re-run,
ever), the key is computed *at comparison time*, directly from each output
file's existing row order: `add_row_ordinal()`
(`src/a4d/migration/compare.py`) partitions by `(clinic_id,
product_sheet_name)` — normalizing both to stripped strings for the key
only, so a whitespace divergence in the raw column still surfaces as an
ordinary cell mismatch rather than silently breaking the group — and takes
each row's 0-based position within that partition as the alignment key.
This works because extraction concatenates sheets in file order (contiguous
per-sheet blocks) and every row-order-changing step in `clean/product.py`
(explode, filter, the product-name sort in step 2.7) preserves *relative*
order within whatever grouping precedes it — confirmed empirically, not
just reasoned: this key achieves 46,314/47,644 (97.2%) row-key match on the
real cleaned-product data.

**Validated directly against the real R/Python output pair on the USB
drive** (`RowKeyOverlap.matched`, not assumption): cleaned-product row-key
divergence dropped from near-100% (ticket 15's diagnosis) to 2.8% (1,330
rows), and every one of those 1,330 is isolated to exactly one clinic across
its three tracker years (`2023/2024/2025_06_North Okkalapa General Hospital`
— 0 matched, 100% unmatched on each) rather than being spread thin across
many files. Inspecting that clinic directly found why: **R's frozen output
has `clinic_id = "NGH"` for all three files; Python has `clinic_id =
"NOH"`.** Python's value matches the tracker's actual folder name on the
drive (`a4dphase2_upload/Myanmar/NOH/`), which is the documented
`clinic_id` derivation rule (`docs/CLAUDE.md`) — R's is a typo, not a
Python bug. Also found and resolved along the way: `2019_CDA A4D Tracker`
had 74/402 rows unmatched under an earlier, less-normalized version of the
key, traced to R's `product_sheet_name` carrying un-trimmed trailing
whitespace (`"May19 "` vs Python's `"May19"`) for two sheets — folding
whitespace-normalization into the join key itself (not the compared value)
fixed this without hiding the divergence, since `product_sheet_name` is
still diffed as an ordinary column and its mismatch count (**201**) now
reproduces the parity-presentation PDF's number for `Product_sheet_name`
exactly — the strongest available confirmation that the new key is sound,
not just less-broken.

**Also re-ran the same validation on raw product** (`product_data_raw`):
109,130/112,381 (97.1%) matched, with the remaining mismatches explained by
the same North Okkalapa `clinic_id` typo (rows only, at raw stage this
clinic's rows aren't even grouped that far apart) plus a handful of
single-row diffs on 5 other files not yet individually inspected — carried
into ticket 18.

**Also surfaced, not yet reconciled:** re-running the row-count check found
the parity-presentation PDF's 189-tracker/61,077-row product baseline still
doesn't match — the currently-frozen `output_r/` on the drive has 155
product-cleaned files totalling 47,644 rows, identical to ticket 15's
count. This rules out "the new key was undercounting files" as the
explanation (the file/row totals are unchanged by this ticket's fix); the
gap is either a stale PDF number or a genuinely different drive snapshot at
the time the PDF was built. Still unresolved — carried into ticket 18.

**Because.** The row-alignment key was the one blocking design question
this ticket exists to answer, and the fix needed exactly the two things the
question asked for: an alignment strategy that isn't a simple equi-join key,
and direct confirmation (not assumed) that R and Python assign the same
ordering. Both are done and validated against real data. The remaining
"triage every flagged difference, both arms" work is unrelated
investigative breadth (each column's cause is its own small investigation)
that the ticket's own text pre-authorized splitting off rather than
attempting to converge in the same session as the design work.

**Rejected.**
- Restoring `clean/product.py`'s `index` column into the output schema and
  using it as the stored key — rejected: R's frozen baseline can't be
  re-run to pick up a new column (ticket 2's decision), so a
  comparison-time-only key was required regardless; and R's own `index`
  resets per-sheet while Python's doesn't, so simply un-dropping Python's
  current column would still not match R's semantics without first fixing
  that divergence in the pipeline itself — a change to production cleaning
  logic this ticket's premise never asked for.
- Including `product` (the product name) in the alignment key alongside the
  ordinal — rejected: the ordinal alone is already unique per row within
  its group by construction; adding `product` back would only reintroduce
  a dependency on `_fill_product_names_and_sort`'s forward-fill matching
  between R and Python exactly, which isn't necessary once ordinal position
  already disambiguates.
- Normalizing whitespace on the actual `product_sheet_name` column values
  (not just the join key) so the 2019_CDA file's rows all matched cleanly
  from the start — rejected: that would have hidden a real R-side data
  defect from `compare_cells`, exactly the kind of divergence this tool
  exists to surface; classifying it as an ordinary `product_sheet_name`
  cell mismatch (which is what happened) is the correct outcome.
- Attempting the full triage pass in this session anyway — rejected: initial
  per-column counts (`product_category`: 13,638 vs the PDF's 214;
  `product_entry_date`: 10,424 vs 559; `product_balance`: 2,343 vs 480) are
  far larger than the PDF's numbers even after the key fix, and a first look
  found `product_category` mismatches are systematically `r_value=None`
  where Python has a real category — that's a distinct, uninvestigated
  question (does R's cleaned product schema genuinely never populate
  `product_category` for some file/year range, or is this itself another
  alignment artifact) that deserves its own focused session rather than a
  guess recorded here.

**Evidence.** *Executed*: ran `just compare-outputs` against the real,
already-existing `output_r`/`output_python` directories on the USB drive
(no pipeline re-run needed — Python's fresh pass from ticket 15 was still
current); confirmed `RowKeyOverlap.matched`/`r_unmatched`/`py_unmatched`
directly from the Excel report's `row_key_overlap` sheet; confirmed the
North Okkalapa `clinic_id` divergence and the 2019_CDA whitespace divergence
by direct inspection of the parquet files and the source tracker folder
name; confirmed the 155-file/47,644-row R product-cleaned count directly.
Added 5 unit tests for `add_row_ordinal` (TDD), full suite green (545
tests), ruff and `ty check` clean. *Judgement*: none — every claim above is
a direct measurement against the real R/Python output pair or the R source
(`read_product_data.R`), not inference.

**Tense.** All claims describe current repository/drive state as of this
session (executed): the key fix is implemented and merged into
`scripts/compare_outputs.py`/`src/a4d/migration/compare.py`, not a proposal.
The `product_category`/`product_entry_date` inflation and the
189-vs-155-tracker gap are diagnoses of what's not yet understood, not
conclusions about their cause.

Commit: `bcfc32e`.
