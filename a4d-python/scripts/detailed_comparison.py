#!/usr/bin/env python3
"""Detailed comparison of R vs Python cleaned outputs - for migration validation."""

from pathlib import Path
import polars as pl


def compare_detailed():
    """Detailed comparison showing all differences for debugging."""

    r_clean_path = Path("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/output/patient_data_cleaned/2024_Sibu Hospital A4D Tracker_patient_cleaned.parquet")
    py_clean_path = Path("output/patient_data_clean/Python/2024_Sibu Hospital A4D Tracker_patient_clean.parquet")

    df_r = pl.read_parquet(r_clean_path)
    df_py = pl.read_parquet(py_clean_path)

    print("=" * 100)
    print("DETAILED COMPARISON - R vs Python Cleaned Patient Data")
    print("=" * 100)

    # 1. SCHEMA DIFFERENCES
    print("\n" + "=" * 100)
    print("1. SCHEMA DIFFERENCES")
    print("=" * 100)

    r_cols = set(df_r.columns)
    py_cols = set(df_py.columns)
    common_cols = sorted(r_cols & py_cols)
    only_r = sorted(r_cols - py_cols)
    only_py = sorted(py_cols - r_cols)

    print(f"\n📋 Column comparison:")
    print(f"   Common columns: {len(common_cols)}")
    print(f"   Only in R:      {len(only_r)}")
    print(f"   Only in Python: {len(only_py)}")

    if only_r:
        print(f"\n   ⚠️  Missing in Python (need to add to schema):")
        for col in only_r:
            r_type = df_r[col].dtype
            null_count = df_r[col].is_null().sum()
            print(f"      - {col:50s} ({r_type}, {null_count}/{len(df_r)} nulls)")

    if only_py:
        print(f"\n   ⚠️  Extra in Python (not in R schema):")
        for col in only_py:
            py_type = df_py[col].dtype
            null_count = df_py[col].is_null().sum()
            print(f"      - {col:50s} ({py_type}, {null_count}/{len(df_py)} nulls)")

    # 2. TYPE DIFFERENCES
    print("\n" + "=" * 100)
    print("2. TYPE DIFFERENCES (common columns)")
    print("=" * 100)

    type_diffs = []
    for col in common_cols:
        r_type = str(df_r[col].dtype)
        py_type = str(df_py[col].dtype)
        if r_type != py_type:
            type_diffs.append((col, r_type, py_type))

    if type_diffs:
        print(f"\n   Found {len(type_diffs)} type differences:")
        for col, r_type, py_type in type_diffs:
            print(f"      {col:50s}: R={r_type:15s} vs Python={py_type:15s}")
    else:
        print("   ✅ All types match!")

    # 3. VALUE DIFFERENCES
    print("\n" + "=" * 100)
    print("3. VALUE DIFFERENCES (common columns)")
    print("=" * 100)

    value_diffs = []

    for col in common_cols:
        r_vals = df_r[col].to_list()
        py_vals = df_py[col].to_list()

        if r_vals != py_vals:
            diff_count = sum(1 for i in range(len(r_vals)) if r_vals[i] != py_vals[i])
            value_diffs.append((col, diff_count, r_vals, py_vals))

    if value_diffs:
        print(f"\n   Found {len(value_diffs)} columns with value differences:\n")

        for col, diff_count, r_vals, py_vals in sorted(value_diffs, key=lambda x: x[1], reverse=True):
            print(f"\n   📌 {col} ({diff_count}/{len(df_r)} rows differ)")
            print(f"      R type:      {df_r[col].dtype}")
            print(f"      Python type: {df_py[col].dtype}")

            # Show first 5 differing examples
            diffs_shown = 0
            for i in range(len(r_vals)):
                if r_vals[i] != py_vals[i] and diffs_shown < 5:
                    print(f"      Row {i+1}: R={repr(r_vals[i]):30s} | Python={repr(py_vals[i])}")
                    diffs_shown += 1

            if diff_count > 5:
                print(f"      ... and {diff_count - 5} more differences")
    else:
        print("   ✅ All values match!")

    # 4. SUMMARY
    print("\n" + "=" * 100)
    print("4. SUMMARY - Action Items")
    print("=" * 100)

    total_issues = len(only_r) + len(only_py) + len(type_diffs) + len(value_diffs)

    if total_issues == 0:
        print("\n   ✅ Perfect match! R and Python outputs are identical.")
    else:
        print(f"\n   Total issues to resolve: {total_issues}")
        print(f"      - Missing columns in Python: {len(only_r)}")
        print(f"      - Extra columns in Python:   {len(only_py)}")
        print(f"      - Type mismatches:           {len(type_diffs)}")
        print(f"      - Value differences:         {len(value_diffs)}")

        print("\n   📋 TODO:")
        if only_r:
            print(f"      1. Add {len(only_r)} missing columns to Python schema")
        if only_py:
            print(f"      2. Review {len(only_py)} extra Python columns (remove or keep?)")
        if type_diffs:
            print(f"      3. Fix {len(type_diffs)} type mismatches")
        if value_diffs:
            print(f"      4. Investigate {len(value_diffs)} columns with value differences")

    print("\n" + "=" * 100)


if __name__ == "__main__":
    compare_detailed()
