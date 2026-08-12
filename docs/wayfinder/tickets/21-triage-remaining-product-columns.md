---
id: 21
title: Triage the remaining product cleaned-stage column mismatches (balance, received_from, released_to, remarks, units_received, product)
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12
claimed_at: 2026-08-12T10:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 18
---

## Premise

Rests on [Triage every flagged R/Python difference for both arms, and
resolve the 189-vs-155-tracker discrepancy](18-triage-comparison-flagged-differences.md),
closed: the product row-alignment key is sound (ticket 17, 97.2% match) and
`product_category`/`product_entry_date` are already root-caused and
classified. This ticket inherits the remaining `product_data_cleaned`
per-column mismatch counts from that session's `just compare-outputs` run,
unexamined: `product_balance` (2,343), `product_received_from` (330),
`product_released_to` (3,834 — not among the causes the parity-presentation
PDF named at all, so there is no prior baseline count to compare against),
`product_remarks` (66), `product_units_received` (265), and `product` itself
(652 — the product name/identity column disagreeing is a different kind of
divergence than a value column and may need its own explanation).

Also rests on the 189-vs-155-tracker finding: per-column counts are not
expected to reproduce the PDF's numbers exactly, since the PDF's baseline
population is provably different and unreachable — the bar is explaining
each divergence's pattern, not hitting an exact count (per ticket 18's
resolution).

**Updated same day, per ticket 18's addendum:** R and Python were both
re-run against the current 248-tracker production set (up from 177) and
`output_r/` now holds that fresh R output (old baseline preserved at
`output_r_155_frozen_backup_2025-11-14`). This changed the picture
significantly for the columns already root-caused (`product_category`
dropped from 13,638 to 866 mismatches — most of the old count was baseline
staleness, not the join-logic bug itself) and moves the 189-vs-155
question closer to reconciled (229/66,020 now, vs the PDF's 189/61,077).
Refreshed counts for this ticket's remaining columns (same run,
`output/comparison/2026-08-11T232419Z/`): `product_balance` 2,740 (was
2,343), `product_received_from` 366 (was 330), `product_released_to` 4,490
(was 3,834), `product_remarks` 70 (was 66), `product_units_received` 305
(was 265), `product` 652 (unchanged), plus a new `file_name` mismatch count
of 60 not seen in the original session (unexplained — check whether this is
a new comparison-tool column or a real divergence before assuming it's in
scope here). Use the current `output_r`/`output_python`, not the backup.

## Question

For each of `product_balance`, `product_received_from`, `product_released_to`,
`product_remarks`, `product_units_received`, and `product`: pull the flagged
mismatch rows (`just compare-outputs`'s `cell_mismatches` sheet, cleaned
stage), look for a systematic pattern the way ticket 18 found for category/
entry_date (e.g. is it also majority R-null-Python-has-value, or a different
shape entirely), fall back to the real source Excel trackers
(`a4dphase2_upload`) as the arbiter, and add a named cause to
`src/a4d/migration/compare.py`'s classifier registry once a pattern is
confirmed. `product_released_to` in particular has no PDF precedent to
compare against — start by establishing whether it's a real divergence or
another comparison-tool artifact (per ticket 20's finding that at least one
column had a false-positive representation issue) before assuming it needs
a data explanation.

## Resolution

**Decision.** Five of the six columns share one root cause, already
half-diagnosed by ticket 18: R's per-(clinic, sheet, product) row sort
(`read_product_data.R:606-617`) falls back to raw input-row order whenever
`product_entry_date` fails to parse for a row. Verified this failure is
*near-universal*, not occasional, for several major clinics — R's
`product_entry_date` is null on literally 100% of "change"-status rows for
2024 Mahosot, 2023 Mahosot, 2022 Mahosot DC, 2020 Mahosot DC, and 99.2% for
2020 Mahosot DC (`output_r`/`output_python`, current 248-tracker set), while
Python correctly parses the same cells (≤3.7% null on the same rows) and
sorts chronologically instead — both sides implement the *identical*
documented rank algorithm (`_fill_product_names_and_sort`'s docstring
already cites the R line numbers; confirmed by re-reading `read_product_data.R`
directly), so this isn't a Python bug, it's R's already-known date-extraction
gap (ticket 18's `r_value_missing`) resurfacing as a *sort-order* divergence.
Since `add_row_ordinal`'s alignment key is purely positional, that legitimate
order difference cascades into value-level "mismatches" on every column
compared through it, even though nothing about the data itself is wrong.
Traced one full example by hand (Mahosot 2024, Jan24, "NovoFine Needles 6mm
x 32G (100s)"): R's cleaned rows show `product_entry_date = null` throughout
and released-then-received in raw appearance order; Python's show the real
dates (2024-01-03 … 2024-01-31) with the receipt correctly slotted in by
date — both reach the same final balance (13), just by a different path.
Confirmed this generalizes: of 2,105 (sheet, product) groups with any
`product_balance` mismatch, 98.3% still land on the *same* end-of-group
balance on both sides (`product_balance_status == "end"`), i.e. the flow is
conserved and only the intermediate path differs.

Added `row_order_divergence` to `src/a4d/migration/compare.py`'s classifier
registry (`PRODUCT_ROW_ORDER_CLASSIFIERS`): `compare_cells` gained an opt-in
`order_group_cols` parameter that, when a mismatch's R value appears
anywhere in Python's own value multiset for its `(clinic_id,
product_sheet_name)` group, flags `CellMismatch.row_order_candidate`; the
classifier just reads that flag. Wired for the five affected columns in
`scripts/compare_outputs.py`. Verified against the real 248-tracker
`output_r`/`output_python` pair: `product_received_from` (366/366, 100%),
`product_released_to` (4,490/4,490, 100%), `product_remarks` (70/70, 100%),
and `product_units_received` (297/305, 97.4%) are now fully or almost fully
explained by this classifier. `product_balance`'s membership check only
catches 764/2,740 (27.9%) directly — a cumulative running total rarely
recurs another row's exact value by coincidence, so the multiset-membership
heuristic under-detects it even though the 98.3% end-balance-match evidence
above says the *same* root cause covers the rest. Building a
balance-specific detector (e.g. comparing per-group ordered value multisets
instead of per-cell membership) is possible future work, not done here —
diminishing returns for this session given the root cause is already
confirmed by other means. **Rejected**: "fixing" Python to replicate R's
sort-order fallback — Python's chronological order is the one that's
actually correct (R's is a data-extraction failure, not an intentional
convention), so matching it would mean deliberately reintroducing a bug.

`product_units_received`'s residual 8 mismatches (all `43566`/`43644`/`43708`
in R vs `0` in Python) are Excel date serials leaking into a unit-count
column — the exact same "openpyxl date/time auto-coercion" pattern [ticket
24](24-triage-remaining-raw-column-residual.md) already flagged as an open,
unverified theory for the *raw*-stage residual, now confirmed to propagate
through to the *cleaned* stage too. Left for ticket 24 rather than fixed
here — same open question, just new cleaned-stage evidence for it.

`product` (652 mismatches) had a *different*, single cause: an embedded
`\r\n`-vs-`\n` line break (e.g. `"FastClix \r\nLancets"` vs `"FastClix
\nLancets"`) that ticket 22 already normalizes for the raw stage but that
survives cleaning unnoticed, since step 2.16's `str.strip_chars()` only
trims line ends, not mid-string breaks. Wired `normalize_whitespace_column`
for the cleaned stage too, scoped to `product` alone (the only cleaned-stage
column found carrying multi-line values). Verified: `product`'s mismatch
count drops from 652 to 0.

`file_name` (60 mismatches, flagged as unexamined in this ticket's premise)
turned out out of scope: it's not one of the six columns this ticket names,
and a quick look shows it's the row-alignment *diagnostic* column
(`add_row_ordinal` prepends `file_name` verbatim as one of the compared
columns), not real tracker data — left untouched, not investigated further.

**New gap surfaced, not this ticket's scope**: `product_units_released`
(2,144 mismatches) was never assigned to any ticket — not this one, not
[ticket 24](24-triage-remaining-raw-column-residual.md) (which only covers
its much smaller raw-stage residual, 24 rows). Spawned [ticket
25](25-triage-product-units-released-cleaned.md) rather than pulled in here,
per the map's split-rather-than-sprawl rule — plausibly the same
row-order-divergence root cause (unverified), but that needs its own look.

Full suite (577 tests + 1 pre-existing skip), ruff, `ty check src/` all
pass. Verified end-to-end against the real 248-tracker drive data, not just
unit tests.

**Evidence.** Executed: every claim above was checked directly against the
real `output_r`/`output_python` parquet pair and/or the actual comparison
tool output (`just compare-outputs`), not inferred from documentation or a
prior session's numbers.
