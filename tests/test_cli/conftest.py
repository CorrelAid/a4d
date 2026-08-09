"""Fixtures for CLI tests, including a minimal valid dummy tracker file."""

from pathlib import Path

import openpyxl
import pytest


@pytest.fixture
def dummy_tracker(tmp_path) -> Path:
    """Create a minimal valid A4D Excel tracker file for testing.

    Structure follows the actual tracker format:
    - Sheet "Jan24" (month abbreviation + 2-digit year)
    - Row 1: empty (no header, data_start_row - 2 → header_2 path)
    - Row 2: column headers (data_start_row - 1 → header_1 path)
    - Row 3+: patient data rows (col A = numeric row number)

    The clinic_id is derived from the parent folder name ("TST").
    """
    clinic_dir = tmp_path / "TST"
    clinic_dir.mkdir()
    tracker_path = clinic_dir / "2024_Test_Clinic.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jan24"

    # Row 1: empty title row → header_2 (≤2 non-None values triggers header_1-only path)
    # Row 2: column headers → header_1
    # "Patient ID" in header_1 + empty header_2 → merge_headers uses header_1 only
    ws.cell(2, 2).value = "Patient ID"
    ws.cell(2, 3).value = "Name"
    ws.cell(2, 4).value = "Sex"
    ws.cell(2, 5).value = "Age"

    # Row 3+: data rows — col A must be numeric (find_data_start_row scans for first int/float)
    ws.cell(3, 1).value = 1
    ws.cell(3, 2).value = "PT-001"
    ws.cell(3, 3).value = "Test Patient One"
    ws.cell(3, 4).value = "Female"
    ws.cell(3, 5).value = 25

    ws.cell(4, 1).value = 2
    ws.cell(4, 2).value = "PT-002"
    ws.cell(4, 3).value = "Test Patient Two"
    ws.cell(4, 4).value = "Male"
    ws.cell(4, 5).value = 30

    wb.save(tracker_path)
    return tracker_path


@pytest.fixture
def dummy_tracker_dir(dummy_tracker) -> Path:
    """Return the directory containing the dummy tracker (data root for batch mode)."""
    return dummy_tracker.parent.parent


@pytest.fixture
def dummy_product_tracker(tmp_path) -> Path:
    """Create a minimal valid A4D Excel tracker file with a product section.

    Headers use real synonyms_product.yaml canonical names so the CLI's
    default (non-stub) column mapper resolves them without mocking.
    """
    clinic_dir = tmp_path / "TST"
    clinic_dir.mkdir()
    tracker_path = clinic_dir / "2024_Test_Clinic.xlsx"

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Jan24"

    rows = [
        [None, None, None, None, None],
        ["Product", "Date", "Received From", "Units Received", "Units Released"],
        ["Insulin A", "2024-01-05", "HQ", 100, 5],
        ["Insulin B", "2024-01-10", "HQ", 50, None],
        ["Patient Recruitment", None, None, None, None],
        ["Patient Name", "Patient ID", None, None, None],
    ]
    for row in rows:
        ws.append(row)

    wb.save(tracker_path)
    return tracker_path
