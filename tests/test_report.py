"""Tests for the findings report workbook.

The workbook is the deliverable A4D staff act on, so these pin the three
properties that make it actionable: the summary ranks by the category that
means "a human must fix this", the glossary covers every code whether or not
this run produced one, and one tracker can be drilled into on its own.
"""

from datetime import datetime

import polars as pl
import pytest
import xlsxwriter
from openpyxl import load_workbook

from a4d.findings import FINDING_GLOSSARY
from a4d.report import (
    _HEADERS,
    build_findings_report,
    glossary_frame,
    load_findings,
    overview_frame,
    summarise_by_tracker,
)


def _findings(rows: list[dict]) -> pl.DataFrame:
    defaults = {
        "file_name": "2024_Clinic_A",
        "arm": "patient",
        "sheet_name": "Jan24",
        "patient_id": "KH_QD001",
        "column": "age",
        "original_value": "abc",
        "message": "could not convert",
        "error_code": "type_conversion",
        "category": "data_lost",
        "stage": "clean",
        "function_name": "safe_convert_column",
        "tracker_year": 2024,
        "tracker_month": 1,
        "timestamp": datetime(2026, 8, 25, 12, 0, 0),
    }
    return pl.DataFrame([{**defaults, **row} for row in rows])


class TestSummary:
    def test_the_tracker_needing_a_human_is_first(self):
        """A staff member opens this to find which workbooks to correct, so a
        tracker with one workbook defect outranks one with a thousand
        recoveries."""
        findings = _findings(
            [
                *[{"file_name": "noisy", "category": "recovered"}] * 50,
                {"file_name": "broken", "category": "fix_workbook"},
            ]
        )

        summary = summarise_by_tracker(findings)

        assert summary["file_name"].to_list() == ["broken", "noisy"]

    def test_a_tracker_counts_each_category_separately(self):
        findings = _findings(
            [
                {"category": "fix_workbook"},
                {"category": "fix_workbook"},
                {"category": "data_lost"},
                {"category": "recovered"},
            ]
        )

        row = summarise_by_tracker(findings).row(0, named=True)

        assert (row["fix_workbook"], row["data_lost"], row["recovered"]) == (2, 1, 1)
        assert row["total"] == 4

    def test_a_tracker_found_by_both_arms_names_both(self):
        """The summary is per workbook, not per workbook-and-arm: a clinic
        correcting a tracker fixes one file."""
        findings = _findings([{"arm": "patient"}, {"arm": "product"}])

        assert summarise_by_tracker(findings).row(0, named=True)["arms"] == "patient, product"

    def test_an_empty_run_still_has_the_summary_columns(self):
        """A clean run must not produce a workbook with a different shape."""
        summary = summarise_by_tracker(_findings([]).clear())

        assert "fix_workbook" in summary.columns
        assert summary.is_empty()


class TestGlossary:
    def test_every_code_appears_even_when_this_run_produced_none(self):
        """Someone looking up a code they saw last month should find it."""
        glossary = glossary_frame(_findings([{"error_code": "type_conversion"}]))

        assert set(glossary["error_code"].to_list()) == set(FINDING_GLOSSARY)

    def test_a_code_that_did_not_fire_reads_zero_rather_than_blank(self):
        glossary = glossary_frame(_findings([{"error_code": "type_conversion"}]))
        counts = dict(zip(glossary["error_code"], glossary["findings_in_this_run"], strict=True))

        assert counts["type_conversion"] == 1
        assert counts["balance_reconciliation"] == 0

    def test_workbook_defects_are_listed_before_recoveries(self):
        categories = glossary_frame(_findings([]).clear())["category"].to_list()

        assert categories.index("fix_workbook") < categories.index("recovered")


class TestWorkbook:
    def test_it_writes_the_three_agreed_sheets(self, tmp_path):
        out = build_findings_report(_findings([{}]), tmp_path / "findings.xlsx")

        assert [sheet.title for sheet in _sheets(out)] == [
            "Overview",
            "Trackers",
            "Findings",
            "Glossary",
        ]

    def test_the_findings_sheet_leads_with_actionability(self, tmp_path):
        """Category first so a reader never scrolls right to learn whether a
        row matters."""
        out = build_findings_report(_findings([{}]), tmp_path / "findings.xlsx")

        assert _header(out, "Findings")[:3] == ["category", "file_name", "sheet_name"]

    def test_drilling_into_one_tracker_excludes_the_others(self, tmp_path):
        findings = _findings([{"file_name": "2024_Wanted"}, {"file_name": "2024_Other"}])

        out = build_findings_report(findings, tmp_path / "one.xlsx", tracker="Wanted")

        assert _column(out, "Findings", "file_name") == ["2024_Wanted"]

    def test_the_glossary_still_covers_every_code_when_drilled_down(self, tmp_path):
        """Filtering to one tracker must not shrink the reference material."""
        findings = _findings([{"file_name": "2024_Wanted"}, {"file_name": "2024_Other"}])

        out = build_findings_report(findings, tmp_path / "one.xlsx", tracker="Wanted")

        assert len(_column(out, "Glossary", "error_code")) == len(FINDING_GLOSSARY)

    def test_an_unknown_tracker_is_an_error_not_an_empty_workbook(self, tmp_path):
        """An empty file looks like a clean tracker; a typo should not."""
        with pytest.raises(ValueError, match="No findings"):
            build_findings_report(_findings([{}]), tmp_path / "none.xlsx", tracker="nonexistent")

    def test_a_missing_findings_table_says_how_to_produce_one(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="a4d run"):
            load_findings(tmp_path / "absent.parquet")


def _sheets(path):
    return load_workbook(path).worksheets


def _header(path, sheet_name: str) -> list[str]:
    """Header row, mapped back to the frame's own column names.

    The sheet shows reader-facing labels; tests assert on the names the code
    uses, so the two cannot drift apart silently.
    """
    sheet = load_workbook(path)[sheet_name]
    back = {label: name for name, label in _HEADERS.items()}
    return [back.get(cell.value, cell.value) for cell in next(sheet.iter_rows(max_row=1))]


def _column(path, sheet_name: str, column: str) -> list:
    sheet = load_workbook(path)[sheet_name]
    rows = list(sheet.iter_rows(values_only=True))
    index = list(rows[0]).index(_HEADERS.get(column, column))
    return [row[index] for row in rows[1:] if row[index] is not None]


def test_xlsxwriter_is_available():
    """The workbook is written with xlsxwriter, added for this report."""
    assert xlsxwriter.__version__


def test_the_trackers_sheet_carries_no_column_the_pipeline_never_fills(tmp_path):
    """`tracker_year` is declared on the findings table but never populated
    (0 of 122,590 on the real run), so shipping it would be a blank column in
    the deliverable."""
    out = build_findings_report(_findings([{}]), tmp_path / "findings.xlsx")

    assert "tracker_year" not in _header(out, "Trackers")


class TestGlossarySpread:
    """A cell count alone cannot say whether a problem is systemic."""

    def test_it_reports_how_many_trackers_a_code_touches(self):
        findings = _findings(
            [
                {"file_name": "a", "error_code": "type_conversion"},
                {"file_name": "a", "error_code": "type_conversion"},
                {"file_name": "b", "error_code": "type_conversion"},
            ]
        )

        row = _glossary_row(glossary_frame(findings), "type_conversion")

        assert row["findings_in_this_run"] == 3
        assert row["trackers_affected"] == 2

    def test_the_share_is_against_the_run_not_the_affected_set(self):
        """Two of four trackers is 50%, not 100%."""
        findings = _findings(
            [
                {"file_name": "a", "error_code": "type_conversion"},
                {"file_name": "b", "error_code": "type_conversion"},
            ]
        )

        row = _glossary_row(glossary_frame(findings, total_trackers=4), "type_conversion")

        assert (row["of_trackers_total"], row["share_of_trackers"]) == (4, "50%")

    def test_the_share_is_floored_so_one_clean_tracker_is_visible(self):
        """254 of 255 must not read as 100%: a share that says "every tracker"
        when one is clean invites the wrong conclusion about how systemic a
        problem is."""
        findings = _findings([{"file_name": f"t{i}"} for i in range(254)])

        row = _glossary_row(glossary_frame(findings, total_trackers=255), "type_conversion")

        assert row["share_of_trackers"] == "99%"

    def test_a_code_that_did_not_fire_reads_zero_trackers(self):
        row = _glossary_row(glossary_frame(_findings([{}])), "balance_reconciliation")

        assert (row["findings_in_this_run"], row["trackers_affected"]) == (0, 0)

    def test_drilling_into_one_tracker_keeps_the_whole_run_spread(self, tmp_path):
        """Filtering the sheets must not make every code read "1 of 1"."""
        findings = _findings(
            [
                {"file_name": "2024_Wanted", "error_code": "type_conversion"},
                {"file_name": "2024_Other", "error_code": "type_conversion"},
            ]
        )

        out = build_findings_report(findings, tmp_path / "one.xlsx", tracker="Wanted")
        codes = _column(out, "Glossary", "error_code")
        affected = _column(out, "Glossary", "trackers_affected")
        totals = _column(out, "Glossary", "of_trackers_total")
        at = codes.index("type_conversion")

        assert (affected[at], totals[at]) == (2, 2)


def _glossary_row(frame, error_code: str) -> dict:
    return frame.filter(pl.col("error_code") == error_code).row(0, named=True)


def _metadata(rows: list[dict]) -> pl.DataFrame:
    defaults = {
        "file_name": "2024_Clinic_A",
        "clinic_code": "CA",
        "md5": "abc",
        "patient_data_raw": True,
        "patient_data_cleaned": True,
        "product_data_raw": True,
        "product_data_cleaned": True,
        "complete": True,
    }
    return pl.DataFrame([{**defaults, **row} for row in rows])


class TestTrackerStatus:
    """The findings say what is wrong with the data; the metadata says whether
    the pipeline got through the file at all. An operator asks both together."""

    def test_a_tracker_with_no_findings_still_appears(self):
        """Absent from a findings-only view, a perfect tracker and one that
        never processed look identical -- both simply missing."""
        summary = summarise_by_tracker(
            _findings([{"file_name": "noisy"}]),
            _metadata([{"file_name": "noisy"}, {"file_name": "silent"}]),
        )

        assert set(summary["file_name"]) == {"noisy", "silent"}
        assert summary.filter(pl.col("file_name") == "silent")["total"].item() == 0

    def test_a_tracker_that_failed_a_stage_is_ranked_first(self):
        """It reports few findings precisely because it produced little."""
        summary = summarise_by_tracker(
            _findings([{"file_name": "noisy", "category": "fix_workbook"}] * 50),
            _metadata(
                [
                    {"file_name": "noisy"},
                    {"file_name": "broken", "product_data_cleaned": False, "complete": False},
                ]
            ),
        )

        assert summary["file_name"].to_list() == ["broken", "noisy"]

    def test_the_failed_stages_are_named_not_left_as_booleans(self):
        summary = summarise_by_tracker(
            _findings([]).clear(),
            _metadata(
                [
                    {
                        "file_name": "broken",
                        "product_data_raw": False,
                        "product_data_cleaned": False,
                        "complete": False,
                    }
                ]
            ),
        )
        row = summary.row(0, named=True)

        assert row["stages_failed"] == "product extract, product clean"
        assert row["product extract"] == "FAILED"
        assert row["patient extract"] == "ok"

    def test_without_metadata_it_falls_back_to_findings_only(self):
        summary = summarise_by_tracker(_findings([{"file_name": "only"}]))

        assert summary["file_name"].to_list() == ["only"]
        assert "stages_failed" not in summary.columns


class TestOverview:
    def test_it_counts_trackers_that_completed_every_stage(self):
        overview = overview_frame(
            _findings([{"file_name": "a"}]),
            _metadata(
                [
                    {"file_name": "a"},
                    {"file_name": "b", "patient_data_cleaned": False, "complete": False},
                ]
            ),
        )
        stats = dict(zip(overview["measure"], overview["value"], strict=True))

        assert stats["Trackers processed"] == 2
        assert stats["Trackers that completed every stage"] == 1
        assert stats["Trackers with a failed stage"] == 1
        assert stats["Failed at patient clean"] == 1

    def test_it_distinguishes_trackers_processed_from_trackers_with_findings(self):
        """Two very different numbers that a findings-only view conflates."""
        overview = overview_frame(
            _findings([{"file_name": "a"}]),
            _metadata([{"file_name": "a"}, {"file_name": "b"}]),
        )
        stats = dict(zip(overview["measure"], overview["value"], strict=True))

        assert stats["Trackers processed"] == 2
        assert stats["Trackers with at least one finding"] == 1

    def test_processing_rows_are_omitted_without_metadata(self):
        overview = overview_frame(_findings([{}]))
        measures = overview["measure"].to_list()

        assert "Trackers processed" not in measures
        assert "Findings total" in measures


def test_a_boolean_column_reads_as_words_not_as_one_and_zero(tmp_path):
    """xlsxwriter takes bool as a number, so "Processed fully?" would read 1."""
    out = build_findings_report(
        _findings([{}]),
        tmp_path / "f.xlsx",
        metadata=_metadata([{"file_name": "2024_Clinic_A", "complete": True}]),
    )

    assert _column(out, "Trackers", "processed_completely") == ["yes"]


def test_the_workbook_orders_sheets_overview_first(tmp_path):
    """The run's shape before its detail."""
    out = build_findings_report(_findings([{}]), tmp_path / "f.xlsx", metadata=_metadata([{}]))

    assert [sheet.title for sheet in _sheets(out)][0] == "Overview"
