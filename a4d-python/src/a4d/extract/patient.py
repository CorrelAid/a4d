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

from a4d.reference.synonyms import ColumnMapper, load_patient_mapper


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

    raise ValueError(
        f"Could not determine year from month sheets {month_sheets} or filename {tracker_file.name}"
    )


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


def find_data_start_row(ws) -> int:
    """Find the first row containing patient data.

    Scans column A for the first non-None value, which indicates
    where patient data begins.

    Args:
        ws: openpyxl worksheet object

    Returns:
        Row number (1-indexed) where patient data starts

    Raises:
        ValueError: If no data is found in column A
    """
    for row_idx, (cell_value,) in enumerate(
        ws.iter_rows(min_col=1, max_col=1, values_only=True), start=1
    ):
        if cell_value is not None:
            return row_idx

    raise ValueError("No patient data found in column A")


def read_header_rows(ws, data_start_row: int, max_cols: int = 100) -> tuple[list, list]:
    """Read and trim the two header rows above the data.

    Headers are located in the two rows immediately before data_start_row.
    Reads up to max_cols columns and trims to the last non-None column.

    Args:
        ws: openpyxl worksheet object
        data_start_row: Row number where patient data starts
        max_cols: Maximum number of columns to read (default: 100)

    Returns:
        Tuple of (header_1, header_2) lists, trimmed to actual width

    Example:
        >>> header_1, header_2 = read_header_rows(ws, 77)
        >>> len(header_1)
        31
    """
    header_row_1 = data_start_row - 1
    header_row_2 = data_start_row - 2

    # Read raw header rows
    header_1_raw = list(
        ws.iter_rows(
            min_row=header_row_1,
            max_row=header_row_1,
            min_col=1,
            max_col=max_cols,
            values_only=True,
        )
    )[0]
    header_2_raw = list(
        ws.iter_rows(
            min_row=header_row_2,
            max_row=header_row_2,
            min_col=1,
            max_col=max_cols,
            values_only=True,
        )
    )[0]

    # Trim to actual width (last non-None column)
    last_col = max_cols
    for i in range(len(header_1_raw) - 1, -1, -1):
        if header_1_raw[i] is not None or header_2_raw[i] is not None:
            last_col = i + 1
            break

    header_1 = list(header_1_raw[:last_col])
    header_2 = list(header_2_raw[:last_col])

    return header_1, header_2


def merge_headers(header_1: list, header_2: list) -> list[str | None]:
    """Merge two header rows with forward-fill for horizontally merged cells.

    Handles the complex logic of merging multi-line headers while preserving
    information from horizontally merged cells by filling forward.

    Logic:
    - If both h1 and h2 exist: concatenate as "h2 h1"
    - If only h2 exists: use h2
    - If only h1 exists and prev_h2 exists: use "prev_h2 h1" (horizontal merge)
    - If only h1 exists and no prev_h2: use h1
    - If both None: append None

    Args:
        header_1: First header row (closer to data)
        header_2: Second header row (further from data)

    Returns:
        List of merged header strings with whitespace normalized

    Example:
        >>> h1 = ["%", "(dd-mmm-yyyy)", "kg"]
        >>> h2 = ["Updated HbA1c", None, "Body Weight"]
        >>> merge_headers(h1, h2)
        ['Updated HbA1c %', 'Updated HbA1c (dd-mmm-yyyy)', 'Body Weight kg']
    """
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

    return headers


def read_patient_rows(ws, data_start_row: int, num_columns: int) -> list[tuple]:
    """Read patient data rows from the worksheet.

    Reads from data_start_row until either ws.max_row or the first completely
    empty row. Skips rows where the first column (patient index) is None.

    Args:
        ws: openpyxl worksheet object
        data_start_row: Row number where patient data starts
        num_columns: Number of columns to read

    Returns:
        List of tuples, each containing one row of patient data

    Example:
        >>> rows = read_patient_rows(ws, 77, 31)
        >>> len(rows)
        4
    """
    data = []
    for row in ws.iter_rows(
        min_row=data_start_row,
        max_row=ws.max_row,
        min_col=1,
        max_col=num_columns,
        values_only=True,
    ):
        # Stop at first completely empty row (all None values)
        if all(cell is None for cell in row):
            break
        # Skip rows where first column (patient index) is None
        if row[0] is None:
            continue
        data.append(row)

    return data


def merge_duplicate_columns_data(
    headers: list[str], data: list[list]
) -> tuple[list[str], list[list]]:
    """Merge data from duplicate column headers by concatenating with commas.

    When Excel cells are merged both horizontally and vertically, the forward-fill
    logic in merge_headers() can create duplicate column names. This function
    merges the data from duplicate columns (like R's tidyr::unite()).

    Args:
        headers: List of header strings (may contain duplicates)
        data: List of data rows (each row is a list)

    Returns:
        Tuple of (unique_headers, merged_data)

    Example:
        >>> headers = ["ID", "DM Complications", "DM Complications", "DM Complications", "Age"]
        >>> data = [["1", "A", "B", "C", "25"], ["2", "X", "Y", "Z", "30"]]
        >>> merge_duplicate_columns_data(headers, data)
        (['ID', 'DM Complications', 'Age'], [['1', 'A,B,C', '25'], ['2', 'X,Y,Z', '30']])
    """
    if len(headers) == len(set(headers)):
        # No duplicates
        return headers, data

    # Map each header to its column positions
    from collections import defaultdict

    header_positions: dict[str, list[int]] = defaultdict(list)
    for idx, header in enumerate(headers):
        header_positions[header].append(idx)

    # Unique headers in order of first appearance (dict keys preserve insertion order in Python 3.7+)
    unique_headers = list(header_positions.keys())

    # Log which headers are duplicated
    duplicated = [h for h, positions in header_positions.items() if len(positions) > 1]
    if duplicated:
        logger.debug(f"Merging {len(duplicated)} duplicate column groups: {duplicated}")

    # Merge data for duplicate columns
    merged_data = []
    for row in data:
        merged_row = []
        for header in unique_headers:
            positions = header_positions[header]
            if len(positions) == 1:
                # No duplicate, use value as-is
                merged_row.append(row[positions[0]])
            else:
                # Merge multiple columns: join non-empty values with commas
                values = [str(row[pos]) if row[pos] is not None else "" for pos in positions]
                values = [v for v in values if v]  # Filter out empty strings
                merged_value = ",".join(values) if values else None
                merged_row.append(merged_value)
        merged_data.append(merged_row)

    return unique_headers, merged_data


def filter_valid_columns(
    headers: list[str | None], data: list[tuple]
) -> tuple[list[str], list[list]]:
    """Filter out columns with None headers and their corresponding data.

    Args:
        headers: List of header strings (may contain None)
        data: List of data rows

    Returns:
        Tuple of (valid_headers, filtered_data)

    Example:
        >>> headers = ["ID", None, "Name", None, "Age"]
        >>> data = [("1", "x", "Alice", "y", "30")]
        >>> filter_valid_columns(headers, data)
        (['ID', 'Name', 'Age'], [['1', 'Alice', '30']])
    """
    valid_cols = [(i, h) for i, h in enumerate(headers) if h]

    if not valid_cols:
        return [], []

    valid_indices = [i for i, _ in valid_cols]
    valid_headers = [h for _, h in valid_cols]

    # Filter data to only include valid columns
    filtered_data = [[row[i] for i in valid_indices] for row in data]

    return valid_headers, filtered_data


def extract_patient_data(
    tracker_file: Path,
    sheet_name: str,
    year: int,
) -> pl.DataFrame:
    """Extract patient data from a single sheet.

    Orchestrates the extraction process by:
    1. Loading the workbook in read-only mode
    2. Finding where patient data starts
    3. Reading and merging header rows (with forward-fill for horizontal merges)
    4. Filtering valid columns
    5. Reading patient data rows
    6. Creating a Polars DataFrame

    Args:
        tracker_file: Path to the tracker Excel file
        sheet_name: Name of the sheet to extract
        year: Year of the tracker (currently unused, reserved for future use)

    Returns:
        Polars DataFrame with patient data (all columns as strings)

    Example:
        >>> df = extract_patient_data(
        ...     Path("2024_Clinic.xlsx"),
        ...     "Jan24",
        ...     2024
        ... )
        >>> len(df)
        4
        >>> "Patient ID*" in df.columns
        True
    """
    # Single-pass read-only loading for optimal performance
    wb = load_workbook(
        tracker_file,
        read_only=True,
        data_only=True,
        keep_vba=False,
        keep_links=False,
    )
    ws = wb[sheet_name]

    # Find where patient data starts
    data_start_row = find_data_start_row(ws)
    logger.debug(
        f"Sheet '{sheet_name}': Patient data found in rows {data_start_row} to {ws.max_row}"
    )

    # Read and merge header rows
    logger.info("Processing headers...")
    header_1, header_2 = read_header_rows(ws, data_start_row)
    headers = merge_headers(header_1, header_2)

    # Filter valid columns BEFORE reading data
    valid_cols = [(i, h) for i, h in enumerate(headers) if h]

    if not valid_cols:
        wb.close()
        logger.warning(f"No valid headers found in sheet '{sheet_name}'")
        return pl.DataFrame()

    # Read patient data rows
    data = read_patient_rows(ws, data_start_row, len(headers))
    wb.close()

    # Filter data to only include valid columns
    valid_headers, filtered_data = filter_valid_columns(headers, data)

    # Merge duplicate columns (handle merged cells that create duplicates)
    # Like R's tidyr::unite() - concatenates values with commas
    valid_headers, filtered_data = merge_duplicate_columns_data(valid_headers, filtered_data)

    # Create DataFrame with all columns as strings
    df = pl.DataFrame(
        {
            header: [str(row[i]) if row[i] is not None else None for row in filtered_data]
            for i, header in enumerate(valid_headers)
        }
    )

    logger.info(f"Extracted {len(df)} rows x {len(df.columns)} cols from sheet '{sheet_name}'")

    return df


def harmonize_patient_data_columns(
    df: pl.DataFrame,
    mapper: ColumnMapper | None = None,
    strict: bool = False,
) -> pl.DataFrame:
    """Harmonize patient data columns using synonym mappings.

    Renames columns from their various synonyms (e.g., "Patient ID", "ID",
    "Patient ID*") to standardized column names (e.g., "patient_id").

    Args:
        df: DataFrame with raw column names from tracker
        mapper: ColumnMapper to use (if None, loads default patient mapper)
        strict: If True, raise error if unmapped columns exist
                If False, keep unmapped columns as-is (default)

    Returns:
        DataFrame with standardized column names

    Raises:
        ValueError: If strict=True and unmapped columns exist

    Example:
        >>> raw_df = pl.DataFrame({
        ...     "Patient ID*": ["MY_SU001", "MY_SU002"],
        ...     "Age": [25, 30],
        ... })
        >>> harmonized = harmonize_patient_data_columns(raw_df)
        >>> harmonized.columns
        ['patient_id', 'age']
    """
    if mapper is None:
        mapper = load_patient_mapper()

    renamed_df = mapper.rename_columns(df, strict=strict)

    logger.info(
        f"Harmonized columns: {len(df.columns)} -> {len(renamed_df.columns)} "
        f"({len(df.columns) - len(renamed_df.columns)} columns removed)"
        if len(df.columns) != len(renamed_df.columns)
        else f"Harmonized {len(renamed_df.columns)} columns"
    )

    return renamed_df


def extract_tracker_month(sheet_name: str) -> int:
    """Extract month number (1-12) from sheet name.

    Args:
        sheet_name: Sheet name like "Jan24", "Feb24", etc.

    Returns:
        Month number (1 for January, 2 for February, etc.)

    Raises:
        ValueError: If month cannot be extracted

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
        return month_abbrs.index(month_prefix) + 1  # +1 because index is 0-based

    raise ValueError(f"Could not extract month from sheet name '{sheet_name}'")


def read_all_patient_sheets(
    tracker_file: Path,
    mapper: ColumnMapper | None = None,
) -> pl.DataFrame:
    """Read patient data from all month sheets in a tracker file.

    Orchestrates the complete extraction process:
    1. Find all month sheets
    2. Extract tracker year
    3. For each month sheet:
        - Extract raw data
        - Harmonize column names
        - Merge duplicate columns
        - Add metadata (sheet_name, tracker_month, tracker_year, file_name)
    4. Combine all sheets
    5. Filter invalid rows (no patient_id and no name)

    Args:
        tracker_file: Path to the tracker Excel file
        mapper: ColumnMapper to use (if None, loads default patient mapper)

    Returns:
        Combined DataFrame with all patient data from all month sheets

    Raises:
        ValueError: If no month sheets found or year cannot be determined

    Example:
        >>> df = read_all_patient_sheets(Path("2024_Clinic.xlsx"))
        >>> "patient_id" in df.columns
        True
        >>> "tracker_month" in df.columns
        True
        >>> "tracker_year" in df.columns
        True
    """
    logger.info(f"Reading all patient sheets from {tracker_file.name}")

    # Load workbook to find sheets
    wb = load_workbook(
        tracker_file, read_only=True, data_only=True, keep_vba=False, keep_links=False
    )

    # Find month sheets
    month_sheets = find_month_sheets(wb)
    if not month_sheets:
        wb.close()
        raise ValueError(f"No month sheets found in {tracker_file.name}")

    # Extract year
    year = get_tracker_year(tracker_file, month_sheets)
    logger.info(f"Processing {len(month_sheets)} month sheets for year {year}")

    wb.close()

    # Extract from each month sheet
    all_sheets_data = []

    for sheet_name in month_sheets:
        logger.info(f"Processing sheet: {sheet_name}")

        # Extract raw data
        df_sheet = extract_patient_data(tracker_file, sheet_name, year)

        if df_sheet.is_empty():
            logger.warning(f"Sheet '{sheet_name}' has no data, skipping")
            continue

        # Harmonize columns
        df_sheet = harmonize_patient_data_columns(df_sheet, mapper=mapper, strict=False)

        # Check for required column
        if "patient_id" not in df_sheet.columns:
            logger.warning(
                f"Sheet '{sheet_name}' has no 'patient_id' column after harmonization, skipping"
            )
            continue

        # Extract month number
        try:
            month_num = extract_tracker_month(sheet_name)
        except ValueError as e:
            logger.warning(f"Could not extract month from '{sheet_name}': {e}, skipping")
            continue

        # Add metadata columns
        df_sheet = df_sheet.with_columns(
            [
                pl.lit(sheet_name).alias("sheet_name"),
                pl.lit(month_num).alias("tracker_month"),
                pl.lit(year).alias("tracker_year"),
                pl.lit(tracker_file.name).alias("file_name"),
            ]
        )

        all_sheets_data.append(df_sheet)

    if not all_sheets_data:
        raise ValueError(f"No valid patient data found in any month sheets of {tracker_file.name}")

    # Combine all sheets (like R's bind_rows - handles different columns and types)
    # Use diagonal_relaxed to handle type mismatches (e.g., Null vs String)
    logger.info(f"Combining {len(all_sheets_data)} sheets...")
    df_combined = pl.concat(all_sheets_data, how="diagonal_relaxed")

    # Filter invalid rows (no patient_id and no name, or patient_id="0" and name="0")
    initial_rows = len(df_combined)

    # Filter 1: Remove rows with both patient_id and name null
    if "name" in df_combined.columns:
        df_combined = df_combined.filter(
            ~(pl.col("patient_id").is_null() & pl.col("name").is_null())
        )

        # Filter 2: Remove rows with patient_id="0" and name="0"
        df_combined = df_combined.filter(~((pl.col("patient_id") == "0") & (pl.col("name") == "0")))
    else:
        # If no 'name' column, just filter null patient_id
        df_combined = df_combined.filter(pl.col("patient_id").is_not_null())

    filtered_rows = initial_rows - len(df_combined)
    if filtered_rows > 0:
        logger.info(f"Filtered out {filtered_rows} invalid rows")

    logger.info(
        f"Successfully extracted {len(df_combined)} total rows "
        f"from {len(all_sheets_data)} month sheets"
    )

    return df_combined
