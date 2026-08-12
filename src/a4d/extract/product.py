"""Product data extraction from Excel tracker files.

Mirrors `src/a4d/extract/patient.py` structure but targets the product
section of each month sheet. Covers R Script 1 steps 1.1-1.10.
"""

import warnings
from pathlib import Path

import openpyxl
import polars as pl
from loguru import logger

from a4d.errors import ErrorCollector
from a4d.extract.common import (
    clean_excel_errors,
    extract_tracker_month,
    find_month_sheets,
    get_tracker_year,
)
from a4d.extract.wide_format import handle_wide_format_cells, handle_wide_format_columns
from a4d.reference.synonyms import ColumnMapper, load_product_mapper

warnings.filterwarnings("ignore", category=UserWarning, module=r"openpyxl\..*")


class ProductSectionNotFoundError(ValueError):
    """Raised when a month sheet has no identifiable product section."""


def find_product_section(ws) -> tuple[int, int]:
    """Locate the start and end rows of the product data region (R step 1.1).

    The start row is the header row containing the product/date/received
    keywords. The end row is the row immediately before the patient
    recruitment / patient data summary section.

    Returns (start_row, end_row) as 1-indexed Excel rows, both inclusive.

    Raises:
        ProductSectionNotFoundError: if either bound cannot be located.
    """
    max_row = ws.max_row or 0
    max_col = ws.max_column or 50

    def _norm(raw_row) -> list[str]:
        return [" ".join(str(cell or "").lower().split()) for cell in raw_row]

    start_row: int | None = None
    end_row: int | None = None

    # 3-row sliding window over the streaming iterator: prev, curr, next.
    # We evaluate curr (at curr_excel_row) against prev and next contexts.
    prev_norm: list[str] | None = None
    curr_norm: list[str] | None = None
    curr_excel_row: int = 0

    for excel_row, raw in enumerate(
        ws.iter_rows(min_row=1, max_row=max_row, max_col=max_col, values_only=True),
        start=1,
    ):
        next_norm = _norm(raw)

        if curr_norm is not None:
            if start_row is None:
                has_product = any("product" in cell for cell in curr_norm)
                has_desc_support = any("description of support" in cell for cell in curr_norm)
                has_date = any("date" in cell for cell in curr_norm)
                has_received = any("received" in cell for cell in curr_norm)
                has_units_received = any("units received" in cell for cell in curr_norm)

                matches_2024 = has_product and has_date and has_received
                matches_2019_2021 = has_product and has_date and has_units_received
                matches_2017_2018 = has_desc_support and has_date and has_units_received

                if matches_2024 or matches_2019_2021 or matches_2017_2018:
                    start_row = curr_excel_row
            elif curr_excel_row > start_row:
                has_patient_name = any("patient name" in cell for cell in next_norm)
                has_patient_id = any("patient id" in cell for cell in next_norm) or any(
                    cell.strip() == "id" for cell in next_norm
                )
                has_recruitment = any("patient recruitment" in cell for cell in curr_norm)
                has_data_summary_above = prev_norm is not None and any(
                    "patient data summary" in cell for cell in prev_norm
                )

                if (
                    (has_recruitment or has_data_summary_above)
                    and has_patient_name
                    and has_patient_id
                ):
                    end_row = curr_excel_row - 1
                    break

        prev_norm = curr_norm
        curr_norm = next_norm
        curr_excel_row = excel_row

    if start_row is None:
        raise ProductSectionNotFoundError("Could not find start of product section")
    if end_row is None:
        raise ProductSectionNotFoundError("Could not find end of product section")

    return start_row, end_row


def extract_product_data(ws, start_row: int, end_row: int) -> pl.DataFrame:
    """Read the product region and promote its first row to headers (R step 1.2).

    Returns a DataFrame with all columns typed as ``pl.String``. Type
    coercion is deferred to the cleaning phase (Sprint 3).
    """
    max_col = ws.max_column or 50

    all_rows = list(
        ws.iter_rows(min_row=start_row, max_row=end_row, max_col=max_col, values_only=True)
    )

    if len(all_rows) < 2:
        return pl.DataFrame()

    header_raw = all_rows[0]
    data_rows = all_rows[1:]

    last_col = 0
    for i in range(len(header_raw) - 1, -1, -1):
        if header_raw[i] is not None or any(
            row[i] is not None for row in data_rows if i < len(row)
        ):
            last_col = i + 1
            break

    if last_col == 0:
        return pl.DataFrame()

    from collections import defaultdict

    col_names: list[str] = []
    for col_idx in range(last_col):
        raw_name = header_raw[col_idx]
        col_names.append(str(raw_name) if raw_name is not None else f"_unnamed_{col_idx}")

    header_positions: dict[str, list[int]] = defaultdict(list)
    for idx, name in enumerate(col_names):
        header_positions[name].append(idx)

    duplicated = [h for h, positions in header_positions.items() if len(positions) > 1]
    if duplicated:
        logger.debug(f"Merging {len(duplicated)} duplicate column groups: {duplicated}")

    data_dict: dict[str, list[str | None]] = {}
    for header, positions in header_positions.items():
        values: list[str | None] = []
        for row in data_rows:
            if len(positions) == 1:
                pos = positions[0]
                raw = row[pos] if pos < len(row) else None
                values.append(str(raw) if raw is not None else None)
            else:
                parts: list[str] = []
                for pos in positions:
                    raw = row[pos] if pos < len(row) else None
                    text = str(raw) if raw is not None else None
                    if text:
                        parts.append(text)
                values.append(",".join(parts) if parts else None)
        data_dict[header] = values

    return pl.DataFrame(data_dict, schema=dict.fromkeys(data_dict, pl.String))


def add_product_metadata(
    df: pl.DataFrame,
    sheet_name: str,
    tracker_month: int,
    tracker_year: int,
    file_name: str,
    clinic_id: str,
) -> pl.DataFrame:
    """Append sheet/tracker metadata columns (R step 1.8)."""
    return df.with_columns(
        [
            pl.lit(f"{tracker_month:02d}", dtype=pl.String).alias("product_table_month"),
            pl.lit(float(tracker_year), dtype=pl.Float64).alias("product_table_year"),
            pl.lit(sheet_name, dtype=pl.String).alias("product_sheet_name"),
            pl.lit(file_name, dtype=pl.String).alias("file_name"),
            pl.lit(clinic_id, dtype=pl.String).alias("clinic_id"),
        ]
    )


def remove_header_rows(df: pl.DataFrame) -> pl.DataFrame:
    """Drop residual header rows and fully empty rows (R step 1.6)."""
    if df.height == 0:
        return df

    # A formula-emptied Excel cell can surface as "" rather than None, which
    # is.null() alone won't catch; R's is.na()-based check drops such rows too.
    blank_exprs = [
        pl.col(name).is_null() | (pl.col(name).str.strip_chars() == "")
        if dtype == pl.String
        else pl.col(name).is_null()
        for name, dtype in df.schema.items()
    ]
    df = df.filter(~pl.all_horizontal(blank_exprs))

    if "product" in df.columns:
        df = df.filter(
            pl.col("product").is_null()
            | ~pl.col("product")
            .str.strip_chars()
            .str.to_lowercase()
            .is_in(["product", "patient data summary"])
        )

    return df


def replace_extra_totals(df: pl.DataFrame) -> pl.DataFrame:
    """Null ``product_units_released`` after a ``Total`` column (R step 1.9)."""
    if df.height == 0:
        return df

    if "product_released_to" in df.columns:
        # R uses trimws(which="left") here, but readxl already strips trailing
        # whitespace on read; openpyxl preserves it. Strip both to match R output.
        df = df.with_columns(
            pl.col("product_released_to").str.strip_chars().alias("product_released_to")
        )

    if "product_units_released" not in df.columns:
        return df

    col_idx = df.columns.index("product_units_released")
    if col_idx < 2:
        return df

    prev1 = df.columns[col_idx - 1]
    prev2 = df.columns[col_idx - 2]

    def _total_mask(col_name: str) -> pl.Expr:
        if df.schema[col_name] == pl.String:
            return (
                pl.col(col_name)
                .str.to_lowercase()
                .str.contains("total", literal=True)
                .fill_null(False)
            )
        return pl.lit(False)

    mask = _total_mask(prev1) | _total_mask(prev2)
    return df.with_columns(
        pl.when(mask)
        .then(None)
        .otherwise(pl.col("product_units_released"))
        .alias("product_units_released")
    )


def _count_orphan_released_units(
    df: pl.DataFrame,
    sheet_name: str,
    file_name: str,
    error_collector: ErrorCollector | None,
) -> None:
    """R-parity warning for orphan ``product_units_released`` values.

    Counts harmonized rows where ``product_released_to`` is null/whitespace
    yet ``product_units_released`` carries a value, and emits one
    ErrorCollector entry per sheet. Mirrors R ``count_na_rows`` in
    ``read_product_data.R`` (called before ``replace_extra_total_values_with_NA``).

    Whitespace-only ``product_released_to`` cells count as orphan: openpyxl
    returns ``""`` for blank cells while ``_normalize_empty_strings_to_null``
    runs in clean rather than extract, so the check folds them into the null
    branch here.
    """
    if error_collector is None:
        return
    if "product_released_to" not in df.columns or "product_units_released" not in df.columns:
        return

    released_to_blank = pl.col("product_released_to").is_null() | (
        pl.col("product_released_to").cast(pl.String).str.strip_chars() == ""
    )
    has_released_units = pl.col("product_units_released").is_not_null() & (
        pl.col("product_units_released").cast(pl.String).str.strip_chars() != ""
    )

    count = df.filter(released_to_blank & has_released_units).height
    if count == 0:
        return

    logger.bind(error_code="invalid_tracker").warning(
        f"Sheet '{sheet_name}' has {count} rows where product_released_to "
        f"is missing next to product_units_released."
    )
    error_collector.add_error(
        file_name=file_name,
        patient_id="unknown",
        column="product_released_to",
        original_value=str(count),
        error_message=(
            f"Sheet '{sheet_name}' has {count} rows where product_released_to "
            f"is missing next to product_units_released."
        ),
        error_code="invalid_tracker",
        script="script1",
        function_name="read_product_data_step1",
    )


def _harmonize(
    df: pl.DataFrame,
    mapper: ColumnMapper,
    sheet_name: str,
    error_collector: ErrorCollector | None,
    file_name: str,
) -> pl.DataFrame:
    """Rename columns via the mapper then drop any column not in the synonym schema (R step 1.5)."""
    unknown = [
        col for col in df.columns if not mapper.is_known_column(col) and col not in mapper.synonyms
    ]
    if unknown:
        logger.bind(error_code="invalid_tracker").warning(
            f"Sheet {sheet_name}: unknown column names: {unknown}."
        )
        if error_collector is not None:
            for col in unknown:
                error_collector.add_error(
                    file_name=file_name,
                    patient_id="unknown",
                    column=col,
                    original_value=col,
                    error_message=f"Sheet {sheet_name}: unknown column '{col}'",
                    error_code="invalid_tracker",
                    script="script1",
                    function_name="harmonize_input_data_columns",
                )

    df = mapper.rename_columns(df)
    known = set(mapper.synonyms.keys())
    keep = [c for c in df.columns if c in known]
    return df.select(keep) if keep else df.clear()


def read_all_product_sheets(
    tracker_file: Path,
    mapper: ColumnMapper | None = None,
    error_collector: ErrorCollector | None = None,
) -> pl.DataFrame:
    """Run steps 1.1-1.10 across every month sheet, returning one combined DataFrame."""
    tracker_file = Path(tracker_file)
    mapper = mapper or load_product_mapper()

    wb = openpyxl.load_workbook(
        tracker_file, read_only=True, data_only=True, keep_vba=False, keep_links=False
    )

    month_sheets = find_month_sheets(wb)
    if not month_sheets:
        raise ValueError(f"No month sheets found in {tracker_file.name}")

    year = get_tracker_year(tracker_file, month_sheets)
    filename = tracker_file.stem
    clinic_id = tracker_file.parent.name

    per_sheet: list[pl.DataFrame] = []
    for sheet_name in month_sheets:
        ws = wb[sheet_name]
        try:
            start, end = find_product_section(ws)
        except ProductSectionNotFoundError as exc:
            logger.bind(error_code="invalid_tracker").warning(
                f"Sheet {sheet_name}: {exc}. Skipping."
            )
            if error_collector is not None:
                error_collector.add_error(
                    file_name=filename,
                    patient_id="unknown",
                    column="",
                    original_value="",
                    error_message=f"Sheet {sheet_name}: {exc}",
                    error_code="invalid_tracker",
                    script="script1",
                    function_name="find_product_section",
                )
            continue

        df = extract_product_data(ws, start, end)
        if df.height == 0:
            continue

        df = handle_wide_format_columns(df, filename)
        df = handle_wide_format_cells(df, filename)

        df = _harmonize(df, mapper, sheet_name, error_collector, filename)
        if df.height == 0 or df.width == 0:
            continue

        try:
            month = extract_tracker_month(sheet_name)
        except ValueError as exc:
            logger.warning(f"Sheet {sheet_name}: month unparseable ({exc}). Skipping.")
            continue

        df = remove_header_rows(df)
        df = add_product_metadata(df, sheet_name, month, year, filename, clinic_id)
        _count_orphan_released_units(df, sheet_name, filename, error_collector)
        df = replace_extra_totals(df)

        if df.height > 0:
            per_sheet.append(df)

    wb.close()

    if not per_sheet:
        logger.bind(error_code="empty_product_data").warning(
            f"Empty product data: no product section found in any sheet of {filename}."
        )
        return pl.DataFrame()

    return clean_excel_errors(pl.concat(per_sheet, how="diagonal_relaxed"))


def export_product_raw(
    df: pl.DataFrame,
    tracker_file: Path,
    output_dir: Path,
) -> Path:
    """Write raw product DataFrame to ``{output_dir}/{tracker_name}_product_raw.parquet``."""
    tracker_file = Path(tracker_file)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    output_path = output_dir / f"{tracker_file.stem}_product_raw.parquet"
    logger.info(f"Writing {df.height} rows to {output_path}")
    df.write_parquet(output_path)
    return output_path
