#!/usr/bin/env python3
"""Detailed analysis of differences between R and Python outputs."""

import polars as pl
from pathlib import Path


def detailed_analysis():
    """Perform detailed analysis of the differences."""

    base_dir = Path(__file__).parent.parent
    r_file = base_dir / "output/patient_data_raw/R/2024_Sibu Hospital A4D Tracker_patient_raw.parquet"
    python_file = base_dir / "output/patient_data_raw/Python/2024_Sibu Hospital A4D Tracker_patient_raw.parquet"

    df_r = pl.read_parquet(r_file)
    df_python = pl.read_parquet(python_file)

    print("=" * 80)
    print("DETAILED ANALYSIS OF DIFFERENCES")
    print("=" * 80)

    # 1. Check if rows are in the same order
    print("\n1. ROW ORDER CHECK")
    print("-" * 80)

    # Check if patient_id exists and compare
    if "patient_id" in df_r.columns and "patient_id" in df_python.columns:
        print("\nFirst 10 patient IDs:")
        print(f"{'Row':<5} {'R':<30} {'Python':<30}")
        print("-" * 65)
        for i in range(min(10, df_r.height)):
            r_id = df_r["patient_id"][i]
            py_id = df_python["patient_id"][i]
            match = "✓" if r_id == py_id else "✗"
            print(f"{i:<5} {str(r_id):<30} {str(py_id):<30} {match}")

    # 2. Check metadata columns
    print("\n\n2. METADATA COLUMNS CHECK")
    print("-" * 80)

    metadata_cols = ["sheet_name", "tracker_month", "tracker_year", "file_name"]
    for col in metadata_cols:
        if col in df_r.columns and col in df_python.columns:
            print(f"\n{col}:")
            print(f"  R unique values: {df_r[col].unique().to_list()[:5]}")
            print(f"  Python unique values: {df_python[col].unique().to_list()[:5]}")
        elif col in df_r.columns:
            print(f"\n{col}: Only in R")
        elif col in df_python.columns:
            print(f"\n{col}: Only in Python")

    # 3. Check the "na" columns in R
    print("\n\n3. R 'NA' COLUMNS ANALYSIS")
    print("-" * 80)

    na_cols = [c for c in df_r.columns if c.startswith("na")]
    for col in na_cols:
        non_null_count = df_r[col].null_count()
        unique_vals = df_r[col].unique().to_list()[:10]
        print(f"\n{col}:")
        print(f"  Non-null count: {df_r.height - non_null_count}/{df_r.height}")
        print(f"  Unique values (first 10): {unique_vals}")

    # 4. Show full row comparison for first patient
    print("\n\n4. FIRST PATIENT FULL COMPARISON")
    print("-" * 80)

    common_cols = sorted(set(df_r.columns) & set(df_python.columns))

    print(f"\n{'Column':<45} {'R Value':<25} {'Python Value':<25} {'Match'}")
    print("-" * 100)

    for col in common_cols[:30]:  # Show first 30 columns
        r_val = df_r[col][0]
        py_val = df_python[col][0]

        # Handle nulls
        r_str = "NULL" if r_val is None else str(r_val)
        py_str = "NULL" if py_val is None else str(py_val)

        match = "✓" if r_val == py_val else "✗"

        print(f"{col:<45} {r_str:<25} {py_str:<25} {match}")

    if len(common_cols) > 30:
        print(f"\n... and {len(common_cols) - 30} more columns")

    # 5. Check column name patterns - synonyms issue?
    print("\n\n5. COLUMN NAME PATTERN ANALYSIS")
    print("-" * 80)

    print("\nR columns with 'na' or unusual patterns:")
    unusual_r = [c for c in df_r.columns if "na" in c.lower() or c.startswith("_")]
    for col in unusual_r:
        print(f"  - {col}")

    print("\nPython columns that might be unmapped:")
    python_unmapped = [c for c in df_python.columns if c[0].isupper() or " " in c]
    for col in python_unmapped:
        print(f"  - {col}")

    # 6. Check if the issue is row sorting
    print("\n\n6. ROW SORTING CHECK")
    print("-" * 80)

    if "patient_id" in df_r.columns and "patient_id" in df_python.columns:
        r_sorted = df_r.sort("patient_id")
        py_sorted = df_python.sort("patient_id")

        print("\nChecking if values match when both are sorted by patient_id...")

        # Check first few key columns
        check_cols = ["patient_id", "name", "age", "clinic_visit"]
        all_match = True

        for col in check_cols:
            if col in r_sorted.columns and col in py_sorted.columns:
                is_equal = r_sorted[col].series_equal(py_sorted[col], null_equal=True)
                print(f"  {col}: {'✓ Match' if is_equal else '✗ Differ'}")
                if not is_equal:
                    all_match = False

        if not all_match:
            print("\n  Values still differ even when sorted. This suggests data extraction differences.")
        else:
            print("\n  Values match when sorted! The issue is just row ordering.")


if __name__ == "__main__":
    detailed_analysis()
