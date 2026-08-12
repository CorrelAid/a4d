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

## Addendum (session-2026-08-12h): the balance mechanism, measured

Follow-up investigation after ticket 25 closed, prompted by the user asking
whether `_compute_running_balance` is itself wrong. Findings are verified,
the decision is **not** made — that is still this ticket's job.

**There is no defect in `_compute_running_balance`.** It mirrors R exactly.
R's `compute_balance` (`r-archive/R/helper_product_data.R:437-481`) loops
over rows and, for every `"change"`/`"end"` row, *overwrites*
`product_balance` with `previous_balance - released + received`; Python's
step 2.15 does the same via a per-group cumsum seeded from the group's first
(`"start"`) row. **Both pipelines discard the source spreadsheet's recorded
balance on non-start rows by design** — this is the original R design, not a
migration artifact.

**What actually differs is the order the ledger accumulates in**, which is
downstream of step 2.7's sort, not of the balance step. Measured on
`2024_Mahosot Hospital`, sheet `Jul24`, `Accu-Chek Performa Test Strips
(50s/ bottle)` (43 rows), against the real source Excel:

- The source's own Balance column is internally consistent **in data-entry
  order** (322, 314, 310, 306, 302, 300, 293, 290, ... — each equals the
  previous minus that row's Units Released).
- R, accumulating in entry order, reproduces the source's balances **exactly**
  (multiset equal, row for row).
- Python, accumulating in chronological order, emits 322, 314, 306, 302,
  298, 294, ... — a self-consistent ledger whose intermediate values appear
  **nowhere in the source file** (source has 172/182/186/202...; Python has
  176/178/183/187...).
- **Both end at 139.0**, matching the source's closing balance.

Note the source's entry order here is *not* chronological (the clinician
entered 2024-07-23 before 2024-07-19), so the source's own Balance column is
a ledger in data-entry order, not a stock history over time.

**Breadth, across all 11,649 `(clinic, sheet, product)` groups:**

| Measure | Groups | Share |
|---|---|---|
| Balance multiset identical R vs Python (no divergence at all) | 11,117 | 95.4% |
| Closing (end-of-group) balance identical | 11,491 | 98.6% |
| Closing balance differs | 158 | 1.4% |

Of those 158, **153 are float-accumulation noise where Python is the cleaner
side** (R `-1.5999999999999999` vs Python `-1.6`; Python's cumsum applies
`.round(10)`, R's loop rounds nothing). The other **5 are R being corrupted
by an Excel date serial leaking into the arithmetic** — e.g. 2019 Penang
General Hospital, `Accu-Chek Performa Glucometer Set`: R's closing balance is
**43,572** where Python has **6.0** (43,572 is a 2019 date serial); same
shape for four Sultanah Bahiyah groups. This is the stray-date-typed-cell
pattern [ticket 24](24-triage-remaining-raw-column-residual.md) already
root-caused, now shown to corrupt R's *balance totals*, not just individual
cells. **Python's closing stock is correct in every group.**

**The open question this ticket must decide** is therefore not "is Python
buggy" but **what `product_balance` is supposed to mean on a non-closing
row**, given it is written per-row to BigQuery's `product_data` table and has
no consumer inside the Python codebase (verified by grep — only
`clean/product.py` and the schema reference it):

1. *Keep current behaviour* — balance accumulates in chronological order, so
   it is coherent as a stock-over-time series and the closing figure is
   right, but an individual row will not match the tracker cell a human
   opens next to it.
2. *Carry the source's recorded balance*, computing only where absent —
   maximally faithful per row, but propagates the source's own arithmetic
   mistakes and abandons R's design.
3. *Accumulate in entry order, output in chronological order* — each row
   keeps the balance the tracker recorded while rows still display
   chronologically; the balance column then reads non-monotonically down the
   output.

Whichever is chosen, consider logging a data-quality error when the
recomputed balance disagrees with the source's recorded balance: nothing
currently surfaces that, and it is the signal that would have exposed the R
date-serial corruption above from the tracker side.
