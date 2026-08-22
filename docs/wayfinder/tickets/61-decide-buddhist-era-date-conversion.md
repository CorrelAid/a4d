---
id: 61
title: Decide whether a Thai clinic's Buddhist-era entry date is published as 2567 or converted to 2024
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-22b
claimed_at: 2026-08-22T12:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 32
---

## Premise

Rests on [the classifier re-audit](32-audit-classifiers-against-decision-bar.md),
closed, which narrowed `_validate_entry_dates`' era exemption
(`clean/product.py`) from "any year >= 2400" to "this tracker's own
Buddhist-era year", and in doing so established the facts this question needs:

- **22 rows** in the cleaned product table carry a genuine Buddhist-era date,
  all from Thai clinics -- 2024/2023/2022/2025 Chiang Mai Maharaj Nakorn, 2024
  Phattalung. They arrive as BE-shifted Excel serials (~243,933) which
  `parse_date_flexible` reads to a year in the 2565-2568 range, matching each
  sheet's month exactly (`2567-11-11` in `Nov24`).
- The pipeline publishes those years **as written**: `product_data` holds an
  entry date of 2567-11-11 for a November 2024 stock movement, 543 years in the
  future to any downstream reader.
- Ticket 32 deliberately did not decide this. It fixed only the corrupt cases
  (`5567-08-19`, `3026-04-30`, `2525-10-02`), which are now sentinelled and
  logged under `implausible_era_date`.

Rests also on the map's standing preference that where a divergence traces to a
human error in the source workbook the fix is the workbook -- which is what
makes this a genuine question rather than an obvious yes: a BE date is not a
clinic's *error*, it is the calendar the clinic uses.

**Void rather than in need of rewriting** if the era exemption is removed
altogether, since there would then be no BE dates in output to convert.

## Question

Should the product pipeline convert a Buddhist-era entry date to Gregorian
before publishing it?

Candidate answers, with what each costs:

1. **Convert (subtract 543)** where the year lands in the tracker's own BE band
   -- the band the pipeline already computes, so the test is free and cannot
   fire on a Gregorian date. Downstream gets one calendar. Costs: it moves 22
   rows of real data; R does not do it, so it becomes a new, deliberate R/Python
   divergence needing its own cause; and if the band is ever wrong the pipeline
   silently rewrites a date.
2. **Publish as written, flag for source correction** -- emit an informational
   error record so the clinics are asked to write Gregorian, and leave output
   untouched until they do. Costs: BigQuery keeps 22 far-future dates for as
   long as it takes.
3. **Convert and flag** -- both, treating the conversion as a recovery like
   `date_recovered_from_text`, auditable through the error table rather than
   silent.

Ticket 39's precedent argues for auditability over silence: it recovered dates
from clinical notes but wrote 1,223 error records so every recovery could be
reviewed. Whether the two situations are alike is exactly what needs deciding --
a BE year is unambiguous once identified, while a note-embedded date is a guess.

Points to settle:

- Does the **patient** arm have the same population? `PATIENT_BUDDHIST_ERA_CLASSIFIERS`
  exists with the same 2400 threshold, and ticket 40 already records
  "Buddhist-Era years typed into Gregorian date cells" as a patient-side source
  defect -- so patient may need the same answer, or may already have a different
  one. Measure before deciding, per the map's scan-the-population preference.
- What does the **downstream consumer** do with `product_entry_date`? If it
  filters or buckets by year, a 2567 row is not merely odd-looking, it is
  invisible or misfiled.
- Is a BE year in a Thai tracker the clinic's convention or an Excel locale
  artifact? The serials suggest the workbook itself is in a Thai-calendar Excel,
  which would mean nobody typed anything wrong.

## Decision (user, 2026-08-22)

**Convert.** Where a date is clearly not Gregorian and its intended value can be
determined unambiguously, the pipeline converts it like any other recovery --
**in the cleaned stage, not in raw**, so raw keeps what the workbook actually
says. This resolves the question above in favour of candidate 3 (convert *and*
flag), consistent with [ticket 39](39-recover-dates-embedded-in-free-text.md)'s
precedent that a recovery is auditable rather than silent.

Not yet implemented -- this records the decision, not the work.

## Measured population (session-2026-08-22, real 254-tracker set)

The ticket asked to measure the patient arm before deciding. Done, and **the
patient arm is the larger and more urgent half**, which the ticket's premise did
not know:

- **Product cleaned: 22 rows**, all published today as BE years (`2567-11-11` in
  a `Nov24` sheet). Visible but wrong-looking.
- **Patient: 381 cells across 95 distinct values, and every one is currently
  destroyed.** Patient's `_validate_dates` clobbers any future date with the
  9999-09-09 sentinel -- so unlike product, patient publishes nothing odd
  *because it publishes nothing at all*. The cells were invisible for exactly
  that reason: no comparison sheet shows them, since R sentinels them too.
  Scanned by re-parsing every raw patient date column with
  `parse_date_flexible` and keeping years in [2400, 9999).

Affected clinics are Thai throughout: 2024/2025/2026 Chiang Mai Maharaj Nakorn,
2026 Chulalongkorn (the largest -- whole complication-screening date columns in
BE), 2026 Nakornping, 2023 Nakornping, 2022 Hat Yai.

**The band test the product fix already uses appears to be the right rule for
patient too, and one case argues it strongly.** 2022 Hat Yai's `t1d_diagnosis_date`
holds `2560-01-01` (12 cells). BE for 2022 is 2565, so 2560 looks like a typo --
but it falls inside the band `[tracker_year + 543 - YEAR_FLOOR_DELTA,
tracker_year + 543]` = 2560-2565, and converting it gives **2017-01-01**, which
is exactly the date [ticket 40](40-source-defect-findings-report.md) independently
established from that patient's own D.O.B. (2013-03-17), recruitment (2017-06-01)
and age at diagnosis (4). The band recovers the right answer without being told.

Patient needs a *wider* lower bound than product, and the data shows why: a
screening or diagnosis date legitimately predates its tracker. 2026
Chulalongkorn records `2567-07-18` (2024) in a kidney-test column, correctly.

**Two values, 6 cells, fall outside any band and must stay sentinelled**,
becoming source-defect findings rather than conversions: `3035-03-01` (2025 CDA,
1 cell) and `5025-05-19` (2025 Surat Thani, 5 cells). Neither decodes to a
plausible year by subtracting 543.

**Still open before implementing:** whether `hospitalisation_date`'s two
note-embedded BE cells (`18-19/11/2567`, `19-22/5/2568`) come along. Ticket 39
refused them on the grounds that subtracting 543 would be guessing at the
clinic's calendar -- this decision overturns that reasoning for cells the band
test identifies, but those two also carry a date *range*, which is a separate
problem ticket 39 already declined.

## Resolution (session-2026-08-22b)

**Decision.** Both arms convert a Buddhist-era date to Gregorian in the cleaned
stage, and log every conversion under a new `buddhist_era_converted` error code
so the shift is auditable rather than silent. Implemented, run against the real
254-tracker set, and every resulting R/Python divergence named.

The open question the previous session left -- whether
`hospitalisation_date`'s two note-embedded BE cells (`18-19/11/2567`,
`19-22/5/2568`) come along -- is answered **no** by the user (2026-08-22): a
date *range* is a separate problem [ticket
39](39-recover-dates-embedded-in-free-text.md) already declined, and this
decision does not overturn that half. They are reported as source defects
instead ([ticket 40](40-source-defect-findings-report.md)).

**What was built.**

- `clean/buddhist_era.py` (new): `BUDDHIST_ERA_OFFSET`, `BUDDHIST_ERA_THRESHOLD`
  and `gregorian_from_buddhist()`, shared by both arms. The shift goes via a
  string rather than `pl.date`/`dt.replace` because both of those *raise* on
  invalid components: 543 is not a multiple of 4, so a Buddhist leap day can
  land on a non-leap Gregorian year (2568-02-29 -> 2025-02-29) and would abort
  the tracker. It yields null there instead, and the cell is left for the
  ordinary implausible-date handling rather than invented.
- `_convert_buddhist_era_dates` (`clean/patient.py`, step 5.4). Domain is
  `get_date_columns()` minus `tracker_date` -- derived, not listed. Placed
  before `_fix_age_from_dob` so no age is ever derived from a BE `dob`, and
  before `_validate_dates`, which is what was destroying these cells.
- `_validate_entry_dates` (`clean/product.py`) converts inside the BE band it
  already computed for ticket 32 rather than passing the date through.

**The band, and why patient's differs from product's.** Product converts only
inside `[table_year + 543 - 5, table_year + 543]`. Patient has no lower bound
at all: a diagnosis or screening date legitimately predates its tracker by
decades, and 2026 Chulalongkorn correctly records `2567-07-18` (2024) in a
kidney-test column. The upper bound alone -- shifted year no later than the
tracker's own year -- is what rejects a value that decodes to nothing, and it
does: `3035` -> 2492 and `5025` -> 4482 both stay sentinelled.

**Measured against the real 254-tracker set** (`a4d run --force`, both arms in
one execution, then `just compare-outputs` against `output_r`):

- **Patient: 375 cells converted** across 11 columns and 7 Thai trackers, each
  logged. The 381 the previous session measured minus the 6 that decode to
  nothing -- exactly the split it predicted.
- **Product: 22 rows converted**; `product_data` now holds **zero** entry dates
  with a year past 2400 (queried directly), where it previously published
  stock movements dated 543 years in the future.
- **The Hat Yai case came out right without being told.** `2022_Hat Yai`
  `TH_HY013`'s `t1d_diagnosis_date` now reads 2017-01-01 against a D.O.B. of
  2013-03-17 and `t1d_diagnosis_age` 4 -- the date [ticket
  40](40-source-defect-findings-report.md) had derived by hand.
- **Patient cell divergence is unchanged at 114,284**, which is the expected
  result: these cells already mismatched, with Python holding the sentinel;
  now it holds a date. Product cleaned rose 22,699 -> 22,735 (+36) from the
  re-sort described below. **Unclassified did not move on either arm** (16 and
  21).

**Two new causes in the comparison tool**, both needed by this map's bar that a
difference is named rather than left over:

- `python_buddhist_era_converted` (287 cells, both arms): R keeps the BE year,
  Python holds exactly the same day 543 years earlier. The test is the exact
  shift -- same month, same day -- so a second divergence riding along cannot
  hide behind the name. It takes over 281 cells `buddhist_era_typo` used to
  hold, 12 `python_rejects_beyond_tracker_year` held, 16 that
  `python_out_of_window_date_preserved` was over-claiming, and 1 that
  `note_dates_read_differently` had swallowed. It is prepended for every
  `get_date_columns()` column, not hand-listed.
- `buddhist_era_conversion_row_order` (3 cells): converting moves the row.
  Product rows pair by ordinal position within (clinic, sheet), and R sorts an
  unconverted 2565 date to the end of its group while Python sorts 2022
  chronologically. Verified on the real pair -- 2022 Chiang Mai Maharaj
  Nakorn, `Dec22`, "Accu-Chek Instant Test Strips": R's ordinal 11 holds
  2565-12-24 where Python holds 2022-12-28, and Python's ordinal 9 holds the
  converted 2022-12-24. Plain value membership cannot see this (R's value is
  by construction absent from Python's group), so `compare_cells` now also
  tests membership of the *shifted* value, via a new
  `era_shift_row_order_candidate` flag.

That same re-sort also moved 36 cells into causes that already existed
(`row_order_divergence` +21 across four columns, `r_value_missing` +17,
`derived_running_total_row_order` +4, offset by
`python_out_of_window_date_preserved` -16). Stated as a consequence of this
change, not as new evidence about R.

**Rejected.**

- *Publish as written and flag only* (candidate 2): rejected by the user's
  decision. On product it leaves BigQuery holding dates 543 years out; on
  patient it is not even available, because publishing as written is what
  `_validate_dates` destroys.
- *Convert in the raw stage*: rejected by the decision -- raw is a faithful
  record of what the workbook says, and the whole audit trail depends on that.
- *Convert the two hospitalisation ranges too*: rejected this session (above).
- *Widen the patient band downward with an explicit floor* (e.g. 1900):
  considered and dropped as dead weight. The 2400 threshold already implies a
  floor of 1857, and no cell sits near it.
- *Let `row_order_divergence` absorb the three displaced product cells* by
  normalizing R's BE value before the membership test: rejected because the
  cells' *values* still differ for a reason worth naming; folding them into a
  generic order cause would have hidden the conversion behind it.

**Evidence.** Everything above is **executed**: a full `a4d run --force` over
the 254-tracker set, `duckdb` queries against the resulting parquets and error
table, two `just compare-outputs` runs, and 927 passing tests (`ruff`, `ty
check src/` clean). The one judgement is the band rule itself -- that a year
past 2400 which decodes to no later than the tracker year *is* a Buddhist-era
date. It is recorded as an assumption on the map.

**Tense.** All counts describe current behaviour on `migration` after this
session's commit, not a proposal.

### Not done here

- The **2 range cells** and the **6 undecodable era cells** are now [ticket
  40](40-source-defect-findings-report.md)'s to report; that ticket's body was
  updated in this session, including retiring "BE years in date cells" as a
  defect class now that they are converted.
- **`buddhist_era_typo` still exists** at its new scope of exactly 6 cells (the
  ones Python cannot convert). [Ticket
  60](60-audit-remaining-pre-bar-classifiers.md) lists it as one of the eight
  pre-bar causes to audit, and its table's "6 rows" now matches what the
  classifier actually holds.
