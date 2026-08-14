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
]


# Any month name written out beyond its 3-letter abbreviation, so it can be
# truncated back to that abbreviation. Word-boundary-anchored so a longer word
# that merely starts with a month name is left alone.
MONTH_NAME_PATTERN = re.compile(
    r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]+\b",
    re.IGNORECASE,
)


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
    for pattern, replacement in TYPO_REPLACEMENTS:
        new_s, n = re.subn(pattern, replacement, s)
        if n > 0:
            s, rescued = new_s, True
    return s, rescued


def parse_date_flexible(date_str: str | None, error_val: str = "9999-09-09") -> date | None:
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
    # Handle None and every way a tracker records "no date here"
    if date_str is None or _is_missing_date_text(str(date_str)):
        return None

    date_str = str(date_str).strip()

    result = _parse_date_str(date_str)
    if result is None:
        result = _parse_longest_parseable_prefix(date_str)
    if result is not None:
        return result

    logger.bind(error_code="invalid_value").warning(
        f"Could not parse date '{date_str}'. Returning error value {error_val}"
    )
    try:
        return datetime.strptime(error_val, "%Y-%m-%d").date()
    except ValueError:
        return None


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
    """
    tokens = date_str.split()
    for end in range(len(tokens) - 1, 0, -1):
        prefix = " ".join(tokens[:end]).rstrip(",;.-/ ")
        if prefix.replace("-", "").replace(",", "").isalpha():
            continue
        result = _parse_date_str(prefix)
        if result is not None:
            logger.debug(f"Parsed '{date_str}' via prefix '{prefix}' → {result}")
            return result
    return None


def _parse_date_str(date_str: str) -> date | None:
    """Parse one already-trimmed, non-null string. None means unparseable."""
    # Handle Excel serial numbers
    # Excel stores dates as number of days since 1899-12-30
    try:
        numeric_val = float(date_str)
        if 1 < numeric_val < 100000:  # Reasonable range for Excel dates (1900-2173)
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
    month_year_pattern = r"^([A-Za-z]{3})[-\s]?(\d{2}|\d{4})$"
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
    try:
        result = date_parser.parse(date_str, dayfirst=True).date()
        logger.debug(f"Parsed '{date_str}' with dateutil → {result}")
        return result
    except ValueError, date_parser.ParserError, OverflowError:
        return None
