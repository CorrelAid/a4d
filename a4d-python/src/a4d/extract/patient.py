"""Patient data extraction from Excel tracker files.

This module handles reading patient data from Excel trackers, which have
evolved over the years with different formats and structures.
"""

import calendar
import re
from pathlib import Path

import polars as pl
from loguru import logger
from openpyxl import load_workbook

from a4d.reference.synonyms import ColumnMapper


def get_tracker_year(tracker_file: Path, month_sheets: list[str]) -> int:
    """Extract tracker year from month sheet names or filename.

    Tries to parse year from month sheet names (e.g., "Jan24" -> 2024).
    Falls back to extracting from filename if parsing fails.

    Args:
        tracker_file: Path to the tracker Excel file
        month_sheets: List of month sheet names

    Returns:
        Year of the tracker (e.g., 2024)

    Raises:
        ValueError: If year cannot be determined

    Example:
        >>> get_tracker_year(Path("2024_Clinic.xlsx"), ["Jan24", "Feb24"])
        2024
    """
    # Try to parse year from month sheet names (e.g., "Jan24" -> 24)
    # Look for 2-digit numbers in month sheet names
    for sheet in month_sheets:
        match = re.search(r"(\d{2})$", sheet)
        if match:
            year_suffix = int(match.group(1))
            # Assume 20xx for now (until 2100!)
            year = 2000 + year_suffix
            logger.debug(f"Parsed year {year} from sheet name '{sheet}'")
            return year

    # Fallback: extract from filename (e.g., "2024_Clinic.xlsx")
    match = re.search(r"(\d{4})", tracker_file.name)
    if match:
        year = int(match.group(1))
        logger.debug(f"Parsed year {year} from filename '{tracker_file.name}'")
        return year

    raise ValueError(f"Could not determine year from month sheets {month_sheets} or filename {tracker_file.name}")


def find_month_sheets(workbook) -> list[str]:
    """Find all month sheets in the tracker workbook.

    Month sheets are identified by matching against month abbreviations
    (Jan, Feb, Mar, etc.).

    Args:
        workbook: openpyxl Workbook object

    Returns:
        List of month sheet names found in the workbook

    Example:
        >>> wb = load_workbook("tracker.xlsx")
        >>> find_month_sheets(wb)
        ['Jan24', 'Feb24', 'Mar24', ...]
    """
    month_abbrs = list(calendar.month_abbr)[1:]  # ['Jan', 'Feb', ...]
    month_sheets = []

    for sheet_name in workbook.sheetnames:
        # Check if sheet name starts with a month abbreviation
        if any(sheet_name.startswith(abbr) for abbr in month_abbrs):
            month_sheets.append(sheet_name)

    logger.info(f"Found {len(month_sheets)} month sheets: {month_sheets}")
    return month_sheets


def extract_patient_data(
    tracker_file: Path,
    sheet_name: str,
    year: int,
) -> pl.DataFrame:
    """Extract patient data from a single sheet.

    This function handles the complex logic of finding where patient data
    starts in the sheet (by scanning column A for non-None values) and
    reading the headers (which may be 1 or 2 rows depending on the year).

    Args:
        tracker_file: Path to the tracker Excel file
        sheet_name: Name of the sheet to extract
        year: Year of the tracker (affects header detection)

    Returns:
        Polars DataFrame with patient data (all columns as strings)

    Example:
        >>> df = extract_patient_data(
        ...     Path("2024_Clinic.xlsx"),
        ...     "Jan24",
        ...     2024
        ... )
    """
    # Single-pass read-only loading for optimal performance
    # We don't need merged cell handling - None values are fine!
    wb = load_workbook(
        tracker_file,
        read_only=True,
        data_only=True,
        keep_vba=False,
        keep_links=False,
    )
    ws = wb[sheet_name]

    # Find where patient data starts (first non-None in column A)
    data_start_row = None
    for row_idx, (cell_value,) in enumerate(
        ws.iter_rows(min_col=1, max_col=1, values_only=True), start=1
    ):
        if cell_value is not None:
            data_start_row = row_idx
            break

    if data_start_row is None:
        raise ValueError(f"No patient data found in sheet '{sheet_name}'")

    # Headers are 1-2 rows before data starts
    header_row_1 = data_start_row - 1
    header_row_2 = data_start_row - 2

    logger.debug(
        f"Sheet '{sheet_name}': Patient data found in rows "
        f"{data_start_row} to {ws.max_row}"
    )

    # Read header rows directly (no merged cell handling needed)
    # In read-only mode, we need to determine max_column from the data
    # Read a reasonable number of columns (100 should cover all trackers)
    max_cols = 100
    header_1_raw = list(ws.iter_rows(min_row=header_row_1, max_row=header_row_1, min_col=1, max_col=max_cols, values_only=True))[0]
    header_2_raw = list(ws.iter_rows(min_row=header_row_2, max_row=header_row_2, min_col=1, max_col=max_cols, values_only=True))[0]

    # Trim to actual width (last non-None column)
    last_col = max_cols
    for i in range(len(header_1_raw) - 1, -1, -1):
        if header_1_raw[i] is not None or header_2_raw[i] is not None:
            last_col = i + 1
            break

    header_1 = list(header_1_raw[:last_col])
    header_2 = list(header_2_raw[:last_col])

    # Build headers by merging h1 and h2 where both exist
    # Handle horizontally merged cells by filling forward from previous column
    # For merged cells (e.g., "Updated HbA1c" merged across 2 cols):
    #   Col 12: h2="Updated HbA1c", h1="%"
    #   Col 13: h2=None (merged), h1="(dd-mmm-yyyy)" → use previous h2
    logger.info("Processing headers...")
    headers = []
    prev_h2 = None  # Track previous h2 for horizontal merges

    for h1, h2 in zip(header_1, header_2, strict=True):
        if h1 and h2:
            # Both have values: concatenate (multi-line detail)
            headers.append(f"{h2} {h1}".strip())
            prev_h2 = h2
        elif h2:
            # Only h2 has value: use it (multi-line base or merged cell)
            headers.append(str(h2).strip())
            prev_h2 = h2
        elif h1:
            # Only h1 has value: check if h2 is horizontally merged
            if prev_h2:
                # h2 is None but h1 exists: likely horizontal merge, fill forward
                headers.append(f"{prev_h2} {h1}".strip())
            else:
                # No previous h2: use h1 (single-line or edge case)
                headers.append(str(h1).strip())
            # Keep prev_h2 for next iteration (it's still merged)
        else:
            # Both None
            headers.append(None)
            prev_h2 = None  # Reset if both are None

    # Clean up headers: remove newlines, extra spaces
    headers = [re.sub(r"\s+", " ", h.replace("\n", " ")) if h else None for h in headers]

    # Note: R adjusts row_min/row_max for 2022+ trackers because openxlsx skips empty rows
    # openpyxl does NOT skip empty rows, so we don't need this adjustment

    # Read data using iter_rows (fast in read-only mode)
    data = []
    for row in ws.iter_rows(
        min_row=data_start_row,
        max_row=ws.max_row,
        min_col=1,
        max_col=len(headers),
        values_only=True,
    ):
        # Stop at first completely empty row (all None values)
        if all(cell is None for cell in row):
            break
        # Skip rows where first column (patient index) is None
        if row[0] is None:
            continue
        data.append(row)

    wb.close()

    # Create DataFrame
    # Filter out None headers and corresponding columns
    valid_cols = [(i, h) for i, h in enumerate(headers) if h]

    if not valid_cols:
        # No valid headers, return empty DataFrame
        return pl.DataFrame()

    valid_indices = [i for i, _ in valid_cols]
    valid_headers = [h for _, h in valid_cols]

    # Filter data to only include valid columns
    filtered_data = [[row[i] for i in valid_indices] for row in data]

    # Create DataFrame with all columns as strings
    df = pl.DataFrame(
        {
            header: [str(row[i]) if row[i] is not None else None for row in filtered_data]
            for i, header in enumerate(valid_headers)
        }
    )

    logger.info(f"Extracted {len(df)} rows x {len(df.columns)} cols from sheet '{sheet_name}'")

    return df
