---
id: 36
title: Triage the product cleaned-stage mismatches no ticket owns (product_balance, sheet_name, entry_date, units_received, file_name)
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 25
---

## Premise

Rests on three closed decisions:

- [Triage the remaining product cleaned-stage column
  mismatches](21-triage-remaining-product-columns.md) — established the
  product arm's dominant cleaned-stage cause (R's row sort falls back to
  input order whenever `product_entry_date` fails to parse, while Python
  sorts chronologically on correctly parsed dates), added the
  `row_order_divergence` classifier, and explicitly left
  `product_balance`'s residual as "future work" without giving it a ticket.
- [Triage the product_units_released cleaned-stage column
  mismatches](25-triage-product-units-released-cleaned.md) — closed the last
  column that *did* have a ticket, and in doing so found that the remaining
  `unclassified` rows on the product cleaned-stage report belong to no
  ticket at all. It also established the mechanism behind `product_balance`'s
  poor classification rate: `product_balance` is *derived*, not carried —
  both pipelines recompute it as a running total
  (`balance[i] = balance[i-1] - released[i] + received[i]`, Python's step
  2.15 `_compute_running_balance`, R's iterative equivalent) — so under a
  legitimate re-sort the balance cannot travel with its row, and
  `row_order_divergence`'s "does R's value appear elsewhere in Python's
  group" membership test structurally under-detects it.
- [Triage every flagged R/Python difference for both arms](18-triage-comparison-flagged-differences.md)
  — established that per-column counts are judged by pattern, not by
  reproducing the parity-presentation PDF's numbers.

Current counts, measured against the real 248-tracker drive comparison
(`output/comparison/2026-08-12T220324Z/`, `Product (cleaned)` stage):

| Column | `unclassified` |
|---|---|
| `product_balance` | 1,976 (of 2,740; 764 already `row_order_divergence`) |
| `product_sheet_name` | 275 |
| `product_entry_date` | 169 (of 11,727) |
| `file_name` | 60 |
| `product_units_received` | 8 (of 305) |

Two of these have a documented lead but no verdict: `product_sheet_name` is
believed to be R's un-trimmed sheet names (noted in passing by [ticket
17](17-fix-product-row-alignment-and-triage.md), whose count of 201
reproduced the PDF exactly — the count is now 275 against the refreshed
baseline), and `product_units_received`'s 8 are believed to be the
Excel-date-serial-leak pattern [ticket
24](24-triage-remaining-raw-column-residual.md) confirmed for the raw stage,
reaching the cleaned stage too. Neither was ever decided under the standing
bar. `file_name` and `product_entry_date`'s residual have no lead at all.

This ticket exists because the destination requires **every** Python/R
difference documented and explicitly decided; these rows were reported as
`unclassified` on every run while each triage ticket worked only the columns
its own title named.

## Question

Explain and decide each of the five columns above. `product_balance` is the
bulk of the work and the one with a known mechanism but no adequate
detection: decide whether its residual is fully accounted for by the
already-established sort-order divergence (in which case the open question is
how to *evidence* that for a derived running total — e.g. comparing
end-of-group balances, or reconstructing R's order and re-deriving — rather
than by value membership), or whether some part of it is a genuine divergence
the sort-order story hides.

If the work does not converge in one session, split rather than sprawl.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: explaining
a difference and naming a cause is only half the job. Each must carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Where
Python turns out to be wrong or to be losing information the source file
carried, fix the pipeline rather than labelling the symptom. A cause
genuinely undecidable on the available evidence is recorded as an open
question, not closed with a label.
