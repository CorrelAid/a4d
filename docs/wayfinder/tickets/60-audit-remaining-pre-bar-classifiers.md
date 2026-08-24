---
id: 60
title: Audit the eight pre-bar causes the first classifier pass did not reach
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-24b
claimed_at: 2026-08-24T12:00:00+02:00
resolution: decided
evidence: executed
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


## Resolution

**Decision.** Six of the eight causes are audited to the two-bar standard and
Python is the correct side in every one. One carried a real defect and is
fixed; one had its verdict written rather than re-evidenced; two were not
reached and are split into
[ticket 62](62-finish-the-pre-bar-classifier-audit.md).

**The defect: `buddhist_era_typo` was naming twelve cells that are not
Buddhist-era dates.** Its whole test was `carried.year >= 2400`, which after
[ticket 61](61-decide-buddhist-era-date-conversion.md) is exactly backwards --
the cleaned stage now *converts* genuine BE dates, so a year still sitting
above the threshold is by construction not a recoverable one. Both real
populations are ordinary year typos, verified in the workbook itself:
`3035-03-01` (2025 CDA, `Mar25!O219`) and `5025-05-19` (2025 Surat Thani,
`May25!O70`), each a genuine date-formatted Excel cell whose year is neither
Gregorian-plausible nor 543 off its tracker's. The cause is now bounded by the
sheet's own BE band, mirroring `_is_python_absurd_excel_serial`; where the
sheet year cannot be read the old behaviour stands, since an unknown tracker
year cannot disprove a BE date.

Bounding it exposed a second false label, which this ticket owns because its
own change surfaced it: five of the twelve fell through to
`r_parse_order_cannot_read_cell`, which asserts R's parse orders failed. R's
parse orders did not fail -- R's raw output holds the Excel serial `1141523`
(and `414611` for CDA) as a string, and it is the comparison's own
`normalize_date_column` that turns those into the sentinel. That is
`python_absurd_excel_serial`'s documented shape (ticket 32 created it for
`1339576` and `411384`; CDA's `414611` is a near sibling of the latter), and it
was only ever wired to the product entry-date registry. It is now prepended to
every patient date column, which is safe only because its own BE band check
declines a genuine BE year -- and that band could not previously apply to
patient columns at all, since no patient stage sets `tracker_year_col`, so it
now falls back to `_sheet_year` the way the other patient date causes do.

Measured end-to-end against the real 254-tracker pair, before and after, every
per-cause count in all four stages: **exactly four entries moved and nothing
else changed.** `buddhist_era_typo` 12 -> 0; patient cleaned
`python_rejects_beyond_tracker_year` 36 -> 42 (R keeps the absurd year, Python
sentinels it -- true); patient raw `python_absurd_excel_serial` 0 -> 6.
`unclassified` is unchanged at 37, so no row was pushed into the unexplained
bucket -- all twelve moved from a false label to a true one.

**`r_extraction_gap`'s lumping is real and wider than its docstring**, which is
what ticket 32 predicted. The test is a blanket `r_value is None and py_value is
not None`; the docstring enumerates six mechanisms over seven columns; the
population spans **thirteen**. Three further mechanisms traced to source, Python
correct in all three:

- `insulin_regimen`, 2021 Kantha Bopha, 194 rows -- `Mar21`/`Apr21` carry the
  patient header at row 85 with `Q85`/`Q86` *empty* where every other sheet has
  `Q13 = "Insulin Regime"`. R publishes 0 for those two sheets and 97 for each
  of the others; `Mar21!Q87` is `"Self-mixed BD"` and Python recovers the name
  from the sibling sheets. The documented `clinic_visit` blank-header
  mechanism, second instance.
- A **blank row number on the 2026 `Annual` sheet**, 7 rows -- 2026 ISDFI rows
  32-34 and 2026 Khon Kaen row 27 are exactly the rows whose column A is empty.
  This **corrects an explanation already in the registry**: the comment above
  those same ISDFI cells attributes them to R reading nothing from the Annual
  sheet, but R reads that file's Annual sheet perfectly well (102 of 120
  `edu_occ`). The sheet is not the mechanism; the missing row number is.
- `edu_occ`, 2026 Nakornping, 42 rows -- `Annual!E9` appends Thai to the header,
  which R's Unicode-aware sanitizer keeps and Python's ASCII folding drops.
  `r_non_latin_header_miss`'s mechanism absorbed here on registry order.

**`r_validator_rejects_multivalue` covers two R defects, not one.** 570 of its
15,647 rows have a Python value with no comma at all, 510 a bare `Pre-mixed` --
which the multi-value story cannot explain, since R publishes `Pre-mixed`
itself 5,426 times. The second mechanism is NA propagation through R's builder:
`ifelse(NA == "Y", ...)` yields `NA`, `paste` stringifies it as `"NA"`, and the
`.x[.x != ""]` filter does not remove it, so a single tick beside unfilled
siblings still produces `"pre-mixed,NA,NA,NA,NA"`. Measured: where R publishes
`Pre-mixed` the siblings are non-null in 4,134 of 4,135 rows; where R publishes
`Undefined` on a pre-mixed tick, 575 have a null sibling. R's output contains no
comma-joined value anywhere and no `Rapid-acting` at all (the `"rapic-acting"`
typo). Python reads the identical raw ticks -- verified on 2024 NPT, MM_NC009,
Apr24 -- and is correct.

**`excel_formula_error`: Python is correct and the test's symmetry is
unexercised.** All 12,680 rows run one way (Python holds the error string, R
null) across `t1d_diagnosis_age` 8,495, `bmi` 4,170, `age` 15, and every one is
raw-stage. Executed: 0 error-string cells in those columns across every cleaned
parquet on both sides, so nothing reaches the tables and raw's extra fidelity
costs downstream nothing.

**`row_order_divergence`: verdict written, no new evidence.** Python's
chronological sort is the correct side; both sides implement the same rank
algorithm and differ only in which rows have a parsable date to sort by.
Recorded with the caveat ticket 32 asked for -- `row_order_candidate` is a loose
value-membership test that false-fires on repeated small numeric values.

**`wide_format_fragment_truncated`: confirmed at full population.** All 5 rows
are strict prefixes (`'2(Error'` -> `'2(Error-1)'`), which is exactly what the
docstring claims.

**Because.** Ticket 32's method -- scan the whole population, then ask which
rows the mechanism does not account for -- found something in every cause it was
applied to. The two it did not reach are the two it was not applied to.

**Rejected.** Re-deriving the 38 post-bar causes: ticket 32 ruled them out and
nothing here disturbs that. Leaving the five parse-order rows on their false
label because that classifier is post-bar and out of scope: this ticket's own
change put them there, so it owns them. Widening `r_extraction_gap` into
separate named causes per mechanism: the name is accurate for all thirteen
columns (R loses data Python keeps) and splitting it would churn counts without
changing a verdict -- the docstring was the thing that was wrong.

**Evidence: executed.** Pipeline re-run over all 254 trackers, full comparison
before and after, per-cause diff across all four stages, source workbooks opened
for every cell named above. Full suite 938 passed / 1 skipped, ruff and
`ty check src/` clean.

**Tense.** The counts and the four moved entries describe current behaviour
after this session's change, measured. `r_extraction_gap`'s and
`r_validator_rejects_multivalue`'s docstring corrections change no behaviour at
all -- no count moved for either.
