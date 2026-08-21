"""Flexible date parsing for A4D tracker data.

Matches R's parse_dates() function (script2_helper_patient_data_fix.R:174-211).
Handles various date formats found in legacy trackers including:
- Standard formats: "28/8/2017", "01-03-2018"
- Abbreviated month-year: "Mar-18", "Jan-20"
- Full month-year: "March-2018", "January-20"
- Excel serial numbers: "45341.0" (days since 1899-12-30)
- Year only: "2018", "18"
"""

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta

from dateutil import parser as date_parser
from loguru import logger

# Excel epoch: dates stored as days since this date
EXCEL_EPOCH = date(1899, 12, 30)

# Known data-entry typos in month names. Patterns are applied case-insensitively
# with word boundaries so unrelated text containing these substrings (e.g.
# "CON0CT") is not rewritten. Replacements use uppercase since downstream
# parsers are case-insensitive.
TYPO_REPLACEMENTS: list[tuple[str, str]] = [
    (r"(?i)\bMACH\b", "MAR"),
    (r"(?i)\b0CT\b", "OCT"),
    (r"(?i)\b0CTOBER\b", "OCTOBER"),
    (r"(?i)\bN0V\b", "NOV"),
    (r"(?i)\bN0VEMBER\b", "NOVEMBER"),
    # A transposed and a dropped letter, each observed on real trackers
    # (ticket 56): "9-Dce-20" at Mahosot DC, "6-ug-2025" at NPH.
    (r"(?i)\bDCE\b", "DEC"),
    (r"(?i)\bUG\b", "AUG"),
    # Bahasa Malaysia month abbreviations, not typos: the Malaysian clinics
    # (Likas, Putrajaya, Sultanah Malihah, Sarawak) write the month in their
    # own language in a column every other clinic writes in English. Mac, Mei
    # and Okt are observed on the current tracker set; Ogos and Dis are the
    # rest of the set that differs from English, added so the next one to
    # appear is read rather than sentinelled. The other seven Malay
    # abbreviations are spelled as in English and need no entry.
    (r"(?i)\bMAC\b", "MAR"),
    (r"(?i)\bMEI\b", "MAY"),
    (r"(?i)\bOGOS\b", "AUG"),
    (r"(?i)\bOKT\b", "OCT"),
    (r"(?i)\bDIS\b", "DEC"),
]


# Thai month abbreviations, with or without the abbreviating full stops, as the
# Thai clinics write them (ticket 56: Nakornping's 2025 and 2026 trackers). The
# guards are lookarounds on the Thai block rather than \b, because a full stop
# between two Thai letters kills the word boundary a trailing \b would need.
# Longest-first so "มี.ค." (March) is not read as "ม.ค." (January).
_THAI_MONTH_REPLACEMENTS: list[tuple[str, str]] = [
    (r"(?<![ก-๛])มี\.?ค\.?(?![ก-๛])", "MAR"),
    (r"(?<![ก-๛])มิ\.?ย\.?(?![ก-๛])", "JUN"),
    (r"(?<![ก-๛])เม\.?ย\.?(?![ก-๛])", "APR"),
    (r"(?<![ก-๛])ม\.?ค\.?(?![ก-๛])", "JAN"),
    (r"(?<![ก-๛])ก\.?พ\.?(?![ก-๛])", "FEB"),
    (r"(?<![ก-๛])พ\.?ค\.?(?![ก-๛])", "MAY"),
    (r"(?<![ก-๛])ก\.?ค\.?(?![ก-๛])", "JUL"),
    (r"(?<![ก-๛])ส\.?ค\.?(?![ก-๛])", "AUG"),
    (r"(?<![ก-๛])ก\.?ย\.?(?![ก-๛])", "SEP"),
    (r"(?<![ก-๛])ต\.?ค\.?(?![ก-๛])", "OCT"),
    (r"(?<![ก-๛])พ\.?ย\.?(?![ก-๛])", "NOV"),
    (r"(?<![ก-๛])ธ\.?ค\.?(?![ก-๛])", "DEC"),
]


# Any month name written out beyond its 3-letter abbreviation, so it can be
# truncated back to that abbreviation. Anchored so a longer word that merely
# starts with a month name is left alone. The tail is a negative lookahead
# rather than \b (ticket 50): a digit is a word character, so \b never fires
# between "July" and "2014" in a cell whose separating space was lost, and the
# month-year branch below never saw such a value.
MONTH_NAME_PATTERN = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]+(?![a-z])",
    re.IGNORECASE,
)


# The largest serial still read as an Excel date, ~year 2600. Raised from
# 100000 (year 2173) for the Buddhist-era typo (ticket 50): a BE year written
# into a Gregorian date cell lands around 241,000-245,000, and below the old
# ceiling those serials fell through to dateutil, which read "241062"
# positionally as 24/10/62 -- a plausible-looking date the cell does not hold.
# Deliberately well below the numeric error sentinel 999999 and the largest
# observed non-date value (1,141,523), so a big count is still not a date.
MAX_EXCEL_DATE_SERIAL = 256_000


# A whole number in this window is a year the clinic typed instead of a date,
# not an Excel serial (ticket 52). Read as a serial it lands in 1905, which no
# tracker records anything from, so the two readings cannot collide. Resolved
# to 1 January: Sarawak General Hospital wrote the same patients' diagnoses as
# real 1-January dates in its 2024 workbook and as bare years in 2025/2026, so
# that is the clinic's own convention for a year with no day. The upper bound
# stays below the Buddhist-era serials (~241,000) the ceiling above admits.
BARE_YEAR_MIN = 1900
BARE_YEAR_MAX = 2100


# The markers that mean "nothing was recorded here". Declared once and shared
# with safe_convert_column (clean/converters.py), which carried its own copy:
# the two drifted, and a date cell holding "-" or "N/A" reached the error
# sentinel while the identical numeric cell was correctly nulled (ticket 38).
# Compared against the stripped, lowercased value.
MISSING_VALUE_MARKERS: frozenset[str] = frozenset(
    {"", "na", "n/a", "n.a", "n.a.", "nan", "none", "null", "-", "--", "."}
)

# Absence written as a word rather than as a marker. Date-scoped: these were
# measured on the real 254-tracker set behind Python's own date sentinel
# ("Nil" 510 rows, "Unknown" 481, "?" 130, plus two spellings of each), where
# the sentinel's claim -- "a date was recorded and it is invalid" -- is simply
# false. The numeric path stamps 999999 on the same words; whether it should
# is a separate question this ticket deliberately did not reopen.
DATE_ABSENCE_MARKERS: frozenset[str] = frozenset(
    {"nil", "nill", "no", "unknown", "unknwon", "uncertain", "?", "??", "n\\a"}
)

# The tracker template's own instruction text, left in place in a data row
# instead of being replaced by a date. Substring-matched because clinics
# copy it with varying suffixes ("Insert Date or NA", "NA or Hospitalisation
# Date"), all of which mean the cell was never filled in.
DATE_PLACEHOLDER_FRAGMENTS: tuple[str, ...] = ("insert date", "hospitalisation date")


def _is_missing_date_text(value: str) -> bool:
    """True when the cell records an absence rather than an unusable date."""
    normalized = value.strip().lower()
    if normalized in MISSING_VALUE_MARKERS or normalized in DATE_ABSENCE_MARKERS:
        return True
    return any(fragment in normalized for fragment in DATE_PLACEHOLDER_FRAGMENTS)


def rescue_date_typos(s: str) -> tuple[str, bool]:
    """Substitute known month-name typos. Returns (possibly-rewritten, was_rescued)."""
    rescued = False
    for pattern, replacement in [*TYPO_REPLACEMENTS, *_THAI_MONTH_REPLACEMENTS]:
        new_s, n = re.subn(pattern, replacement, s)
        if n > 0:
            s, rescued = new_s, True
    return s, rescued


# A year below this is a source cell with a digit missing, not a date: the
# trackers record births, diagnoses and visits, none of which predate 1900.
# dateutil reads "1/16/224" as the year 224 without complaint, so the guard has
# to sit outside it, and it mirrors the cleaned stage's own beyond-tracker-year
# guard at the other end of the calendar (ticket 55).
_MIN_PLAUSIBLE_YEAR = 1900


# Characters that carry no meaning of their own but survive a copy-paste out of
# a browser or a chat message and make an otherwise clean date unparseable.
_INVISIBLE_CHARS = str.maketrans(dict.fromkeys("\u200b\u200c\u200d\u2060\ufeff"))


# A separator run damaged by a stray keystroke: either two or more separator
# characters where one belongs ("26-05- 2007", "23/05//2025", "02-Apr=-2026"),
# or a single character that is never a date separator to begin with ("_", "=").
# R recovers all of these because lubridate splits on any non-alphanumeric run,
# where dateutil requires the separator to be well-formed (ticket 56).
#
# Deliberately narrow. A single "/" or "." is left alone so that no
# already-parsing value changes reading, and a whitespace-only run is left alone
# so the trailing-free-text path ("16-Nov-2019 due to DKA") still sees its own
# word boundaries.
_DAMAGED_SEPARATOR = re.compile(r"(?=[-/_=.\s]*[-/_=.])[-/_=.\s]{2,}|[_=]")


def parse_date_flexible(
    date_str: str | None,
    error_val: str = "9999-09-09",
    tracker_year: int | None = None,
) -> date | None:
    """Parse date strings flexibly using Python's dateutil.parser.

    Handles common edge cases from A4D tracker data:
    - NA/None/empty values → None
    - Excel serial numbers (e.g., "45341.0") → converted from days since 1899-12-30
    - Long month names (e.g., "March") → truncated to 3 letters before parsing
    - A date followed by a free-text clause ("16-Nov-2019 due to DKA") → the
      date, via the longest parseable prefix
    - All standard date formats via dateutil.parser (very flexible)

    Examples:
        "Mar-18" → 2018-03-01
        "28/8/2017" → 2017-08-28
        "45341.0" → 2024-01-13 (Excel serial)
        "January-20" → 2020-01-01
        "Jun 2006" → 2006-06-01

    Args:
        date_str: Date string to parse
        error_val: Value to parse and return on failure (default "9999-09-09")

    Returns:
        Parsed date, None for NA/empty, or error date if parsing fails
    """
    return parse_date_detailed(date_str, error_val, tracker_year)[0]


def parse_date_detailed(
    date_str: str | None,
    error_val: str = "9999-09-09",
    tracker_year: int | None = None,
) -> tuple[date | None, TextDateRecovery | None]:
    """``parse_date_flexible`` plus what the free-text recogniser did, if it ran.

    The second element is None whenever the cell parsed without reaching the
    recogniser, which is the overwhelming majority. It exists so
    ``parse_date_column`` can log the decisions taken on a note -- what was
    read, what was discarded, what was filled in from the tracker year --
    without parsing every string twice to find out (ticket 39).
    """
    # Handle None and every way a tracker records "no date here"
    if date_str is None or _is_missing_date_text(str(date_str)):
        return None, None

    date_str = str(date_str).translate(_INVISIBLE_CHARS).strip()

    recovery: TextDateRecovery | None = None

    # A stay written as a bare range, with no prose around it to stop the
    # ordinary readings, is misread rather than refused: dateutil takes the
    # range's first number for a year, so "6-12 Nov 2020" becomes 2006-11-12 and
    # "3-9 Sep 2020" becomes 2003-09-09. The range patterns are explicit about
    # which number is the admission day, so they are consulted first when the
    # cell *opens* with one (ticket 39).
    leading = _DATE_IN_TEXT.match(date_str)
    if leading is not None and _is_range(leading):
        recovery = recover_date_from_text(date_str, tracker_year)
        if recovery.value is not None:
            return recovery.value, recovery
        recovery = None

    result = _parse_date_str(date_str)
    if result is None:
        repaired = _DAMAGED_SEPARATOR.sub("-", date_str)
        # A fourth number means the repair joined something that was never one
        # date: "26-05- 2007" is a damaged separator, where "1/2/2021-11/2/2021"
        # is two dates and reading it as one invents a date neither says.
        # Repair only what can still be a day/month/year.
        if repaired != date_str and len(re.findall(r"\d+", repaired)) <= 3:
            result = _parse_date_str(repaired)
    if result is None:
        # The date is somewhere inside a note rather than in a date-shaped cell.
        # Tried ahead of the prefix walk because it is the *explicit* reading:
        # the walk shortens the string until something parses and ends at
        # dateutil, so it will read the fragment "3-9 Sep" of "3-9 Sep 2020" as
        # the year 3 and publish 2003-09-09, where the range pattern reads the
        # admission day the note states (ticket 39).
        recovery = recover_date_from_text(date_str, tracker_year)
        result = recovery.value
    if result is None:
        recovery = None
        result = _parse_longest_parseable_prefix(date_str)
        if result is not None:
            # Reaching the walk means the ordinary readings failed, so this is
            # still a date recovered from free text and still reportable --
            # it is the shape the recogniser has no pattern for, e.g. a note
            # opening with a bare year ("2019 DKA").
            recovery = TextDateRecovery(result, 1, False)
    if result is not None and result.year >= _MIN_PLAUSIBLE_YEAR:
        return result, recovery

    logger.bind(error_code="invalid_value").warning(
        f"Could not parse date '{date_str}'. Returning error value {error_val}"
    )
    try:
        return datetime.strptime(error_val, "%Y-%m-%d").date(), recovery
    except ValueError:
        return None, recovery


def _parse_longest_parseable_prefix(date_str: str) -> date | None:
    """Drop trailing words until what remains parses as a date.

    Hospitalisation and diagnosis cells routinely carry a clause after the
    date ("16-Nov-2019 due to DKA", "Jan-2020 due to poor glycaemic control").
    The caller used to strip these by taking everything before the first
    space, which also destroyed genuine space-separated dates like
    "Jun 2006" (ticket 37) -- so the truncation lives here instead, tried only
    after the whole string has failed.

    A purely alphabetic prefix is skipped: dateutil would complete a bare
    month name from *today*, making the result depend on the run date.

    A small bare number is skipped for the mirror-image reason (ticket 53):
    truncating "26 Jun (ceton urine high)" down to "26" leaves a day-of-month,
    which ``_parse_date_str`` would read as an Excel serial and turn into a
    1900 date. A four-digit year is still a legitimate prefix ("2019 DKA"), so
    the cut is at the bare-year floor rather than at "is it numeric".
    """
    tokens = date_str.split()
    for end in range(len(tokens) - 1, 0, -1):
        prefix = " ".join(tokens[:end]).rstrip(",;.-/ ")
        if prefix.replace("-", "").replace(",", "").isalpha():
            continue
        if prefix.isdigit() and int(prefix) < BARE_YEAR_MIN:
            continue
        result = _parse_date_str(prefix)
        if result is not None:
            logger.debug(f"Parsed '{date_str}' via prefix '{prefix}' → {result}")
            return result
    return None


_MONTH_TOKEN = r"(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"


# The date shapes a clinician actually writes inside a note, in the order they
# are tried at each scan position (ticket 39). Every alternative is anchored on
# a day/month/year shape, so a cell carrying numbers and no date -- "3 month
# come back meet Doctor", "on stamlor 5mg" -- yields nothing rather than a date
# built from today, which is what dateutil's fuzzy mode returns for all of them
# and how R reads "7-15 Apr" as 2015-07-01.
#
# The two range alternatives come first because a stay is written with both
# endpoints ("6-12 Nov 2020", "20-29/12/2020") and the day wanted is the
# admission, i.e. the first: without them the general alternatives would match
# from the second number and publish the discharge date.
_DATE_IN_TEXT = re.compile(
    rf"""
      (?P<range_num>\b(?P<rn_day>\d{{1,2}})\s*[-–]\s*\d{{1,2}}\s*[/.]\s*
                     (?P<rn_month>\d{{1,2}})\s*[/.]\s*(?P<rn_year>\d{{2,4}})\b)
    | (?P<range_mon>\b(?P<rm_day>\d{{1,2}})(?:st|nd|rd|th)?\s*[-–]\s*
                     \d{{1,2}}(?:st|nd|rd|th)?\s*[-–]?\s*
                     (?P<rm_month>{_MONTH_TOKEN})
                     (?:\s*[-,./ ]?\s*'?(?P<rm_year>\d{{2,4}})\b)?)
    | (?P<full_num>\b(?P<fn_day>\d{{1,2}})\s*[/.-]\s*(?P<fn_month>\d{{1,2}})\s*[/.-]\s*
                    (?P<fn_year>\d{{2,4}})\b(?!\s*/\s*\d))
    | (?P<full_mon>\b(?P<fm_day>\d{{1,2}})(?:st|nd|rd|th)?\s*[-./ ]?\s*
                    (?P<fm_month>{_MONTH_TOKEN})\s*[-,./ ]?\s*'?(?P<fm_year>\d{{2,4}})\b)
    | (?P<mon_year>\b(?P<my_month>{_MONTH_TOKEN})\s*[-,./ ]?\s*'?(?P<my_year>\d{{2,4}})\b)
    | (?P<day_mon>\b(?P<dm_day>\d{{1,2}})(?:st|nd|rd|th)?\s*[-./ ]?\s*
                   (?P<dm_month>{_MONTH_TOKEN})\b(?![-,./=_ ]*'?\d))
    """,
    re.IGNORECASE | re.VERBOSE,
)

_MONTH_NUMBERS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip


def _is_range(match: re.Match[str]) -> bool:
    """True when this match is a stay written with both its endpoints."""
    return match.group("range_num") is not None or match.group("range_mon") is not None


@dataclass(frozen=True)
class TextDateRecovery:
    """What the free-text recogniser read out of one cell.

    ``tokens_found`` and ``year_inferred`` exist so the caller can log *which*
    decision was taken, not just the result: a cell naming three admissions and
    a cell naming one are both published as a single date, and only the first
    is a source-tracker defect worth reporting back to the clinic.
    """

    value: date | None
    tokens_found: int
    year_inferred: bool


def _expand_two_digit_year(digits: str) -> int:
    """00-68 -> 2000-2068, 69-99 -> 1969-1999, matching the month-year branch."""
    if len(digits) == 4:
        return int(digits)
    year = int(digits)
    return 2000 + year if year <= 68 else 1900 + year


def recover_date_from_text(text: str, tracker_year: int | None = None) -> TextDateRecovery:
    """Read the first date a clinical note contains.

    The ``hospitalisation_date`` header is free text -- "Hospitalisation due to
    diabetes emergency or glucose control (Include Date)" -- so clinicians write
    a case note with the date somewhere inside it. Recovery previously depended
    on where the date sat, because the prefix walk can only reach one at the
    front of the string: "16-Nov-2019 due to DKA" was published and
    "DKA 16-Nov-2019" was sentinelled.

    Where a note records several dates, the first is published and the rest are
    discarded -- a single date column cannot represent three admissions, and the
    repair for that is the source workbook, not a cleverer parser. A day the
    note omits becomes the 1st; a year it omits comes from the tracker, which is
    the one component taken from outside the cell.
    """
    matches = list(_DATE_IN_TEXT.finditer(text))
    if not matches:
        return TextDateRecovery(None, 0, False)

    first = matches[0]
    # A range names two days, so it is a discard even though it is one stay.
    tokens = len(matches) + (1 if _is_range(first) else 0)
    groups = first.groupdict()

    for prefix in ("rn", "rm", "fn", "fm", "my", "dm"):
        if groups.get(f"{prefix}_month") is None:
            continue
        raw_month = groups[f"{prefix}_month"]
        month = (
            int(raw_month) if raw_month.isdigit() else _MONTH_NUMBERS.get(raw_month[:3].lower(), 0)
        )
        day = int(groups[f"{prefix}_day"]) if groups.get(f"{prefix}_day") else 1
        raw_year = groups.get(f"{prefix}_year")
        year_inferred = raw_year is None
        if year_inferred:
            if tracker_year is None:
                return TextDateRecovery(None, tokens, False)
            year = tracker_year
        else:
            year = _expand_two_digit_year(raw_year)
        try:
            value = date(year, month, day)
        except ValueError:
            return TextDateRecovery(None, tokens, False)
        if not _MIN_PLAUSIBLE_YEAR <= year <= BARE_YEAR_MAX:
            return TextDateRecovery(None, tokens, False)
        return TextDateRecovery(value, tokens, year_inferred)

    return TextDateRecovery(None, tokens, False)


def _parse_date_str(date_str: str) -> date | None:
    """Parse one already-trimmed, non-null string. None means unparseable."""
    # Handle Excel serial numbers
    # Excel stores dates as number of days since 1899-12-30
    try:
        numeric_val = float(date_str)
        if numeric_val.is_integer() and BARE_YEAR_MIN <= numeric_val <= BARE_YEAR_MAX:
            result = date(int(numeric_val), 1, 1)
            logger.debug(f"Parsed bare year {date_str} → {result}")
            return result
        if 1 < numeric_val < MAX_EXCEL_DATE_SERIAL:
            days = int(numeric_val)
            result = EXCEL_EPOCH + timedelta(days=days)
            logger.debug(f"Parsed Excel serial {date_str} → {result}")
            return result
    except ValueError:
        pass  # Not a number, continue with text parsing

    # Truncate long month names to their 3-letter abbreviation
    # ("March" -> "Mar", "January" -> "Jan", "Sept" -> "Sep"), which the
    # month-year branch below and dateutil both handle.
    #
    # Anchored on the month names themselves rather than on any run of 4+
    # letters (ticket 37): the previous form dropped only the *fourth* letter,
    # so "March" became "Marh" and "January" became "Janary" -- unparseable,
    # and sentinelled as an error date. Every full month name in the trackers
    # was affected.
    date_str = MONTH_NAME_PATTERN.sub(lambda m: m.group(1).title(), date_str)

    # Special handling for month-year formats (e.g., "Mar-18", "Jan-20", "May18")
    # These should be interpreted as "Mar 2018", "Jan 2020", not "Mar day-18 of current year"
    # Separator (hyphen/space) is optional to handle both "May-18" and "May18"
    # A 4-digit year ("Jun 2006", the 2017-era trackers' diagnosis-date format)
    # is handled here too rather than left to dateutil: dateutil fills the
    # missing day from datetime.now(), which makes the parse depend on the day
    # the pipeline runs -- and can push a genuinely historical date past the
    # tracker year, where _validate_dates then sentinels it (ticket 37).
    # The apostrophe spelling ("Jun'09", "Apr'21") is admitted alongside the
    # hyphen and the space (ticket 53): without it the value fell through to
    # dateutil, which read the two digits as a day-of-month in the current year.
    month_year_pattern = r"^([A-Za-z]{3})[-\s']?(\d{2}|\d{4})$"
    match = re.match(month_year_pattern, date_str)
    if match:
        month_abbr, year_digits = match.groups()
        if len(year_digits) == 4:
            year_4digit = int(year_digits)
        else:
            # Convert 2-digit year to 4-digit: 00-68 → 2000-2068, 69-99 → 1969-1999
            year_int = int(year_digits)
            if year_int <= 68:
                year_4digit = 2000 + year_int
            else:
                year_4digit = 1900 + year_int
        # Parse as "Mon YYYY" format, defaults to first day of month
        date_str_full = f"{month_abbr} {year_4digit}"
        try:
            result = datetime.strptime(date_str_full, "%b %Y").date()
            logger.debug(f"Parsed month-year '{date_str}' → {result}")
            return result
        except ValueError:
            pass  # Fall through to general parser

    # Try explicit DD/MM/YYYY and DD-MM-YYYY formats first (Southeast Asian standard)
    # This is more reliable than dateutil.parser's dayfirst=True parameter
    for fmt in [
        "%d/%m/%Y",  # 06/05/2013 → 2013-05-06 (6th May)
        "%d-%m-%Y",  # 06-05-2013 → 2013-05-06
        "%d/%m/%y",  # 06/05/13 → 2013-05-06
        "%d-%m-%y",  # 06-05-13 → 2013-05-06
        "%Y-%m-%d",  # 2013-05-06 (ISO format from Excel)
        "%d/%m/%Y %H:%M:%S",  # With time component
        "%Y-%m-%d %H:%M:%S",  # ISO with time
    ]:
        try:
            result = datetime.strptime(date_str, fmt).date()
            logger.debug(f"Parsed '{date_str}' using format {fmt} → {result}")
            return result
        except ValueError:
            continue

    # Fall back to dateutil.parser for other formats (month names, etc.)
    # dayfirst=True is still useful for remaining ambiguous cases
    return _parse_with_dateutil(date_str)


# Two defaults that share no field value, so any component dateutil takes from
# the default differs between the two parses and can be told apart from one the
# string actually supplied. Both are far outside the trackers' range, so a
# genuine value can never coincide with either.
_PROBE_DEFAULT_A = datetime(1111, 1, 1)
_PROBE_DEFAULT_B = datetime(2222, 2, 2)


def _parse_with_dateutil(date_str: str) -> date | None:
    """dateutil's reading, with every component it invented from today rejected.

    ``dateutil.parser.parse`` fills any field the string omits from
    ``datetime.now()``, so "10/2019" becomes the 19th of October on the 19th
    and the 3rd on the 3rd -- the cleaned output changes with no input change.
    Ticket 50 hit this through a rich-text-damaged "July2014" and fixed that one
    route into it; ticket 53 found the same fill still reachable through the
    numeric ("10/2019") and comma-separated ("Mar, 2017") month-year spellings,
    which the alphabetic month-year branch above does not match, and through a
    bare month name inside a longer string.

    Parsing twice against two disjoint defaults tells a supplied component from
    an invented one without having to enumerate the spellings that reach here:
    - an invented **day** resolves to the 1st, the same convention the
      alphabetic month-year branch already uses;
    - an invented **month or year** makes the cell unparseable, because
      neither can be recovered from the string and the current date is not an
      answer.
    """
    try:
        probe_a = date_parser.parse(date_str, dayfirst=True, default=_PROBE_DEFAULT_A)
        probe_b = date_parser.parse(date_str, dayfirst=True, default=_PROBE_DEFAULT_B)
    except ValueError, date_parser.ParserError, OverflowError:
        return None

    if probe_a.year != probe_b.year or probe_a.month != probe_b.month:
        logger.debug(f"Rejected '{date_str}': dateutil would supply the month/year from today")
        return None

    day = probe_a.day if probe_a.day == probe_b.day else 1
    result = date(probe_a.year, probe_a.month, day)
    logger.debug(f"Parsed '{date_str}' with dateutil → {result}")
    return result
