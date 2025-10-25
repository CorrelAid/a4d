#!/usr/bin/env python3
"""Export a single tracker for comparison with R pipeline output.

Usage:
    uv run python scripts/export_single_tracker.py <tracker_file> <output_dir>

Example:
    uv run python scripts/export_single_tracker.py \
        "/Volumes/USB SanDisk 3.2Gen1 Media/A4D/data/a4dphase2_upload/Malaysia/SBU/2024_Sibu Hospital A4D Tracker.xlsx" \
        output/patient_data_raw
"""

import sys
from pathlib import Path

from loguru import logger

from a4d.extract.patient import export_patient_raw, read_all_patient_sheets


def main():
    """Extract and export a single tracker."""
    if len(sys.argv) != 3:
        print(__doc__)
        sys.exit(1)

    tracker_file = Path(sys.argv[1])
    output_dir = Path(sys.argv[2])

    if not tracker_file.exists():
        logger.error(f"Tracker file not found: {tracker_file}")
        sys.exit(1)

    logger.info(f"Extracting patient data from: {tracker_file}")
    logger.info(f"Output directory: {output_dir}")

    # Extract patient data
    df = read_all_patient_sheets(tracker_file)
    logger.info(f"Extracted {len(df)} rows from {tracker_file.name}")

    # Export to parquet
    output_path = export_patient_raw(df, tracker_file, output_dir)
    logger.success(f"✓ Successfully exported to: {output_path}")

    # Summary
    unique_months = df["tracker_month"].unique().to_list()
    logger.info(f"Summary: {len(df)} patients across {len(unique_months)} months")
    logger.info(f"Clinic ID: {df['clinic_id'][0]}")
    logger.info(f"Tracker year: {df['tracker_year'][0]}")


if __name__ == "__main__":
    main()
