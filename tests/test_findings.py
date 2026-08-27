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
    FINDING_SCOPE,
    SCOPES_INSIDE_A_SHEET,
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
        "sheet_name": "Jan24",
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
            _report(error_code="value_out_of_range")
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
            _report(error_code="tracker_layout_changed", sheet_name="")
        finding = collector.findings[0]
        assert (finding.tracker_year, finding.tracker_month) == (2024, 10)

    def test_the_sheet_the_finding_names_decides_its_month(self, tmp_path):
        """A sheet called "Jan24" states its own month, and it beats the
        tracker-wide one: the context's month is a whole-workbook default,
        while the sheet is where the finding actually is."""
        with tracker_context(
            "2024_Penang", "patient", tmp_path, tracker_year=2024, tracker_month=10
        ) as collector:
            _report(sheet_name="Jan24")
        assert collector.findings[0].tracker_month == 1

    def test_a_static_sheet_names_no_month(self, tmp_path):
        """A Patient List sheet covers the whole year, so inventing a month
        for it would be worse than leaving it blank."""
        with tracker_context("2024_Penang", "patient", tmp_path, tracker_year=2024) as collector:
            _report(error_code="sheet_skipped", sheet_name="Patient List")
        assert collector.findings[0].tracker_month is None

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
                _report(error_code="value_out_of_range")
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
                _report(error_code="value_out_of_range")
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
            sheet_name="Jan24",
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
            ("unrecognised_column", "fix_workbook"),
            ("sheet_skipped", "fix_workbook"),
            ("blank_header_with_data", "fix_workbook"),
            ("buddhist_era_converted", "recovered"),
            ("typo_rescued", "recovered"),
            ("type_conversion", "data_lost"),
            ("value_out_of_range", "data_lost"),
        ],
    )
    def test_the_three_way_split_lands_where_agreed(self, error_code, expected):
        assert FINDING_CATEGORY[error_code] == expected

    def test_category_is_readable_off_the_finding(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report(error_code="unrecognised_column")
        assert collector.findings[0].category == "fix_workbook"


class TestScope:
    """Scope says what one row of the findings table counts.

    Two findings side by side used to be able to mean "one cell" and "one
    distinct value across thousands of cells", with nothing in the table
    saying which -- so the Summary sheet's ranking silently weighted a
    per-row emitter above a per-value one. Scope is derived from the error
    code exactly as category is, for the same reason: one code cannot be
    counted two ways in two modules.
    """

    def test_every_error_code_has_a_scope(self):
        unmapped = sorted(set(get_args(ErrorCode)) - set(FINDING_SCOPE))
        assert unmapped == [], f"error codes with no scope: {unmapped}"

    def test_no_scope_entry_names_an_unknown_code(self):
        stale = sorted(set(FINDING_SCOPE) - set(get_args(ErrorCode)))
        assert stale == [], f"scope entries for codes that no longer exist: {stale}"

    @pytest.mark.parametrize(
        ("error_code", "expected"),
        [
            # The workbook as a whole: there is no sheet to name, because the
            # finding is precisely that a sheet is absent or that no sheet had
            # what was looked for.
            ("empty_product_data", "tracker"),
            ("month_sheet_missing", "tracker"),
            # One sheet, named.
            ("product_section_not_found", "sheet"),
            ("released_units_without_recipient", "sheet"),
            # One column of one sheet.
            ("blank_header_with_data", "sheet_column"),
            ("unrecognised_column", "sheet_column"),
            # One column across every sheet of the tracker, so no one sheet.
            ("tracker_layout_changed", "tracker_column"),
            ("glucose_unit_swapped", "tracker_column"),
            # One patient, deduplicated across the months they appear in.
            ("diagnosis_age_negative_from_dob", "patient"),
            # One distinct offending value, deduplicated across the rows
            # carrying it -- 1,170 province findings against 26,124 rows --
            # by the tracker for one code and by the sheet for the other.
            ("value_not_in_allowed_list", "tracker_value"),
            ("product_not_in_catalogue", "sheet_value"),
            # One source row.
            ("type_conversion", "row"),
            ("source_formula_error", "row"),
        ],
    )
    def test_the_taxonomy_lands_where_measured(self, error_code, expected):
        assert FINDING_SCOPE[error_code] == expected

    def test_scope_is_readable_off_the_finding(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report(error_code="type_conversion", sheet_name="Jan24")
        assert collector.findings[0].scope == "row"

    def test_dataframe_carries_the_derived_scope(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report(error_code="empty_product_data", sheet_name="")
        assert collector.to_dataframe()["scope"].to_list() == ["tracker"]

    def test_scopes_inside_a_sheet_are_exactly_the_ones_that_name_one(self):
        """The point of the field: blankness becomes checkable.

        An empty ``sheet_name`` used to mean either "this finding is about the
        whole workbook" or "this finding is about a sheet and we lost which
        one". Splitting the scopes into those that sit inside a sheet and
        those that do not is what tells the two apart.
        """
        assert SCOPES_INSIDE_A_SHEET == {"sheet", "sheet_column", "sheet_value", "row"}


class TestSheetNameMatchesScope:
    """The guard, not just the fix.

    Filling the field once is worth nothing if the next emitter added leaves
    it empty again and nothing says so. ``file_name`` already refuses a
    finding nobody can trace to a workbook; this is the same rule one level
    down, and it is what stops the gap this taxonomy exists to close from
    reopening silently.
    """

    def test_a_finding_inside_a_sheet_must_name_it(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path):
            with pytest.raises(ValueError, match="sheet_name"):
                _report(error_code="type_conversion", sheet_name="")

    def test_a_finding_about_the_whole_workbook_must_not_name_a_sheet(self, tmp_path):
        """A sheet on a tracker-scoped finding is a claim the scope denies."""
        with tracker_context("2024_Penang", "product", tmp_path):
            with pytest.raises(ValueError, match="sheet_name"):
                _report(error_code="empty_product_data", sheet_name="Jan24")

    def test_the_matching_case_passes(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report(error_code="type_conversion", sheet_name="Jan24")
            _report(error_code="tracker_layout_changed", sheet_name="")
        assert [f.sheet_name for f in collector.findings] == ["Jan24", ""]


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
            _report(error_code="value_out_of_range")
        assert collector.summary() == {"type_conversion": 2, "value_out_of_range": 1}

    def test_empty_collector_is_falsy(self):
        assert not FindingCollector()

    def test_dataframe_carries_the_derived_category(self, tmp_path):
        with tracker_context("2024_Penang", "patient", tmp_path) as collector:
            _report(error_code="unrecognised_column")
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
