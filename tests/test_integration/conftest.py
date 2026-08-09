"""Shared fixtures for integration tests."""

from pathlib import Path

import pytest

# Base path to tracker files
TRACKER_BASE = Path("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload")


@pytest.fixture
def tracker_2024_penang():
    """2024 Penang tracker - has Annual + Patient List sheets."""
    return TRACKER_BASE / "Malaysia/PNG/2024_Penang General Hospital A4D Tracker.xlsx"


@pytest.fixture
def tracker_2023_sibu():
    """2023 Sibu tracker - has duplicate column mapping edge case."""
    return TRACKER_BASE / "Malaysia/SBU/2023_Sibu Hospital A4D Tracker.xlsx"


@pytest.fixture
def tracker_2022_penang():
    """2022 Penang tracker - legacy format without Annual sheet."""
    return TRACKER_BASE / "Malaysia/PNG/2022_Penang General Hospital A4D Tracker.xlsx"


@pytest.fixture
def tracker_2024_isdfi():
    """2024 ISDFI Philippines tracker."""
    return TRACKER_BASE / "Philippines/ISD/2024_ISDFI A4D Tracker.xlsx"


@pytest.fixture
def tracker_2020_mandalay():
    """2020 Mandalay Children's tracker - triggers wide-format column expansion."""
    return TRACKER_BASE / "Myanmar/MCH/2020_Mandalay Children's Hospital A4D Tracker.xlsx"


@pytest.fixture
def tracker_2018_mandalay():
    """2018 Mandalay Children's tracker - triggers comma-separated cell splitting."""
    return TRACKER_BASE / "Myanmar/MCH/2018_Mandalay Children's Hospital A4D Tracker.xlsx"


# Expected values for validation
EXPECTED_SCHEMA_COLS = 83  # After cleaning (patient)
EXPECTED_SCHEMA_COLS_PRODUCT = 20  # After cleaning (product)


def skip_if_missing(tracker_path: Path):
    """Skip test if tracker file is not available."""
    if not tracker_path.exists():
        pytest.skip(f"Tracker file not found: {tracker_path}")
