---
id: 60
title: Audit the eight pre-bar causes the first classifier pass did not reach
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 32
---

## Premise

Rests on [the classifier re-audit](32-audit-classifiers-against-decision-bar.md),
closed, which established the scope this ticket inherits and the standard it is
judged by:

- **Twelve** of the 50 causes in `src/a4d/migration/compare.py` predate the
  map's **triage means deciding, not labelling** preference (dated by first
  commit: 2026-08-11 and 2026-08-12). The other 38 were written after it, each
  argued in its own triage ticket, and are **out of this audit's scope** --
  ticket 32 rejected re-deriving them.
- Four of the twelve are resolved: `off_by_one_day` and `ce_typo` deleted,
  `sentinel_null` renamed to `python_sentinel_r_extraction_gap`,
  `r_value_missing` bounded by `python_out_of_window_date_preserved` and
  `python_absurd_excel_serial`.

Rests also on the map's standing preference that naming a cause is not a
decision in favour of Python's value, and on ticket 32's demonstration that the
weakness is usually not in the mechanism but in the *silence about the Python
side*: `r_value_missing` was correct about R for 11,436 of 11,468 rows and wrong
to speak for the other 32.

**Void rather than in need of rewriting** if ticket 32's scoping is overturned
-- i.e. if someone decides the post-bar 38 must be audited too, this ticket is
the wrong unit of work and the whole audit should be re-cut by registry.

## Question

Audit the eight remaining pre-bar causes against the two-bar standard. For each:
what the mechanism actually is, what evidence establishes it, and the explicit
verdict on whether Python is correct. Where Python is wrong or lossy, fix the
pipeline rather than keeping the label.

Current volumes, from the 2026-08-22 run against the real 254-tracker set:

| cause | rows | ticket 32's read |
|---|---|---|
| `r_extraction_gap` | ~31,000 | "likely fine", but later widened to serve three columns and three separately-verified R mechanisms -- the widening is the risk |
| `r_validator_rejects_multivalue` | 15,647 | "likely fine" (documented R validator bug) |
| `excel_formula_error` | 12,680 | "likely fine", both directions verified by ticket 27 |
| `row_order_divergence` | 7,480 | mechanism established; the "is Python correct" half is strong but was never written down as a verdict |
| `r_category_lookup_miss` | 866 | "likely fine" (traced to `read_product_data.R`'s unnormalized join) |
| `openpyxl_date_typed_stray_cell` | 100 | "likely fine" (source-Excel verified) |
| `buddhist_era_typo` | 6 | "likely fine", but later made symmetric -- re-check at its new scope |
| `wide_format_fragment_truncated` | 5 | "likely fine" (R's value verified a strict prefix of Python's) |

Three things ticket 32 established that this ticket should use rather than
re-derive:

1. **`row_order_divergence` needs a verdict written, not more evidence.**
   Ticket 25 already proved per-column multiset equality across all 2,283
   `(clinic_id, product_sheet_name)` groups for `product_units_released`, and
   row-identity preservation across all 11,649 product groups. What is missing
   is the explicit statement that Python's chronological sort is the correct
   side, plus the caveat that the `row_order_candidate` flag itself is a loose
   membership test that false-fires on repeated small numeric values.
   `product_balance`'s under-detection is already explained and already homed on
   [ticket 36](36-triage-product-cleaned-unclassified-residual.md).
2. **`r_extraction_gap`'s lumping is the thing to test.** `classify()` cannot
   see the file, so one cause covers three mechanisms across three columns.
   Ticket 32's method applies directly: scan the whole population, then ask
   which rows the mechanism does *not* account for.
3. **Ask what the classifier says about the Python side.** Every one of ticket
   32's four findings came from that question, not from doubting R.

## Residual inherited from ticket 32

Product cleaned `unclassified` is 21 rows (11 `product_balance`, owned by ticket
36; 10 `product_entry_date`). The `product_entry_date` ten include a population
nobody has named: rows where R holds a date roughly a year ahead of Python's --
`2028-02-26` vs `2026-02-26` (2026 NOGH), `2022-12-12` vs `2021-12-30` (2021
VNCH), `2025-05-20` vs `2024-05-30` (2024 Surat Thani). Whether that is one
mechanism or several is unmeasured.
