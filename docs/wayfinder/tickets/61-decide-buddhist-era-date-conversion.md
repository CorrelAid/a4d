---
id: 61
title: Decide whether a Thai clinic's Buddhist-era entry date is published as 2567 or converted to 2024
labels: [wayfinder:grilling]
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
