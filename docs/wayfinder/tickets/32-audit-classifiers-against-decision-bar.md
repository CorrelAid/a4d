---
id: 32
title: Re-audit every existing cause classifier — is Python actually right, or was the diff merely labelled?
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 27
---

## Premise

Rests on [Triage the residual patient raw-stage column mismatches after date
normalization](27-triage-patient-raw-residual.md), closed: that ticket was
first closed treating a formula-error divergence as a comparison-tool
labelling job, on an unverified claim that both sides were "just
representing no-value differently". Checking downstream showed R and Python
disagreed in 2,073 of 2,073 cleaned rows, and the real mechanism turned out
to be Python's own extraction silently discarding data the source file
carried — a pipeline bug the classifier would have cemented as "explained".

That prompted the map's standing preference **triage means deciding, not
labelling** (see Notes): every flagged difference must both (1) be explained
by a mechanism traced to source Excel or to R's/Python's own code, and (2)
carry an explicit decision on whether Python is doing the right thing.
Naming a cause is not a decision in favour of Python's value.

Every classifier now in `src/a4d/migration/compare.py` was written *before*
that bar was stated, across tickets 15, 18, 20, 21, 22, 24, 26, 27 and 28.
Some clear it comfortably (the mechanism was traced to R's source or to a
real source-Excel cell); others were shape-matching heuristics seeded from
the parity-presentation PDF and never verified against anything.

## Question

Audit all nine classifier registries against the two-bar standard, and for
each one record: what the mechanism actually is, what evidence establishes
it, and the explicit verdict on whether Python is correct. Where Python is
wrong or lossy, fix the pipeline (ticket 27's precedent) rather than
keeping the label.

**Known weak, in priority order — these are the reason this ticket exists:**

- `off_by_one_day` (`PRODUCT_ENTRY_DATE_CLASSIFIERS`) — the clearest
  failure of the bar: it matches any pair of dates one day apart and says
  nothing about which side is right. A one-day gap is exactly the shape a
  real timezone/serial-origin bug would take. Never traced to a mechanism,
  never checked against source Excel. 10 cleaned + 2 raw rows currently.
- `r_value_missing` (same registry, **11,468 cleaned product rows** — the
  single largest classified cause on the map) — deliberately lumps together
  "R rescued a source typo" and "R plainly failed to extract a clean value",
  because `classify()` only sees the parsed value pair. Ticket 18 verified
  *one* instance against real source Excel (2018 Mahosot, Jan18) and
  generalized from it. At this volume that generalization needs testing, and
  the two sub-causes need separating.
- `sentinel_null` and `ce_typo` (same registry) — both seeded from the
  parity-presentation PDF's four named causes rather than from evidence;
  the PDF's own baseline is now known stale (ticket 18). Neither has been
  re-checked against the current 248-tracker data.
- `row_order_divergence` (`PRODUCT_ROW_ORDER_CLASSIFIERS`) — the mechanism
  *is* established (R falls back to input order when its date parse fails;
  Python sorts chronologically) and Python is very likely right, but the
  "is Python correct" half rests on a 98.3%-of-groups end-balance spot
  check, and `product_balance` is knowingly only 27.9% detected, left as
  "future work". Finish the verdict or state the residual as an open
  question.

**Likely fine, confirm briefly rather than re-derive:**
`r_category_lookup_miss` (traced to `read_product_data.R`'s unnormalized
join), `openpyxl_date_typed_stray_cell` (source-Excel verified),
`wide_format_fragment_truncated` (R's value verified a strict prefix of
Python's), `r_extraction_gap` (source-Excel verified),
`r_validator_rejects_multivalue` (documented R validator bug),
`buddhist_era_typo` (source-Excel verified + cleaned-stage reconciliation
checked), `excel_formula_error` (ticket 27, both directions verified).

If this doesn't converge in one session, split by registry rather than
leaving it open-ended.
