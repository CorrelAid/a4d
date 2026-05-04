"""Shared tracker-level extraction plumbing used by patient and product arms.

Holds helpers that are not patient-specific or product-specific: detecting
month sheets in a workbook, parsing the tracker year, normalising Excel
error strings, and parsing the sheet-name month suffix.
"""

import calendar
import re
from pathlib import Path

import polars as pl
from loguru import logger

from a4d.config import settings


def get_tracker_year(tracker_file: Path, month_sheets: list[str]) -> int:
    """Extract tracker year from month sheet names or filename.

    Tries to parse year from month sheet names (e.g., "Jan24" -> 2024).
    Falls back to extracting from filename if parsing fails.
    Validates year is in reasonable range (2017-2030).

    Args:
        tracker_file: Path to the tracker Excel file
        month_sheets: List of month sheet names

    Returns:
        Year of the tracker (e.g., 2024)

    Raises:
        ValueError: If year cannot be determined or is out of valid range

    Example:
        >>> get_tracker_year(Path("2024_Clinic.xlsx"), ["Jan24", "Feb24"])
        2024
    """
    for sheet in month_sheets:
        match = re.search(r"(\d{2})$", sheet)
        if match:
            year_suffix = int(match.group(1))
            year = 2000 + year_suffix  # Assume 20xx until 2100
            logger.debug(f"Parsed year {year} from sheet name '{sheet}'")

            if not (settings.min_tracker_year <= year <= settings.max_tracker_year):
                raise ValueError(
                    f"Year {year} is out of valid range "
                    f"({settings.min_tracker_year}-{settings.max_tracker_year}). "
                    f"Parsed from sheet name '{sheet}'"
                )

            return year

    match = re.search(r"(\d{4})", tracker_file.name)
    if match:
        year = int(match.group(1))
        logger.debug(f"Parsed year {year} from filename '{tracker_file.name}'")

        if not (settings.min_tracker_year <= year <= settings.max_tracker_year):
            raise ValueError(
                f"Year {year} is out of valid range "
                f"({settings.min_tracker_year}-{settings.max_tracker_year}). "
                f"Parsed from filename '{tracker_file.name}'"
            )

        return year

    raise ValueError(
        f"Could not determine year from month sheets {month_sheets} or filename {tracker_file.name}"
    )


def find_month_sheets(workbook) -> list[str]:
    """Find all month sheets in the tracker workbook.

    Month sheets are identified by matching against month abbreviations
    (Jan, Feb, Mar, etc.) and sorted by month number for consistent processing.

    Args:
        workbook: openpyxl Workbook object

    Returns:
        List of month sheet names found in the workbook, sorted by month number
        (Jan=1, Feb=2, ..., Dec=12)

    Example:
        >>> wb = load_workbook("tracker.xlsx")
        >>> find_month_sheets(wb)
        ['Jan24', 'Feb24', 'Mar24', ...]
    """
    month_abbrs = list(calendar.month_abbr)[1:]  # ['Jan', 'Feb', ...]
    month_sheets = []

    for sheet_name in workbook.sheetnames:
        if any(sheet_name.startswith(abbr) for abbr in month_abbrs):
            month_sheets.append(sheet_name)

    def get_month_number(sheet_name: str) -> int:
        """Extract month number from sheet name (Jan=1, ..., Dec=12)."""
        month_prefix = sheet_name[:3]
        try:
            return month_abbrs.index(month_prefix) + 1
        except ValueError:
            return 999  # Push unrecognized sheets to end

    month_sheets.sort(key=get_month_number)

    logger.info(f"Found {len(month_sheets)} month sheets (sorted by month): {month_sheets}")
    return month_sheets


def clean_excel_errors(df: pl.DataFrame) -> pl.DataFrame:
    """Convert Excel error strings to NULL values.

    Excel error codes like #DIV/0!, #VALUE!, etc. are not usable values
    and should be treated as missing data.

    Args:
        df: DataFrame with potential Excel error strings

    Returns:
        DataFrame with Excel errors converted to NULL

    Example:
        >>> df = pl.DataFrame({"bmi": ["17.5", "#DIV/0!", "18.2"]})
        >>> clean_df = clean_excel_errors(df)
        >>> clean_df["bmi"].to_list()
        ['17.5', None, '18.2']
    """
    excel_errors = [
        "#DIV/0!",
        "#VALUE!",
        "#REF!",
        "#NAME?",
        "#NUM!",
        "#N/A",
        "#NULL!",
    ]

    # Excel error strings only appear in String columns; filtering by dtype
    # lets both patient and product callers share this helper regardless of
    # which metadata columns (e.g. product_table_year:Float64) are present.
    data_cols = [col for col in df.columns if df.schema[col] == pl.String]

    if not data_cols:
        return df

    for error in excel_errors:
        for col in data_cols:
            count = (df[col] == error).sum()
            if count > 0:
                logger.debug(f"Converted {count} '{error}' values to NULL in column '{col}'")

    df = df.with_columns(
        [
            pl.when(pl.col(col).is_in(excel_errors)).then(None).otherwise(pl.col(col)).alias(col)
            for col in data_cols
        ]
    )

    return df


def extract_tracker_month(sheet_name: str) -> int:
    """Extract month number (1-12) from sheet name.

    Args:
        sheet_name: Sheet name like "Jan24", "Feb24", etc.

    Returns:
        Month number (1 for January, 2 for February, etc.)

    Raises:
        ValueError: If month cannot be extracted or is out of valid range

    Example:
        >>> extract_tracker_month("Jan24")
        1
        >>> extract_tracker_month("Dec23")
        12
    """
    month_abbrs = list(calendar.month_abbr)[1:]  # ['Jan', 'Feb', ...]

    # Check first 3 characters
    month_prefix = sheet_name[:3]

    if month_prefix in month_abbrs:
        month_num = month_abbrs.index(month_prefix) + 1  # +1 because index is 0-based

        # Validate month is in valid range (1-12)
        # This should always be true given the logic above, but check anyway for safety
        if not (1 <= month_num <= 12):
            raise ValueError(
                f"Month number {month_num} is out of valid range (1-12). "
                f"Parsed from sheet name '{sheet_name}'"
            )

        return month_num

    raise ValueError(f"Could not extract month from sheet name '{sheet_name}'")
