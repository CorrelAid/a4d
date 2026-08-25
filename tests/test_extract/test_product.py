"""Unit tests for product data extraction (`a4d.extract.product`)."""

from pathlib import Path
from unittest.mock import Mock

import polars as pl
import pytest
from openpyxl import Workbook

from a4d.extract.product import (
    ProductSectionNotFoundError,
    _count_orphan_released_units,
    _harmonize,
    add_product_metadata,
    extract_product_data,
    find_product_section,
    read_all_product_sheets,
    remove_header_rows,
    replace_extra_totals,
)


def _make_ws(rows: list[list]):
    """Build an in-memory openpyxl worksheet with the given rows.

    Returns the worksheet handle (1-indexed Excel rows). Empty cells use
    ``None``.
    """
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    return ws


def test_find_product_section_2024_layout():
    """Header row contains product/date/received; patient section follows."""
    ws = _make_ws(
        [
            [None, None, None, None, None],
            ["Product", "Date", "Units Received", "From", "Released"],
            ["Insulin", "2024-06-01", 100, "DKSH", 5],
            ["Strips", "2024-06-02", 50, "DKSH", None],
            ["Patient Recruitment", None, None, None, None],
            ["Patient Name", "Patient ID", None, None, None],
        ]
    )
    start, end = find_product_section(ws)
    assert start == 2
    assert end == 4


def test_find_product_section_raises_on_missing_start():
    """No header row with product/date/received markers triggers the error."""
    ws = _make_ws(
        [
            ["Random", "Junk", "Headers"],
            ["Patient Name", "Patient ID", None],
        ]
    )
    with pytest.raises(ProductSectionNotFoundError):
        find_product_section(ws)


def test_find_product_section_raises_on_missing_end():
    """Header found but no patient-section terminator triggers the error."""
    ws = _make_ws(
        [
            ["Product", "Date", "Units Received"],
            ["Insulin", "2024-06-01", 100],
        ]
    )
    with pytest.raises(ProductSectionNotFoundError):
        find_product_section(ws)


def _make_mapper(known_to_standard: dict[str, str]):
    """Build a mock ColumnMapper.

    ``known_to_standard`` maps source column names to the standardized name
    they should be renamed to. Anything not in the dict is treated as
    unknown (caught by ``is_known_column`` returning False) and dropped.
    """
    mapper = Mock()
    mapper.synonyms = {standard: [src] for src, standard in known_to_standard.items()}
    mapper.is_known_column = lambda col: col in known_to_standard
    mapper.rename_columns = lambda df: df.rename(known_to_standard)
    return mapper


def test_harmonize_renames_known_drops_unknown(collector):
    df = pl.DataFrame(
        {"Product Name": ["Insulin"], "Random Junk": ["x"]},
        schema={"Product Name": pl.String, "Random Junk": pl.String},
    )
    mapper = _make_mapper({"Product Name": "product"})

    out = _harmonize(df, mapper, sheet_name="Jun24", file_name="t.xlsx")

    assert out.columns == ["product"]
    assert len(collector) == 1
    assert collector.findings[0].column == "Random Junk"
    assert collector.findings[0].error_code == "invalid_tracker"
    assert collector.findings[0].function_name == "harmonize_input_data_columns"


def test_harmonize_no_unknowns_no_log(collector):
    df = pl.DataFrame(
        {"Product Name": ["Insulin"]},
        schema={"Product Name": pl.String},
    )
    mapper = _make_mapper({"Product Name": "product"})

    out = _harmonize(df, mapper, sheet_name="Jun24", file_name="t.xlsx")

    assert out.columns == ["product"]
    assert len(collector) == 0


def test_replace_extra_totals_masks_after_total_column():
    """If a column to the immediate left of product_units_released contains
    'total' (case-insensitive), the released value is nulled."""
    df = pl.DataFrame(
        {
            "product": ["A", "B"],
            "Total Released": ["Total", None],
            "product_units_released": ["10", "20"],
        },
        schema={
            "product": pl.String,
            "Total Released": pl.String,
            "product_units_released": pl.String,
        },
    )
    out = replace_extra_totals(df)
    assert out["product_units_released"].to_list() == [None, "20"]


def test_replace_extra_totals_preserves_clean_rows():
    """No 'total' marker in either of the two preceding columns leaves
    product_units_released unchanged."""
    df = pl.DataFrame(
        {
            "product": ["A", "B"],
            "product_received_from": ["DKSH", None],
            "product_released_to": ["P1", "P2"],
            "product_units_released": ["10", "20"],
        },
        schema={
            "product": pl.String,
            "product_received_from": pl.String,
            "product_released_to": pl.String,
            "product_units_released": pl.String,
        },
    )
    out = replace_extra_totals(df)
    assert out["product_units_released"].to_list() == ["10", "20"]


def test_replace_extra_totals_case_insensitive():
    """'total' / 'TOTAL' / 'Total' all trigger masking."""
    df = pl.DataFrame(
        {
            "product": ["A"],
            "TOTAL": ["TOTAL"],
            "product_units_released": ["10"],
        },
        schema={
            "product": pl.String,
            "TOTAL": pl.String,
            "product_units_released": pl.String,
        },
    )
    out = replace_extra_totals(df)
    assert out["product_units_released"].to_list() == [None]


def test_extract_product_data_promotes_headers_and_types_strings():
    """First row becomes column names; all values are coerced to pl.String."""
    rows = [
        ["Cover", None, None],  # 1: pre-section
        ["Product", "Date", "Units"],  # 2: header
        ["Insulin", "2024-06-01", 100],  # 3
        ["Strips", "2024-06-02", 50],  # 4
    ]
    ws = _make_ws(rows)

    out = extract_product_data(ws, start_row=2, end_row=4)

    assert out.columns == ["Product", "Date", "Units"]
    assert out.dtypes == [pl.String, pl.String, pl.String]
    assert out["Product"].to_list() == ["Insulin", "Strips"]
    assert out["Units"].to_list() == ["100", "50"]


def test_extract_product_data_merges_duplicate_headers_with_comma():
    """When two columns share a header, values are joined with ','."""
    rows = [
        ["Product", "Note", "Note"],
        ["Insulin", "A", "B"],
        ["Strips", None, "C"],
    ]
    ws = _make_ws(rows)

    out = extract_product_data(ws, start_row=1, end_row=3)
    assert "Note" in out.columns
    assert out["Note"].to_list() == ["A,B", "C"]


def test_extract_product_data_returns_empty_for_short_section():
    rows = [["Product", "Date"]]  # only header, no data
    ws = _make_ws(rows)
    out = extract_product_data(ws, start_row=1, end_row=1)
    assert out.height == 0
    assert out.width == 0


def test_add_product_metadata_appends_five_cols():
    df = pl.DataFrame({"product": ["A"]}, schema={"product": pl.String})
    out = add_product_metadata(df, "Jun24", 6, 2024, "tracker.xlsx", "CL001")
    assert out["product_table_month"].to_list() == ["06"]
    assert out["product_table_year"].to_list() == [2024.0]
    assert out["product_sheet_name"].to_list() == ["Jun24"]
    assert out["file_name"].to_list() == ["tracker.xlsx"]
    assert out["clinic_id"].to_list() == ["CL001"]


def test_remove_header_rows_drops_repeated_header_and_empty():
    df = pl.DataFrame(
        {
            "product": ["Product", "Insulin", None, "Patient Data Summary"],
            "product_entry_date": [None, "2024-06", None, None],
        },
        schema={"product": pl.String, "product_entry_date": pl.String},
    )
    out = remove_header_rows(df)
    assert out["product"].to_list() == ["Insulin"]


def test_remove_header_rows_empty_input():
    df = pl.DataFrame({"product": []}, schema={"product": pl.String})
    out = remove_header_rows(df)
    assert out.height == 0


def test_remove_header_rows_drops_row_of_empty_strings():
    # A formula-emptied Excel cell surfaces as "" rather than None; such a row
    # carries no information and must not reach the output as a movement.
    df = pl.DataFrame(
        {
            "product": ["Insulin", ""],
            "product_entry_date": ["2024-06", ""],
        },
        schema={"product": pl.String, "product_entry_date": pl.String},
    )
    out = remove_header_rows(df)
    assert out["product"].to_list() == ["Insulin"]


def test_read_all_product_sheets_end_to_end(tmp_path: Path, collector):
    """End-to-end: build a tracker workbook with one month sheet, stub the
    mapper, and verify the orchestrator wires extract → harmonize →
    metadata → totals correctly."""
    wb = Workbook()
    # Remove the default sheet and add a Jun24 sheet.
    wb.remove(wb.active)
    ws = wb.create_sheet("Jun24")

    rows = [
        [None, None, None, None, None],  # 1: pre-section
        ["Product", "Date", "Units Received", "From", "Released"],  # 2: header
        ["Insulin", "2024-06-01", 100, "DKSH", 5],  # 3: data
        ["Strips", "2024-06-02", 50, "DKSH", None],  # 4: data
        ["Patient Recruitment", None, None, None, None],  # 5: terminator
        ["Patient Name", "Patient ID", None, None, None],  # 6: end
    ]
    for row in rows:
        ws.append(row)

    tracker_path = tmp_path / "2024_test_tracker.xlsx"
    wb.save(tracker_path)

    mapper = _make_mapper(
        {
            "Product": "product",
            "Date": "product_entry_date",
            "Units Received": "product_units_received",
            "From": "product_received_from",
            "Released": "product_units_released",
        }
    )

    out = read_all_product_sheets(tracker_path, mapper=mapper)

    assert out.height == 2
    assert "product" in out.columns
    assert "product_table_year" in out.columns
    assert "product_sheet_name" in out.columns
    assert "clinic_id" in out.columns
    assert out["product_sheet_name"].to_list() == ["Jun24", "Jun24"]
    assert out["product_table_year"].to_list() == [2024.0, 2024.0]
    assert out["clinic_id"].to_list() == [tracker_path.parent.name] * 2
    # No unknown columns; collector should be empty.
    assert len(collector) == 0


def test_read_all_product_sheets_no_month_sheets_raises(tmp_path: Path):
    wb = Workbook()
    # Default sheet has no month-prefix; remove and add a non-month sheet.
    wb.remove(wb.active)
    wb.create_sheet("Cover")
    tracker_path = tmp_path / "2024_no_months.xlsx"
    wb.save(tracker_path)

    mapper = _make_mapper({})

    with pytest.raises(ValueError, match="No month sheets"):
        read_all_product_sheets(tracker_path, mapper=mapper)


def test_count_orphan_released_units_logs_per_sheet(collector):
    """3 orphan rows (released_to null while units_released non-null)
    produce exactly 1 ErrorCollector entry naming the sheet and count."""
    df = pl.DataFrame(
        {
            "product_released_to": [None, None, None, "P1", "P2"],
            "product_units_released": ["10", "20", "30", "40", None],
        },
        schema={
            "product_released_to": pl.String,
            "product_units_released": pl.String,
        },
    )

    _count_orphan_released_units(df, sheet_name="Jul24", file_name="t.xlsx")

    assert len(collector) == 1
    err = collector.findings[0]
    assert err.error_code == "invalid_tracker"
    assert err.function_name == "_count_orphan_released_units"
    assert err.column == "product_released_to"
    assert "Jul24" in err.message
    assert "3" in err.message


def test_count_orphan_released_units_zero_rows_no_log(collector):
    """Clean fixture (all releases have a recipient) emits no log."""
    df = pl.DataFrame(
        {
            "product_released_to": ["P1", "P2", None],
            "product_units_released": ["10", "20", None],
        },
        schema={
            "product_released_to": pl.String,
            "product_units_released": pl.String,
        },
    )
    _count_orphan_released_units(df, "Jul24", "t.xlsx")
    assert len(collector) == 0


def test_count_orphan_released_units_treats_whitespace_as_null(collector):
    """Whitespace-only product_released_to (e.g. ' ') counts as orphan."""
    df = pl.DataFrame(
        {
            "product_released_to": [" ", "\t", "P1"],
            "product_units_released": ["10", "20", "30"],
        },
        schema={
            "product_released_to": pl.String,
            "product_units_released": pl.String,
        },
    )
    _count_orphan_released_units(df, "Jul24", "t.xlsx")
    assert len(collector) == 1
    assert "2" in collector.findings[0].message


def test_count_orphan_released_units_without_findings_does_not_raise(collector):
    """When no collector is passed (e.g. preview path), the helper is a no-op."""
    df = pl.DataFrame(
        {
            "product_released_to": [None],
            "product_units_released": ["10"],
        },
        schema={
            "product_released_to": pl.String,
            "product_units_released": pl.String,
        },
    )
    # Must not raise: no orphan rows means no findings.
    _count_orphan_released_units(df, "Jul24", "t.xlsx")
