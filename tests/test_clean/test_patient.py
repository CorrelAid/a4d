"""Unit tests for patient cleaning functions."""

from datetime import date

import polars as pl
import pytest

from a4d.clean.patient import (
    _apply_preprocessing,
    _apply_range_validation,
    _apply_type_conversions,
    _convert_buddhist_era_dates,
    _derive_insulin_fields,
    _extract_date_from_measurement,
    _fix_age_from_dob,
    _fix_t1d_diagnosis_age,
    _validate_dates,
    clean_patient_data,
)
from a4d.config import settings
from a4d.findings import tracker_context


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

        result = _fix_age_from_dob(df)

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

        result = _fix_age_from_dob(df)

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

        result = _fix_age_from_dob(df)

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

        result = _fix_age_from_dob(df)

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

        result = _fix_age_from_dob(df)

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
        needed to recompute it don't parse: a value the clinic typed is not
        discarded to null just because the arithmetic cannot run."""
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
    before validation, so a value is not rejected for whitespace alone.
    """

    def test_strips_identifier_columns(self):
        df_raw = pl.DataFrame(
            {
                "file_name": ["2024_Some Hospital A4D Tracker - final "],
                "sheet_name": ["Dec24 "],
                "patient_id": ["MY_QA001"],
            }
        )

        result = clean_patient_data(df_raw)

        assert result["file_name"].to_list() == ["2024_Some Hospital A4D Tracker - final"]
        assert result["sheet_name"].to_list() == ["Dec24"]

    def test_whitespace_does_not_defeat_allowed_value_validation(self):
        df_raw = pl.DataFrame({"patient_id": ["MY_QA001"], "sheet_name": ["Jan24"], "sex": ["F "]})

        result = clean_patient_data(df_raw)

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

    result = _apply_type_conversions(df)

    assert result["t1d_diagnosis_date"].to_list() == [date(2006, 6, 1), date(2009, 4, 17)]


class TestHeightRangeValidation:
    """Height cm-to-m conversion must not rescue implausible source values.

    Conversion applies only above 50, so a value between 2.3 and 50 is neither
    metres nor centimetres and falls out of the [0, 2.3] bound as an error.
    Dividing it by 100 instead manufactures a plausible-looking metre reading
    from an unusable cell -- 120 such cells were published as 0.069 metres
    (ticket 55).
    """

    def _validate(self, df: pl.DataFrame) -> pl.DataFrame:
        return _apply_range_validation(df)

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
        """An unusable height voids the BMI rather than producing one.

        Deriving BMI before the height bound gave 60 / 2.43^2 = 10.16, which
        then passed its own bound and reached production."""
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
        """Allowed-value validation turns the empty string into "Undefined".

        This overstates what the clinic recorded on 17,418 rows; nulling them
        instead was measured and reverted (ticket 55), so the behaviour is
        pinned here deliberately rather than left unexamined."""
        result = self._derive(
            human_insulin_pre_mixed=["-"],
            human_insulin_short_acting=["-"],
            human_insulin_intermediate_acting=["-"],
            analog_insulin_rapid_acting=["-"],
            analog_insulin_long_acting=["-"],
        )

        assert result["insulin_subtype"].to_list() == [""]


class TestExtractDateFromMeasurement:
    """The closing parenthesis is optional, because the source often omits it.

    The 2017/2018 Mandalay, CDA and Mahosot trackers write `180(May-2017`
    without ever closing the bracket -- 25 of the 30 cells in this population
    -- and requiring the closer lost the measurement date on every one.
    """

    @staticmethod
    def _extract(value: str) -> tuple[str | None, str | None]:
        df = pl.DataFrame({"fbg_updated_mg": [value]})
        out = _extract_date_from_measurement(df, "fbg_updated_mg")
        return out["fbg_updated_mg"][0], out["fbg_updated_date"][0]

    def test_closed_parenthesis(self):
        assert self._extract("8.53 (28/8/2017)") == ("8.53", "28/8/2017")

    def test_unclosed_parenthesis(self):
        assert self._extract("180(May-2017") == ("180", "May-2017")

    def test_doubled_opening_parenthesis_uses_the_last_one(self):
        """The greedy prefix consumes the first `(`, so the date starts after
        the second. The stray `(` is stripped from the value rather than kept,
        because leaving it fails the numeric cast and loses the 196."""
        assert self._extract("196((Dec-2017)") == ("196", "Dec-2017")

    def test_no_parenthesis_leaves_the_value_alone(self):
        assert self._extract("3") == ("3", None)

    def test_units_inside_the_value_are_preserved(self):
        assert self._extract("148 mg/dl   (Mar-18)") == ("148 mg/dl", "Mar-18")


class TestBuddhistEraConversion:
    """Tests for _convert_buddhist_era_dates (ticket 61).

    Thai clinics keep their workbooks in a Thai-locale Excel, so a date arrives
    with a Buddhist-era year (BE = CE + 543). Before this conversion existed,
    _validate_dates saw a year centuries in the future and clobbered the cell
    with the 9999-09-09 sentinel -- 381 cells across the real corpus, destroyed
    rather than published oddly.
    """

    @staticmethod
    def _df(dates: list[date | None], tracker_year: int = 2024) -> pl.DataFrame:
        n = len(dates)
        return pl.DataFrame(
            {
                "patient_id": [f"TH_CM{i:03d}" for i in range(n)],
                "file_name": ["t.xlsx"] * n,
                "tracker_year": [tracker_year] * n,
                "t1d_diagnosis_date": dates,
            },
            schema={
                "patient_id": pl.String,
                "file_name": pl.String,
                "tracker_year": pl.Int32,
                "t1d_diagnosis_date": pl.Date,
            },
        )

    def test_converts_a_buddhist_year_to_gregorian(self, collector):

        result = _convert_buddhist_era_dates(self._df([date(2567, 11, 11)]))

        assert result["t1d_diagnosis_date"].to_list() == [date(2024, 11, 11)]
        assert len(collector) == 1
        err = collector.findings[0]
        assert err.error_code == "buddhist_era_converted"
        assert err.column == "t1d_diagnosis_date"
        assert err.original_value == "2567-11-11"

    def test_leaves_a_gregorian_date_untouched(self, collector):

        result = _convert_buddhist_era_dates(self._df([date(2024, 3, 1), None]))

        assert result["t1d_diagnosis_date"].to_list() == [date(2024, 3, 1), None]
        assert len(collector) == 0

    def test_converts_a_year_that_predates_its_tracker(self, collector):
        """A diagnosis or screening date legitimately predates its tracker, so
        patient needs no lower band at all -- 2022 Hat Yai's 2560-01-01 becomes
        2017-01-01, which ticket 40 independently derived from that patient's
        own D.O.B., recruitment and age at diagnosis."""

        result = _convert_buddhist_era_dates(self._df([date(2560, 1, 1)], tracker_year=2022))

        assert result["t1d_diagnosis_date"].to_list() == [date(2017, 1, 1)]

    def test_leaves_a_year_that_still_lands_in_the_future(self, collector):
        """3035 and 5025 (2025 CDA, 2025 Surat Thani) decode to 2492 and 4482 --
        no calendar makes those a recorded date, so they stay for _validate_dates
        to sentinel and become source-defect findings instead."""

        result = _convert_buddhist_era_dates(
            self._df([date(3035, 3, 1), date(5025, 5, 19)], tracker_year=2025)
        )

        assert result["t1d_diagnosis_date"].to_list() == [date(3035, 3, 1), date(5025, 5, 19)]
        assert len(collector) == 0

    def test_leaves_a_leap_day_that_does_not_exist_once_shifted(self, collector):
        """543 is not a multiple of 4, so a BE leap day can land on a non-leap
        Gregorian year. Converting would have to invent a date, so the cell is
        left for the ordinary implausible-date handling."""

        result = _convert_buddhist_era_dates(self._df([date(2568, 2, 29)], tracker_year=2025))

        assert result["t1d_diagnosis_date"].to_list() == [date(2568, 2, 29)]
        assert len(collector) == 0

    def test_leaves_the_parse_failure_sentinel_alone(self, collector):

        result = _convert_buddhist_era_dates(self._df([date(9999, 9, 9)]))

        assert result["t1d_diagnosis_date"].to_list() == [date(9999, 9, 9)]
        assert len(collector) == 0

    def test_conversion_runs_before_the_future_date_sentinel(self):
        """The whole point: end to end, a Buddhist-era cell must reach output as
        a date rather than as 9999-09-09."""
        df = self._df([date(2567, 11, 11)])

        result = _validate_dates(_convert_buddhist_era_dates(df))

        assert result["t1d_diagnosis_date"].to_list() == [date(2024, 11, 11)]


class TestAgeFromDobBranchOrder:
    """A negative calculated age is a workbook defect whether or not the age
    cell was filled in.

    The empty-age branch used to be tested first, so a row with *both* an empty
    age and a date of birth after the visit reported ``age_derived_from_dob``
    -- a recovery -- and published the negative number. One such row exists in
    the real data: "Age missing, calculated from DOB as -1".
    """

    def test_an_empty_age_with_a_bad_dob_is_a_defect_not_a_recovery(self, tmp_path):
        df = pl.DataFrame(
            {
                "patient_id": ["KH_QD001"],
                "file_name": ["2024_CDA A4D Tracker"],
                "age": [None],
                "dob": [date(2025, 6, 1)],
                "tracker_year": [2024],
                "tracker_month": [1],
            }
        )

        with tracker_context("2024_CDA A4D Tracker", "patient", tmp_path) as collector:
            _fix_age_from_dob(df)

        assert [f.error_code for f in collector.findings] == ["age_negative_from_dob"]

    def test_an_empty_age_with_a_sound_dob_is_still_a_recovery(self, tmp_path):
        df = pl.DataFrame(
            {
                "patient_id": ["KH_QD001"],
                "file_name": ["2024_CDA A4D Tracker"],
                "age": [None],
                "dob": [date(2010, 6, 1)],
                "tracker_year": [2024],
                "tracker_month": [1],
            }
        )

        with tracker_context("2024_CDA A4D Tracker", "patient", tmp_path) as collector:
            _fix_age_from_dob(df)

        assert [f.error_code for f in collector.findings] == ["age_derived_from_dob"]


class TestDiagnosisAgeNegativeFromDob:
    """A diagnosis recorded before the patient was born is a workbook defect,
    and it must be reported whether or not the age cell was filled in.

    ``_fix_age_from_dob`` reports the same contradiction on the *visit* age as
    ``age_negative_from_dob``. On the diagnosis age it was met silently: the
    derivation published ``None`` (ticket 52) and a recorded age was kept
    untouched, so eight patients across seven real trackers carried the
    contradiction with nothing said about it (ticket 73).
    """

    def _df(self, recorded_age: int | None) -> pl.DataFrame:
        return pl.DataFrame(
            {
                "patient_id": ["MY_QE025"],
                "file_name": ["2024_Putrajaya Hospital A4D Tracker"],
                "dob": [date(2021, 5, 5)],
                "t1d_diagnosis_date": [date(2014, 6, 20)],
                "t1d_diagnosis_age": pl.Series([recorded_age], dtype=pl.Int32),
            }
        )

    def test_an_empty_age_reports_the_contradiction(self, tmp_path):
        with tracker_context("2024_Putrajaya", "patient", tmp_path) as collector:
            result = _fix_t1d_diagnosis_age(self._df(None))

        assert [f.error_code for f in collector.findings] == ["diagnosis_age_negative_from_dob"]
        assert result["t1d_diagnosis_age"].to_list() == [None]

    def test_a_recorded_age_is_reported_and_kept(self, tmp_path):
        """The recorded age is a plausible clinic-entered number; the suspect
        evidence is the date pair. Reporting it does not licence discarding it
        (ticket 73)."""
        with tracker_context("2024_Putrajaya", "patient", tmp_path) as collector:
            result = _fix_t1d_diagnosis_age(self._df(7))

        assert [f.error_code for f in collector.findings] == ["diagnosis_age_negative_from_dob"]
        assert result["t1d_diagnosis_age"].to_list() == [7]

    def test_sound_dates_report_nothing(self, tmp_path):
        df = pl.DataFrame(
            {
                "patient_id": ["MY_QE026"],
                "file_name": ["2024_Putrajaya Hospital A4D Tracker"],
                "dob": [date(2010, 1, 1)],
                "t1d_diagnosis_date": [date(2015, 6, 20)],
                "t1d_diagnosis_age": pl.Series([None], dtype=pl.Int32),
            }
        )

        with tracker_context("2024_Putrajaya", "patient", tmp_path) as collector:
            result = _fix_t1d_diagnosis_age(df)

        assert len(collector) == 0
        assert result["t1d_diagnosis_age"].to_list() == [5]
