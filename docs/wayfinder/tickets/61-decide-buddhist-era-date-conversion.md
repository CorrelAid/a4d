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
