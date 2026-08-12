---
id: 25
title: Triage the product_units_released cleaned-stage column mismatches
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12h
claimed_at: 2026-08-12T22:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 21
---

## Premise

Rests on [Triage the remaining product cleaned-stage column
mismatches](21-triage-remaining-product-columns.md), closed: five sibling
cleaned-stage columns (`product_balance`, `product_received_from`,
`product_released_to`, `product_remarks`, `product_units_received`) turned
out to be dominated by one root cause — R's per-(clinic, sheet, product)
row sort falling back to raw input-row order whenever
`product_entry_date` fails to parse (a near-universal failure for several
major clinics, confirmed against real data), while Python correctly sorts
chronologically. Since the row-alignment key (`add_row_ordinal`) is purely
positional, that legitimate order difference cascades into value-level
mismatches on every column compared through it. A `row_order_divergence`
classifier (`PRODUCT_ROW_ORDER_CLASSIFIERS` in
`src/a4d/migration/compare.py`) now detects this directly for value columns
whose mismatched R value reappears elsewhere in Python's own group.

`product_units_released` was never assigned to any ticket: ticket 21 named
six specific columns and this wasn't one of them, and [ticket
24](24-triage-remaining-raw-column-residual.md) only covers this column's
much smaller *raw*-stage residual (24 rows, a distinct "unexplained value
pattern" ticket 24 is still chasing) — not the cleaned stage. On the current
248-tracker `output_r`/`output_python` comparison
(`output/comparison/2026-08-12T084709Z/` as of this writing, or re-run `just
compare-outputs`), `product_units_released` has 2,144 cleaned-stage
mismatches, the second-largest count among all product columns after
`product_entry_date`.

## Question

Pull `product_units_released`'s flagged cleaned-stage mismatch rows and
determine whether they're explained by the same row-order-divergence root
cause ticket 21 found for its five sibling columns (plausible but
unverified — check whether wiring `product_units_released` into
`PRODUCT_ROW_ORDER_CLASSIFIERS` explains most of the count, and whether
end-of-group balance/totals are preserved the way ticket 21 verified for
`product_balance`), or whether it's a distinct pattern requiring its own
explanation. If it's the same cause, wiring the existing classifier may be
enough; if not, fall back to the real source Excel trackers
(`a4dphase2_upload`) as the arbiter per the destination's standing
verification bar.


## Standing bar (added 2026-08-12g, applies to this ticket)

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Noting
"Python has A where R has B" and adding a classifier is not a decision in
favour of A. Where Python turns out to be wrong or to be losing information
the source file carried, fix the pipeline rather than labelling the symptom
— see [ticket 27](27-triage-patient-raw-residual.md), where exactly that
turned a labelling job into a real extraction fix. A cause genuinely
undecidable on available evidence is recorded as an open question, not
closed with a label.

## Resolution (session-2026-08-12h)

**Decision.** All 2,144 cleaned-stage `product_units_released` mismatches are
the same row-order divergence [ticket 21](21-triage-remaining-product-columns.md)
root-caused for this column's five siblings — not a distinct pattern.
**Python is doing the right thing**; R is not. No pipeline change. The
comparison tool's column-to-registry map was the only defect: this column
carried `WIDE_FORMAT_FRAGMENT_CLASSIFIERS` alone (raw-stage-only, ticket 24)
and so reported every cleaned-stage row as `unclassified`. Wiring
`PRODUCT_ROW_ORDER_CLASSIFIERS` alongside it takes the column from
2,144 `unclassified` to 2,144 `row_order_divergence` / **0 unclassified**.

**Because.** Three independent checks, each executed against the real
248-tracker `output_r`/`output_python` pair on the drive:

1. **Nothing is added, lost or altered.** Across all 229 files and all 2,283
   `(clinic_id, product_sheet_name)` groups, R's and Python's *multisets* of
   `product_units_released` values are byte-identical (0 differing groups).
   Per-file totals agree everywhere too — the report's `totals` sheet lists
   no `product_units_released` row for any of the 229 files, while listing 34
   for other columns.
2. **Row identity survives the re-sort.** Across all 11,649
   `(clinic_id, product_sheet_name, product)` groups, the multiset of
   `(product_units_released, product_released_to)` *pairs* is identical
   between R and Python (0 differing groups) — every unit release keeps its
   recipient. The difference is purely which position within the group each
   row occupies. (Group keys whitespace-normalized for this check, including
   embedded line breaks, per ticket 21's `\r\n`-vs-`\n` product-name finding;
   without that normalization 430 groups appear to differ under different
   names for the same group.)
3. **Python's order is the correct one, per source.** In the worst-affected
   file/sheet (`2024_Mahosot Hospital A4D Tracker`, `Jul24`, product
   `Accu-Chek Performa Test Strips (50s/ bottle)`, 69 differing rows), R's
   output has `product_entry_date = null` on **every** row of the group,
   while Python has real parsed dates. Read directly from the source Excel
   (`a4dphase2_upload/Laos/MHS/2024_Mahosot Hospital A4D Tracker.xlsx`,
   sheet `Jul24`, header row 15): the "Entry Date" column is fully populated
   with genuine `datetime` values (2024-07-01, 2024-07-23, 2024-07-19, ...).
   So R falls back to raw input order because of its own date-extraction gap
   — the same gap already root-caused as `r_value_missing` (ticket 18) — and
   Python sorts chronologically on dates that really are in the file. Both
   sides implement the same documented rank algorithm; only the date input
   differs.

**Rejected.**
- *Closing on the classifier hit alone.* 100% of the rows set
  `row_order_candidate`, which looks conclusive but isn't: that flag only
  asks whether R's value appears **anywhere** in Python's group, and on a
  numeric column full of repeated small values (0, 2, 4, 8) it false-fires
  easily — a risk `CLASSIFIERS_BY_COLUMN` already documents for
  `product_received_from`. Checks 1 and 2 above are what actually establish
  the claim; the classifier is only how the finding is recorded.
- *"Fixing" Python toward R's order.* R's order is an artifact of failing to
  read dates the source file plainly contains. Sorting to match it would
  discard correct information — the ticket-27 precedent inverted.
- *Ordering row-order ahead of wide-format in the registry.* Measured both
  orderings against the real data: identical results (the wide-format prefix
  heuristic matches nothing at the cleaned stage, and the raw stage's 5
  `wide_format_fragment_truncated` rows are unaffected either way).
  Wide-format kept first anyway, since it is source-verified and
  stage-specific while row-order is the loose one.
- *Treating the `product_balance` re-pairing as this ticket's problem.*
  Investigating check 2 surfaced that `product_balance` does **not** travel
  with its row (R has `(released 8.0, balance 314.0, LA-MH063)` where Python
  has `(released 8.0, balance 168.0, LA-MH063)`). Traced to
  `_compute_running_balance` (`src/a4d/clean/product.py` step 2.15): balance
  is *derived* as `balance[i-1] - released[i] + received[i]` on both sides,
  never carried from the source cell, so it cannot follow a row under a
  re-sort by construction. That is ticket 21's known, unowned
  `product_balance` residual rather than new data loss — handed to [ticket
  36](36-triage-product-cleaned-unclassified-residual.md) with the mechanism
  recorded, not resolved here.

**Evidence: executed.** Every count above comes from running against the real
drive data, not from reading the previous run's report: three ad-hoc analysis
passes over all 229 file pairs, one source-Excel read, and a full
`just compare-outputs` re-run confirming the before/after
(`output/comparison/2026-08-12T220324Z/`). The one *read* claim is that R's
rank algorithm matches Python's, inherited from ticket 21 rather than
re-derived from R's source here; it is not load-bearing — checks 1-3 stand
without it.

**Tense.** All claims describe current behaviour of the code on disk and of
the frozen R baseline. The only change made is to the comparison tool's
classifier wiring; no pipeline code was touched, so no pipeline output moved.

**Changes.** `scripts/compare_outputs.py`: `product_units_released` now maps
to `WIDE_FORMAT_FRAGMENT_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS`.
`tests/test_migration/test_compare.py`: new `TestClassifiersByColumnWiring`,
written first and confirmed failing — one test pins that *every* product
column aligned through the positional row-ordinal key carries the row-order
classifier (so the same silent omission cannot recur on another column), one
pins this column's own classification. Full suite 606 passed / 1 skipped,
`ruff check`, `ruff format --check`, `ty check src/` all pass.
