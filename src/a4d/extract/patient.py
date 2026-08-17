"""Patient data extraction from Excel tracker files.

This module handles reading patient data from Excel trackers, which have
evolved over the years with different formats and structures.
"""

import re
import warnings
from dataclasses import dataclass
from pathlib import Path

import polars as pl
from loguru import logger
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from a4d.errors import ErrorCollector
from a4d.extract.common import (
    extract_tracker_month,
    find_month_sheets,
    get_tracker_year,
)
from a4d.reference.synonyms import ColumnMapper, load_patient_mapper

__all__ = [
    "extract_tracker_month",
    "find_month_sheets",
    "get_tracker_year",
]

# Suppress openpyxl warnings about unsupported Excel features
# We only read data, so these warnings are not actionable
warnings.filterwarnings("ignore", category=UserWarning, module=r"openpyxl\..*")


def find_data_start_row(ws) -> int:
    """Find the first row containing patient data.

    Scans column A for the first numeric value (patient row numbers: 1, 2, 3...).
    This skips any non-numeric values that may appear above the patient data
    (e.g., spaces, text, product data).

    Args:
        ws: openpyxl worksheet object

    Returns:
        Row number (1-indexed) where patient data starts

    Raises:
        ValueError: If no numeric data is found in column A
    """
    # Sequential iter_rows scan, not repeated ws.cell() calls: on a read-only
    # worksheet each ws.cell() re-parses the sheet's XML from row 1, making a
    # per-row loop O(n^2) in the row count before data starts.
    max_row = ws.max_row or 1000
    for row_idx, (cell_value,) in enumerate(
        ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=1, values_only=True),
        start=1,
    ):
        if cell_value is not None and isinstance(cell_value, (int, float)):
            return row_idx

    raise ValueError("No patient data found in column A (looking for numeric row numbers)")


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

    last_col = max_cols
    for i in range(len(header_1_raw) - 1, -1, -1):
        if header_1_raw[i] is not None or header_2_raw[i] is not None:
            last_col = i + 1
            break

    header_1 = list(header_1_raw[:last_col])
    header_2 = list(header_2_raw[:last_col])

    return header_1, header_2


_UPDATED_YEAR_MARKER = re.compile(r"^updated\s*(19|20)\d{2}$")


def _is_updated_year_marker(header_cell: object) -> bool:
    """Is this header cell a bare "Updated <year>" continuation marker?

    Whole-cell match only: "Level of Education Or Occupation Updated 2023" is a
    real single-cell header (see synonyms_patient.yaml) and must not match.
    """
    normalized = re.sub(r"\s+", " ", str(header_cell).replace("\n", " ")).strip().lower()
    return bool(_UPDATED_YEAR_MARKER.match(normalized))


def merge_headers(
    header_1: list,
    header_2: list,
    mapper: ColumnMapper | None = None,
) -> list[str | None]:
    """Merge two header rows using heuristic forward-fill with synonym validation.

    When h2=None but h1 exists:
    1. Try forward-fill: combine prev_h2 + h1
    2. If mapper validates this as known column, use it
    3. Otherwise, treat h1 as standalone column

    This replaces Excel merge metadata detection with synonym-based validation,
    eliminating the need for slow read_only=False workbook loading.

    Special case: If header_1 contains "Patient ID" (or known synonyms) and
    header_2 appears to be a title row (mostly None), use only header_1.

    Args:
        header_1: First header row (closer to data), 0-indexed
        header_2: Second header row (further from data), 0-indexed
        mapper: Optional ColumnMapper for validating forward-filled headers

    Returns:
        List of merged header strings with whitespace normalized
    """
    patient_id_indicators = ["patient id", "patient.id"]
    has_patient_id_in_h1 = any(
        str(h1).strip().lower() in patient_id_indicators for h1 in header_1 if h1 is not None
    )

    non_none_count_h2 = sum(1 for h2 in header_2 if h2 is not None)

    if has_patient_id_in_h1 and non_none_count_h2 <= 2:
        logger.debug(
            "Detected title row in header_2 with Patient ID in header_1, using header_1 only"
        )
        headers = [str(h1).strip() if h1 is not None else None for h1 in header_1]
        headers = [re.sub(r"\s+", " ", h.replace("\n", " ")) if h else None for h in headers]
        return headers

    headers = []
    prev_h2 = None

    for h1, h2 in zip(header_1, header_2, strict=True):
        if h2 is not None and _is_updated_year_marker(h2) and prev_h2:
            # The 2022 template labels an update-date column "Updated 2022"
            # instead of repeating its subject, so the marker alone is not a
            # column name -- the subject sits in the column to its left. R
            # rewrites the same cell in script1_helper_read_patient_data.R.
            h2 = prev_h2

        if h1 and h2:
            headers.append(f"{h2} {h1}".strip())
            prev_h2 = str(h2).strip()
        elif h2:
            headers.append(str(h2).strip())
            prev_h2 = str(h2).strip()
        elif h1:
            # Try forward-fill with validation
            if prev_h2:
                candidate = f"{prev_h2} {h1}".strip()
                if mapper and mapper.is_known_column(candidate):
                    headers.append(candidate)
                else:
                    # Forward-fill not valid, use h1 standalone
                    headers.append(str(h1).strip())
            else:
                headers.append(str(h1).strip())
        else:
            headers.append(None)
            prev_h2 = None  # Reset on gap

    headers = [re.sub(r"\s+", " ", h.replace("\n", " ")) if h else None for h in headers]

    return headers


def _carries_data_beyond_identifier(row: tuple) -> bool:
    """Does a row hold anything past a repeat of its own patient identifier?

    Deliberately not a count threshold: the trackers repeat the identifier in
    a second column, so "more than n non-empty cells" would be a guess about
    layout, while "a value that isn't the identifier" is what actually
    distinguishes a record from a leftover ID.
    """
    identifier = row[1]
    return any(
        cell is not None and str(cell).strip() != "" and cell != identifier for cell in row[2:]
    )


def read_patient_rows(ws, data_start_row: int, num_columns: int) -> list[tuple]:
    """Read patient data rows from the worksheet.

    Reads from data_start_row until either ws.max_row or the first completely
    empty row. Skips rows where both the row number (column A) and patient_id
    (column B) are None, but accepts rows where patient_id exists even if row
    number is missing (handles data quality issues in Excel files).

    An unnumbered row must additionally carry a value that is not just a
    repeat of its own identifier. R bounds the data block by the row-number
    column alone, so it never sees these rows at all; keeping every one of
    them instead turned a bare list of patient IDs left below the data block
    into invented monthly records (2024_Vietnam National Children's Jul24,
    24 rows of nothing but the ID twice), which then picked up real-looking
    demographics from the Patient List join. Requiring actual data keeps the
    case the "or" was written for -- 2024_Mahosot's Jun24 LA-QA088 is a
    complete record that simply lost its row number, and R does lose it.

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
        if all(cell is None for cell in row):
            break
        # Skip rows where both row number (col A) AND patient_id (col B) are missing
        # This handles cases where Excel has missing row numbers but valid patient data
        if row[0] is None and (len(row) < 2 or row[1] is None):
            continue
        if row[0] is None and not _carries_data_beyond_identifier(row):
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
        return headers, data

    from collections import defaultdict

    header_positions: dict[str, list[int]] = defaultdict(list)
    for idx, header in enumerate(headers):
        header_positions[header].append(idx)

    unique_headers = list(header_positions.keys())

    duplicated = [h for h, positions in header_positions.items() if len(positions) > 1]
    if duplicated:
        logger.debug(f"Merging {len(duplicated)} duplicate column groups: {duplicated}")

    merged_data = []
    for row in data:
        merged_row = []
        for header in unique_headers:
            positions = header_positions[header]
            if len(positions) == 1:
                merged_row.append(row[positions[0]])
            else:
                values = [str(row[pos]) if row[pos] is not None else "" for pos in positions]
                values = [v for v in values if v]
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

    filtered_data = [[row[i] for i in valid_indices] for row in data]

    return valid_headers, filtered_data


def _is_number(value: object) -> bool:
    try:
        float(str(value))
    except ValueError:
        return False
    return True


def find_dropped_data_columns(
    headers: list[str | None], data: list[tuple]
) -> list[tuple[int, int]]:
    """Find headerless columns that nonetheless carry data.

    `filter_valid_columns` drops any column whose header cell is blank, which is
    right for the trackers' many spacer columns but silently loses real values
    when a clinician left a header cell empty by mistake -- e.g. 2021 Kantha
    Bopha's Mar21/Apr21 sheets, where the insulin-regimen column has data from
    row 87 down and no header, while the same column in May21 reads
    "Insulin Regime". Reporting these lets the source workbook be corrected;
    the pipeline cannot name such a column on its own.

    All-numeric columns are excluded: the trackers put an unlabelled row counter
    left of the patient data, which accounts for 189 of the 199 headerless
    columns holding values across the 254-tracker set.

    Returns:
        (column index, count of non-empty values) per affected column
    """
    findings = []
    for i, header in enumerate(headers):
        if header:
            continue
        values = [row[i] for row in data if i < len(row) and row[i] not in (None, "")]
        if not values or all(_is_number(v) for v in values):
            continue
        findings.append((i, len(values)))
    return findings


def recover_blank_headers(
    headers: list[str | None], data: list[tuple], sibling_headers: list[list[str | None]]
) -> list[str | None]:
    """Name a headerless data column from the month sheets that do label it.

    A tracker's month sheets share one layout, so when a clinician leaves a
    header cell empty in one sheet the same column is usually still labelled in
    the others -- e.g. 2021 Kantha Bopha, where Mar21/Apr21 hold insulin-regimen
    values under an empty header and May21 reads "Insulin Regime". Without this
    the column is dropped and its values are lost on both pipelines.

    Deliberately self-limiting; it abstains unless the workbook itself settles
    the answer:

    - the siblings must **agree**: two different candidate names is a guess
      (2021 Putrajaya offers three at one position),
    - a position no sibling names is left alone -- which is what keeps the 2022
      template's hidden merged-cell column, blank in every sheet and correctly
      dropped, out of reach of this rule,
    - a name this sheet already uses is refused, since it would collide,
    - and only columns `find_dropped_data_columns` reports are eligible, so
      spacer columns and the unlabelled row counter are untouched.

    Measured over the 254-tracker set: recovers 316 values across 5 trackers and
    does nothing to the other 4,256.
    """
    if not sibling_headers:
        return headers

    recovered = list(headers)
    taken = {h for h in headers if h}

    for index, _ in find_dropped_data_columns(headers, data):
        donors: set[str] = set()
        for sibling in sibling_headers:
            if index < len(sibling):
                candidate = sibling[index]
                if candidate:
                    donors.add(candidate)
        if len(donors) != 1:
            continue
        donor = donors.pop()
        if donor in taken:
            continue
        recovered[index] = donor
        taken.add(donor)

    return recovered


@dataclass(frozen=True)
class LayoutChange:
    """One column position the month sheets of a tracker disagree about."""

    index: int
    headers: list[str]
    canonical: list[str]
    renames_only: bool


def find_layout_changes(
    layouts_by_sheet: dict[str, list[str | None]], mapper: ColumnMapper
) -> list[LayoutChange]:
    """Find column positions whose meaning is not stable across a tracker's sheets.

    A tracker is one workbook for one clinic-year and should not change shape
    partway through it, so a position that means one thing in January and
    another in June is a defect in the workbook worth reporting -- and a
    dangerous one, because nothing downstream can see it.

    Two kinds, distinguished because only one is harmful:

    - **renames_only**: every spelling at that position maps to the same
      canonical column (`Insulin regime` -> `Insulin regimen`). The synonym file
      already absorbs these.
    - the rest: the canonical column itself changes. Either a column was added
      or dropped mid-year and everything to its right shifted (2018 CDA's Apr18
      has no `Insulin Regimen`, so BASAL dose sits where the regimen sits in the
      other eleven sheets), or the header was edited over unchanged data (2020
      CDA relabels `Baseline FBG` from `mmol/dL` to `mg/dL` in June while the
      values stay 67-500, i.e. mg/dL throughout, so five months are filed under
      the wrong unit).

    A blank header on one sheet is not a change -- that is
    `recover_blank_headers`' business.
    """
    if len(layouts_by_sheet) < 2:
        return []

    changes = []
    width = max(len(headers) for headers in layouts_by_sheet.values())
    for index in range(width):
        names: set[str] = set()
        for headers in layouts_by_sheet.values():
            if index < len(headers):
                header = headers[index]
                if header:
                    names.add(header)
        if len(names) < 2:
            continue
        canonical = {mapper.get_standard_name(name) for name in names}
        changes.append(
            LayoutChange(
                index=index,
                headers=sorted(names),
                canonical=sorted(canonical),
                renames_only=len(canonical) == 1,
            )
        )
    return changes


@dataclass(frozen=True)
class SheetLayout:
    """Where a sheet's data starts and what its merged header row says."""

    data_start_row: int
    headers: list[str | None]


def collect_sheet_layouts(
    workbook, month_sheets: list[str], mapper: ColumnMapper | None = None
) -> dict[str, SheetLayout]:
    """Resolve every month sheet's layout once per tracker.

    `recover_blank_headers` needs every *other* sheet's headers before any one
    sheet can be finalized, so this pass has to happen up front. Its results are
    then handed back to `extract_patient_data`, which would otherwise redo
    `find_data_start_row` -- a full column-A scan per sheet, and the hot spot
    ticket 10 rewrote to be linear. Reusing the layout keeps that pass off the
    critical path instead of doubling it.
    """
    layouts: dict[str, SheetLayout] = {}
    for sheet_name in month_sheets:
        try:
            worksheet = workbook[sheet_name]
            data_start_row = find_data_start_row(worksheet)
            header_1, header_2 = read_header_rows(worksheet, data_start_row)
        except ValueError, KeyError:
            # A sheet whose layout cannot be read simply donates nothing.
            continue
        layouts[sheet_name] = SheetLayout(
            data_start_row=data_start_row,
            headers=merge_headers(header_1, header_2, mapper=mapper),
        )
    return layouts


def extract_patient_data(
    tracker_file: Path,
    sheet_name: str,
    year: int,
    mapper: ColumnMapper | None = None,
    workbook=None,
    layout: SheetLayout | None = None,
    sibling_headers: list[list[str | None]] | None = None,
) -> pl.DataFrame:
    """Extract patient data from a single sheet.

    Uses single read_only=True load with synonym-validated header merging.

    Args:
        tracker_file: Path to the tracker Excel file
        sheet_name: Name of the sheet to extract
        year: Year of the tracker (currently unused, reserved for future use)
        mapper: Optional ColumnMapper for validating forward-filled headers
        workbook: Optional pre-loaded workbook for caching across sheets
        layout: This sheet's already-resolved start row and headers, from
            collect_sheet_layouts; recomputed here when not supplied
        sibling_headers: Other month sheets' merged headers, used to name a
            column whose own header cell is empty (see recover_blank_headers)

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
    if mapper is None:
        mapper = load_patient_mapper()

    # Use cached workbook or load new one
    close_wb = workbook is None
    if workbook is None:
        workbook = load_workbook(
            tracker_file,
            read_only=True,
            data_only=True,
            keep_vba=False,
            keep_links=False,
        )

    ws = workbook[sheet_name]

    if layout is None:
        data_start_row = find_data_start_row(ws)
        logger.info("Processing headers...")
        header_1, header_2 = read_header_rows(ws, data_start_row)
        # Use synonym-validated forward-fill instead of Excel merge metadata
        headers = merge_headers(header_1, header_2, mapper=mapper)
    else:
        data_start_row, headers = layout.data_start_row, list(layout.headers)

    logger.debug(
        f"Sheet '{sheet_name}': Patient data found in rows {data_start_row} to {ws.max_row}"
    )

    valid_cols = [(i, h) for i, h in enumerate(headers) if h]

    if not valid_cols:
        if close_wb:
            workbook.close()
        logger.bind(error_code="invalid_tracker").warning(
            f"No valid headers found in sheet '{sheet_name}'"
        )
        return pl.DataFrame()

    data = read_patient_rows(ws, data_start_row, len(headers))

    if close_wb:
        workbook.close()

    if sibling_headers:
        recovered = recover_blank_headers(headers, data, sibling_headers)
        for i, (before, after) in enumerate(zip(headers, recovered, strict=True)):
            if before != after:
                logger.info(
                    f"Sheet '{sheet_name}': column {get_column_letter(i + 1)} has an empty "
                    f"header cell; recovered '{after}' from the sheets that label it."
                )
        headers = recovered

    for column_index, value_count in find_dropped_data_columns(headers, data):
        logger.bind(error_code="blank_header_with_data").warning(
            f"Sheet '{sheet_name}': column {get_column_letter(column_index + 1)} holds "
            f"{value_count} values but its header cell is empty and no other sheet names "
            "it, so the column is dropped. Fix the header in the source tracker to recover it."
        )

    valid_headers, filtered_data = filter_valid_columns(headers, data)

    valid_headers, filtered_data = merge_duplicate_columns_data(valid_headers, filtered_data)

    # Create DataFrame with ALL columns explicitly as String type to ensure consistent schema
    # across all files and avoid type inference issues (Null vs String dtype)
    df = pl.DataFrame(
        {
            header: pl.Series(
                [str(row[i]) if row[i] is not None else None for row in filtered_data],
                dtype=pl.String,
            )
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
        ...     "Patient ID*": ["MY_QI001", "MY_QI002"],
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


def read_all_patient_sheets(
    tracker_file: Path,
    mapper: ColumnMapper | None = None,
    error_collector: ErrorCollector | None = None,
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
        error_collector: ErrorCollector for tracking data quality issues (optional)

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

    # Load mapper once for all sheets
    if mapper is None:
        mapper = load_patient_mapper()

    # Load workbook once and reuse across all sheets
    wb = load_workbook(
        tracker_file, read_only=True, data_only=True, keep_vba=False, keep_links=False
    )

    month_sheets = find_month_sheets(wb)
    if not month_sheets:
        wb.close()
        raise ValueError(f"No month sheets found in {tracker_file.name}")

    year = get_tracker_year(tracker_file, month_sheets)
    logger.info(f"Processing {len(month_sheets)} month sheets for year {year}")

    all_sheets_data = []

    layouts = collect_sheet_layouts(wb, month_sheets, mapper=mapper)

    if mapper is None:
        mapper = load_patient_mapper()
    headers_by_sheet = {sheet: layout.headers for sheet, layout in layouts.items()}
    for change in find_layout_changes(headers_by_sheet, mapper):
        column = get_column_letter(change.index + 1)
        if change.renames_only:
            logger.info(
                f"Column {column} is spelled differently across month sheets "
                f"({', '.join(change.headers)}); all map to '{change.canonical[0]}'."
            )
        else:
            logger.bind(error_code="tracker_layout_changed").warning(
                f"Column {column} does not mean the same thing in every month sheet: "
                f"{', '.join(change.headers)} -> {', '.join(change.canonical)}. "
                "A tracker should keep one layout for the whole year; check the workbook."
            )

    for sheet_name in month_sheets:
        logger.info(f"Processing sheet: {sheet_name}")

        siblings = [layout.headers for name, layout in layouts.items() if name != sheet_name]
        df_sheet = extract_patient_data(
            tracker_file,
            sheet_name,
            year,
            mapper=mapper,
            workbook=wb,
            layout=layouts.get(sheet_name),
            sibling_headers=siblings,
        )

        if df_sheet.is_empty():
            logger.bind(error_code="invalid_tracker").warning(
                f"Sheet '{sheet_name}' has no data, skipping"
            )
            continue

        df_sheet = harmonize_patient_data_columns(df_sheet, mapper=mapper, strict=False)

        if "patient_id" not in df_sheet.columns:
            logger.bind(error_code="invalid_tracker").warning(
                f"Sheet '{sheet_name}' has no 'patient_id' column after harmonization, skipping"
            )
            continue

        try:
            month_num = extract_tracker_month(sheet_name)
        except ValueError as e:
            logger.bind(error_code="invalid_tracker").warning(
                f"Could not extract month from '{sheet_name}': {e}, skipping"
            )
            continue

        # Derived metadata (year, month) use Int64; text metadata (sheet_name, etc.) use String
        clinic_id = tracker_file.parent.name
        file_name = tracker_file.stem
        df_sheet = df_sheet.with_columns(
            [
                pl.lit(sheet_name, dtype=pl.String).alias("sheet_name"),
                pl.lit(month_num, dtype=pl.Int64).alias("tracker_month"),
                pl.lit(year, dtype=pl.Int64).alias("tracker_year"),
                pl.lit(file_name, dtype=pl.String).alias("file_name"),
                pl.lit(clinic_id, dtype=pl.String).alias("clinic_id"),
            ]
        )

        all_sheets_data.append(df_sheet)

    if not all_sheets_data:
        raise ValueError(f"No valid patient data found in any month sheets of {tracker_file.name}")

    # Use diagonal_relaxed to handle type mismatches (e.g., Null vs String) like R's bind_rows
    logger.info(f"Combining {len(all_sheets_data)} sheets...")
    df_combined = pl.concat(all_sheets_data, how="diagonal_relaxed")

    initial_rows = len(df_combined)

    # Track rows with missing patient_id for error reporting
    missing_patient_id_rows = df_combined.filter(pl.col("patient_id").is_null())
    missing_count = len(missing_patient_id_rows)

    if missing_count > 0:
        logger.bind(error_code="invalid_value").error(
            f"Found {missing_count} rows with missing patient_id in {tracker_file.name} - "
            f"these rows will be excluded from processing"
        )

        # Log to ErrorCollector if available
        if error_collector is not None:
            for row in missing_patient_id_rows.iter_rows(named=True):
                sheet_name = row.get("sheet_name", "unknown")
                name_value = row.get("name", "")
                error_collector.add_error(
                    file_name=tracker_file.stem,
                    patient_id="MISSING",
                    column="patient_id",
                    original_value=None,
                    error_message=(
                        f"Row in sheet '{sheet_name}' has missing patient_id (name: {name_value})"
                    ),
                    error_code="missing_required_field",
                    script="extract",
                    function_name="read_all_patient_sheets",
                )

    # Filter out ALL rows with missing patient_id
    df_combined = df_combined.filter(pl.col("patient_id").is_not_null())

    # Filter out empty rows (both patient_id and name are null/empty)
    # This is redundant now but kept for clarity
    if "name" in df_combined.columns:
        df_combined = df_combined.filter(
            ~(
                (pl.col("patient_id").str.strip_chars() == "")
                & (pl.col("name").is_null() | (pl.col("name").str.strip_chars() == ""))
            )
        )

    # Filter out rows where both patient_id and name are numeric zeros (0, 0.0, "0", "0.0", etc.)
    if "name" in df_combined.columns:
        df_combined = df_combined.filter(
            ~(
                pl.col("patient_id").str.strip_chars().is_in(["0", "0.0"])
                & pl.col("name").str.strip_chars().is_in(["0", "0.0"])
            )
        )

    # Filter out rows with patient_id starting with "#" (Excel errors like #REF!)
    df_combined = df_combined.filter(~pl.col("patient_id").str.starts_with("#"))

    filtered_rows = initial_rows - len(df_combined)
    if filtered_rows > 0:
        logger.info(f"Filtered out {filtered_rows} invalid rows total")

    # Excel formula-error strings are deliberately NOT stripped here (ticket
    # 27): the raw layer records what the source cell actually contained.
    # a4d.clean.converters.normalize_excel_formula_errors nulls and logs them.

    # Use already-loaded workbook for sheet checking
    all_sheets = wb.sheetnames

    # Process Patient List sheet if it exists (R: lines 103-130)
    if "Patient List" in all_sheets:
        logger.info("Processing 'Patient List' sheet...")
        try:
            patient_list = extract_patient_data(
                tracker_file, "Patient List", year, mapper=mapper, workbook=wb
            )
            if not patient_list.is_empty():
                patient_list = harmonize_patient_data_columns(
                    patient_list, mapper=mapper, strict=False
                )

                if "patient_id" in patient_list.columns:
                    # Filter out rows with missing patient_id
                    patient_list = patient_list.filter(pl.col("patient_id").is_not_null())

                    # Filter out numeric zeros and Excel errors
                    if "name" in patient_list.columns:
                        patient_list = patient_list.filter(
                            ~(
                                pl.col("patient_id").str.strip_chars().is_in(["0", "0.0"])
                                & pl.col("name").str.strip_chars().is_in(["0", "0.0"])
                            )
                        )

                    patient_list = patient_list.filter(~pl.col("patient_id").str.starts_with("#"))

                    # R: select(-any_of(c("hba1c_baseline"))) and select(-any_of(c("name")))
                    df_monthly = (
                        df_combined.drop("hba1c_baseline")
                        if "hba1c_baseline" in df_combined.columns
                        else df_combined
                    )
                    patient_list_join = (
                        patient_list.drop("name")
                        if "name" in patient_list.columns
                        else patient_list
                    )

                    df_combined = df_monthly.join(
                        patient_list_join, on="patient_id", how="left", suffix=".static"
                    )
                    logger.info(f"Joined {len(patient_list)} Patient List records")
                else:
                    logger.bind(error_code="invalid_tracker").warning(
                        "Patient List sheet has no 'patient_id' column after harmonization"
                    )
            else:
                logger.bind(error_code="invalid_tracker").warning("Patient List sheet is empty")
        except Exception as e:
            logger.bind(error_code="invalid_tracker").warning(
                f"Could not process Patient List sheet: {e}"
            )

    # Process Annual sheet if it exists (R: lines 132-160)
    if "Annual" in all_sheets:
        logger.info("Processing 'Annual' sheet...")
        try:
            annual_data = extract_patient_data(
                tracker_file, "Annual", year, mapper=mapper, workbook=wb
            )
            if not annual_data.is_empty():
                annual_data = harmonize_patient_data_columns(
                    annual_data, mapper=mapper, strict=False
                )

                if "patient_id" in annual_data.columns:
                    # Filter out rows with missing patient_id
                    annual_data = annual_data.filter(pl.col("patient_id").is_not_null())

                    # Filter out numeric zeros and Excel errors
                    if "name" in annual_data.columns:
                        annual_data = annual_data.filter(
                            ~(
                                pl.col("patient_id").str.strip_chars().is_in(["0", "0.0"])
                                & pl.col("name").str.strip_chars().is_in(["0", "0.0"])
                            )
                        )

                    annual_data = annual_data.filter(~pl.col("patient_id").str.starts_with("#"))

                    # R: select(-any_of(c("status", "name")))
                    cols_to_drop = [col for col in ["status", "name"] if col in annual_data.columns]
                    annual_data_join = (
                        annual_data.drop(cols_to_drop) if cols_to_drop else annual_data
                    )

                    df_combined = df_combined.join(
                        annual_data_join, on="patient_id", how="left", suffix=".annual"
                    )
                    logger.info(f"Joined {len(annual_data)} Annual records")
                else:
                    logger.bind(error_code="invalid_tracker").warning(
                        "Annual sheet has no 'patient_id' column after harmonization"
                    )
            else:
                logger.bind(error_code="invalid_tracker").warning("Annual sheet is empty")
        except Exception as e:
            logger.bind(error_code="invalid_tracker").warning(
                f"Could not process Annual sheet: {e}"
            )

    # Close workbook after all processing
    wb.close()

    logger.info(
        f"Successfully extracted {len(df_combined)} total rows "
        f"from {len(all_sheets_data)} month sheets"
    )

    # Reorder: metadata first, then patient data
    # (tracker_year, tracker_month, clinic_id, patient_id)
    priority_cols = ["tracker_year", "tracker_month", "clinic_id", "patient_id"]
    existing_priority = [c for c in priority_cols if c in df_combined.columns]
    other_cols = [c for c in df_combined.columns if c not in priority_cols]
    df_combined = df_combined.select(existing_priority + other_cols)

    return df_combined


def export_patient_raw(
    df: pl.DataFrame,
    tracker_file: Path,
    output_dir: Path,
) -> Path:
    """Export raw patient data to parquet file.

    Matches R pipeline behavior:
    - Filename: {tracker_name}_patient_raw.parquet
    - Location: output_dir/{tracker_name}_patient_raw.parquet

    Args:
        df: Patient DataFrame to export
        tracker_file: Path to original tracker file (used to extract tracker_name)
        output_dir: Directory to write parquet file (e.g., data_root/output/patient_data_raw)

    Returns:
        Path to the written parquet file

    Example:
        >>> df = read_all_patient_sheets(Path("2024_Clinic.xlsx"))
        >>> output_path = export_patient_raw(
        ...     df,
        ...     Path("2024_Clinic.xlsx"),
        ...     Path("output/patient_data_raw")
        ... )
        >>> output_path.name
        '2024_Clinic_patient_raw.parquet'
    """
    # Extract tracker name (filename without extension)
    tracker_name = tracker_file.stem

    # Create output filename: {tracker_name}_patient_raw.parquet
    output_filename = f"{tracker_name}_patient_raw.parquet"
    output_path = output_dir / output_filename

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Write parquet file
    logger.info(f"Writing {len(df)} rows to {output_path}")
    df.write_parquet(output_path)

    logger.info(f"Successfully exported to {output_path}")
    return output_path
