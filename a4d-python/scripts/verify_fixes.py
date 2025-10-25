#!/usr/bin/env python3
"""Verify that the Python fixes are working correctly by analyzing the output."""

import polars as pl
from pathlib import Path


def verify_python_output():
    """Verify Python output has correct types and column ordering."""

    python_file = Path("output/patient_data_raw/Python/2024_Sibu Hospital A4D Tracker_patient_raw.parquet")

    if not python_file.exists():
        print(f"❌ Python file not found: {python_file}")
        return False

    print("=" * 80)
    print("VERIFYING PYTHON OUTPUT FIXES")
    print("=" * 80)

    df = pl.read_parquet(python_file)

    # Check 1: Column ordering
    print("\n1. COLUMN ORDERING")
    print("-" * 80)
    priority_cols = ["tracker_year", "tracker_month", "clinic_id", "patient_id"]
    first_n = min(10, len(df.columns))
    actual_first_cols = df.columns[:first_n]

    print(f"First {first_n} columns: {actual_first_cols}")

    # Check which priority columns are at the start
    for i, expected_col in enumerate(priority_cols):
        if expected_col in df.columns:
            actual_pos = df.columns.index(expected_col)
            if actual_pos == i:
                print(f"  ✅ {expected_col}: position {actual_pos} (expected {i})")
            else:
                print(f"  ❌ {expected_col}: position {actual_pos} (expected {i})")
        else:
            print(f"  ⚠️  {expected_col}: not found in columns")

    # Check 2: Data types (all should be String)
    print("\n2. DATA TYPES")
    print("-" * 80)

    dtypes = df.schema
    non_string_cols = [(name, dtype) for name, dtype in dtypes.items() if str(dtype) not in ["String", "Utf8"]]

    if non_string_cols:
        print(f"❌ Found {len(non_string_cols)} non-String columns:")
        for col, dtype in non_string_cols[:10]:
            print(f"  - {col}: {dtype}")
        if len(non_string_cols) > 10:
            print(f"  ... and {len(non_string_cols) - 10} more")
    else:
        print("✅ All columns are String type")

    # Check 3: No Null dtype columns
    null_cols = [(name, dtype) for name, dtype in dtypes.items() if str(dtype) == "Null"]

    if null_cols:
        print(f"\n❌ Found {len(null_cols)} Null-type columns (should be String):")
        for col, dtype in null_cols:
            print(f"  - {col}: {dtype}")
    else:
        print("✅ No Null-type columns found")

    # Check 4: Sample data
    print("\n3. SAMPLE DATA (first 3 rows)")
    print("-" * 80)
    print(df.head(3))

    # Check 5: Dimensions
    print("\n4. DIMENSIONS")
    print("-" * 80)
    print(f"Rows: {df.height}")
    print(f"Columns: {df.width}")
    print(f"Column names: {df.columns[:20]}")
    if df.width > 20:
        print(f"... and {df.width - 20} more")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    issues = []
    if non_string_cols:
        issues.append(f"{len(non_string_cols)} non-String columns")
    if null_cols:
        issues.append(f"{len(null_cols)} Null-type columns")

    # Check column ordering
    priority_check_failed = False
    for i, expected_col in enumerate(priority_cols):
        if expected_col in df.columns:
            if df.columns.index(expected_col) != i:
                priority_check_failed = True
                break

    if priority_check_failed:
        issues.append("Column ordering incorrect")

    if issues:
        print(f"❌ Issues found: {', '.join(issues)}")
        return False
    else:
        print("✅ All checks passed!")
        return True


if __name__ == "__main__":
    import sys
    success = verify_python_output()
    sys.exit(0 if success else 1)
