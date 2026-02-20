#!/usr/bin/env python3
"""Extended end-to-end tests on older tracker files (2018-2021)."""

# Disable logging for clean output
import logging
import sys
from pathlib import Path

from a4d.clean.patient import clean_patient_data
from a4d.errors import ErrorCollector
from a4d.extract.patient import read_all_patient_sheets

logging.disable(logging.CRITICAL)

test_files = [
    (
        "2021_Siriraj_Thailand",
        Path(
            "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Thailand/SRJ/2021_Siriraj Hospital A4D Tracker.xlsx"  # noqa: E501
        ),
    ),
    (
        "2021_UdonThani_Thailand",
        Path(
            "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Thailand/UTH/2021_Udon Thani Hospital A4D Tracker.xlsx"  # noqa: E501
        ),
    ),
    (
        "2020_VNC_Vietnam",
        Path(
            "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Vietnam/VNC/2020_Vietnam National Children's Hospital A4D Tracker.xlsx"  # noqa: E501
        ),
    ),
    (
        "2019_Penang_Malaysia",
        Path(
            "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Malaysia/PNG/2019_Penang General Hospital A4D Tracker_DC.xlsx"  # noqa: E501
        ),
    ),
    (
        "2019_Mandalay_Myanmar",
        Path(
            "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Myanmar/MCH/2019_Mandalay Children's Hospital A4D Tracker.xlsx"  # noqa: E501
        ),
    ),
    (
        "2018_Yangon_Myanmar",
        Path(
            "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Myanmar/YCH/2018_Yangon Children's Hospital A4D Tracker.xlsx"  # noqa: E501
        ),
    ),
]

print("=" * 100)
print("EXTENDED END-TO-END TESTING: Older Trackers (2018-2021)")
print("=" * 100)

results = []

for name, tracker_path in test_files:
    print(f"\n📁 {name}")
    print("-" * 100)

    if not tracker_path.exists():
        print(f"  ❌ File not found: {tracker_path}")
        results.append((name, "MISSING", {}))
        continue

    try:
        # Extract
        df_raw = read_all_patient_sheets(tracker_path)

        # Get metadata
        year = (
            df_raw["tracker_year"][0]
            if len(df_raw) > 0 and "tracker_year" in df_raw.columns
            else "N/A"
        )
        months = (
            df_raw["tracker_month"].unique().sort().to_list()
            if "tracker_month" in df_raw.columns
            else []
        )

        print(
            f"  ✅ EXTRACTION: {len(df_raw)} rows, "
            f"{len(df_raw.columns)} cols, year={year}, months={months}"
        )

        # Clean
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # Validate schema
        if len(df_clean.columns) != 83:
            print(f"  ⚠️  Schema: Expected 83 columns, got {len(df_clean.columns)}")

        # Check key columns
        stats = {
            "insulin_type": df_clean["insulin_type"].is_not_null().sum()
            if "insulin_type" in df_clean.columns
            else 0,
            "insulin_total_units": df_clean["insulin_total_units"].is_not_null().sum()
            if "insulin_total_units" in df_clean.columns
            else 0,
        }

        print(
            f"  ✅ CLEANING: {len(df_clean)} rows, "
            f"{len(df_clean.columns)} cols, {len(collector)} errors"
        )
        print(
            f"     Key columns: insulin_type={stats['insulin_type']}/{len(df_clean)}, "
            + f"insulin_total={stats['insulin_total_units']}/{len(df_clean)}"
        )

        results.append((name, "PASS", stats))

    except Exception as e:
        print(f"  ❌ ERROR: {type(e).__name__}: {str(e)[:150]}")
        results.append((name, "FAIL", {"error": str(e)[:100]}))

# Summary
print("\n" + "=" * 100)
print("SUMMARY")
print("=" * 100)

passed = sum(1 for _, status, _ in results if status == "PASS")
failed = sum(1 for _, status, _ in results if status == "FAIL")
missing = sum(1 for _, status, _ in results if status == "MISSING")

print(f"\nTotal: {len(results)} trackers")
print(f"  ✅ Passed: {passed}")
print(f"  ❌ Failed: {failed}")
print(f"  ⚠️  Missing: {missing}")

if passed == len(results):
    print("\n✨ All older trackers processed successfully!")
    sys.exit(0)
else:
    print("\n⚠️  Some trackers failed - review output above")
    sys.exit(1)
