#!/usr/bin/env python3
"""Compare R and Python pipeline outputs for the same tracker file."""

import polars as pl
from pathlib import Path
import sys


def compare_parquets(r_path: Path, python_path: Path):
    """Compare two parquet files and report all differences."""

    print("=" * 80)
    print("COMPARING R vs PYTHON PIPELINE OUTPUTS")
    print("=" * 80)
    print(f"\nR file: {r_path}")
    print(f"Python file: {python_path}")
    print()

    # Read both files
    df_r = pl.read_parquet(r_path)
    df_python = pl.read_parquet(python_path)

    differences = []

    # 1. Compare dimensions
    print("\n" + "=" * 80)
    print("1. DIMENSIONS")
    print("=" * 80)
    print(f"R:      {df_r.height:,} rows × {df_r.width} columns")
    print(f"Python: {df_python.height:,} rows × {df_python.width} columns")

    if (df_r.height, df_r.width) != (df_python.height, df_python.width):
        differences.append(f"Shape mismatch: R=({df_r.height}, {df_r.width}), Python=({df_python.height}, {df_python.width})")
        print("❌ DIFFERENCE: Shapes don't match")
    else:
        print("✅ Same dimensions")

    # 2. Compare column names
    print("\n" + "=" * 80)
    print("2. COLUMN NAMES")
    print("=" * 80)

    cols_r = set(df_r.columns)
    cols_python = set(df_python.columns)

    cols_only_r = cols_r - cols_python
    cols_only_python = cols_python - cols_r
    common_cols = cols_r & cols_python

    print(f"Common columns: {len(common_cols)}")
    print(f"Only in R: {len(cols_only_r)}")
    print(f"Only in Python: {len(cols_only_python)}")

    if cols_only_r:
        differences.append(f"Columns only in R: {sorted(cols_only_r)}")
        print("\nColumns ONLY in R:")
        for col in sorted(cols_only_r):
            print(f"  - {col}")

    if cols_only_python:
        differences.append(f"Columns only in Python: {sorted(cols_only_python)}")
        print("\nColumns ONLY in Python:")
        for col in sorted(cols_only_python):
            print(f"  - {col}")

    # Check column order
    if df_r.columns != df_python.columns:
        differences.append("Column order differs")
        print("\n❌ DIFFERENCE: Column order differs")
        print("\nColumn order comparison (first 10):")
        print("R:     ", df_r.columns[:10])
        print("Python:", df_python.columns[:10])
    else:
        print("✅ Column names and order match")

    # 3. Compare data types
    print("\n" + "=" * 80)
    print("3. DATA TYPES")
    print("=" * 80)

    dtype_diffs = []
    for col in sorted(common_cols):
        dtype_r = str(df_r[col].dtype)
        dtype_python = str(df_python[col].dtype)
        if dtype_r != dtype_python:
            dtype_diffs.append((col, dtype_r, dtype_python))

    if dtype_diffs:
        differences.append(f"Data type mismatches: {len(dtype_diffs)} columns")
        print(f"❌ DIFFERENCE: {len(dtype_diffs)} columns have different types:")
        print(f"\n{'Column':<40} {'R Type':<20} {'Python Type':<20}")
        print("-" * 80)
        for col, dtype_r, dtype_python in dtype_diffs[:20]:  # Show first 20
            print(f"{col:<40} {dtype_r:<20} {dtype_python:<20}")
        if len(dtype_diffs) > 20:
            print(f"... and {len(dtype_diffs) - 20} more")
    else:
        print("✅ All data types match")

    # 4. Compare values for common columns
    print("\n" + "=" * 80)
    print("4. VALUE COMPARISON")
    print("=" * 80)

    if df_r.height != df_python.height:
        print("⚠️  Cannot compare values row-by-row (different number of rows)")
    else:
        # Reorder Python columns to match R for comparison
        df_python_ordered = df_python.select(df_r.columns) if set(df_r.columns) == set(df_python.columns) else df_python

        value_diffs = []
        for col in sorted(common_cols):
            if col not in df_r.columns or col not in df_python.columns:
                continue

            # Compare values
            r_vals = df_r[col]
            py_vals = df_python[col]

            # Check if columns are equal (handles nulls automatically)
            try:
                is_equal = r_vals.series_equal(py_vals, null_equal=True)
                if not is_equal:
                    # Count differences
                    mask_both_null = r_vals.is_null() & py_vals.is_null()
                    mask_equal = (r_vals == py_vals) | mask_both_null
                    n_diff = (~mask_equal).sum()
                    if n_diff > 0:
                        value_diffs.append((col, n_diff))
            except Exception:
                # If comparison fails (e.g., different dtypes), mark as different
                value_diffs.append((col, df_r.height))

        if value_diffs:
            differences.append(f"Value mismatches: {len(value_diffs)} columns")
            print(f"❌ DIFFERENCE: {len(value_diffs)} columns have different values:")
            print(f"\n{'Column':<40} {'# Differences':<15}")
            print("-" * 55)
            for col, n_diff in value_diffs[:20]:  # Show first 20
                print(f"{col:<40} {n_diff:>10,}")
            if len(value_diffs) > 20:
                print(f"... and {len(value_diffs) - 20} more")

            # Show sample of differences for first differing column
            if value_diffs:
                col, _ = value_diffs[0]
                print(f"\n--- Sample differences in '{col}' (first 10 rows with differences) ---")
                r_vals = df_r[col]
                py_vals = df_python[col]

                # Find rows where values differ
                mask_both_null = r_vals.is_null() & py_vals.is_null()
                mask_diff = ~((r_vals == py_vals) | mask_both_null)

                # Get first 10 differing rows
                diff_df = df_r.filter(mask_diff).select([col]).head(10)
                diff_df_py = df_python.filter(mask_diff).select([col]).head(10)

                for i in range(min(10, len(diff_df))):
                    r_val = diff_df[col][i]
                    py_val = diff_df_py[col][i]
                    print(f"  Row {i}: R={repr(r_val)} | Python={repr(py_val)}")
        else:
            print("✅ All values match")

    # 5. Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    if differences:
        print(f"\n❌ Found {len(differences)} categories of differences:")
        for i, diff in enumerate(differences, 1):
            print(f"  {i}. {diff}")
        return False
    else:
        print("\n✅ Files are identical!")
        return True


if __name__ == "__main__":
    base_dir = Path(__file__).parent.parent

    r_file = base_dir / "output/patient_data_raw/R/2024_Sibu Hospital A4D Tracker_patient_raw.parquet"
    python_file = base_dir / "output/patient_data_raw/Python/2024_Sibu Hospital A4D Tracker_patient_raw.parquet"

    if not r_file.exists():
        print(f"❌ R file not found: {r_file}")
        sys.exit(1)

    if not python_file.exists():
        print(f"❌ Python file not found: {python_file}")
        sys.exit(1)

    success = compare_parquets(r_file, python_file)
    sys.exit(0 if success else 1)
