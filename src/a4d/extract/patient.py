"""Patient data extraction from Excel tracker files.

This module handles reading patient data from Excel trackers, which have
evolved over the years with different formats and structures.
"""

import datetime
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
from loguru import logger
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter, range_boundaries
from openpyxl.utils.datetime import to_excel

from a4d.extract.common import (
    extract_tracker_month,
    find_month_sheets,
    get_tracker_year,
    normalize_patient_id_expr,
)
from a4d.findings import report_finding
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

    A clinician who clears a row number leaves a whitespace-only string behind,
    and that row is still a patient row -- so the numeric block is extended back
    over any such cells directly abutting it. Starting one row too late is not a
    lost row but a lost sheet: the header rows are read from the data, no
    patient_id survives harmonization, and the sheet is skipped entirely (2022
    Children's Hospital 2, Oct22). Only cells touching the block qualify: the
    broader "first non-empty cell in column A" rule was measured across all 254
    trackers and would start 14 sheets at row 1 on a stray 'm'/'f'/'n' left up
    there (2026 Gensan, 2025/2026 VNCH). The narrow rule moves exactly one
    sheet in the corpus.
    One row only, since a longer run of blanks has never been observed and
    swallowing several would risk reading a header row as data instead.

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
    previous_blank_string_row: int | None = None
    for row_idx, (cell_value,) in enumerate(
        ws.iter_rows(min_row=1, max_row=max_row, min_col=1, max_col=1, values_only=True),
        start=1,
    ):
        if isinstance(cell_value, (int, float)) and not isinstance(cell_value, bool):
            if previous_blank_string_row == row_idx - 1:
                return previous_blank_string_row
            return row_idx

        if isinstance(cell_value, str) and cell_value.strip() == "":
            previous_blank_string_row = row_idx
        else:
            previous_blank_string_row = None

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


_MERGE_CELLS_BLOCK = re.compile(rb"<mergeCells.*?</mergeCells>", re.S)
_MERGE_REF = re.compile(rb'ref="([A-Z0-9:]+)"')


def merged_header_spans(workbook, worksheet, upper_header_row: int) -> list[tuple[int, int]]:
    """Horizontal cell merges covering the upper header row, as (first, last) columns.

    A merged title is the workbook's own statement that the columns beneath it
    are one block -- the only structural evidence available for a sub-header
    whose own upper cell is empty. openpyxl drops merge metadata in read_only
    mode, and loading a workbook read-write costs the 6.6x that ticket 10 won
    back, so the ranges are read straight out of the sheet XML in the archive
    openpyxl already has open.

    Degrades to "no spans" -- i.e. the pre-existing forward-fill behaviour --
    if the private attributes it leans on ever move.
    """
    try:
        archive = workbook._archive
        data = archive.read(worksheet._worksheet_path.lstrip("/"))
    except AttributeError, KeyError, OSError:
        return []

    block = _MERGE_CELLS_BLOCK.search(data)
    if not block:
        return []

    spans = []
    for ref in _MERGE_REF.findall(block.group(0)):
        try:
            min_col, min_row, max_col, max_row = range_boundaries(ref.decode())
        except ValueError:
            continue
        if max_col > min_col and min_row <= upper_header_row <= max_row:
            spans.append((min_col, max_col))
    return spans


def _merge_header_pair(
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
            # column name -- the subject sits in the column to its left.
            # Without this, blood_pressure_updated and edu_occ_updated go
            # unmapped on every 2022 tracker (7,165 values).
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


def merge_headers(
    header_1: list,
    header_2: list,
    mapper: ColumnMapper | None = None,
    merged_spans: list[tuple[int, int]] | None = None,
) -> list[str | None]:
    """Merge two header rows into one column name per column.

    Forward-fill alone cannot cross a column whose *both* header cells are
    empty -- it resets there, deliberately, so a title cannot leak into a block
    it does not cover. Where the workbook says a title is merged across a span,
    that reset throws away information the file actually carries: 2021
    Putrajaya merges "Complication Screening (Current Month Testing)" over five
    columns, and the "Results"/"Date (mmm-yy)" sub-headers past the gap were
    left bare and mapped nowhere, losing the recorded screening results.

    A merged title *qualifies a sub-header*; it never names a column outright.
    A column blank in both header rows has no name for the title to qualify, so
    calling it by the bare block title would be a guess -- and a harmful one:
    in the 2022 template that guess maps a second column onto
    `complication_screening`, which one already claims (290 sheets), and in the
    2022 "Insulin Regimen" merge it would comma-join two columns holding
    near-duplicate values ("Basal-bolus MDI (AN/HI)" against "Basal-bolus
    (AN/HI)") into one worse value -- 3,659 near-duplicate cells. So the first
    column is kept alone in both cases. Two sub-headers that would qualify to
    the same name are refused for the same reason.

    Args:
        header_1: First header row (closer to data), 0-indexed
        header_2: Second header row (further from data), 0-indexed
        mapper: Optional ColumnMapper for validating forward-filled headers
        merged_spans: (first, last) 1-indexed column pairs the upper header row
            is merged across, from `merged_header_spans`
    """
    headers = _merge_header_pair(header_1, header_2, mapper)
    if not merged_spans:
        return headers

    filled = list(header_2)
    for first, last in merged_spans:
        if first - 1 >= len(filled):
            continue
        title = header_2[first - 1]
        if title is None:
            continue
        for col in range(first, min(last, len(filled)) + 1):
            has_sub_header = col - 1 < len(header_1) and header_1[col - 1] is not None
            if filled[col - 1] is None and has_sub_header:
                filled[col - 1] = title

    propagated = _merge_header_pair(header_1, filled, mapper)
    taken = {h for h in headers if h}
    for index, name in enumerate(propagated):
        if name is None or name == headers[index] or name in taken:
            continue
        headers[index] = name
        taken.add(name)
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


# Excel's serial epoch starts at 1899-12-30, so a "date" in the first years
# of the 1900s is a small number that inherited a date number format from a
# neighbouring cell, not a date anyone could have entered. Raised from 1903
# to 1906 (ticket 52): a bare four-digit year typed into a date-formatted
# cell is a serial of 1900-2100, which resolves into March-September 1905 and
# so escaped the old bound -- 2019 Yangon Children's writes 163 D.O.B. cells
# that way. Still nowhere near a real date: the earliest genuine one in the
# 254-tracker set is a 1956 D.O.B.
_IMPOSSIBLE_DATE_BEFORE = datetime.datetime(1906, 1, 1)


def _recover_number_typed_as_date(value: object) -> object:
    """Undo Excel's date formatting of a plainly numeric entry.

    openpyxl honors each cell's own format, so a plain number sitting in a
    date-formatted cell comes back as a datetime, which the numeric conversion
    then rejects into a 999999 sentinel -- 24 systolic readings were reaching
    BigQuery that way. Excel's 1899-12-30 epoch is what makes this recoverable:
    such a "date" is a small number, so a pre-1903 datetime converts back to
    the serial the clinician actually typed. Verified against the real source
    Excel (2025 Hat Yai, Annual!H
    for TH_HY035: a dd-mmm-yyyy-formatted cell holding datetime(1900, 4, 29),
    i.e. the systolic 120 the neighbouring diastolic 74 belongs with).

    Only the impossible range is recovered. A date that could plausibly have
    been typed stays a date even in a numeric column -- that is a different
    cause, already settled on the product arm as
    ``openpyxl_date_typed_stray_cell``.
    """
    if not isinstance(value, datetime.datetime) or value >= _IMPOSSIBLE_DATE_BEFORE:
        return value
    serial = to_excel(value)
    return int(serial) if float(serial).is_integer() else serial


def read_patient_rows(ws, data_start_row: int, num_columns: int) -> list[tuple]:
    """Read patient data rows from the worksheet.

    Reads from data_start_row until either ws.max_row or the first completely
    empty row. Skips rows where both the row number (column A) and patient_id
    (column B) are None, but accepts rows where patient_id exists even if row
    number is missing (handles data quality issues in Excel files).

    An unnumbered row must additionally carry a value that is not just a
    repeat of its own identifier. Keeping every unnumbered row instead turned a
    bare list of patient IDs left below the data block into invented monthly
    records (2024_Vietnam National Children's Jul24, 24 rows of nothing but the
    ID twice), which then picked up real-looking demographics from the Patient
    List join. Bounding the block by the row-number column alone would be the
    other obvious fix, but a 254-tracker sweep showed it loses a genuine record
    -- 2024_Mahosot's Jun24 LA-MH088 is a complete patient row that simply lost
    its row number. Requiring actual data keeps that case and drops the other.

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
        data.append(tuple(_recover_number_typed_as_date(cell) for cell in row))

    return data


def merge_duplicate_columns_data(
    headers: list[str], data: list[list]
) -> tuple[list[str], list[list]]:
    """Merge data from duplicate column headers by concatenating with commas.

    When Excel cells are merged both horizontally and vertically, the forward-fill
    logic in merge_headers() can create duplicate column names. This function
    concatenates their values rather than keeping only the first, which was
    discarding 2,489 recorded values across 27 trackers -- the 2023 template's
    B.P./Kidney/Eye/Foot/Lipids screening sub-columns all share one canonical
    name.

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
    headers: list[str | None],
    data: list[tuple],
    sibling_headers: list[list[str | None]],
    merged_spans: list[tuple[int, int]] | None = None,
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
    - a position covered by a merged header is refused: the merge is this
      sheet's own statement about what the column belongs to, and outranks a
      sibling laid out differently. Putrajaya's Jul21 sheet carries "Patient
      Observations" at the position Dec21 uses for a complication-screening
      selection, so recovering by position filed a screening result under
      observations,
    - and only columns `find_dropped_data_columns` reports are eligible, so
      spacer columns and the unlabelled row counter are untouched.

    Measured over the 254-tracker set: recovers 316 values across 5 trackers and
    does nothing to the other 4,256.
    """
    if not sibling_headers:
        return headers

    recovered = list(headers)
    taken = {h for h in headers if h}
    covered = {
        col - 1 for first, last in (merged_spans or []) for col in range(first + 1, last + 1)
    }

    for index, _ in find_dropped_data_columns(headers, data):
        if index in covered:
            continue
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
    merged_spans: list[tuple[int, int]] = field(default_factory=list)


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
        spans = merged_header_spans(workbook, worksheet, data_start_row - 2)
        layouts[sheet_name] = SheetLayout(
            data_start_row=data_start_row,
            headers=merge_headers(header_1, header_2, mapper=mapper, merged_spans=spans),
            merged_spans=spans,
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
        merged_spans = merged_header_spans(workbook, ws, data_start_row - 2)
        headers = merge_headers(header_1, header_2, mapper=mapper, merged_spans=merged_spans)
    else:
        data_start_row, headers = layout.data_start_row, list(layout.headers)
        merged_spans = layout.merged_spans

    logger.debug(
        f"Sheet '{sheet_name}': Patient data found in rows {data_start_row} to {ws.max_row}"
    )

    valid_cols = [(i, h) for i, h in enumerate(headers) if h]

    if not valid_cols:
        if close_wb:
            workbook.close()
        report_finding(
            error_code="sheet_skipped",
            message=(f"No valid headers found in sheet '{sheet_name}'"),
            sheet_name=sheet_name,
            stage="extract",
            function_name="extract_patient_data",
        )
        return pl.DataFrame()

    data = read_patient_rows(ws, data_start_row, len(headers))

    if close_wb:
        workbook.close()

    if sibling_headers:
        recovered = recover_blank_headers(headers, data, sibling_headers, merged_spans=merged_spans)
        for i, (before, after) in enumerate(zip(headers, recovered, strict=True)):
            if before != after:
                logger.info(
                    f"Sheet '{sheet_name}': column {get_column_letter(i + 1)} has an empty "
                    f"header cell; recovered '{after}' from the sheets that label it."
                )
        headers = recovered

    for column_index, value_count in find_dropped_data_columns(headers, data):
        report_finding(
            error_code="blank_header_with_data",
            message=(
                f"Sheet '{sheet_name}': column {get_column_letter(column_index + 1)} holds "
                f"{value_count} values but its header cell is empty and no other sheet names "
                "it, so the column is dropped. Fix the header in the source tracker to recover it."
            ),
            sheet_name=sheet_name,
            stage="extract",
            function_name="extract_patient_data",
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


def join_static_sheet(
    df_monthly: pl.DataFrame,
    static_sheet: pl.DataFrame,
    suffix: str,
    sheet_name: str,
) -> pl.DataFrame:
    """Attach a per-patient sheet's columns onto that patient's month rows.

    Used for both whole-tracker joins: the ``Patient List`` demographics and
    the ``Annual`` sheet.

    Keyed on the *normalized* ID rather than the raw one (ticket 58). A month
    sheet routinely spells an ID differently from the Patient List in the same
    workbook -- 2023/2024 Mahosot write ``LA-MH056`` against a Patient List
    entry of ``LA_MH056`` -- and on the raw key those rows kept their
    measurements and silently lost every static column. Measured across the
    real 254-tracker corpus, the raw key misses 695 Patient List rows in 6
    files (680 recoverable, 6,863 cells) and 132 Annual rows (19 recoverable,
    40 cells); the rest name a patient the sheet does not list at all, which is
    a source defect rather than a key mismatch.

    The key is derived for the join only: ``patient_id`` in the returned frame
    is still the spelling the month sheet used, which is what the raw layer
    promises: the raw stage records what the workbook says, and only cleaning
    resolves identity.
    """
    key = "__static_join_key"
    static = static_sheet.with_columns(
        normalize_patient_id_expr(pl.col("patient_id")).alias(key)
    ).drop("patient_id")

    # Normalization introduces no new key collisions anywhere in the corpus,
    # but if a sheet ever does carry two entries folding to one key, a fan-out
    # would silently duplicate that patient's month rows -- so collapse to the
    # first entry rather than let the join multiply rows.
    deduped = static.unique(subset=[key], keep="first", maintain_order=True)
    if deduped.height != static.height:
        report_finding(
            error_code="static_sheet_duplicate_id",
            message=(
                f"'{sheet_name}' has {static.height - deduped.height} entries whose IDs "
                "differ only by hyphen or transfer-clinic suffix; keeping the first of each"
            ),
            sheet_name=sheet_name,
            stage="extract",
            function_name="join_static_sheet",
        )

    return (
        df_monthly.with_columns(normalize_patient_id_expr(pl.col("patient_id")).alias(key))
        .join(deduped, on=key, how="left", suffix=suffix)
        .drop(key)
    )


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
            report_finding(
                error_code="tracker_layout_changed",
                message=(
                    f"Column {column} does not mean the same thing in every month sheet: "
                    f"{', '.join(change.headers)} -> {', '.join(change.canonical)}. "
                    "A tracker should keep one layout for the whole year; check the workbook."
                ),
                stage="extract",
                function_name="read_all_patient_sheets",
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
            report_finding(
                error_code="sheet_skipped",
                message=(f"Sheet '{sheet_name}' has no data, skipping"),
                sheet_name=sheet_name,
                stage="extract",
                function_name="read_all_patient_sheets",
            )
            continue

        df_sheet = harmonize_patient_data_columns(df_sheet, mapper=mapper, strict=False)

        if "patient_id" not in df_sheet.columns:
            report_finding(
                error_code="sheet_skipped",
                message=(
                    f"Sheet '{sheet_name}' has no 'patient_id' column after harmonization, skipping"
                ),
                sheet_name=sheet_name,
                stage="extract",
                function_name="read_all_patient_sheets",
            )
            continue

        try:
            month_num = extract_tracker_month(sheet_name)
        except ValueError as e:
            report_finding(
                error_code="sheet_skipped",
                message=(f"Could not extract month from '{sheet_name}': {e}, skipping"),
                sheet_name=sheet_name,
                stage="extract",
                function_name="read_all_patient_sheets",
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

    # diagonal_relaxed: sheets within one workbook differ in which columns they
    # carry and in inferred dtype (Null vs String for an all-blank column), and
    # a strict concat would fail on either.
    logger.info(f"Combining {len(all_sheets_data)} sheets...")
    df_combined = pl.concat(all_sheets_data, how="diagonal_relaxed")

    initial_rows = len(df_combined)

    # Track rows with missing patient_id for error reporting
    missing_patient_id_rows = df_combined.filter(pl.col("patient_id").is_null())
    missing_count = len(missing_patient_id_rows)

    if missing_count > 0:
        report_finding(
            error_code="missing_required_field",
            message=(
                f"Found {missing_count} rows with missing patient_id in {tracker_file.name} - "
                f"these rows will be excluded from processing"
            ),
            stage="extract",
            function_name="read_all_patient_sheets",
        )

        # Log to ErrorCollector if available
        for row in missing_patient_id_rows.iter_rows(named=True):
            sheet_name = row.get("sheet_name", "unknown")
            name_value = row.get("name", "")
            report_finding(
                patient_id="MISSING",
                column="patient_id",
                original_value=None,
                message=(
                    f"Row in sheet '{sheet_name}' has missing patient_id (name: {name_value})"
                ),
                error_code="missing_required_field",
                stage="extract",
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

    # Filter out rows with patient_id starting with "#" (Excel errors like #REF!).
    # Dropped rather than sentinelled to "Undefined" the way fix_patient_id
    # handles a misspelled ID: #REF! is not an identifier a clinic could
    # reconcile against its records, so keeping the row would pool its
    # measurements with every other unidentified patient under one group key.
    # The measurements are real, though (2026 Preah Kossamak's May26 sheet loses
    # a whole month this way), so each discard is reported for source correction
    # instead of vanishing into the "filtered N invalid rows" count.
    excel_error_id_rows = df_combined.filter(pl.col("patient_id").str.starts_with("#"))
    if len(excel_error_id_rows) > 0:
        for row in excel_error_id_rows.iter_rows(named=True):
            report_finding(
                patient_id="MISSING",
                column="patient_id",
                original_value=row["patient_id"],
                message=(
                    f"Row in sheet '{row.get('sheet_name', 'unknown')}' has an Excel formula "
                    f"error ({row['patient_id']}) where its patient ID should be; the row is "
                    "dropped because the patient cannot be identified"
                ),
                error_code="excel_error_patient_id",
                stage="extract",
                function_name="read_all_patient_sheets",
            )

    df_combined = df_combined.filter(~pl.col("patient_id").str.starts_with("#"))

    filtered_rows = initial_rows - len(df_combined)
    if filtered_rows > 0:
        logger.info(f"Filtered out {filtered_rows} invalid rows total")

    # Excel formula-error strings are deliberately NOT stripped here (ticket
    # 27): the raw layer records what the source cell actually contained.
    # a4d.clean.converters.normalize_excel_formula_errors nulls and logs them.

    # Use already-loaded workbook for sheet checking
    all_sheets = wb.sheetnames

    # Process Patient List sheet if it exists
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

                    # Drop the monthly hba1c_baseline and name before joining:
                    # the Patient List is the authority for both, and keeping
                    # each side's copy collides the names on join.
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

                    df_combined = join_static_sheet(
                        df_monthly, patient_list_join, ".static", "Patient List"
                    )
                    logger.info(f"Joined {len(patient_list)} Patient List records")
                else:
                    report_finding(
                        error_code="sheet_skipped",
                        message=(
                            "Patient List sheet has no 'patient_id' column after harmonization"
                        ),
                        stage="extract",
                        function_name="read_all_patient_sheets",
                    )
            else:
                report_finding(
                    error_code="sheet_skipped",
                    message="Patient List sheet is empty",
                    sheet_name="Patient List",
                    stage="extract",
                    function_name="read_patient_list_sheet",
                )
        except Exception as e:
            report_finding(
                error_code="sheet_skipped",
                message=(f"Could not process Patient List sheet: {e}"),
                stage="extract",
                function_name="read_all_patient_sheets",
            )

    # Process Annual sheet if it exists
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

                    # status and name come from the Patient List, not here.
                    cols_to_drop = [col for col in ["status", "name"] if col in annual_data.columns]
                    annual_data_join = (
                        annual_data.drop(cols_to_drop) if cols_to_drop else annual_data
                    )

                    df_combined = join_static_sheet(
                        df_combined, annual_data_join, ".annual", "Annual"
                    )
                    logger.info(f"Joined {len(annual_data)} Annual records")
                else:
                    report_finding(
                        error_code="sheet_skipped",
                        message=("Annual sheet has no 'patient_id' column after harmonization"),
                        stage="extract",
                        function_name="read_all_patient_sheets",
                    )
            else:
                report_finding(
                    error_code="sheet_skipped",
                    message="Annual sheet is empty",
                    sheet_name="Annual",
                    stage="extract",
                    function_name="read_annual_sheet",
                )
        except Exception as e:
            report_finding(
                error_code="sheet_skipped",
                message=(f"Could not process Annual sheet: {e}"),
                stage="extract",
                function_name="read_all_patient_sheets",
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
