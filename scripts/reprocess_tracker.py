#!/usr/bin/env python3
"""Quick script to re-process a single tracker."""

from pathlib import Path

from a4d.pipeline.tracker import process_tracker_patient

tracker_file = Path(
    "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Cambodia/CDA/2025_06_CDA A4D Tracker.xlsx"  # noqa: E501
)
output_root = Path("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python")

result = process_tracker_patient(tracker_file, output_root)
print(f"Success: {result.success}")
print(f"Cleaned output: {result.cleaned_output}")
print(f"Cleaning errors: {result.cleaning_errors}")
