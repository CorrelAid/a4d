---
id: 25
title: Triage the product_units_released cleaned-stage column mismatches
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
