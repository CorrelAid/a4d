---
id: 32
title: Re-audit every existing cause classifier — is Python actually right, or was the diff merely labelled?
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-22
claimed_at: 2026-08-22
resolution: decided
evidence: executed
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

## Addendum (session-2026-08-12h, from [ticket 25](25-triage-product-units-released-cleaned.md))

`row_order_divergence`'s "is Python correct" half is now substantially
stronger than the 98.3% end-balance spot check this ticket was written
against — don't re-derive it, extend it. Ticket 25 established, against the
real 248-tracker drive pair:

- Per-column multiset equality for `product_units_released` across **all**
  2,283 `(clinic_id, product_sheet_name)` groups (0 differing) — the
  divergence provably adds, loses and alters nothing.
- Row-identity preservation: the multiset of
  `(product_units_released, product_released_to)` pairs is identical across
  all 11,649 `(clinic_id, product_sheet_name, product)` groups.
- Direct source-Excel confirmation that R's fallback trigger is real: in the
  worst-affected group, R has `product_entry_date` null on every row while
  the source file's "Entry Date" column is fully populated with genuine
  datetimes.

Two caveats this ticket should still carry:

1. The `row_order_candidate` flag itself remains a **loose** membership test
   ("R's value appears somewhere in Python's group"), which false-fires on
   repeated small numeric values. It is adequate as a *record* of a cause
   established by other means, but it is not evidence on its own — ticket 25
   deliberately did not close on it.
2. `product_balance`'s under-detection is now **explained**, not just
   observed: balance is *derived* (`_compute_running_balance`, step 2.15,
   `balance[i-1] - released[i] + received[i]`, mirrored in R), so it cannot
   travel with a row under a re-sort and value-membership cannot detect it in
   principle. That residual now has its own home in [ticket
   36](36-triage-product-cleaned-unclassified-residual.md); this ticket's
   `row_order_divergence` entry can point there instead of holding it open.

## Inherited from session-2026-08-14 (ticket 37)

This ticket also now inherits `r_ifelse_na_propagation` (new), plus three
changes to existing causes:

- `PATIENT_RECRUITMENT_DATE_CLASSIFIERS` was renamed
  `PATIENT_R_EXTRACTION_GAP_CLASSIFIERS` and now serves three columns, its
  single `r_extraction_gap` cause documenting three separately-verified R
  mechanisms. That lumping is deliberate -- `classify()` cannot see the file,
  so it cannot tell a 2022 tracker from a 2026 one -- but it is exactly the
  kind of generalization this ticket exists to re-check.
- `buddhist_era_typo` is now symmetric (either side may hold the sentinel).
- `python_future_date_sentinel` is now wired to a patient column as well as
  product ones.

All were verified against the real drive data or the source Excel when
written, per the map's Notes.

## Premise update (session-2026-08-15b, ticket 31's session)

This audit now also inherits **`r_na_unite_padding`**
(`PATIENT_NA_UNITE_PADDING_CLASSIFIERS`, `src/a4d/migration/compare.py`), added
by [ticket 31](31-triage-patient-raw-residual-2.md). It is source-verified
against the real 2023 Kantha Bopha workbook rather than sampled, and it is
deliberately narrow: it fires only when stripping R's literal `NA` tokens
leaves exactly Python's value. Ticket 31 is also worth reading as a worked
example of what this audit is looking for -- the column it covers had a real
Python data-loss bug sitting underneath a classifiable R artifact, and
classifying first would have cemented the bug as "explained".

## Resolution (session-2026-08-22)

**Decision.** The audit is scoped to the classifiers written *before* the
two-bar standard, and the four the ticket named as known-weak are resolved:
`off_by_one_day` and `ce_typo` are **deleted** as shape-matching labels that
named no mechanism, `sentinel_null` is **renamed** to the mechanism it actually
describes, and `r_value_missing` is **bounded** so it can no longer absorb cells
where Python is the questionable side. Two pipeline defects found underneath
them are fixed. The remaining eight pre-bar causes are split into
[the second half of the audit](60-audit-remaining-pre-bar-classifiers.md), per
this ticket's own "split by registry rather than leaving it open-ended".

**Because.** The ticket's premise -- "every classifier now in `compare.py` was
written before that bar was stated" -- was **false when this session opened**,
and measuring it is what set the scope. Dating all 50 causes by first commit
(`git log -S` over `compare.py`) puts **12** before the bar (2026-08-11/12) and
**38** after it, each of the 38 argued in its own triage ticket against real
data. Auditing all 50 would have re-derived a week of reviewed work; auditing
the 12 is the ticket's actual subject.

Findings, each traced rather than pattern-matched:

- **`off_by_one_day` (12 rows) named a coincidence.** Its 10 cleaned-stage rows
  are consecutive daily entries in VNCH's 2022 and PKH's 2025 trackers. Pulling
  the whole `(VNC, May22)` group shows R holding null entry dates at ordinals
  42, 47 and 51 -- its sort falls back to input order -- so its rows sit one
  position behind Python's chronological sort and the "one day apart" is just
  what neighbouring rows of a daily sequence look like. This is
  `row_order_divergence`; `off_by_one_day` only won because
  `PRODUCT_ENTRY_DATE_CLASSIFIERS` merges ahead of `PRODUCT_ROW_ORDER_CLASSIFIERS`.
  The 2 raw-stage rows are a real and different mechanism: source serials `25`
  and `12`, where openpyxl reproduces Excel's phantom 1900-02-29 (serial 25 ->
  1900-01-25) and `normalize_date_column`'s epoch arithmetic does not
  (1900-01-24). Named `excel_1900_leap_serial`, bounded to serials below 61.
- **`ce_typo` (2 rows) fired on the comparison tool's own sentinel and hid a
  production defect.** It tested `r_value.year > 2100`; both rows have R at
  9999-09-09, which is what `normalize_date_column` produces when R's raw
  string will not parse. The source cells are junk Excel serials -- 1,339,576
  and 411,384 -- and **Python was publishing them as `5567-08-19` and
  `3026-04-30` in cleaned output**, because `_validate_entry_dates` exempted
  every year >= 2400 so Buddhist-era dates could flow through. Replaced by
  `python_absurd_excel_serial`, which judges the *Python* side and excludes a
  genuine BE year.
- **`sentinel_null` (78 rows) was a shape, but Python is right.** Traced to
  source: Sarawak's 2023 tracker genuinely carries December **2024** dates in
  its `Dec23` sheet, so Python's beyond-tracker-year guard fires while R's
  cleaned side is null for the reason `r_value_missing` already describes.
  Renamed `python_sentinel_r_extraction_gap` -- the intersection of two
  already-decided mechanisms, not a third one.
- **`r_value_missing` (11,468 rows) holds for 11,436 and absorbed 32 it should
  not have.** Filtering the population to rows whose Python date is implausible
  for its own `product_table_year` found 29 year-floor cells -- `0202-06-20`
  (Surat Thani), `0205-12-02` (QMC), `1935-04-30`, seven `2009-12-04` in a 2019
  Mahosot tracker -- which `_validate_entry_dates` logs and deliberately
  preserves, plus the 3 era cells above. The cause asserts Python read the cell
  correctly, so it may not cover these: `python_out_of_window_date_preserved`
  now names them ahead of it.

**Two pipeline fixes, both measured against the real 254-tracker data:**

1. `_validate_entry_dates` (`clean/product.py`) no longer exempts everything
   above 2400. The exemption is now the tracker's own BE band
   (`product_table_year + 543`, minus `YEAR_FLOOR_DELTA`), so all 22 genuine BE
   dates from the Thai clinics survive untouched while `5567-08-19`,
   `3026-04-30` and Hat Yai's `2525-10-02` (BE for 2025 is 2568) are
   sentinelled and logged under a new `implausible_era_date` error code. Cleaned
   product rows with a year >= 2400 that is not the sentinel: **25 -> 22**. Total
   rows unchanged at 74,689.
2. **`a4d run` -- the production entry point behind the Cloud Run Job -- was
   publishing an errors table containing the patient arm only.** The patient arm
   writes the table from inside `run_patient_pipeline`; nothing wrote the product
   arm's, so `table_errors.parquet` and BigQuery's `errors` table have been
   patient-only. Measured: 63,295 records, zero `balance_reconciliation` (116
   exist) and zero `implausible_era_date`. `run` now writes the table once after
   both arms: **63,295 -> 97,326 records**. Found because the fix in (1) emitted
   records that never arrived.

**Rejected.**
- *Auditing all 50 causes* -- the premise that made that the job is false; the
  38 post-bar causes were each verified when written.
- *Converting Buddhist-era dates to Gregorian* -- the pipeline publishes
  `2567-11-11` for a November 2024 transaction, which downstream reads as a
  stock movement 543 years out. Correct in principle and deliberately **not**
  decided here: it moves 22 rows of real data and R does not do it. Spawned as
  [ticket 61](61-decide-buddhist-era-date-conversion.md).
- *Leaving the >= 2400 exemption alone and only bounding the classifier* (the
  option B put to the user) -- rejected by the user, who asked for the source
  and pipeline to be addressed rather than the comparison alone.
- *Fixing `parse_date_flexible`'s serial epoch to match openpyxl* -- it is
  pipeline code, and the cleaned stage already nulls tiny-int residue, so the
  change would move production output to fix two raw-stage comparison rows.
- *`product_balance`'s 11 unclassified rows* -- untouched; they belong to
  [ticket 36](36-triage-product-cleaned-unclassified-residual.md), which already
  argued them as a real signal worth surfacing.

**Evidence: executed.** All counts come from a full pipeline run over the real
254-tracker set on the USB drive and a full `just compare-outputs` against the
frozen `output_r/`, not from reasoning. Cause deltas (previous run -> this run),
product cleaned: `off_by_one_day` 10 -> 0, `sentinel_null` 78 -> 0,
`python_sentinel_r_extraction_gap` 0 -> 81, `python_out_of_window_date_preserved`
0 -> 29, `r_value_missing` 11,468 -> 11,436, `row_order_divergence` 113 -> 121.
Product raw: `ce_typo` 2 -> 0, `off_by_one_day` 2 -> 0,
`excel_1900_leap_serial` 0 -> 2, `python_absurd_excel_serial` 0 -> 2. Both
patient stages are byte-identical (114,284 and 26,171 unchanged), which is the
check that this session moved nothing it did not intend to. Full suite 913
passed, ruff and `ty check src/` clean.

One measurement scare worth recording: an intermediate run showed six patient
`fbg_baseline_mg` cells losing their `python_glucose_unit_corrected` label. That
was not a regression -- it was defect (2) biting the measurement itself. Running
the product arm alone had overwritten the shared errors table, and
`load_glucose_unit_swaps` reads that table. It disappeared once both arms wrote
the table together.

**Tense.** Every count above describes current behaviour on this branch after
the two fixes, except the "was publishing" statements about the >= 2400
exemption and the patient-only errors table, which describe behaviour before
this session.

**Residual, deliberately left open.** Product cleaned `unclassified` moves 20 ->
21 (`product_entry_date` 9 -> 10): the PKH row that `off_by_one_day` used to
cover has no mechanism yet, and it sits with a group of rows where R holds a
date a year ahead of Python's (`2028-02-26` vs `2026-02-26` at 2026 NOGH,
`2022-12-12` vs `2021-12-30` at 2021 VNCH). Naming that population is
[ticket 60](60-audit-remaining-pre-bar-classifiers.md)'s to pick up; it is a
question stated, not a label applied.
