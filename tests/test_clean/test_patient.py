"""Unit tests for patient cleaning functions."""

from datetime import date

import polars as pl
import pytest

from a4d.clean.patient import (
    _apply_preprocessing,
    _apply_range_validation,
    _apply_type_conversions,
    _derive_insulin_fields,
    _fix_age_from_dob,
    _fix_t1d_diagnosis_age,
    clean_patient_data,
)
from a4d.config import settings
from a4d.errors import ErrorCollector


class TestPatientIdNormalization:
    """Tests for patient_id normalization (transfer clinic suffix removal)."""

    def test_normalize_transfer_patient_id(self):
        """Should normalize patient_id by removing transfer clinic suffix."""
        df = pl.DataFrame(
            {
                "patient_id": ["MY_QH003_SB", "TH_QA001_PT", "LA_QB002_VP"],
                "name": ["Patient A", "Patient B", "Patient C"],
            }
        )

        result = _apply_preprocessing(df)

        assert result["patient_id"].to_list() == ["MY_QH003", "TH_QA001", "LA_QB002"]

    def test_preserve_normal_patient_id(self):
        """Should preserve patient_id without transfer suffix."""
        df = pl.DataFrame(
            {
                "patient_id": ["MY_QG001", "TH_QG003", "LA_LFH042"],
                "name": ["Patient A", "Patient B", "Patient C"],
            }
        )

        result = _apply_preprocessing(df)

        # Should remain unchanged
        assert result["patient_id"].to_list() == ["MY_QG001", "TH_QG003", "LA_LFH042"]

    def test_mixed_patient_ids(self):
        """Should handle mix of normal and transfer patient IDs."""
        df = pl.DataFrame(
            {
                "patient_id": [
                    "MY_QG001",  # Normal
                    "MY_QH003_SB",  # Transfer
                    "TH_QG003",  # Normal
                    "TH_QA001_PT",  # Transfer
                ],
                "name": ["A", "B", "C", "D"],
            }
        )

        result = _apply_preprocessing(df)

        assert result["patient_id"].to_list() == [
            "MY_QG001",
            "MY_QH003",  # Normalized
            "TH_QG003",
            "TH_QA001",  # Normalized
        ]

    def test_multiple_underscores_keeps_only_first_two_parts(self):
        """Should keep only first two underscore-separated parts."""
        df = pl.DataFrame(
            {
                "patient_id": ["MY_QH003_SB_EXTRA"],  # Three underscores
                "name": ["Patient A"],
            }
        )

        result = _apply_preprocessing(df)

        # Should extract only MY_QH003
        assert result["patient_id"][0] == "MY_QH003"

    def test_patient_id_without_underscores(self):
        """Should preserve patient_id without underscores."""
        df = pl.DataFrame(
            {
                "patient_id": ["MYID001", "NOMATCH"],
                "name": ["Patient A", "Patient B"],
            }
        )

        result = _apply_preprocessing(df)

        # Pattern won't match, should keep original
        assert result["patient_id"].to_list() == ["MYID001", "NOMATCH"]

    def test_null_patient_id_preserved(self):
        """Should preserve null patient_ids."""
        df = pl.DataFrame(
            {
                "patient_id": [None, "MY_QG001", None],
                "name": ["A", "B", "C"],
            }
        )

        result = _apply_preprocessing(df)

        assert result["patient_id"][0] is None
        assert result["patient_id"][1] == "MY_QG001"
        assert result["patient_id"][2] is None


class TestHbA1cPreprocessing:
    """Tests for HbA1c exceeds marker handling."""

    def test_hba1c_baseline_exceeds_marker(self):
        """Should extract > or < markers and remove them from value."""
        df = pl.DataFrame(
            {
                "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003"],
                "hba1c_baseline": [">14", "<5.5", "7.2"],
            }
        )

        result = _apply_preprocessing(df)

        assert result["hba1c_baseline_exceeds"].to_list() == [True, True, False]
        assert result["hba1c_baseline"].to_list() == ["14", "5.5", "7.2"]

    def test_hba1c_updated_exceeds_marker(self):
        """Should extract > or < markers from updated HbA1c."""
        df = pl.DataFrame(
            {
                "patient_id": ["XX_QA001"],
                "hba1c_updated": [">12.5"],
            }
        )

        result = _apply_preprocessing(df)

        assert result["hba1c_updated_exceeds"][0] is True
        assert result["hba1c_updated"][0] == "12.5"


class TestFbgPreprocessing:
    """Tests for FBG (fasting blood glucose) text value handling."""

    def test_fbg_qualitative_to_numeric(self):
        """Should convert qualitative FBG values to numeric."""
        df = pl.DataFrame(
            {
                "patient_id": ["XX_QA001", "XX_QA002", "XX_QA003", "XX_QA004"],
                "fbg_updated_mg": ["high", "medium", "low", "150"],
            }
        )

        result = _apply_preprocessing(df)

        # high→200, medium→170, low→140
        assert result["fbg_updated_mg"].to_list() == ["200", "170", "140", "150"]

    def test_fbg_removes_dka_marker(self):
        """Should attempt to remove (DKA) marker from FBG values."""
        df = pl.DataFrame(
            {
                "patient_id": ["XX_QA001"],
                "fbg_updated_mg": ["350 (DKA)"],
            }
        )

        result = _apply_preprocessing(df)

        # Note: Current implementation lowercases first, then tries to remove literal "(DKA)"
        # which doesn't match lowercase "(dka)", so it's not actually removed
        # This is a known issue but matches current behavior
        assert result["fbg_updated_mg"][0] == "350 (dka)"


class TestYesNoHyphenReplacement:
    """Tests for replacing '-' with 'N' in insulin-related Y/N columns."""

    def test_replace_hyphen_in_insulin_columns(self):
        """Should replace '-' with 'N' in analog insulin columns (2024+ trackers)."""
        df = pl.DataFrame(
            {
                "patient_id": ["XX_QA001"],
                "analog_insulin_long_acting": ["-"],
                "analog_insulin_rapid_acting": ["-"],
            }
        )

        result = _apply_preprocessing(df)

        assert result["analog_insulin_long_acting"][0] == "N"
        assert result["analog_insulin_rapid_acting"][0] == "N"

    def test_preserve_hyphen_in_other_columns(self):
        """Should NOT replace '-' in non-insulin Y/N columns."""
        df = pl.DataFrame(
            {
                "patient_id": ["XX_QA001"],
                "clinic_visit": ["-"],
                "active": ["-"],
            }
        )

        result = _apply_preprocessing(df)

        # These columns are not in the insulin list, so '-' is preserved
        assert result["clinic_visit"][0] == "-"
        assert result["active"][0] == "-"


class TestFixAgeFromDob:
    """Tests for age calculation from DOB."""

    def test_calculates_age_from_dob(self):
        """Should calculate age from DOB and tracker date."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "age": [None],
                "dob": [date(2010, 6, 15)],
                "tracker_year": [2025],
                "tracker_month": [1],
            }
        )
        collector = ErrorCollector()

        result = _fix_age_from_dob(df, collector)

        # 2025 - 2010 = 15, but Jan < June so 15 - 1 = 14
        assert result["age"][0] == 14

    def test_birthday_already_passed(self):
        """Should not subtract 1 if birthday already passed in tracker year."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "age": [None],
                "dob": [date(2010, 3, 15)],
                "tracker_year": [2025],
                "tracker_month": [6],
            }
        )
        collector = ErrorCollector()

        result = _fix_age_from_dob(df, collector)

        # 2025 - 2010 = 15, June > March so no adjustment
        assert result["age"][0] == 15

    def test_missing_dob_keeps_null(self):
        """Should keep null age if DOB is missing."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "age": [None],
                "dob": pl.Series([None], dtype=pl.Date),
                "tracker_year": [2025],
                "tracker_month": [1],
            }
        )
        collector = ErrorCollector()

        result = _fix_age_from_dob(df, collector)

        assert result["age"][0] is None

    def test_error_date_dob_keeps_null(self):
        """Should keep null age if DOB is error date."""
        error_date = date.fromisoformat(settings.error_val_date)
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "age": [None],
                "dob": [error_date],
                "tracker_year": [2025],
                "tracker_month": [1],
            }
        )
        collector = ErrorCollector()

        result = _fix_age_from_dob(df, collector)

        assert result["age"][0] is None

    def test_corrects_wrong_excel_age(self):
        """Should replace wrong Excel age with calculated age."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "age": [99.0],  # Wrong value from Excel
                "dob": [date(2010, 6, 15)],
                "tracker_year": [2025],
                "tracker_month": [8],
            }
        )
        collector = ErrorCollector()

        result = _fix_age_from_dob(df, collector)

        # Should be corrected to 15
        assert result["age"][0] == 15


class TestFixT1dDiagnosisAge:
    """Tests for t1d_diagnosis_age calculation from DOB and diagnosis date."""

    def test_calculates_diagnosis_age(self):
        """Should calculate age at diagnosis from DOB and diagnosis date."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [date(2005, 8, 20)],
                "t1d_diagnosis_date": [date(2020, 3, 15)],
                "t1d_diagnosis_age": [None],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        # 2020 - 2005 = 15, but March < August so 15 - 1 = 14
        assert result["t1d_diagnosis_age"][0] == 14

    def test_birthday_passed_before_diagnosis(self):
        """Should not subtract 1 if birthday passed before diagnosis."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [date(2005, 3, 20)],
                "t1d_diagnosis_date": [date(2020, 8, 15)],
                "t1d_diagnosis_age": [None],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        # 2020 - 2005 = 15, August > March so no adjustment
        assert result["t1d_diagnosis_age"][0] == 15

    def test_diagnosis_before_birth_returns_null(self):
        """A diagnosis date earlier than the birth date is a source
        contradiction, so the derived age is meaningless (ticket 52).

        2023 Likas Women & Children's records MY_QC004 as born 2016-08-17 and
        diagnosed 2015-05-29; the workbook's own age formula resolves to
        #NUM!. Deriving anyway emitted -2 into BigQuery.
        """
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [date(2016, 8, 17)],
                "t1d_diagnosis_date": [date(2015, 5, 29)],
                "t1d_diagnosis_age": [None],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        assert result["t1d_diagnosis_age"][0] is None

    def test_missing_dob_returns_null(self):
        """Should return null if DOB is missing."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": pl.Series([None], dtype=pl.Date),
                "t1d_diagnosis_date": [date(2020, 3, 15)],
                "t1d_diagnosis_age": [None],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        assert result["t1d_diagnosis_age"][0] is None

    def test_missing_diagnosis_date_returns_null(self):
        """Should return null if diagnosis date is missing."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [date(2005, 8, 20)],
                "t1d_diagnosis_date": pl.Series([None], dtype=pl.Date),
                "t1d_diagnosis_age": [None],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        assert result["t1d_diagnosis_age"][0] is None

    def test_error_date_dob_returns_null(self):
        """Should return null if DOB is error date."""
        error_date = date.fromisoformat(settings.error_val_date)
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [error_date],
                "t1d_diagnosis_date": [date(2020, 3, 15)],
                "t1d_diagnosis_age": [None],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        assert result["t1d_diagnosis_age"][0] is None

    def test_error_date_diagnosis_returns_null(self):
        """Should return null if diagnosis date is error date."""
        error_date = date.fromisoformat(settings.error_val_date)
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [date(2005, 8, 20)],
                "t1d_diagnosis_date": [error_date],
                "t1d_diagnosis_age": [None],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        assert result["t1d_diagnosis_age"][0] is None

    def test_replaces_excel_error_value(self):
        """Should replace Excel error (#NUM!) that became 999999 with calculated value."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [date(2005, 8, 20)],
                "t1d_diagnosis_date": [date(2020, 3, 15)],
                "t1d_diagnosis_age": [999999],  # Error value from Excel
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        # Should be calculated as 14
        assert result["t1d_diagnosis_age"][0] == 14

    def test_keeps_recorded_age_when_dates_missing(self):
        """A real recorded diagnosis age must survive even if the dates
        needed to recompute it don't parse -- R never recomputes this field
        at all, so a directly recorded value should never be discarded to
        null just because the calculation can't run."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": pl.Series([None], dtype=pl.Date),
                "t1d_diagnosis_date": pl.Series([None], dtype=pl.Date),
                "t1d_diagnosis_age": [12],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        assert result["t1d_diagnosis_age"][0] == 12

    def test_keeps_recorded_age_over_disagreeing_calculation(self):
        """A real recorded diagnosis age is trusted over date arithmetic even
        when both dates parse and disagree with it -- the recorded value is
        the clinic's own entry, not something to silently override."""
        df = pl.DataFrame(
            {
                "patient_id": ["P001"],
                "dob": [date(2005, 8, 20)],
                "t1d_diagnosis_date": [date(2020, 3, 15)],  # would calculate to 14
                "t1d_diagnosis_age": [15],
            }
        )

        result = _fix_t1d_diagnosis_age(df)

        assert result["t1d_diagnosis_age"][0] == 15


class TestStripStringWhitespace:
    """Ticket 36: whitespace at the ends of a string never carries meaning.

    Product's cleaning already stripped every string column (step 2.16) while
    patient's did not, so the same tracker's `file_name` and `sheet_name`
    disagreed between `patient_data_cleaned` and `product_data_cleaned` --
    silently dropping rows from any join between the two arms. Stripping runs
    before validation, matching readxl's `trim_ws = TRUE` default on R's side,
    so a value is not rejected for whitespace alone.
    """

    def test_strips_identifier_columns(self):
        df_raw = pl.DataFrame(
            {
                "file_name": ["2024_Some Hospital A4D Tracker - final "],
                "sheet_name": ["Dec24 "],
                "patient_id": ["MY_QA001"],
            }
        )

        result = clean_patient_data(df_raw, ErrorCollector())

        assert result["file_name"].to_list() == ["2024_Some Hospital A4D Tracker - final"]
        assert result["sheet_name"].to_list() == ["Dec24"]

    def test_whitespace_does_not_defeat_allowed_value_validation(self):
        df_raw = pl.DataFrame({"patient_id": ["MY_QA001"], "sheet_name": ["Jan24"], "sex": ["F "]})

        result = clean_patient_data(df_raw, ErrorCollector())

        assert result["sex"].to_list() == ["F"]


def test_apply_type_conversions_keeps_the_year_of_a_space_separated_date():
    """Stripping a trailing time component must not eat a real date's year.

    2017-era trackers record diagnosis dates as "Jun 2006"; splitting on the
    first space left "Jun", which dateutil then completed with the *current*
    year, so the row was sentinelled as a future date and the real value lost.
    """
    df = pl.DataFrame(
        {
            "file_name": ["t.xlsx", "t.xlsx"],
            "patient_id": ["P1", "P2"],
            "t1d_diagnosis_date": ["Jun 2006", "2009-04-17 00:00:00"],
        }
    )

    result = _apply_type_conversions(df, ErrorCollector())

    assert result["t1d_diagnosis_date"].to_list() == [date(2006, 6, 1), date(2009, 4, 17)]


class TestHeightRangeValidation:
    """Height cm-to-m conversion must not rescue implausible source values.

    R converts only above 50 (transform_cm_to_m), so a value between 2.3 and 50
    is neither metres nor centimetres and falls out of the [0, 2.3] bound as an
    error. Dividing it by 100 instead manufactures a plausible-looking metre
    reading from an unusable cell (ticket 55).
    """

    def _validate(self, df: pl.DataFrame) -> pl.DataFrame:
        return _apply_range_validation(df, ErrorCollector())

    def test_centimetre_height_is_converted_to_metres(self):
        df = pl.DataFrame({"height": [135.5], "file_name": ["f"], "patient_id": ["p"]})

        assert self._validate(df)["height"].to_list() == [1.355]

    def test_metre_height_is_kept(self):
        df = pl.DataFrame({"height": [1.75], "file_name": ["f"], "patient_id": ["p"]})

        assert self._validate(df)["height"].to_list() == [1.75]

    def test_value_between_the_two_units_becomes_the_error_value(self):
        df = pl.DataFrame(
            {
                "height": [2.43, 6.9, 13.0],
                "file_name": ["f", "f", "f"],
                "patient_id": ["p", "p", "p"],
            }
        )

        assert self._validate(df)["height"].to_list() == [settings.error_val_numeric] * 3

    def test_bmi_is_derived_from_the_validated_height(self):
        """R cuts height before fix_bmi, so an unusable height voids the BMI."""
        df = pl.DataFrame(
            {
                "height": [2.43, 1.75],
                "weight": [60.0, 70.0],
                "bmi": [None, None],
                "file_name": ["f", "f"],
                "patient_id": ["p", "q"],
            }
        )

        result = self._validate(df)

        assert result["bmi"][0] == settings.error_val_numeric
        assert result["bmi"][1] == pytest.approx(70.0 / 1.75**2)


class TestInsulinSubtypeDerivation:
    """The 2024+ template's five insulin columns are tick boxes, but one clinic
    ticks them by writing the drug's name (ticket 55)."""

    def _derive(self, **cols: list[str | None]) -> pl.DataFrame:
        return _derive_insulin_fields(pl.DataFrame(cols))

    def test_ticked_columns_become_the_subtype_list(self):
        result = self._derive(
            human_insulin_pre_mixed=["-"],
            human_insulin_short_acting=["-"],
            human_insulin_intermediate_acting=["-"],
            analog_insulin_rapid_acting=["Y"],
            analog_insulin_long_acting=["Y"],
        )

        assert result["insulin_subtype"].to_list() == ["rapid-acting,long-acting"]
        assert result["insulin_type"].to_list() == ["analog insulin"]

    def test_a_drug_name_in_a_tick_column_counts_as_ticked(self):
        """2024 Sarawak writes Novorapid/Glargine where the template wants Y."""
        result = self._derive(
            human_insulin_pre_mixed=["-"],
            human_insulin_short_acting=["-"],
            human_insulin_intermediate_acting=["-"],
            analog_insulin_rapid_acting=["Novorapid"],
            analog_insulin_long_acting=["Glargine"],
        )

        assert result["insulin_subtype"].to_list() == ["rapid-acting,long-acting"]

    def test_negative_markers_do_not_count_as_ticked(self):
        result = self._derive(
            human_insulin_pre_mixed=["0"],
            human_insulin_short_acting=["N"],
            human_insulin_intermediate_acting=["-"],
            analog_insulin_rapid_acting=[""],
            analog_insulin_long_acting=["-"],
        )

        assert result["insulin_subtype"].to_list() == [""]

    def test_no_tick_at_all_leaves_the_subtype_empty(self):
        """Allowed-value validation turns the empty string into "Undefined", and
        R does the same -- the two agree, so this ticket does not change it."""
        result = self._derive(
            human_insulin_pre_mixed=["-"],
            human_insulin_short_acting=["-"],
            human_insulin_intermediate_acting=["-"],
            analog_insulin_rapid_acting=["-"],
            analog_insulin_long_acting=["-"],
        )

        assert result["insulin_subtype"].to_list() == [""]
