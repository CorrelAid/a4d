#!/usr/bin/env python3
"""Check which sheets are being processed by R vs Python."""

from pathlib import Path

import polars as pl


def check_sheets():
    """Compare which sheets were processed."""

    r_file = Path("output/patient_data_raw/R/2024_Sibu Hospital A4D Tracker_patient_raw.parquet")
    python_file = Path(
        "output/patient_data_raw/Python/2024_Sibu Hospital A4D Tracker_patient_raw.parquet"
    )

    df_r = pl.read_parquet(r_file)
    df_python = pl.read_parquet(python_file)

    print("=" * 80)
    print("SHEET ANALYSIS")
    print("=" * 80)

    # R sheets
    r_sheets = df_r["sheet_name"].unique().sort().to_list()
    r_counts = df_r.group_by("sheet_name").count().sort("sheet_name")

    print("\nR PIPELINE:")
    print(f"Total rows: {len(df_r)}")
    print(f"Sheets: {r_sheets}")
    print("\nRow counts per sheet:")
    print(r_counts)

    # Python sheets
    py_sheets = df_python["sheet_name"].unique().sort().to_list()
    py_counts = df_python.group_by("sheet_name").count().sort("sheet_name")

    print("\n" + "=" * 80)
    print("PYTHON PIPELINE:")
    print(f"Total rows: {len(df_python)}")
    print(f"Sheets: {py_sheets}")
    print("\nRow counts per sheet:")
    print(py_counts)

    # Compare
    print("\n" + "=" * 80)
    print("COMPARISON")
    print("=" * 80)

    r_set = set(r_sheets)
    py_set = set(py_sheets)

    only_r = r_set - py_set
    only_py = py_set - r_set
    common = r_set & py_set

    print(f"\nCommon sheets ({len(common)}): {sorted(common)}")
    if only_r:
        print(f"Only in R ({len(only_r)}): {sorted(only_r)}")
    if only_py:
        print(f"Only in Python ({len(only_py)}): {sorted(only_py)}")

    # Check month order
    print("\n" + "=" * 80)
    print("MONTH ORDER CHECK")
    print("=" * 80)

    r_months = df_r.select(["sheet_name", "tracker_month"]).unique().sort("sheet_name")
    py_months = df_python.select(["sheet_name", "tracker_month"]).unique().sort("sheet_name")

    print("\nR month mapping:")
    print(r_months)

    print("\nPython month mapping:")
    print(py_months)


if __name__ == "__main__":
    check_sheets()
