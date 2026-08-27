"""The audit of sheets a workbook holds but the pipeline never opens (ticket 72).

Sheet selection happens before any finding could be raised: ``find_month_sheets``
keeps a name only if it starts with a capitalised month abbreviation, and the
static sheets are matched by exact string. A sheet nobody selected therefore
emitted nothing at all -- these tests pin the audit that closes that gap.
"""

import pytest

from a4d.extract.sheet_audit import (
    STATIC_SHEET_INTRODUCED,
    audit_workbook_sheets,
    unopened_sheets,
)
from a4d.findings import tracker_context


class _StubWorkbook:
    def __init__(self, sheetnames: list[str]):
        self.sheetnames = sheetnames


def _codes(collector) -> list[str]:
    return [f.error_code for f in collector.findings]


def _messages(collector) -> str:
    return " | ".join(f.message for f in collector.findings)


class TestUnopenedSheets:
    """Every sheet no code path opens, whatever its name looks like."""

    def test_lists_sheets_neither_matcher_selects(self):
        wb = _StubWorkbook(["Jan24", "Patient List", "Annual", "Lookup List", "INV"])
        assert unopened_sheets(wb) == ["Lookup List", "INV"]

    def test_a_month_sheet_in_the_wrong_case_counts_as_unopened(self):
        """``find_month_sheets`` is case-sensitive, so ``JAN24`` is never read."""
        wb = _StubWorkbook(["JAN24", "Feb24"])
        assert unopened_sheets(wb) == ["JAN24"]

    def test_an_annual_variant_counts_as_unopened(self):
        """The real VNC 2026 case: the exact-string test misses ``Annual_2025``."""
        wb = _StubWorkbook(["Jan26", "Patient List", "Annual_2026", "Annual_2025"])
        assert unopened_sheets(wb) == ["Annual_2026", "Annual_2025"]

    def test_workbook_the_pipeline_fully_reads_has_nothing_unopened(self):
        wb = _StubWorkbook(["Jan24", "Feb24", "Patient List", "Annual"])
        assert unopened_sheets(wb) == []


class TestMissingMonthSheets:
    """A month absent from inside the tracker's own range."""

    def test_gap_inside_the_range_is_reported(self, tmp_path):
        """The 2017 Mahosot case: Feb17, then Apr17, no Mar17 under any name."""
        wb = _StubWorkbook(["Jan17", "Feb17", "Apr17", "May17"])
        with tracker_context("2017_Mahosot", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2017, is_year_complete=True)
        assert "month_sheet_missing" in _codes(collector)
        assert "Mar" in _messages(collector)

    def test_a_clinic_joining_mid_year_is_not_a_gap(self, tmp_path):
        """31 of 255 trackers start after January; none of them is a defect."""
        wb = _StubWorkbook(["Jul21", "Aug21", "Sep21", "Oct21", "Nov21", "Dec21"])
        with tracker_context("2021_Putrajaya", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2021, is_year_complete=True)
        assert "month_sheet_missing" not in _codes(collector)

    def test_a_completed_year_stopping_early_is_reported(self, tmp_path):
        """2022 Udon Thani stops at Aug22; the year itself is long over."""
        wb = _StubWorkbook([f"{m}22" for m in ("Jan", "Feb", "Mar", "Apr")])
        with tracker_context("2022_Udon_Thani", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2022, is_year_complete=True)
        assert "month_sheets_end_early" in _codes(collector)
        assert "Apr" in _messages(collector)

    def test_an_in_progress_year_stopping_early_is_not_reported(self, tmp_path):
        """Every 2026 tracker stops mid-year because the year has not happened."""
        wb = _StubWorkbook([f"{m}26" for m in ("Jan", "Feb", "Mar", "Apr", "May", "Jun")])
        with tracker_context("2026_VNC", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2026, is_year_complete=False)
        assert "month_sheets_end_early" not in _codes(collector)


class TestMissingStaticSheets:
    """A static sheet absent although the tracker's year is past its introduction."""

    def test_missing_annual_is_reported_after_its_introduction_year(self, tmp_path):
        wb = _StubWorkbook(["Jan24", "Patient List"])
        with tracker_context("2024_Clinic", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2024, is_year_complete=True)
        assert "static_sheet_missing" in _codes(collector)
        assert "Annual" in _messages(collector)

    def test_missing_annual_is_not_reported_before_its_introduction_year(self, tmp_path):
        """No tracker before 2024 has an Annual sheet; absence is the norm."""
        wb = _StubWorkbook(["Jan23", "Patient List"])
        with tracker_context("2023_Clinic", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2023, is_year_complete=True)
        assert "static_sheet_missing" not in _codes(collector)

    def test_missing_patient_list_is_reported_from_2022(self, tmp_path):
        wb = _StubWorkbook(["Jan22"])
        with tracker_context("2022_Clinic", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2022, is_year_complete=True)
        assert "static_sheet_missing" in _codes(collector)
        assert "Patient List" in _messages(collector)

    def test_a_near_miss_spelling_is_named_in_the_message(self, tmp_path):
        """The VNC 2026 case, and the whole point of the check.

        The workbook holds ``Annual_2025`` and ``Annual_2026`` but no sheet
        named exactly ``Annual``, so the pipeline reads no annual data at all.
        Naming the candidates is what turns the finding into an instruction.
        """
        wb = _StubWorkbook(["Jan26", "Patient List", "Annual_2026", "Annual_2025"])
        with tracker_context("2026_VNC", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2026, is_year_complete=False)
        message = _messages(collector)
        assert "static_sheet_missing" in _codes(collector)
        assert "Annual_2026" in message
        assert "Annual_2025" in message

    def test_a_complete_recent_tracker_reports_nothing(self, tmp_path):
        wb = _StubWorkbook(
            [
                f"{m}25"
                for m in (
                    "Jan",
                    "Feb",
                    "Mar",
                    "Apr",
                    "May",
                    "Jun",
                    "Jul",
                    "Aug",
                    "Sep",
                    "Oct",
                    "Nov",
                    "Dec",
                )
            ]
            + ["Patient List", "Annual"]
        )
        with tracker_context("2025_Clinic", "patient", tmp_path) as collector:
            audit_workbook_sheets(wb, 2025, is_year_complete=True)
        assert _codes(collector) == []


class TestIntroductionYears:
    """The introduction years are derived from the corpus, so they are pinned."""

    @pytest.mark.parametrize(("sheet", "year"), [("Patient List", 2022), ("Annual", 2024)])
    def test_measured_introduction_years(self, sheet, year):
        assert STATIC_SHEET_INTRODUCED[sheet] == year
