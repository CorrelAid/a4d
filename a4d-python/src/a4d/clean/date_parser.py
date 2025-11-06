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
from typing import Optional

from dateutil import parser as date_parser
from loguru import logger

# Excel epoch: dates stored as days since this date
EXCEL_EPOCH = date(1899, 12, 30)


def parse_date_flexible(date_str: Optional[str], error_val: str = "9999-09-09") -> Optional[date]:
    """Parse date strings flexibly using Python's dateutil.parser.

    Handles common edge cases from A4D tracker data:
    - NA/None/empty values → None
    - Excel serial numbers (e.g., "45341.0") → converted from days since 1899-12-30
    - 4-letter month names (e.g., "March") → truncated to 3 letters before parsing
    - All standard date formats via dateutil.parser (very flexible)

    Examples:
        "Mar-18" → 2018-03-01
        "28/8/2017" → 2017-08-28
        "45341.0" → 2024-01-13 (Excel serial)
        "January-20" → 2020-01-01

    Args:
        date_str: Date string to parse
        error_val: Value to parse and return on failure (default "9999-09-09")

    Returns:
        Parsed date, None for NA/empty, or error date if parsing fails
    """
    # Handle None, empty, or NA strings
    if date_str is None or date_str == "" or str(date_str).strip().lower() in ["na", "nan", "null", "none"]:
        return None

    date_str = str(date_str).strip()

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

    # Truncate 4-letter month names to 3 letters for better parsing
    # "March" → "Mar", "January" → "Jan", etc.
    if re.search(r"[a-zA-Z]{4}", date_str):
        date_str = re.sub(r"([a-zA-Z]{3})[a-zA-Z]", r"\1", date_str)

    # Special handling for month-year formats (e.g., "Mar-18", "Jan-20")
    # These should be interpreted as "Mar 2018", "Jan 2020", not "Mar day-18 of current year"
    month_year_pattern = r"^([A-Za-z]{3})[-\s](\d{2})$"
    match = re.match(month_year_pattern, date_str)
    if match:
        month_abbr, year_2digit = match.groups()
        # Convert 2-digit year to 4-digit: 00-68 → 2000-2068, 69-99 → 1969-1999
        year_int = int(year_2digit)
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
    except (ValueError, date_parser.ParserError) as e:
        # If parsing fails, log warning and return error date
        logger.warning(f"Could not parse date '{date_str}': {e}. Returning error value {error_val}")
        try:
            return datetime.strptime(error_val, "%Y-%m-%d").date()
        except ValueError:
            return None
