"""Tests for `create_table_product_data` — Script 3 (steps 3.1-3.3) directly.

`test_link_product_patient.py` already covers `link_product_patient`; this
file covers table creation, which was previously only reached indirectly.
"""

from datetime import date
from pathlib import Path

import polars as pl
import pytest

from a4d.clean.schema_product import get_product_data_schema
from a4d.tables.product import create_table_product_data, read_cleaned_product_data


def _cleaned_product_df(rows: list[dict]) -> pl.DataFrame:
    """Build a DataFrame matching clean_product_data's output schema (20 cols)."""
    schema = get_product_data_schema()
    return pl.DataFrame(rows, schema=schema)


def _base_row(**overrides) -> dict:
    row = {
        "product": "Insulin A",
        "product_units_notes": None,
        "product_entry_date": date(2024, 1, 15),
        "product_units_released": 5.0,
        "product_released_to": "MY_SU001",
        "product_units_received": None,
        "product_received_from": "HQ",
        "product_balance": 10.0,
        "product_units_returned": None,
        "product_returned_by": None,
        "product_table_month": 1,
        "product_table_year": 2024,
        "product_sheet_name": "Jan24",
        "file_name": "tracker_a.xlsx",
        "product_balance_status": "ok",
        "product_category": "Insulin",
        "orig_product_released_to": None,
        "product_unit_capacity": 1,
        "product_remarks": None,
        "clinic_id": "SU",
    }
    row.update(overrides)
    return row


def test_read_cleaned_product_data_empty_list_raises():
    with pytest.raises(ValueError, match="No cleaned product files"):
        read_cleaned_product_data([])


def test_read_cleaned_product_data_concatenates_diagonally(tmp_path: Path):
    file_a = tmp_path / "a_product_cleaned.parquet"
    file_b = tmp_path / "b_product_cleaned.parquet"
    _cleaned_product_df([_base_row(file_name="a.xlsx")]).write_parquet(file_a)
    _cleaned_product_df([_base_row(file_name="b.xlsx")]).write_parquet(file_b)

    result = read_cleaned_product_data([file_a, file_b])

    assert result.height == 2
    assert set(result["file_name"].to_list()) == {"a.xlsx", "b.xlsx"}


def test_create_table_writes_output_with_full_schema(tmp_path: Path):
    cleaned_file = tmp_path / "tracker_a_product_cleaned.parquet"
    _cleaned_product_df([_base_row(), _base_row(product_released_to="MY_SU002")]).write_parquet(
        cleaned_file
    )
    output_dir = tmp_path / "tables"

    output_path = create_table_product_data([cleaned_file], output_dir)

    assert output_path == output_dir / "product_data.parquet"
    assert output_path.exists()

    df = pl.read_parquet(output_path)
    assert set(df.columns) == set(get_product_data_schema().keys())
    assert df.height == 2


def test_create_table_preserves_original_released_to(tmp_path: Path):
    """orig_product_released_to should carry the pre-fix_patient_id value."""
    cleaned_file = tmp_path / "tracker_a_product_cleaned.parquet"
    _cleaned_product_df([_base_row(product_released_to="MY-SU001")]).write_parquet(cleaned_file)
    output_dir = tmp_path / "tables"

    output_path = create_table_product_data([cleaned_file], output_dir)
    df = pl.read_parquet(output_path)

    # fix_patient_id normalizes hyphens to underscores.
    assert df["product_released_to"].to_list() == ["MY_SU001"]
    assert df["orig_product_released_to"].to_list() == ["MY-SU001"]


def test_create_table_replaces_invalid_released_to(tmp_path: Path):
    cleaned_file = tmp_path / "tracker_a_product_cleaned.parquet"
    _cleaned_product_df([_base_row(product_released_to="not-a-patient-id")]).write_parquet(
        cleaned_file
    )
    output_dir = tmp_path / "tables"

    output_path = create_table_product_data([cleaned_file], output_dir)
    df = pl.read_parquet(output_path)

    # Invalid, <=8-char-after-normalization IDs get replaced by fix_patient_id;
    # the raw value survives untouched in orig_product_released_to.
    assert df["orig_product_released_to"].to_list() == ["not-a-patient-id"]
    assert df["product_released_to"].to_list() != ["not-a-patient-id"]


def test_create_table_concatenates_multiple_files(tmp_path: Path):
    file_a = tmp_path / "a_product_cleaned.parquet"
    file_b = tmp_path / "b_product_cleaned.parquet"
    _cleaned_product_df([_base_row(file_name="a.xlsx")]).write_parquet(file_a)
    _cleaned_product_df(
        [
            _base_row(file_name="b.xlsx"),
            _base_row(file_name="b.xlsx", product_released_to="MY_SU003"),
        ]
    ).write_parquet(file_b)
    output_dir = tmp_path / "tables"

    output_path = create_table_product_data([file_a, file_b], output_dir)
    df = pl.read_parquet(output_path)

    assert df.height == 3
    assert sorted(df["file_name"].unique().to_list()) == ["a.xlsx", "b.xlsx"]


def test_create_table_casts_numeric_columns(tmp_path: Path):
    """safe_convert_column should cast to schema dtypes (e.g. Float64 balance)."""
    cleaned_file = tmp_path / "tracker_a_product_cleaned.parquet"
    _cleaned_product_df([_base_row(product_balance=12.5)]).write_parquet(cleaned_file)
    output_dir = tmp_path / "tables"

    output_path = create_table_product_data([cleaned_file], output_dir)
    df = pl.read_parquet(output_path)

    assert df.schema["product_balance"] == pl.Float64
    assert df["product_balance"].to_list() == [12.5]
