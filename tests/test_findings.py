"""Tests for the unified data-quality findings channel.

Every finding the pipeline reports about a source workbook goes through
``report_finding``. These tests pin the three properties that make it a single
channel rather than a second one: a finding cannot be emitted without a place
to put it, the file name it carries is the bare tracker stem so it joins
against every other table, and every error code has a category.
"""

import re
from typing import get_args

import pytest
from loguru import logger

from a4d.findings import (
    FINDING_CATEGORY,
    FINDING_GLOSSARY,
    ErrorCode,
    Finding,
    FindingCollector,
    NoFindingContextError,
    current_findings,
    findings_collected,
    findings_discarded,
    report_finding,
    tracker_context,
)

# These tests drive the context machinery directly, including asserting that
# a finding outside any context raises, so the autouse binding must not apply.
pytestmark = pytest.mark.no_findings_context


def _report(**overrides):
    """Emit one finding with sensible defaults, overriding what a test cares about."""
    kwargs = {
        "patient_id": "XX_QA001",
        "column": "age",
        "original_value": "invalid",
        "message": "Could not convert 'invalid' to Int32",
        "error_code": "type_conversion",
        "function_name": "safe_convert_column",
    }
    kwargs.update(overrides)
    report_finding(**kwargs)


class TestNoSilentDrops:
    """A finding emitted with nowhere to go is a loud failure, never a no-op."""

    def test_report_finding_outside_any_context_raises(self):
        with pytest.raises(NoFindingContextError):
            _report()

    def test_error_names_the_finding_so_the_caller_is_findable(self):
        with pytest.raises(NoFindingContextError, match="type_conversion"):
            _report()

    def test_context_does_not_leak_after_exit(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path):
            _report()
        with pytest.raises(NoFindingContextError):
            _report()

    def test_context_is_torn_down_even_when_the_body_raises(self, tmp_path):
        with pytest.raises(ValueError, match="tracker exploded"):
            with tracker_context("2024_Penang", "patient", tmp_path):
                raise ValueError("tracker exploded")
        assert current_findings() is None


class TestTrackerContext:
    """The per-tracker context binds the collector and the log context together."""

    def test_findings_are_collected(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report()
            _report(error_code="invalid_value")
        assert len(collector) == 2

    def test_file_name_is_the_bare_stem_not_the_arm_suffixed_name(self, tmp_path):
        """The suffixed name is what made findings and logs unjoinable (ticket 66)."""
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report()
        assert collector.findings[0].file_name == "2024_Penang"

    def test_arm_is_its_own_field(self, tmp_path):
        with tracker_context("2024_Penang", "product", tmp_path) as collector:
            _report()
        assert collector.findings[0].arm == "product"

    def test_tracker_year_and_month_ride_on_the_finding(self, tmp_path):
        with tracker_context(
            "2024_Penang", "patient", tmp_path, tracker_year=2024, tracker_month=10
        ) as collector:
            _report()
        finding = collector.findings[0]
        assert (finding.tracker_year, finding.tracker_month) == (2024, 10)

    def test_the_log_file_still_carries_the_arm_so_the_two_arms_do_not_collide(self, tmp_path):
        """One tracker produces a patient and a product log; the files must differ."""
        with tracker_context("2024_Penang", "patient", tmp_path):
            logger.info("processing")
        with tracker_context("2024_Penang", "product", tmp_path):
            logger.info("processing")
        written = sorted(p.name for p in (tmp_path / "logs").glob("*.log"))
        assert written == ["2024_Penang_patient.log", "2024_Penang_product.log"]

    def test_every_finding_also_reaches_the_log_stream(self, tmp_path):
        """One emit point, two consumers -- a finding cannot exist in only one."""
        with tracker_context("2024_Penang", "patient", tmp_path):
            _report(message="a very distinctive message")
        log_text = (tmp_path / "logs" / "2024_Penang_patient.log").read_text()
        assert "a very distinctive message" in log_text
        assert "type_conversion" in log_text

    def test_nested_tracker_contexts_restore_the_outer_collector(self, tmp_path):
        with tracker_context("outer", "patient", tmp_path) as outer:
            _report()
            with tracker_context("inner", "product", tmp_path) as inner:
                _report(error_code="invalid_value")
            assert current_findings() is outer
        assert len(outer) == 1
        assert len(inner) == 1


class TestEscapeHatches:
    """Both non-tracker cases are explicit contexts, so neither is a silent drop."""

    def test_findings_discarded_swallows_findings(self):
        with findings_discarded():
            _report()
        assert current_findings() is None

    def test_findings_discarded_does_not_pollute_an_enclosing_collector(self, tmp_path):
        """The sacrificial-collector case: a re-parse must not reach the real run."""
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report()
            with findings_discarded():
                _report(error_code="invalid_value")
            assert len(collector) == 1

    def test_findings_collected_yields_a_collector_outside_any_tracker(self):
        """The validator case: its own collector, no tracker and no log file."""
        with findings_collected() as collector:
            _report(file_name="2024_Penang")
        assert len(collector) == 1
        assert collector.findings[0].file_name == "2024_Penang"

    def test_findings_collected_requires_an_explicit_file_name(self):
        """Outside a tracker context there is nothing to infer the file name from."""
        with findings_collected():
            with pytest.raises(ValueError, match="file_name"):
                _report()


class TestFileNameIsNeverBlank:
    """The user's rule (2026-08-24): a finding without a file name cannot exist."""

    @pytest.mark.parametrize("blank", ["", "   "])
    def test_blank_file_name_is_rejected(self, blank):
        with pytest.raises(ValueError, match="file_name"):
            Finding(
                file_name=blank,
                arm="patient",
                patient_id="XX_QA001",
                column="age",
                original_value="invalid",
                message="nope",
                error_code="type_conversion",
                stage="clean",
                function_name="f",
            )

    def test_a_real_file_name_is_accepted(self):
        finding = Finding(
            file_name="2024_Penang",
            arm="patient",
            patient_id="XX_QA001",
            column="age",
            original_value="invalid",
            message="nope",
            error_code="type_conversion",
            stage="clean",
            function_name="f",
        )
        assert finding.file_name == "2024_Penang"


class TestCategory:
    """Category is derived from the error code, never stored per call site."""

    def test_every_error_code_has_a_category(self):
        """An unmapped code would publish a null category; fail loudly instead."""
        unmapped = sorted(set(get_args(ErrorCode)) - set(FINDING_CATEGORY))
        assert unmapped == [], f"error codes with no category: {unmapped}"

    def test_no_category_entry_names_an_unknown_code(self):
        stale = sorted(set(FINDING_CATEGORY) - set(get_args(ErrorCode)))
        assert stale == [], f"category entries for codes that no longer exist: {stale}"

    @pytest.mark.parametrize(
        ("error_code", "expected"),
        [
            ("missing_column", "fix_workbook"),
            ("invalid_tracker", "fix_workbook"),
            ("blank_header_with_data", "fix_workbook"),
            ("buddhist_era_converted", "recovered"),
            ("typo_rescued", "recovered"),
            ("type_conversion", "data_lost"),
            ("invalid_value", "data_lost"),
        ],
    )
    def test_the_three_way_split_lands_where_agreed(self, error_code, expected):
        assert FINDING_CATEGORY[error_code] == expected

    def test_category_is_readable_off_the_finding(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report(error_code="missing_column")
        assert collector.findings[0].category == "fix_workbook"


class TestStageNames:
    """Ticket 65, folded in: stage and function_name say Python, never R."""

    def test_stage_default_is_a_stage_name(self):
        assert Finding.model_fields["stage"].default == "clean"

    def test_no_r_script_names_survive_in_the_source(self):
        """script1/script3 named R files; nothing may publish them again."""
        from pathlib import Path

        src = Path(__file__).resolve().parent.parent / "src" / "a4d"
        offenders = [
            f"{path.relative_to(src)}:{n}"
            for path in src.rglob("*.py")
            if "migration" not in path.parts
            for n, line in enumerate(path.read_text().splitlines(), 1)
            if re.search(r'"script[0-9]"', line)
        ]
        assert offenders == [], f"R script names still published: {offenders}"


class TestCollector:
    """The collector stays the in-run accumulator that feeds the CLI summary."""

    def test_summary_counts_by_error_code(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report()
            _report()
            _report(error_code="invalid_value")
        assert collector.summary() == {"type_conversion": 2, "invalid_value": 1}

    def test_empty_collector_is_falsy(self):
        assert not FindingCollector()

    def test_dataframe_carries_the_derived_category(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report(error_code="missing_column")
        df = collector.to_dataframe()
        assert df["category"].to_list() == ["fix_workbook"]


class TestGlossary:
    """The report's glossary sheet is generated from FINDING_GLOSSARY.

    A glossary transcribed by hand drifts from the taxonomy the moment a code
    is added, so these mirror the category tests: a new code cannot ship
    without an explanation, and a deleted one cannot leave a stale entry.
    """

    def test_every_error_code_has_a_glossary_entry(self):
        """A code with no entry would publish a blank glossary row."""
        missing = sorted(set(get_args(ErrorCode)) - set(FINDING_GLOSSARY))
        assert missing == [], f"error codes with no glossary entry: {missing}"

    def test_no_glossary_entry_names_an_unknown_code(self):
        stale = sorted(set(FINDING_GLOSSARY) - set(get_args(ErrorCode)))
        assert stale == [], f"glossary entries for codes that no longer exist: {stale}"

    @pytest.mark.parametrize("error_code", sorted(get_args(ErrorCode)))
    def test_each_entry_says_what_to_do_not_just_what_happened(self, error_code):
        """The reader is whoever opens the workbook, so an entry has to be long
        enough to name an action rather than restate the code as a phrase."""
        text = FINDING_GLOSSARY[error_code]
        assert len(text) > 80, f"{error_code}: glossary entry too short to be actionable"
        assert text[0].isupper(), f"{error_code}: glossary entry does not start a sentence"
        assert text.rstrip().endswith("."), f"{error_code}: glossary entry has no full stop"
