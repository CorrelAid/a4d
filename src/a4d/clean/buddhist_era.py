"""Buddhist-era date handling, shared by the patient and product cleaning arms.

Thai clinics write dates in the Buddhist calendar (BE = CE + 543), and their
workbooks are often kept in a Thai-locale Excel, so the shift arrives as a
BE-shifted serial rather than as anything a clinician typed wrongly. The
pipeline converts such a date to Gregorian in the cleaned stage only (ticket
61); the raw stage keeps what the workbook actually says.
"""

import polars as pl

# Buddhist Era is Common Era + 543.
BUDDHIST_ERA_OFFSET: int = 543

# Buddhist Era / Common Era disambiguation point. A parsed year at or beyond
# this is implausible as a Gregorian date in a 2017+ tracker corpus, so it is
# either a Buddhist-era year or a corrupt Excel serial. Keeping the threshold
# well above any real tracker year is what makes the conversion unable to fire
# on a Gregorian date.
BUDDHIST_ERA_THRESHOLD: int = 2400


def gregorian_from_buddhist(col: str) -> pl.Expr:
    """Shift ``col`` back by 543 years, yielding null where that date does not exist.

    Goes via a string rather than ``pl.date``/``dt.replace`` because both of
    those raise on invalid components: 543 is not a multiple of 4, so a 29
    February in a Buddhist leap year can land on a non-leap Gregorian one
    (2568-02-29 -> 2025-02-29). A null there leaves the cell unconverted, which
    routes it to the ordinary implausible-date handling instead of aborting the
    tracker.
    """
    return pl.format(
        "{}-{}",
        pl.col(col).dt.year() - BUDDHIST_ERA_OFFSET,
        pl.col(col).dt.strftime("%m-%d"),
    ).str.to_date(format="%Y-%m-%d", strict=False)
