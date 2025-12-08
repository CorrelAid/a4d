#!/usr/bin/env python3
"""Test cleaning pipeline on Sibu Hospital 2024 tracker."""

from pathlib import Path
import polars as pl

from a4d.clean.patient import clean_patient_data
from a4d.errors import ErrorCollector


def test_cleaning():
    """Test cleaning on real tracker data."""

    # Read the raw parquet we generated in Phase 2
    raw_path = Path(
        "output/patient_data_raw/Python/2024_Sibu Hospital A4D Tracker_patient_raw.parquet"
    )

    if not raw_path.exists():
        print(f"❌ Raw parquet not found: {raw_path}")
        print("Please run patient extraction first")
        return

    print("=" * 80)
    print("CLEANING TEST - Sibu Hospital 2024")
    print("=" * 80)

    # Read raw data
    df_raw = pl.read_parquet(raw_path)
    print(f"\n📥 Raw data loaded:")
    print(f"   Rows: {len(df_raw)}")
    print(f"   Columns: {len(df_raw.columns)}")
    print(f"   Columns: {df_raw.columns[:10]}...")

    # Create error collector
    collector = ErrorCollector()

    # Clean data
    print(f"\n🧹 Cleaning data...")
    df_clean = clean_patient_data(df_raw, collector)

    print(f"\n📤 Cleaned data:")
    print(f"   Rows: {len(df_clean)}")
    print(f"   Columns: {len(df_clean.columns)}")

    # Show schema
    print(f"\n📋 Schema (first 20 columns):")
    for i, (col, dtype) in enumerate(df_clean.schema.items()):
        if i < 20:
            null_count = df_clean[col].null_count()
            print(f"   {col:50s} {str(dtype):15s} ({null_count:2d} nulls)")
    print(f"   ... and {len(df_clean.columns) - 20} more columns")

    # Show errors
    print(f"\n⚠️  Errors collected: {len(collector)}")
    if len(collector) > 0:
        errors_df = collector.to_dataframe()
        print(f"\n   Error breakdown by column:")
        error_counts = errors_df.group_by("column").count().sort("count", descending=True)
        for row in error_counts.iter_rows(named=True):
            print(f"      {row['column']:40s}: {row['count']:3d} errors")

        print(f"\n   First 5 errors:")
        print(errors_df.head(5))

    # Write output
    output_dir = Path("output/patient_data_clean/Python")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "2024_Sibu Hospital A4D Tracker_patient_clean.parquet"

    df_clean.write_parquet(output_path)
    print(f"\n✅ Cleaned data written to: {output_path}")

    # Sample data check
    print(f"\n🔍 Sample row (first non-null patient):")
    sample = df_clean.filter(pl.col("patient_id").is_not_null()).head(1)
    for col in sample.columns[:15]:
        print(f"   {col:40s}: {sample[col][0]}")

    print("\n" + "=" * 80)
    print("✅ CLEANING TEST COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    test_cleaning()
