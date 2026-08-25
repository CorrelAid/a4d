"""Tests for schema and validation utilities."""

import polars as pl
import pytest

from a4d.clean.validators import (
    fix_patient_id,
    load_validation_rules,
    validate_all_columns,
    validate_allowed_values,
    validate_column_from_rules,
)
from a4d.config import settings


def test_load_validation_rules():
    """Test loading validation rules from YAML."""
    rules = load_validation_rules()

    # Check that rules were loaded
    assert isinstance(rules, dict)
    assert len(rules) > 0

    # Check a specific column rule (new simplified structure)
    assert "status" in rules
    assert "allowed_values" in rules["status"]
    assert "replace_invalid" in rules["status"]
    assert isinstance(rules["status"]["allowed_values"], list)
    assert len(rules["status"]["allowed_values"]) > 0

    # Check another column
    assert "clinic_visit" in rules
    assert rules["clinic_visit"]["allowed_values"] == ["N", "Y"]
    assert rules["clinic_visit"]["replace_invalid"] is True


def test_validate_allowed_values_all_valid(collector):
    """Test validation when all values are valid."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "status": ["Active", "Inactive", "Active"],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive", "Transferred"],
        replace_invalid=True,
    )

    assert result["status"].to_list() == ["Active", "Inactive", "Active"]
    assert len(collector) == 0


def test_validate_allowed_values_with_invalid(collector):
    """Test validation when some values are invalid."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 4,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003", "XX_QA004"],
            "status": ["Active", "INVALID", "Inactive", "BAD_VALUE"],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive"],
        replace_invalid=True,
    )

    assert result["status"].to_list() == [
        "Active",
        settings.error_val_character,
        "Inactive",
        settings.error_val_character,
    ]
    assert len(collector) == 2

    # Check error details
    # Note: file_name and patient_id are "unknown" placeholders in validate_allowed_values
    # They get filled in during bulk processing operations
    errors_df = collector.to_dataframe()
    # Order is not guaranteed, so check using sets
    assert set(errors_df["original_value"].to_list()) == {"INVALID", "BAD_VALUE"}
    assert errors_df["column"].to_list() == ["status", "status"]
    assert errors_df["error_code"].to_list() == ["invalid_value", "invalid_value"]


def test_validate_allowed_values_preserves_nulls(collector):
    """Test that nulls are preserved and not logged as errors."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "status": ["Active", None, "Inactive"],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive"],
        replace_invalid=True,
    )

    assert result["status"].to_list() == ["Active", None, "Inactive"]
    assert len(collector) == 0


def test_validate_allowed_values_no_replace(collector):
    """Test validation without replacing invalid values."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 2,
            "patient_id": ["XX_QA001", "XX_QA002"],
            "status": ["Active", "INVALID"],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active"],
        replace_invalid=False,
    )

    # Invalid value should NOT be replaced
    assert result["status"].to_list() == ["Active", "INVALID"]
    # But it should still be logged
    assert len(collector) == 1


def test_validate_allowed_values_missing_column(collector):
    """Test that missing columns are handled gracefully."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="nonexistent",
        allowed_values=["Active"],
    )

    assert result.equals(df)
    assert len(collector) == 0


def test_validate_allowed_values_ignores_existing_errors(collector):
    """Test that existing error values are not re-logged."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "status": ["Active", settings.error_val_character, "INVALID"],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Inactive"],
        replace_invalid=True,
    )

    # Only "INVALID" should be logged, not the existing error value
    assert len(collector) == 1
    assert result["status"].to_list() == [
        "Active",
        settings.error_val_character,
        settings.error_val_character,
    ]


def test_validate_column_from_rules(collector):
    """Test validation using rules from data_cleaning.yaml."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "clinic_visit": ["Y", "N", "INVALID"],
        }
    )

    rules = load_validation_rules()

    result = validate_column_from_rules(
        df=df,
        column="clinic_visit",
        rules=rules["clinic_visit"],
    )

    # "INVALID" should be replaced with error value
    assert result["clinic_visit"].to_list() == ["Y", "N", settings.error_val_character]
    assert len(collector) == 1


def test_validate_column_from_rules_missing_column(collector):
    """Test validation with missing column."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
        }
    )

    rules = load_validation_rules()

    result = validate_column_from_rules(
        df=df,
        column="nonexistent",
        rules=rules["clinic_visit"],
    )

    assert result.equals(df)
    assert len(collector) == 0


def test_validate_all_columns(collector):
    """Test validation of all columns with rules.

    Note: Validation uses case-insensitive matching and normalizes to canonical values.
    For example, "active" becomes "Active", "y" becomes "Y".
    """
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "clinic_visit": ["Y", "N", "INVALID1"],
            "patient_consent": ["Y", "INVALID2", "N"],
            "status": ["active", "INVALID3", "inactive"],  # Lowercase input
        }
    )

    result = validate_all_columns(df)

    # All invalid values should be replaced
    # Valid values should be normalized to canonical form (Title Case for status)
    assert result["clinic_visit"].to_list() == ["Y", "N", settings.error_val_character]
    assert result["patient_consent"].to_list() == ["Y", settings.error_val_character, "N"]
    assert result["status"].to_list() == ["Active", settings.error_val_character, "Inactive"]

    # Should have logged 3 errors (one per invalid value)
    assert len(collector) == 3


def test_validate_all_columns_only_validates_existing(collector):
    """Test that validation only processes columns that exist in DataFrame."""
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
            "clinic_visit": ["Y"],
            # Many other columns from rules don't exist
        }
    )

    # Should not raise error even though many rule columns don't exist
    result = validate_all_columns(df)

    assert "clinic_visit" in result.columns
    assert len(collector) == 0


def test_validate_allowed_values_case_insensitive(collector):
    """Test that validation is case-insensitive and normalizes to canonical values.

    - "y" matches "Y" (case-insensitive)
    - Returns canonical value "Y" (not the input "y")
    """
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 3,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
            "clinic_visit": ["Y", "y", "N"],  # Mixed case
        }
    )

    result = validate_allowed_values(
        df=df,
        column="clinic_visit",
        allowed_values=["Y", "N"],
        replace_invalid=True,
    )

    # Lowercase "y" should match "Y" and be normalized to canonical "Y"
    assert result["clinic_visit"].to_list() == ["Y", "Y", "N"]
    assert len(collector) == 0  # No errors - "y" is valid


def test_validate_allowed_values_csv_subset(collector):
    """CSV values whose every token is in allowed_values emit canonical CSV."""
    allowed = ["Pre-mixed", "Short-acting", "Intermediate-acting", "Rapid-acting", "Long-acting"]
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"] * 5,
            "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003", "XX_QA004", "XX_QA005"],
            "insulin_subtype": [
                "rapid-acting",  # single valid
                "pre-mixed,rapid-acting",  # two-token CSV valid
                "pre-mixed,rapid-acting,long-acting",  # three-token CSV valid
                "pre-mixed,unknown-thing",  # CSV with one bad token
                "not-in-list",  # single invalid
            ],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="insulin_subtype",
        allowed_values=allowed,
        replace_invalid=True,
        allow_csv_subset=True,
    )

    assert result["insulin_subtype"].to_list() == [
        "Rapid-acting",
        "Pre-mixed,Rapid-acting",
        "Pre-mixed,Rapid-acting,Long-acting",
        settings.error_val_character,
        settings.error_val_character,
    ]
    assert len(collector) == 2


def test_validate_allowed_values_csv_subset_disabled():
    """Without allow_csv_subset, CSV values are treated as single strings and fail."""
    allowed = ["Pre-mixed", "Rapid-acting"]
    df = pl.DataFrame(
        {
            "file_name": ["test.xlsx"],
            "patient_id": ["XX_QA001"],
            "insulin_subtype": ["pre-mixed,rapid-acting"],
        }
    )

    result = validate_allowed_values(
        df=df,
        column="insulin_subtype",
        allowed_values=allowed,
        replace_invalid=True,
    )

    assert result["insulin_subtype"].to_list() == [settings.error_val_character]


# Tests for fix_patient_id


def test_fix_patient_id_valid_ids(collector):
    """Test that valid patient IDs are not changed."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_QB004", "AB_QA123", "XY_QA999"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["KD_QB004", "AB_QA123", "XY_QA999"]
    assert len(collector) == 0


def test_fix_patient_id_hyphen_normalization(collector):
    """Test that hyphens are replaced with underscores."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD-QB004", "AB-QA123"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["KD_QB004", "AB_QA123"]
    assert len(collector) == 0  # Normalization doesn't generate errors


def test_fix_patient_id_overlong_without_candidate_is_sentinelled(collector):
    """An over-length ID is never truncated into an identity nobody wrote.

    Truncating to 8 characters manufactures an ID that appears in no source
    workbook (ticket 47: KH_QEH026 -> KH_QEH02, which then collected four
    different patients' records).
    """
    df = pl.DataFrame(
        {
            "patient_id": ["KD_QB004XY", "KD_QB004ABC", "VERYLONGID"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined", "Undefined"]
    assert len(collector) == 3


def test_fix_patient_id_recovers_from_the_tracker_s_own_spelling(collector):
    """A one-edit typo resolves to the ID the same tracker spells correctly."""
    df = pl.DataFrame(
        {
            "patient_id": ["KH_QEH026", "KH_QE026", "KH_QE027"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["KH_QE026", "KH_QE026", "KH_QE027"]
    # Recovery is still a defect in the source workbook, so it is reported.
    assert len(collector) == 1
    assert "KH_QEH026" in collector.findings[0].original_value


def test_fix_patient_id_recovers_a_short_id_too():
    """Recovery is not limited to the over-length branch."""
    df = pl.DataFrame({"patient_id": ["MM_QD97", "MM_QD097"]})

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["MM_QD097", "MM_QD097"]


def test_fix_patient_id_ambiguous_candidates_are_sentinelled():
    """Two candidates one edit away means the intended patient is unknowable."""
    df = pl.DataFrame({"patient_id": ["KH_QE02", "KH_QE021", "KH_QE023"]})

    result = fix_patient_id(df)

    assert result["patient_id"][0] == "Undefined"


def test_fix_patient_id_candidate_must_be_in_the_same_tracker():
    """No candidate in the frame means no recovery, however plausible the guess.

    2026_NOGH writes MM_QD97 in its Patient List and every month sheet, and
    has no MM_QD097 anywhere -- so nothing licenses inventing one.
    """
    df = pl.DataFrame({"patient_id": ["MM_QD97", "MM_QD096", "MM_QD001"]})

    result = fix_patient_id(df)

    assert result["patient_id"][0] == "Undefined"


def test_fix_patient_id_invalid_too_short_first_part(collector):
    """Test that IDs with < 2 letters in first part are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["K_QB004", "A_CD123"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_invalid_too_short_second_part(collector):
    """Test that IDs with < 2 letters in second part are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_Q004", "AB_C123"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_invalid_wrong_digits():
    """Test that IDs without exactly 3 digits are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_QB04", "KD_QB0", "KD_QB0001"],
        }
    )

    result = fix_patient_id(df)

    # All invalid (2 digits, 1 digit, 4 digits), and none has a well-formed
    # ID in the same frame to recover against.
    assert result["patient_id"].to_list() == ["Undefined", "Undefined", "Undefined"]


def test_fix_patient_id_invalid_digits_in_letter_positions(collector):
    """Test that IDs with digits instead of letters are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["11_EW004", "KD_Q1004", "12_34567"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined", "Undefined"]
    assert len(collector) == 3


def test_fix_patient_id_invalid_letters_in_digit_positions(collector):
    """Test that IDs with letters in digit positions are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_QBX04", "KD_QBABC"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_invalid_no_underscore(collector):
    """Test that IDs without underscore are replaced."""
    df = pl.DataFrame(
        {
            "patient_id": ["KDEW004", "INVALID"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["Undefined", "Undefined"]
    assert len(collector) == 2


def test_fix_patient_id_null_values(collector):
    """Test that null values are preserved."""
    df = pl.DataFrame(
        {
            "patient_id": ["KD_QB004", None, "AB_QA123"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"][0] == "KD_QB004"
    assert result["patient_id"][1] is None
    assert result["patient_id"][2] == "AB_QA123"
    assert len(collector) == 0


def test_fix_patient_id_empty_string(collector):
    """Test that empty string is replaced with error value."""
    df = pl.DataFrame(
        {
            "patient_id": ["", "KD_QB004"],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"][0] == "Undefined"
    assert result["patient_id"][1] == "KD_QB004"
    assert len(collector) == 1


def test_fix_patient_id_missing_column(collector):
    """Test that missing column is handled gracefully."""
    df = pl.DataFrame({"other": [1, 2, 3]})

    result = fix_patient_id(df)

    assert result.equals(df)
    assert len(collector) == 0


def test_fix_patient_id_mixed_valid_invalid(collector):
    """Test mixed valid and invalid IDs."""
    df = pl.DataFrame(
        {
            "patient_id": [
                "KD_QB004",  # Valid
                "KD-QA123",  # Valid after normalization
                "INVALID",  # Invalid, replaced
                "KD_QB004XY",  # Invalid, two edits from KD_QB004
                None,  # Null preserved
            ],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"][0] == "KD_QB004"
    assert result["patient_id"][1] == "KD_QA123"
    assert result["patient_id"][2] == "Undefined"
    assert result["patient_id"][3] == "Undefined"
    assert result["patient_id"][4] is None
    assert len(collector) == 2


def test_fix_patient_id_lowercase_letters(collector):
    """Test that lowercase letters make ID invalid."""
    df = pl.DataFrame(
        {
            "patient_id": ["kd_qb004", "KD_qb004", "kd_QB004"],
        }
    )

    result = fix_patient_id(df)

    # All should be replaced (format requires uppercase)
    assert result["patient_id"].to_list() == ["Undefined", "Undefined", "Undefined"]
    assert len(collector) == 3


def test_fix_patient_id_never_truncates_an_overlong_id(collector):
    """Ticket 47: every malformed ID is recovered or sentinelled, never cut.

    A malformed ID is recovered against a well-formed ID in the same tracker
    (edit distance 1, unique candidate only) or sentinelled -- so the output
    only ever contains an ID some tracker actually spells.
    """
    df = pl.DataFrame(
        {
            "patient_id": [
                "KD_QB004",  # Valid
                "KD-QB004",  # Normalize - to _
                "11_EW004",  # Digits instead of letters, two edits away
                "KD_QB004XY",  # Over-length, two edits away
                None,  # Null
                "",  # Empty
            ],
        }
    )

    result = fix_patient_id(df)

    expected = [
        "KD_QB004",  # Valid
        "KD_QB004",  # Normalized
        "Undefined",  # No unambiguous candidate
        "Undefined",  # Not truncated to KD_QB004
        None,  # Null
        "Undefined",  # Empty
    ]
    assert result["patient_id"].to_list() == expected
    assert len(collector) == 3


def test_fix_patient_id_recovers_a_single_character_typo(collector):
    """The other half of the same divergence: one edit, one candidate, recover.

    These four spellings are all one edit from the valid `KD_QB004` the same
    frame carries, which is the 2023_NPH shape that opened ticket 47.
    """
    df = pl.DataFrame(
        {
            "patient_id": [
                "KD_QB004",  # Valid, the recovery target
                "K_QB004",  # Dropped letter
                "KD_Q004",  # Dropped letter
                "KD_QBX04",  # Substituted character
                "KD_Q1004",  # Substituted character
            ],
        }
    )

    result = fix_patient_id(df)

    assert result["patient_id"].to_list() == ["KD_QB004"] * 5
    # Recovered, but still four defective source cells to report.
    assert len(collector) == 4


def test_validate_allowed_values_maps_a_configured_alias_to_its_canonical_form():
    """Ticket 29: the pre-2024 template's spelling is an alias, not a value.

    The source carries both "Active - Remote" (2020-2023 trackers) and
    "Active Remote" (2024+ trackers, and the only spelling the current
    Lookup List dropdown defines). One canonical label must reach the
    reports, and which one is canonical is stated in the config rather than
    implied by list order.
    """
    df = pl.DataFrame({"status": ["Active - Remote", "active remote", "Active"]})

    result = validate_allowed_values(
        df=df,
        column="status",
        allowed_values=["Active", "Active Remote"],
        aliases={"Active Remote": ["Active - Remote"]},
    )

    assert result["status"].to_list() == ["Active Remote", "Active Remote", "Active"]


def test_validate_allowed_values_rejects_two_allowed_values_that_sanitize_alike():
    """Two canonical values reducing to one key made the winner depend on
    dict-insertion order (ticket 29). Fail loudly instead of picking one."""
    df = pl.DataFrame({"status": ["Active Remote"]})

    with pytest.raises(ValueError, match="sanitize to the same key"):
        validate_allowed_values(
            df=df,
            column="status",
            allowed_values=["Active - Remote", "Active Remote"],
        )


def test_validate_allowed_values_rejects_aliases_for_a_non_allowed_canonical():
    """Aliases declared under a label that is not a canonical value are a
    config typo."""
    df = pl.DataFrame({"status": ["Active"]})

    with pytest.raises(ValueError, match="not an allowed value"):
        validate_allowed_values(
            df=df,
            column="status",
            allowed_values=["Active"],
            aliases={"Active Remotte": ["Active - Remote"]},
        )
