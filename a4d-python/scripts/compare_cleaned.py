#!/usr/bin/env python3
"""Compare cleaned output from R vs Python pipelines."""

from pathlib import Path
import polars as pl


def compare_cleaned_outputs():
    """Compare R and Python cleaned patient data."""

    # Check if R cleaned output exists
    # (You'll need to run R pipeline's script2 to generate this)
    r_clean_path = Path("output/patient_data_clean/R/2024_Sibu Hospital A4D Tracker_patient_clean.parquet")
    py_clean_path = Path("output/patient_data_clean/Python/2024_Sibu Hospital A4D Tracker_patient_clean.parquet")

    if not py_clean_path.exists():
        print(f"❌ Python cleaned parquet not found: {py_clean_path}")
        print("   Run: uv run python scripts/test_cleaning.py")
        return

    if not r_clean_path.exists():
        print(f"⚠️  R cleaned parquet not found: {r_clean_path}")
        print("   You need to run the R pipeline's script2 (clean_data) first")
        print("   This will process the raw parquet and output cleaned data")
        return

    print("=" * 80)
    print("CLEANED DATA COMPARISON - R vs Python")
    print("=" * 80)

    # Read both files
    df_r = pl.read_parquet(r_clean_path)
    df_py = pl.read_parquet(py_clean_path)

    print(f"\n📊 Dimensions:")
    print(f"   R:      {df_r.shape[0]:3d} rows × {df_r.shape[1]:3d} columns")
    print(f"   Python: {df_py.shape[0]:3d} rows × {df_py.shape[1]:3d} columns")

    # Compare columns
    r_cols = set(df_r.columns)
    py_cols = set(df_py.columns)

    common = r_cols & py_cols
    only_r = r_cols - py_cols
    only_py = py_cols - r_cols

    print(f"\n📋 Columns:")
    print(f"   Common:        {len(common)}")
    print(f"   Only in R:     {len(only_r)}")
    print(f"   Only in Python: {len(only_py)}")

    if only_r:
        print(f"\n   Columns only in R:")
        for col in sorted(only_r):
            print(f"      - {col}")

    if only_py:
        print(f"\n   Columns only in Python:")
        for col in sorted(only_py):
            print(f"      - {col}")

    # Compare schemas for common columns
    print(f"\n🔍 Schema differences (common columns):")
    schema_diffs = []
    for col in sorted(common):
        r_type = str(df_r[col].dtype)
        py_type = str(df_py[col].dtype)
        if r_type != py_type:
            schema_diffs.append((col, r_type, py_type))

    if schema_diffs:
        print(f"   Found {len(schema_diffs)} type differences:")
        for col, r_type, py_type in schema_diffs[:20]:
            print(f"      {col:40s}: R={r_type:15s} vs Python={py_type}")
        if len(schema_diffs) > 20:
            print(f"      ... and {len(schema_diffs) - 20} more")
    else:
        print(f"   ✅ All common columns have matching types!")

    # Compare row ordering
    print(f"\n🔢 Row ordering check:")
    if "patient_id" in common and "tracker_month" in common:
        r_ids = df_r.select(["patient_id", "tracker_month"]).to_dicts()
        py_ids = df_py.select(["patient_id", "tracker_month"]).to_dicts()

        if r_ids == py_ids:
            print(f"   ✅ Row ordering matches perfectly!")
        else:
            print(f"   ⚠️  Row ordering differs")
            print(f"      First 5 R:      {r_ids[:5]}")
            print(f"      First 5 Python: {py_ids[:5]}")

    # Sample data comparison
    print(f"\n📝 Sample data (first patient, first 15 columns):")
    if len(df_r) > 0 and len(df_py) > 0:
        sample_cols = sorted(common)[:15]
        print(f"\n   R:")
        for col in sample_cols:
            print(f"      {col:40s}: {df_r[col][0]}")

        print(f"\n   Python:")
        for col in sample_cols:
            print(f"      {col:40s}: {df_py[col][0]}")

    # Value comparison for common columns
    print(f"\n🔍 Value comparison (common columns):")
    differences = []

    for col in sorted(common):
        # Compare column values
        r_vals = df_r[col].to_list()
        py_vals = df_py[col].to_list()

        if r_vals != py_vals:
            # Count how many rows differ
            diff_count = sum(1 for i in range(len(r_vals)) if r_vals[i] != py_vals[i])
            differences.append((col, diff_count))

    if differences:
        print(f"   Found {len(differences)} columns with value differences:")
        for col, diff_count in sorted(differences, key=lambda x: x[1], reverse=True)[:20]:
            print(f"      {col:40s}: {diff_count:3d}/{len(df_r):3d} rows differ")
        if len(differences) > 20:
            print(f"      ... and {len(differences) - 20} more columns")
    else:
        print(f"   ✅ All column values match perfectly!")

    print("\n" + "=" * 80)


if __name__ == "__main__":
    compare_cleaned_outputs()
