"""Guard the *meaning* of a category, not just that every code has one.

Ticket 66's tests prove ``FINDING_CATEGORY`` is exhaustive over ``ErrorCode``.
That is not what went wrong: ``missing_value`` was the largest code on the run
(27,038 findings) and was categorised ``data_lost`` while both its emit sites
fired on a *successful* recovery. Exhaustiveness cannot catch that, because the
entry was present -- it was just wrong.

What made it wrong was reuse: a code acquires a second emit site whose outcome
differs from the first, and the category silently stops describing half of its
population. So the check here pins the code-to-emitter map. Adding an emit site
to an existing code fails this test, and the fix is to look at what the new site
does with the value before deciding it shares the old site's category.

The map is derived from the source with :mod:`ast`, never hand-listed; only the
expectation is written down.
"""

import ast
from pathlib import Path

import pytest

from a4d.findings import FINDING_CATEGORY, ErrorCode

SRC = Path(__file__).resolve().parent.parent / "src" / "a4d"

# code -> the functions allowed to emit it. Changing this is the moment to
# re-read the new site and confirm the category still describes what it does.
EXPECTED_EMITTERS: dict[ErrorCode, set[str]] = {
    "blank_header_with_data": {"extract_patient_data"},
    "tracker_layout_changed": {"read_all_patient_sheets"},
    "duplicate_source_columns": {"rename_columns"},
    "unrecognised_column": {"harmonize_input_data_columns", "rename_columns"},
    "sheet_skipped": {
        "extract_patient_data",
        "read_all_patient_sheets",
        "read_annual_sheet",
        "read_patient_list_sheet",
    },
    "month_sheet_missing": {"audit_workbook_sheets"},
    "month_sheets_end_early": {"audit_workbook_sheets"},
    "static_sheet_missing": {"audit_workbook_sheets"},
    "static_sheet_duplicate_id": {"join_static_sheet"},
    "empty_product_data": {"read_all_product_sheets"},
    "product_section_not_found": {"read_all_product_sheets"},
    "excel_error_patient_id": {"read_all_patient_sheets"},
    "missing_required_field": {"read_all_patient_sheets"},
    "patient_id_unrepairable": {"fix_patient_id"},
    "source_formula_error": {"normalize_excel_formula_errors"},
    "glucose_unit_swapped": {"_swap_column_to_mmol"},
    "glucose_unit_suspect": {"resolve_glucose_units"},
    "balance_reconciliation": {"_compute_running_balance"},
    "negative_stock_balance": {"_validate_negative_balances"},
    "released_units_without_recipient": {"_count_orphan_released_units"},
    "released_units_to_unknown_patient": {"link_product_patient"},
    "product_not_in_catalogue": {"_report_unknown_products"},
    "entry_date_outside_sheet_month": {"check_entry_dates"},
    "entry_date_outside_tracker_year": {"_validate_entry_dates"},
    "age_negative_from_dob": {"_fix_age_from_dob"},
    "diagnosis_age_negative_from_dob": {"_fix_t1d_diagnosis_age"},
    "typo_rescued": {"parse_date_column"},
    "buddhist_era_converted": {"_convert_buddhist_era_dates", "_validate_entry_dates"},
    "age_derived_from_dob": {"_fix_age_from_dob"},
    "age_corrected_from_dob": {"_fix_age_from_dob"},
    "patient_id_recovered": {"fix_patient_id"},
    "testing_frequency_averaged": {"convert_testing_frequency"},
    "type_conversion": {"_clean_units_received", "parse_date_column", "safe_convert_column"},
    "implausible_era_date": {"_validate_entry_dates"},
    "date_beyond_tracker_year": {"_validate_dates"},
    "value_out_of_range": {
        "check_out_of_range",
        "check_row_count_delta",
        "check_value_shifts",
        "cut_numeric_value",
    },
    "value_not_in_allowed_list": {"fix_sex", "validate_allowed_values"},
    "blood_pressure_unparseable": {"split_blood_pressure"},
    "source_row_not_in_output": {
        "check_missing_groups",
        "check_missing_patients",
        "check_unexpected_nulls",
    },
}


# Codes reached only through the ``(message, code)`` list that
# ``_report_date_recoveries`` (clean/converters.py) loops over, so no call site
# names them literally and the map above cannot see them.
INDIRECT_CODES: dict[str, str] = {
    "date_recovered_from_text": "parse_date_column",
    "date_multiple_in_cell": "parse_date_column",
    "date_year_inferred": "parse_date_column",
}

# The two functions allowed to take ``error_code`` as a parameter rather than
# naming it: the reporting primitive itself, and the validation tool's wrapper.
INDIRECT_EMIT_SITES = ["clean/converters.py", "validate/common.py"]


def _emitters() -> dict[str, set[str]]:
    """Every ``report_finding`` call in ``src/a4d``, as code -> function names.

    Reads the literal ``error_code=`` and ``function_name=`` keywords. A call
    passing either as a variable is invisible here, which is why
    :func:`test_no_emit_site_hides_its_code` exists.
    """
    found: dict[str, set[str]] = {}
    for path in SRC.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            kwargs = {k.arg: k.value for k in node.keywords if k.arg}
            code, function = kwargs.get("error_code"), kwargs.get("function_name")
            if not isinstance(code, ast.Constant) or not isinstance(function, ast.Constant):
                continue
            found.setdefault(str(code.value), set()).add(str(function.value))
    return found


class TestCodeToEmitterMap:
    def test_no_code_gained_an_emit_site_without_its_category_being_rechecked(self):
        """The failure this file exists for: a second site with a different
        outcome from the first, inheriting a category that no longer fits."""
        actual = _emitters()
        drifted = {
            code: sorted(sites)
            for code, sites in actual.items()
            if sites != EXPECTED_EMITTERS.get(code, set())
        }
        assert drifted == {}, (
            "these codes are emitted from functions the taxonomy does not expect. "
            "Read each new site and confirm FINDING_CATEGORY still describes what "
            f"it does with the value, then update EXPECTED_EMITTERS: {drifted}"
        )

    def test_no_expected_emitter_names_a_code_that_no_longer_exists(self):
        stale = sorted(set(EXPECTED_EMITTERS) - set(FINDING_CATEGORY))
        assert stale == [], f"expectations for codes that were removed: {stale}"

    @pytest.mark.parametrize("code", sorted(FINDING_CATEGORY))
    def test_every_code_in_the_taxonomy_is_actually_emitted(self, code):
        """A code nothing emits is dead weight in the operator's glossary."""
        assert code in _emitters() or code in INDIRECT_CODES, (
            f"{code} is in FINDING_CATEGORY but no call site emits it"
        )


class TestNoHiddenCodes:
    def test_no_emit_site_hides_its_code(self):
        """``error_code=some_variable`` would slip past the map above. Two such
        sites exist by design -- the date-recovery loop and the validation
        wrapper both carry the code in a variable -- and nothing else may."""
        indirect = []
        for path in SRC.rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text())):
                if not isinstance(node, ast.Call):
                    continue
                if getattr(node.func, "id", getattr(node.func, "attr", "")) != "report_finding":
                    continue
                code = next((k.value for k in node.keywords if k.arg == "error_code"), None)
                if code is not None and not isinstance(code, ast.Constant):
                    indirect.append(str(path.relative_to(SRC)))
        assert sorted(indirect) == sorted(INDIRECT_EMIT_SITES), (
            f"report_finding called with a non-literal error_code in: {indirect}"
        )
