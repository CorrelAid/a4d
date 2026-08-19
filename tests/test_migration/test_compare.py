"""Tests for the R-vs-Python output comparison (ticket 15)."""

import datetime
import functools

import polars as pl

from a4d.clean.schema_product import get_product_data_schema
from a4d.migration.compare import (
    DERIVED_RUNNING_TOTAL_CLASSIFIERS,
    EXCEL_FORMULA_ERROR_CLASSIFIERS,
    GROUP_INVARIANT_PRODUCT_COLUMNS,
    PATIENT_AGE_FROM_BARE_YEAR_CLASSIFIERS,
    PATIENT_BARE_YEAR_CLASSIFIERS,
    PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS,
    PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    PATIENT_INSULIN_SUBTYPE_CLASSIFIERS,
    PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS,
    PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS,
    PATIENT_MERGED_SUBVALUE_TRIM_CLASSIFIERS,
    PATIENT_NA_UNITE_PADDING_CLASSIFIERS,
    PATIENT_NON_LATIN_HEADER_CLASSIFIERS,
    PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    PATIENT_RICHTEXT_SPACE_CLASSIFIERS,
    PATIENT_SCREENING_SELECTION_CLASSIFIERS,
    PATIENT_UNICODE_SANITIZER_CLASSIFIERS,
    PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS,
    PATIENT_YMD_FIRST_CLASSIFIERS,
    PRODUCT_CATEGORY_CLASSIFIERS,
    PRODUCT_ENTRY_DATE_CLASSIFIERS,
    PRODUCT_ROW_ORDER_CLASSIFIERS,
    PYTHON_CANONICAL_LABEL_CLASSIFIERS,
    R_DATE_ERROR_SENTINEL_CLASSIFIERS,
    R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS,
    ROW_ORDINAL_COL,
    SENTINEL_DATE,
    STRAY_DATE_CLASSIFIERS,
    STRAY_DATE_ZEROED_CLASSIFIERS,
    WIDE_FORMAT_FRAGMENT_CLASSIFIERS,
    CategoricalOverlap,
    CellMismatch,
    ColumnsResult,
    Delta,
    DirectoryComparison,
    FileComparison,
    IdOverlapResult,
    RowKeyOverlap,
    ShapeResult,
    TotalsMismatch,
    add_row_ordinal,
    align_duplicate_rows,
    build_mismatch_rows,
    build_summary_rows,
    classify,
    classify_column_divergence,
    compare_categorical_overlap,
    compare_cells,
    compare_columns,
    compare_directory,
    compare_id_overlap,
    compare_row_key_overlap,
    compare_shape,
    compare_totals,
    compute_deltas,
    normalize_boolean_literal_column,
    normalize_date_column,
    normalize_numeric_column,
    normalize_whitespace_column,
    numeric_normalize_targets,
    snapshot_from_summary,
    summarize_directory,
    whitespace_normalize_targets,
)


class TestNormalizeDateColumn:
    def test_parses_excel_serial_string(self):
        df = pl.DataFrame({"product_entry_date": ["42872.0"]})

        result = normalize_date_column(df, "product_entry_date")

        assert result["product_entry_date"].to_list() == [datetime.date(2017, 5, 17)]

    def test_parses_excel_serial_string_without_decimal(self):
        df = pl.DataFrame({"product_entry_date": ["46023"]})

        result = normalize_date_column(df, "product_entry_date")

        assert result["product_entry_date"].to_list() == [datetime.date(2026, 1, 1)]

    def test_parses_iso_datetime_string_to_the_same_date(self):
        r_df = pl.DataFrame({"product_entry_date": ["42872.0"]})
        py_df = pl.DataFrame({"product_entry_date": ["2017-05-17 00:00:00"]})

        r_result = normalize_date_column(r_df, "product_entry_date")
        py_result = normalize_date_column(py_df, "product_entry_date")

        assert r_result["product_entry_date"].to_list() == py_result["product_entry_date"].to_list()

    def test_passes_through_null(self):
        df = pl.DataFrame({"product_entry_date": [None]}, schema={"product_entry_date": pl.Utf8})

        result = normalize_date_column(df, "product_entry_date")

        assert result["product_entry_date"].to_list() == [None]

    def test_falls_back_to_sentinel_date_on_unparseable_text(self):
        df = pl.DataFrame({"product_entry_date": ["04-May-20026"]})

        result = normalize_date_column(df, "product_entry_date")

        assert result["product_entry_date"].to_list() == [SENTINEL_DATE]

    def test_is_a_no_op_when_the_column_is_absent(self):
        df = pl.DataFrame({"other": [1, 2]})

        result = normalize_date_column(df, "product_entry_date")

        assert result.columns == ["other"]


class TestNormalizeNumericColumn:
    def test_parses_numeric_strings_to_float(self):
        df = pl.DataFrame({"product_balance": ["9.300000000000001"]})

        result = normalize_numeric_column(df, "product_balance")

        assert result["product_balance"].to_list() == [9.300000000000001]

    def test_same_float_from_different_string_representations_compare_equal(self):
        r_df = pl.DataFrame({"product_balance": ["9.300000000000001"]})
        py_df = pl.DataFrame({"product_balance": ["9.3"]})

        r_result = normalize_numeric_column(r_df, "product_balance")
        py_result = normalize_numeric_column(py_df, "product_balance")

        assert r_result["product_balance"][0] == py_result["product_balance"][0]

    def test_passes_through_null(self):
        df = pl.DataFrame({"product_balance": [None]}, schema={"product_balance": pl.Utf8})

        result = normalize_numeric_column(df, "product_balance")

        assert result["product_balance"].to_list() == [None]

    def test_leaves_non_numeric_text_unchanged(self):
        df = pl.DataFrame({"product_units_received": ["START BALANCE"]})

        result = normalize_numeric_column(df, "product_units_received")

        assert result["product_units_received"].to_list() == ["START BALANCE"]

    def test_is_a_no_op_when_the_column_is_absent(self):
        df = pl.DataFrame({"other": [1, 2]})

        result = normalize_numeric_column(df, "product_balance")

        assert result.columns == ["other"]


class TestNumericNormalizeTargets:
    def test_includes_a_patient_list_join_suffix_copy(self):
        df = pl.DataFrame({"patient_id": ["A"], "fbg_baseline_mg.static": ["93.6"]})

        assert "fbg_baseline_mg.static" in numeric_normalize_targets(df, exclude=["patient_id"])

    def test_includes_a_column_the_cleaned_schema_types_as_string(self):
        df = pl.DataFrame(
            {"patient_id": ["A"], "complication_screening_kidney_test_value": ["9.2"]}
        )

        targets = numeric_normalize_targets(df, exclude=["patient_id"])

        assert "complication_screening_kidney_test_value" in targets

    def test_excludes_the_row_alignment_key_columns(self):
        df = pl.DataFrame({"patient_id": ["A"], "sheet_name": ["Jul24"], "weight": ["31.5"]})

        targets = numeric_normalize_targets(df, exclude=["patient_id", "sheet_name"])

        assert targets == ["weight"]

    def test_excludes_synthetic_join_helper_columns(self):
        df = pl.DataFrame({"__row_ordinal": [1], "weight": ["31.5"]})

        assert numeric_normalize_targets(df, exclude=[]) == ["weight"]


class TestWhitespaceNormalizeTargets:
    def test_includes_a_raw_only_column_absent_from_the_cleaned_schema(self):
        df = pl.DataFrame({"patient_id": ["A"], "dm_complications": ["Kidney \r\nDamage"]})

        assert "dm_complications" in whitespace_normalize_targets(df, exclude=["patient_id"])

    def test_includes_a_column_the_cleaned_schema_types_as_numeric(self):
        df = pl.DataFrame({"patient_id": ["A"], "insulin_injections": ["  "]})

        assert "insulin_injections" in whitespace_normalize_targets(df, exclude=["patient_id"])

    def test_excludes_non_string_columns(self):
        df = pl.DataFrame({"weight": [31.5], "edu_occ": ["college "]})

        assert whitespace_normalize_targets(df, exclude=[]) == ["edu_occ"]

    def test_excludes_synthetic_join_helper_columns(self):
        df = pl.DataFrame({"__key_patient_id": ["A"], "edu_occ": ["college "]})

        assert whitespace_normalize_targets(df, exclude=[]) == ["edu_occ"]


class TestNormalizeWhitespaceColumn:
    def test_strips_leading_and_trailing_whitespace(self):
        df = pl.DataFrame({"product": ["WIZ Twist Lancets (25s)\t"]})

        result = normalize_whitespace_column(df, "product")

        assert result["product"].to_list() == ["WIZ Twist Lancets (25s)"]

    def test_r_and_python_representations_compare_equal_after_strip(self):
        r_df = pl.DataFrame({"product_remarks": ["Remote"]})
        py_df = pl.DataFrame({"product_remarks": ["Remote "]})

        r_result = normalize_whitespace_column(r_df, "product_remarks")
        py_result = normalize_whitespace_column(py_df, "product_remarks")

        assert r_result["product_remarks"].to_list() == py_result["product_remarks"].to_list()

    def test_passes_through_null(self):
        df = pl.DataFrame({"product": [None]}, schema={"product": pl.Utf8})

        result = normalize_whitespace_column(df, "product")

        assert result["product"].to_list() == [None]

    def test_normalizes_crlf_line_endings_to_lf(self):
        r_df = pl.DataFrame({"product": ["Accu-Chek Instant Forward \r\nGlucometer Set"]})
        py_df = pl.DataFrame({"product": ["Accu-Chek Instant Forward \nGlucometer Set"]})

        r_result = normalize_whitespace_column(r_df, "product")
        py_result = normalize_whitespace_column(py_df, "product")

        assert r_result["product"].to_list() == py_result["product"].to_list()

    def test_whitespace_only_cell_normalizes_to_null(self):
        col = "product_received_from"
        r_df = pl.DataFrame({col: [None]}, schema={col: pl.Utf8})
        py_df = pl.DataFrame({col: [" "]})

        r_result = normalize_whitespace_column(r_df, col)
        py_result = normalize_whitespace_column(py_df, col)

        assert r_result[col].to_list() == py_result[col].to_list()

    def test_is_a_no_op_when_the_column_is_absent(self):
        df = pl.DataFrame({"other": [1, 2]})

        result = normalize_whitespace_column(df, "product")

        assert result.columns == ["other"]


class TestNormalizeBooleanLiteralColumn:
    def test_r_and_python_boolean_spellings_compare_equal(self):
        r_df = pl.DataFrame({"clinic_visit": ["FALSE", "TRUE"]})
        py_df = pl.DataFrame({"clinic_visit": ["False", "True"]})

        r_result = normalize_boolean_literal_column(r_df, "clinic_visit")
        py_result = normalize_boolean_literal_column(py_df, "clinic_visit")

        assert r_result["clinic_visit"].to_list() == py_result["clinic_visit"].to_list()

    def test_leaves_ordinary_text_untouched(self):
        df = pl.DataFrame({"observations": ["Nil", "false alarm reported"]})

        result = normalize_boolean_literal_column(df, "observations")

        assert result["observations"].to_list() == ["Nil", "false alarm reported"]

    def test_passes_through_null(self):
        df = pl.DataFrame({"clinic_visit": [None]}, schema={"clinic_visit": pl.Utf8})

        result = normalize_boolean_literal_column(df, "clinic_visit")

        assert result["clinic_visit"].to_list() == [None]

    def test_is_a_no_op_when_the_column_is_absent(self):
        df = pl.DataFrame({"other": [1, 2]})

        assert normalize_boolean_literal_column(df, "clinic_visit").columns == ["other"]


class TestAddRowOrdinal:
    def test_assigns_sequential_ordinal_within_group(self):
        df = pl.DataFrame({"clinic_id": ["A", "A", "A", "B"], "value": [10, 20, 30, 40]})

        result, key_cols = add_row_ordinal(df, ["clinic_id"])

        assert key_cols == ["__key_clinic_id", "__row_ordinal"]
        assert result["__row_ordinal"].to_list() == [0, 1, 2, 0]

    def test_resets_ordinal_per_distinct_group_combination(self):
        df = pl.DataFrame(
            {
                "clinic_id": ["A", "A", "B", "B", "B"],
                "sheet": ["Jan", "Feb", "Jan", "Jan", "Feb"],
            }
        )

        result, key_cols = add_row_ordinal(df, ["clinic_id", "sheet"])

        assert key_cols == ["__key_clinic_id", "__key_sheet", "__row_ordinal"]
        assert result["__row_ordinal"].to_list() == [0, 0, 0, 1, 0]

    def test_strips_whitespace_for_the_join_key_but_not_the_original_column(self):
        r_df = pl.DataFrame({"sheet": ["May19 "]})
        py_df = pl.DataFrame({"sheet": ["May19"]})

        r_result, key_cols = add_row_ordinal(r_df, ["sheet"])
        py_result, _ = add_row_ordinal(py_df, ["sheet"])

        assert r_result["__key_sheet"].to_list() == py_result["__key_sheet"].to_list()
        assert r_result["sheet"].to_list() == ["May19 "]
        assert py_result["sheet"].to_list() == ["May19"]

    def test_leaves_non_string_group_columns_unstripped(self):
        df = pl.DataFrame({"year": [2019, 2019, 2020]})

        result, key_cols = add_row_ordinal(df, ["year"])

        assert result["__key_year"].to_list() == [2019, 2019, 2020]
        assert result["__row_ordinal"].to_list() == [0, 1, 0]

    def test_keys_as_null_when_group_column_is_missing_entirely(self):
        df = pl.DataFrame(schema={})

        result, key_cols = add_row_ordinal(df, ["clinic_id"])

        assert key_cols == ["__key_clinic_id", "__row_ordinal"]
        assert result.height == 0


class TestPatientOccurrenceOrdinalKey:
    """Ticket 45: patient keeps `patient_id` + `sheet_name` as its identity key
    and uses `add_row_ordinal` only to break ties within it.

    Product groups by `(clinic_id, product_sheet_name)`, so its ordinal is a
    purely positional key. Patient's natural key is sound in all but a handful
    of files, so grouping by the identity key itself keeps the identity check
    everywhere and disambiguates only where a source sheet lists the same
    patient twice.
    """

    PATIENT_KEY = ["patient_id", "sheet_name"]

    def _spliced_sheet(self) -> tuple[pl.DataFrame, pl.DataFrame]:
        """`2024_Vietnam National Children`'s `Jul24` shape: two lists spliced
        together, so a patient appears twice on one sheet with different data.
        """
        rows = {
            "patient_id": ["VN001", "VN002", "VN001"],
            "sheet_name": ["Jul24", "Jul24", "Jul24"],
            "weight": [30.0, 41.0, 55.0],
        }
        return pl.DataFrame(rows), pl.DataFrame(rows)

    def test_duplicate_identity_key_fans_out_without_the_ordinal(self):
        r_df, py_df = self._spliced_sheet()

        mismatches = compare_cells(r_df, py_df, key_cols=self.PATIENT_KEY)

        # VN001's two rows pair every way round; the two cross pairings compare
        # unrelated physical rows and report a difference that does not exist.
        assert sorted((m.r_value, m.py_value) for m in mismatches) == [(30.0, 55.0), (55.0, 30.0)]

    def test_ordinal_within_the_identity_key_pairs_duplicates_one_to_one(self):
        r_df, py_df = self._spliced_sheet()

        r_keyed, key_cols = add_row_ordinal(r_df, self.PATIENT_KEY)
        py_keyed, _ = add_row_ordinal(py_df, self.PATIENT_KEY)

        assert key_cols == ["__key_patient_id", "__key_sheet_name", ROW_ORDINAL_COL]
        assert compare_row_key_overlap(r_keyed, py_keyed, key_cols) == RowKeyOverlap(
            matched=3, r_unmatched=0, py_unmatched=0
        )
        assert compare_cells(r_keyed, py_keyed, key_cols=key_cols) == []

    def test_unique_keys_are_unaffected_by_the_ordinal(self):
        r_df = pl.DataFrame(
            {"patient_id": ["A", "B"], "sheet_name": ["Jan24", "Jan24"], "weight": [10.0, 20.0]}
        )
        py_df = pl.DataFrame(
            {"patient_id": ["B", "A"], "sheet_name": ["Jan24", "Jan24"], "weight": [20.0, 11.0]}
        )

        r_keyed, key_cols = add_row_ordinal(r_df, self.PATIENT_KEY)
        py_keyed, _ = add_row_ordinal(py_df, self.PATIENT_KEY)

        # Every ordinal is 0, so pairing is by identity exactly as before -- and
        # row order across the two sides still does not matter.
        assert r_keyed[ROW_ORDINAL_COL].to_list() == [0, 0]
        assert [
            (m.key["__key_patient_id"], m.r_value, m.py_value)
            for m in compare_cells(r_keyed, py_keyed, key_cols=key_cols)
        ] == [("A", 10.0, 11.0)]

    def test_duplicates_pair_by_content_not_by_position(self):
        """Within one patient-and-sheet group the row order carries no meaning,
        and the cleaned stage demonstrably reorders: R and Python emit
        `VN_VC007`'s two `Jul24` rows the other way round. Pairing by position
        there compares the wrong two copies.
        """
        r_df = pl.DataFrame(
            {
                "patient_id": ["VN007", "VN007"],
                "sheet_name": ["Jul24", "Jul24"],
                "weight": [30.0, 55.0],
                "hba1c": [7.0, 9.0],
            }
        )
        py_df = pl.DataFrame(
            {
                "patient_id": ["VN007", "VN007"],
                "sheet_name": ["Jul24", "Jul24"],
                "weight": [55.0, 30.0],
                "hba1c": [9.0, 7.1],
            }
        )

        r_keyed, py_keyed, key_cols = align_duplicate_rows(r_df, py_df, self.PATIENT_KEY)

        # Only the genuine hba1c difference survives; the swap does not become
        # four false mismatches.
        assert [
            (m.column, m.r_value, m.py_value)
            for m in compare_cells(r_keyed, py_keyed, key_cols=key_cols)
        ] == [("hba1c", 7.0, 7.1)]

    def test_position_is_kept_when_no_pairing_beats_it(self):
        """The tie-break only moves a row when the alternative is strictly
        better, so a group whose rows genuinely both changed is not permuted
        into looking like agreement."""
        r_df = pl.DataFrame(
            {"patient_id": ["A", "A"], "sheet_name": ["Jan24"] * 2, "weight": [30.0, 40.0]}
        )
        py_df = pl.DataFrame(
            {"patient_id": ["A", "A"], "sheet_name": ["Jan24"] * 2, "weight": [31.0, 41.0]}
        )

        r_keyed, py_keyed, key_cols = align_duplicate_rows(r_df, py_df, self.PATIENT_KEY)

        assert sorted(
            (m.r_value, m.py_value) for m in compare_cells(r_keyed, py_keyed, key_cols=key_cols)
        ) == [
            (30.0, 31.0),
            (40.0, 41.0),
        ]

    def test_unique_keys_and_uneven_groups_fall_back_to_position(self):
        r_df = pl.DataFrame(
            {"patient_id": ["A", "A", "B"], "sheet_name": ["Jan24"] * 3, "weight": [1.0, 2.0, 3.0]}
        )
        py_df = pl.DataFrame(
            {"patient_id": ["A", "B"], "sheet_name": ["Jan24"] * 2, "weight": [1.0, 3.0]}
        )

        r_keyed, py_keyed, key_cols = align_duplicate_rows(r_df, py_df, self.PATIENT_KEY)

        assert compare_row_key_overlap(r_keyed, py_keyed, key_cols) == RowKeyOverlap(
            matched=2, r_unmatched=1, py_unmatched=0
        )

    def test_a_patient_on_another_sheet_never_pairs(self):
        """Sheet is the data's monthly granularity, so it stays part of the key:
        the same patient's June and July rows must not be compared."""
        r_df = pl.DataFrame({"patient_id": ["A"], "sheet_name": ["Jun24"], "weight": [10.0]})
        py_df = pl.DataFrame({"patient_id": ["A"], "sheet_name": ["Jul24"], "weight": [10.0]})

        r_keyed, key_cols = add_row_ordinal(r_df, self.PATIENT_KEY)
        py_keyed, _ = add_row_ordinal(py_df, self.PATIENT_KEY)

        assert compare_row_key_overlap(r_keyed, py_keyed, key_cols) == RowKeyOverlap(
            matched=0, r_unmatched=1, py_unmatched=1
        )


class TestCompareShape:
    def test_match_when_row_counts_equal(self):
        r_df = pl.DataFrame({"a": [1, 2, 3]})
        py_df = pl.DataFrame({"a": [1, 2, 3]})

        result = compare_shape(r_df, py_df)

        assert result == ShapeResult(r_rows=3, py_rows=3, match=True)

    def test_no_match_when_row_counts_differ(self):
        r_df = pl.DataFrame({"a": [1, 2, 3]})
        py_df = pl.DataFrame({"a": [1, 2]})

        result = compare_shape(r_df, py_df)

        assert result == ShapeResult(r_rows=3, py_rows=2, match=False)


class TestCompareTotals:
    def test_no_mismatches_when_sums_match(self):
        r_df = pl.DataFrame({"balance": [1.0, 2.0, 3.0]})
        py_df = pl.DataFrame({"balance": [3.0, 2.0, 1.0]})

        assert compare_totals(r_df, py_df, numeric_cols=["balance"]) == []

    def test_flags_column_whose_sum_differs(self):
        r_df = pl.DataFrame({"balance": [1.0, 2.0, 3.0]})
        py_df = pl.DataFrame({"balance": [1.0, 2.0, 30.0]})

        result = compare_totals(r_df, py_df, numeric_cols=["balance"])

        assert result == [TotalsMismatch(column="balance", r_total=6.0, py_total=33.0)]

    def test_ignores_negligible_float_drift(self):
        r_df = pl.DataFrame({"balance": [0.1, 0.2]})
        py_df = pl.DataFrame({"balance": [0.1 + 1e-12, 0.2]})

        assert compare_totals(r_df, py_df, numeric_cols=["balance"]) == []

    def test_skips_a_column_missing_from_either_side(self):
        r_df = pl.DataFrame({"balance": [1.0]})
        py_df = pl.DataFrame({"balance": [1.0]})

        result = compare_totals(r_df, py_df, numeric_cols=["balance", "not_in_either"])

        assert result == []

    def test_skips_a_column_present_only_on_one_side(self):
        r_df = pl.DataFrame({"balance": [1.0], "only_r_has_this": [5.0]})
        py_df = pl.DataFrame({"balance": [1.0]})

        result = compare_totals(r_df, py_df, numeric_cols=["balance", "only_r_has_this"])

        assert result == []


class TestCompareColumns:
    def test_no_diff_when_columns_and_dtypes_match(self):
        r_df = pl.DataFrame({"a": [1], "b": ["x"]})
        py_df = pl.DataFrame({"a": [1], "b": ["x"]})

        result = compare_columns(r_df, py_df)

        assert result == ColumnsResult(only_in_r=[], only_in_py=[], dtype_mismatches=[])

    def test_flags_columns_present_in_only_one_side(self):
        r_df = pl.DataFrame({"a": [1], "b": ["x"]})
        py_df = pl.DataFrame({"a": [1], "c": ["y"]})

        result = compare_columns(r_df, py_df)

        assert result.only_in_r == ["b"]
        assert result.only_in_py == ["c"]

    def test_flags_dtype_mismatch_on_common_column(self):
        r_df = pl.DataFrame({"a": [1]}, schema={"a": pl.Int64})
        py_df = pl.DataFrame({"a": [1.0]}, schema={"a": pl.Float64})

        result = compare_columns(r_df, py_df)

        assert result.dtype_mismatches == [("a", pl.Int64, pl.Float64)]


class TestCompareIdOverlap:
    def test_no_diff_when_ids_match(self):
        r_df = pl.DataFrame({"patient_id": ["a", "b", "c"]})
        py_df = pl.DataFrame({"patient_id": ["c", "b", "a"]})

        result = compare_id_overlap(r_df, py_df, id_col="patient_id")

        assert result == IdOverlapResult(only_in_r=[], only_in_py=[], common_count=3)

    def test_flags_ids_present_on_only_one_side(self):
        r_df = pl.DataFrame({"patient_id": ["a", "b", "dropped"]})
        py_df = pl.DataFrame({"patient_id": ["a", "b", "new"]})

        result = compare_id_overlap(r_df, py_df, id_col="patient_id")

        assert result == IdOverlapResult(only_in_r=["dropped"], only_in_py=["new"], common_count=2)

    def test_ignores_nulls(self):
        r_df = pl.DataFrame({"product": ["a", None]}, schema={"product": pl.Utf8})
        py_df = pl.DataFrame({"product": ["a", None]}, schema={"product": pl.Utf8})

        result = compare_id_overlap(r_df, py_df, id_col="product")

        assert result == IdOverlapResult(only_in_r=[], only_in_py=[], common_count=1)

    def test_deduplicates_repeated_ids(self):
        r_df = pl.DataFrame({"product": ["a", "a", "b"]})
        py_df = pl.DataFrame({"product": ["a"]})

        result = compare_id_overlap(r_df, py_df, id_col="product")

        assert result == IdOverlapResult(only_in_r=["b"], only_in_py=[], common_count=1)


class TestCompareCategoricalOverlap:
    def test_no_mismatches_when_all_categorical_columns_agree(self):
        r_df = pl.DataFrame({"category": ["a", "b"], "status": ["x", "y"]})
        py_df = pl.DataFrame({"category": ["b", "a"], "status": ["y", "x"]})

        result = compare_categorical_overlap(r_df, py_df, categorical_cols=["category", "status"])

        assert result == []

    def test_flags_only_columns_with_unseen_values(self):
        r_df = pl.DataFrame({"category": ["a", "b"], "status": ["x", "y"]})
        py_df = pl.DataFrame({"category": ["a", "typo"], "status": ["x", "y"]})

        result = compare_categorical_overlap(r_df, py_df, categorical_cols=["category", "status"])

        assert result == [
            CategoricalOverlap(column="category", only_in_r=["b"], only_in_py=["typo"])
        ]

    def test_ignores_columns_not_listed(self):
        r_df = pl.DataFrame({"category": ["a"], "unrelated": ["z"]})
        py_df = pl.DataFrame({"category": ["a"], "unrelated": ["different"]})

        result = compare_categorical_overlap(r_df, py_df, categorical_cols=["category"])

        assert result == []

    def test_skips_a_column_missing_from_either_side(self):
        r_df = pl.DataFrame({"category": ["a"]})
        py_df = pl.DataFrame({"category": ["a"]})

        result = compare_categorical_overlap(
            r_df, py_df, categorical_cols=["category", "not_in_either"]
        )

        assert result == []

    def test_skips_a_column_present_only_on_one_side(self):
        r_df = pl.DataFrame({"category": ["a"], "only_r_has_this": ["x"]})
        py_df = pl.DataFrame({"category": ["a"]})

        result = compare_categorical_overlap(
            r_df, py_df, categorical_cols=["category", "only_r_has_this"]
        )

        assert result == []


class TestCompareRowKeyOverlap:
    def test_all_rows_matched_when_keys_align_1to1(self):
        r_df = pl.DataFrame({"id": [1, 2], "sheet": ["a", "b"]})
        py_df = pl.DataFrame({"id": [2, 1], "sheet": ["b", "a"]})

        result = compare_row_key_overlap(r_df, py_df, key_cols=["id", "sheet"])

        assert result == RowKeyOverlap(matched=2, r_unmatched=0, py_unmatched=0)

    def test_flags_rows_whose_key_never_appears_on_the_other_side(self):
        r_df = pl.DataFrame({"id": [1, 2]})
        py_df = pl.DataFrame({"id": [1, 3]})

        result = compare_row_key_overlap(r_df, py_df, key_cols=["id"])

        assert result == RowKeyOverlap(matched=1, r_unmatched=1, py_unmatched=1)

    def test_fan_out_excess_counts_as_unmatched_on_the_heavier_side(self):
        r_df = pl.DataFrame({"id": [1, 1, 1]})
        py_df = pl.DataFrame({"id": [1]})

        result = compare_row_key_overlap(r_df, py_df, key_cols=["id"])

        assert result == RowKeyOverlap(matched=1, r_unmatched=2, py_unmatched=0)


class TestCompareCells:
    def test_no_mismatches_when_matched_rows_equal(self):
        r_df = pl.DataFrame({"id": [1, 2], "balance": [10.0, 20.0]})
        py_df = pl.DataFrame({"id": [2, 1], "balance": [20.0, 10.0]})

        assert compare_cells(r_df, py_df, key_cols=["id"]) == []

    def test_flags_value_mismatch_on_common_column(self):
        r_df = pl.DataFrame({"id": [1], "balance": [10.0]})
        py_df = pl.DataFrame({"id": [1], "balance": [99.0]})

        result = compare_cells(r_df, py_df, key_cols=["id"])

        assert result == [
            CellMismatch(key={"id": 1}, column="balance", r_value=10.0, py_value=99.0)
        ]

    def test_null_status_mismatch_is_flagged(self):
        r_df = pl.DataFrame({"id": [1], "note": [None]}, schema={"id": pl.Int64, "note": pl.Utf8})
        py_df = pl.DataFrame({"id": [1], "note": ["x"]})

        result = compare_cells(r_df, py_df, key_cols=["id"])

        assert result == [CellMismatch(key={"id": 1}, column="note", r_value=None, py_value="x")]

    def test_ignores_float_drift_within_tolerance(self):
        r_df = pl.DataFrame({"id": [1], "balance": [0.1]})
        py_df = pl.DataFrame({"id": [1], "balance": [0.1 + 1e-12]})

        assert compare_cells(r_df, py_df, key_cols=["id"]) == []

    def test_only_diffs_rows_matched_on_key(self):
        r_df = pl.DataFrame({"id": [1, 2], "balance": [10.0, 999.0]})
        py_df = pl.DataFrame({"id": [1], "balance": [10.0]})

        assert compare_cells(r_df, py_df, key_cols=["id"]) == []

    def test_row_order_candidate_false_without_order_group_cols(self):
        r_df = pl.DataFrame({"grp": ["a", "a"], "id": [0, 1], "balance": [10.0, 20.0]})
        py_df = pl.DataFrame({"grp": ["a", "a"], "id": [0, 1], "balance": [20.0, 10.0]})

        result = compare_cells(r_df, py_df, key_cols=["grp", "id"])

        assert all(m.row_order_candidate is False for m in result)

    def test_row_order_candidate_true_when_value_present_elsewhere_in_group(self):
        # R's row 0 (10.0) matches Python's row 1 (10.0) within the same group --
        # a shifted-row pattern, not a genuine content divergence.
        r_df = pl.DataFrame({"grp": ["a", "a"], "id": [0, 1], "balance": [10.0, 999.0]})
        py_df = pl.DataFrame({"grp": ["a", "a"], "id": [0, 1], "balance": [20.0, 10.0]})

        result = compare_cells(r_df, py_df, key_cols=["grp", "id"], order_group_cols=["grp"])

        by_id = {m.key["id"]: m for m in result}
        assert by_id[0].row_order_candidate is True
        assert by_id[1].row_order_candidate is False

    def test_group_endpoint_matches_when_last_positional_row_agrees(self):
        """Ticket 36: a derived running total diverges on every intermediate
        row under a re-sort but still lands on the same closing value."""
        r_df = pl.DataFrame(
            {"grp": ["a"] * 3, ROW_ORDINAL_COL: [0, 1, 2], "balance": [10.0, 8.0, 5.0]}
        )
        py_df = pl.DataFrame(
            {"grp": ["a"] * 3, ROW_ORDINAL_COL: [0, 1, 2], "balance": [10.0, 7.0, 5.0]}
        )

        result = compare_cells(
            r_df, py_df, key_cols=["grp", ROW_ORDINAL_COL], order_group_cols=["grp"]
        )

        assert [m.group_endpoint_matches for m in result] == [True]

    def test_group_endpoint_matches_false_when_last_positional_row_differs(self):
        r_df = pl.DataFrame(
            {"grp": ["a"] * 3, ROW_ORDINAL_COL: [0, 1, 2], "balance": [10.0, 8.0, 43572.0]}
        )
        py_df = pl.DataFrame(
            {"grp": ["a"] * 3, ROW_ORDINAL_COL: [0, 1, 2], "balance": [10.0, 7.0, 5.0]}
        )

        result = compare_cells(
            r_df, py_df, key_cols=["grp", ROW_ORDINAL_COL], order_group_cols=["grp"]
        )

        assert all(m.group_endpoint_matches is False for m in result)

    def test_group_endpoint_matches_false_without_a_positional_ordinal(self):
        r_df = pl.DataFrame({"grp": ["a"], "id": [0], "balance": [10.0]})
        py_df = pl.DataFrame({"grp": ["a"], "id": [0], "balance": [999.0]})

        result = compare_cells(r_df, py_df, key_cols=["grp", "id"], order_group_cols=["grp"])

        assert all(m.group_endpoint_matches is False for m in result)

    def test_row_order_candidate_false_when_value_genuinely_absent_from_group(self):
        r_df = pl.DataFrame({"grp": ["a"], "id": [0], "balance": [10.0]})
        py_df = pl.DataFrame({"grp": ["a"], "id": [0], "balance": [999.0]})

        result = compare_cells(r_df, py_df, key_cols=["grp", "id"], order_group_cols=["grp"])

        assert result == [
            CellMismatch(
                key={"grp": "a", "id": 0},
                column="balance",
                r_value=10.0,
                py_value=999.0,
                row_order_candidate=False,
            )
        ]

    def test_row_order_candidate_scoped_to_own_group(self):
        r_df = pl.DataFrame({"grp": ["a", "b"], "id": [0, 0], "balance": [10.0, 10.0]})
        py_df = pl.DataFrame({"grp": ["a", "b"], "id": [0, 0], "balance": [999.0, 10.0]})

        result = compare_cells(r_df, py_df, key_cols=["grp", "id"], order_group_cols=["grp"])

        assert result == [
            CellMismatch(
                key={"grp": "a", "id": 0},
                column="balance",
                r_value=10.0,
                py_value=999.0,
                row_order_candidate=False,
            )
        ]


def _mismatch(r_value, py_value, column="product_entry_date"):
    return CellMismatch(key={"id": 1}, column=column, r_value=r_value, py_value=py_value)


class TestClassify:
    def test_sentinel_null_when_r_is_null_and_python_is_sentinel(self):
        mismatch = _mismatch(r_value=None, py_value=SENTINEL_DATE)

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "sentinel_null"

    def test_r_value_missing_when_r_is_null_and_python_parsed_a_real_date(self):
        mismatch = _mismatch(r_value=None, py_value=datetime.date(2021, 3, 10))

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "r_value_missing"

    def test_off_by_one_day_when_dates_are_one_day_apart(self):
        mismatch = _mismatch(
            r_value=datetime.date(2020, 11, 28), py_value=datetime.date(2020, 11, 29)
        )

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "off_by_one_day"

    def test_ce_typo_when_years_are_far_apart(self):
        mismatch = _mismatch(r_value=datetime.date(2565, 12, 24), py_value=SENTINEL_DATE)

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "ce_typo"

    def test_unclassified_when_no_classifier_matches(self):
        mismatch = _mismatch(r_value=datetime.date(2021, 1, 1), py_value=datetime.date(2021, 6, 1))

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "unclassified"

    def test_r_category_lookup_miss_when_r_is_null_and_python_has_a_category(self):
        mismatch = _mismatch(r_value=None, py_value="INSULIN", column="product_category")

        assert classify(mismatch, PRODUCT_CATEGORY_CLASSIFIERS) == "r_category_lookup_miss"

    def test_category_unclassified_when_no_classifier_matches(self):
        mismatch = _mismatch(r_value="INSULIN", py_value="TEST STRIPS", column="product_category")

        assert classify(mismatch, PRODUCT_CATEGORY_CLASSIFIERS) == "unclassified"

    def test_row_order_divergence_when_flagged_as_candidate(self):
        mismatch = CellMismatch(
            key={"id": 1},
            column="product_balance",
            r_value=10.0,
            py_value=999.0,
            row_order_candidate=True,
        )

        assert classify(mismatch, PRODUCT_ROW_ORDER_CLASSIFIERS) == "row_order_divergence"

    def test_row_order_unclassified_when_not_flagged_as_candidate(self):
        mismatch = CellMismatch(
            key={"id": 1},
            column="product_balance",
            r_value=10.0,
            py_value=999.0,
            row_order_candidate=False,
        )

        assert classify(mismatch, PRODUCT_ROW_ORDER_CLASSIFIERS) == "unclassified"

    def test_r_extraction_gap_when_r_is_null_and_python_has_a_date(self):
        mismatch = _mismatch(
            r_value=None, py_value=datetime.date(2025, 12, 1), column="recruitment_date"
        )

        assert classify(mismatch, PATIENT_R_EXTRACTION_GAP_CLASSIFIERS) == "r_extraction_gap"

    def test_screening_selection_dropped_when_r_keeps_only_the_first_selection(self):
        """Ticket 50, 2021 NPH Dec21 KH_NP006: AD84/AE84 are two "(Select)"
        sub-columns of one merged block; R's own raw output parks the second in
        ``complicationscreeningselect1`` and maps only the first."""
        mismatch = _mismatch(
            r_value="Dilated Eye Examination",
            py_value="Dilated Eye Examination,Foot Examination (Nerves)",
            column="complication_screening",
        )

        assert (
            classify(mismatch, PATIENT_SCREENING_SELECTION_CLASSIFIERS)
            == "r_duplicate_header_selection_dropped"
        )

    def test_screening_selection_unclassified_when_the_kept_selection_differs(self):
        """R's value must be Python's own first selection, not merely shorter."""
        mismatch = _mismatch(
            r_value="Foot Examination (Nerves)",
            py_value="Dilated Eye Examination,Foot Examination (Nerves)",
            column="complication_screening",
        )

        assert classify(mismatch, PATIENT_SCREENING_SELECTION_CLASSIFIERS) == "unclassified"

    def test_screening_selection_unclassified_when_python_adds_nothing(self):
        mismatch = _mismatch(
            r_value="Dilated Eye Examination",
            py_value="Dilated Eye Examination",
            column="complication_screening",
        )

        assert classify(mismatch, PATIENT_SCREENING_SELECTION_CLASSIFIERS) == "unclassified"

    def test_recruitment_date_unclassified_when_both_sides_null(self):
        mismatch = _mismatch(r_value=None, py_value=None, column="recruitment_date")

        assert classify(mismatch, PATIENT_R_EXTRACTION_GAP_CLASSIFIERS) == "unclassified"

    def test_r_validator_rejects_multivalue_when_r_is_undefined(self):
        mismatch = _mismatch(
            r_value="Undefined", py_value="Rapid-acting,Long-acting", column="insulin_subtype"
        )

        assert (
            classify(mismatch, PATIENT_INSULIN_SUBTYPE_CLASSIFIERS)
            == "r_validator_rejects_multivalue"
        )

    def test_insulin_subtype_unclassified_when_r_is_not_the_undefined_sentinel(self):
        mismatch = _mismatch(
            r_value="Long-acting", py_value="Rapid-acting", column="insulin_subtype"
        )

        assert classify(mismatch, PATIENT_INSULIN_SUBTYPE_CLASSIFIERS) == "unclassified"

    def test_stray_date_typed_cell_when_r_serial_matches_python_full_datetime(self):
        mismatch = _mismatch(
            r_value="43566", py_value="2019-04-11 00:00:00", column="product_units_received"
        )

        assert classify(mismatch, STRAY_DATE_CLASSIFIERS) == "openpyxl_date_typed_stray_cell"

    def test_stray_date_typed_cell_when_r_serial_hits_the_1900_leap_year_bug(self):
        # Excel (and openpyxl, matching it) treats 1900 as a leap year that
        # never existed -- serial 59 resolves to 1900-02-28, not 1900-02-27
        # (ticket 24, a real flagged row).
        mismatch = _mismatch(
            r_value="59", py_value="1900-02-28 00:00:00", column="product_units_received"
        )

        assert classify(mismatch, STRAY_DATE_CLASSIFIERS) == "openpyxl_date_typed_stray_cell"

    def test_stray_date_typed_cell_when_r_serial_matches_python_bare_time(self):
        mismatch = _mismatch(r_value="0", py_value="00:00:00", column="product_units_received")

        assert classify(mismatch, STRAY_DATE_CLASSIFIERS) == "openpyxl_date_typed_stray_cell"

    def test_stray_date_typed_cell_unclassified_when_values_are_genuinely_different(self):
        mismatch = _mismatch(r_value="5", py_value="7", column="product_units_received")

        assert classify(mismatch, STRAY_DATE_CLASSIFIERS) == "unclassified"

    def test_stray_date_typed_cell_unclassified_when_r_value_is_not_numeric(self):
        mismatch = _mismatch(
            r_value="START BALANCE", py_value="2019-04-11 00:00:00", column="product_units_received"
        )

        assert classify(mismatch, STRAY_DATE_CLASSIFIERS) == "unclassified"

    def test_derived_running_total_row_order_when_group_endpoint_matches(self):
        """Ticket 36: product_balance is recomputed as a running total, so it
        cannot travel with its row under a re-sort -- the order-independent
        evidence is the group's closing balance, not value membership."""
        mismatch = CellMismatch(
            key={"clinic_id": "MHS"},
            column="product_balance",
            r_value=310.0,
            py_value=306.0,
            group_endpoint_matches=True,
        )

        assert (
            classify(mismatch, DERIVED_RUNNING_TOTAL_CLASSIFIERS)
            == "derived_running_total_row_order"
        )

    def test_derived_running_total_unclassified_when_group_endpoint_differs(self):
        """A group whose closing balance disagrees is a real divergence, not a
        re-sort -- it must not be swept up by the same label."""
        mismatch = CellMismatch(
            key={"clinic_id": "SBY"},
            column="product_balance",
            r_value=43572.0,
            py_value=6.0,
            group_endpoint_matches=False,
        )

        assert classify(mismatch, DERIVED_RUNNING_TOTAL_CLASSIFIERS) == "unclassified"

    def test_python_future_date_sentinel_when_python_holds_the_error_sentinel(self):
        mismatch = _mismatch(r_value=datetime.date(2029, 8, 29), py_value=SENTINEL_DATE)

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "python_future_date_sentinel"

    def test_python_future_date_sentinel_unclassified_when_python_holds_a_real_date(self):
        mismatch = _mismatch(
            r_value=datetime.date(2029, 8, 29), py_value=datetime.date(2023, 8, 29)
        )

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) != "python_future_date_sentinel"

    def test_summary_residue_nulled_when_r_holds_a_tiny_serial_and_python_is_null(self):
        mismatch = _mismatch(r_value=datetime.date(1900, 1, 30), py_value=None)

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "summary_residue_nulled"

    def test_summary_residue_nulled_unclassified_when_r_holds_a_real_date(self):
        mismatch = _mismatch(r_value=datetime.date(2023, 8, 29), py_value=None)

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "unclassified"

    def test_stray_date_zeroed_when_r_holds_a_serial_and_python_cleaned_it_to_zero(self):
        """Ticket 36: the cleaned-stage face of STRAY_DATE_CLASSIFIERS' cause."""
        mismatch = _mismatch(r_value=43708.0, py_value=0.0, column="product_units_received")

        assert classify(mismatch, STRAY_DATE_ZEROED_CLASSIFIERS) == "stray_date_zeroed"

    def test_stray_date_zeroed_unclassified_when_python_is_a_real_quantity(self):
        mismatch = _mismatch(r_value=43708.0, py_value=12.0, column="product_units_received")

        assert classify(mismatch, STRAY_DATE_ZEROED_CLASSIFIERS) == "unclassified"

    def test_stray_date_zeroed_unclassified_when_r_value_is_a_plausible_quantity(self):
        """A real unit count must never be mistaken for a date serial."""
        mismatch = _mismatch(r_value=120.0, py_value=0.0, column="product_units_received")

        assert classify(mismatch, STRAY_DATE_ZEROED_CLASSIFIERS) == "unclassified"

    def test_stray_date_zeroed_unclassified_when_r_value_is_not_numeric(self):
        mismatch = _mismatch(r_value="START BALANCE", py_value=0.0, column="product_units_received")

        assert classify(mismatch, STRAY_DATE_ZEROED_CLASSIFIERS) == "unclassified"

    def test_wide_format_fragment_truncated_when_python_value_extends_r_value(self):
        mismatch = _mismatch(
            r_value="2(Error", py_value="2(Error-1)", column="product_units_released"
        )

        assert (
            classify(mismatch, WIDE_FORMAT_FRAGMENT_CLASSIFIERS) == "wide_format_fragment_truncated"
        )

    def test_wide_format_fragment_truncated_unclassified_when_values_are_equal(self):
        mismatch = _mismatch(r_value="7", py_value="7", column="product_units_released")

        assert classify(mismatch, WIDE_FORMAT_FRAGMENT_CLASSIFIERS) == "unclassified"

    def test_wide_format_fragment_truncated_unclassified_when_not_a_prefix_relation(self):
        mismatch = _mismatch(
            r_value="2 MM_MD023", py_value="3 MM_MD099", column="product_units_released"
        )

        assert classify(mismatch, WIDE_FORMAT_FRAGMENT_CLASSIFIERS) == "unclassified"

    def test_excel_formula_error_when_r_holds_the_error_string_and_python_is_null(self):
        mismatch = _mismatch(r_value="#DIV/0!", py_value=None, column="bmi")

        assert classify(mismatch, EXCEL_FORMULA_ERROR_CLASSIFIERS) == "excel_formula_error"

    def test_excel_formula_error_when_python_holds_the_error_string_and_r_is_null(self):
        """readxl nulls an error cell in a numerically-guessed column; Python keeps it."""
        mismatch = _mismatch(r_value=None, py_value="#DIV/0!", column="bmi")

        assert classify(mismatch, EXCEL_FORMULA_ERROR_CLASSIFIERS) == "excel_formula_error"

    def test_excel_formula_error_matches_every_seeded_excel_error_string(self):
        for error_string in ("#DIV/0!", "#VALUE!", "#NUM!", "#N/A", "#REF!", "#NAME?", "#NULL!"):
            mismatch = _mismatch(r_value=error_string, py_value=None, column="bmi")

            assert classify(mismatch, EXCEL_FORMULA_ERROR_CLASSIFIERS) == "excel_formula_error"

    def test_excel_formula_error_unclassified_when_both_sides_have_a_value(self):
        mismatch = _mismatch(r_value="#DIV/0!", py_value=0.0, column="bmi")

        assert classify(mismatch, EXCEL_FORMULA_ERROR_CLASSIFIERS) == "unclassified"

    def test_excel_formula_error_unclassified_when_neither_side_is_an_error_string(self):
        mismatch = _mismatch(r_value="9.3", py_value=None, column="bmi")

        assert classify(mismatch, EXCEL_FORMULA_ERROR_CLASSIFIERS) == "unclassified"

    def test_r_na_unite_padding_when_r_pads_absent_sub_columns_with_na(self):
        mismatch = _mismatch(
            r_value="JAN,NA,NA,NA,NA", py_value="JAN", column="complication_screening"
        )

        assert classify(mismatch, PATIENT_NA_UNITE_PADDING_CLASSIFIERS) == "r_na_unite_padding"

    def test_r_na_unite_padding_when_every_sub_column_is_absent(self):
        mismatch = _mismatch(
            r_value="NA,NA,NA,NA,NA", py_value=None, column="complication_screening"
        )

        assert classify(mismatch, PATIENT_NA_UNITE_PADDING_CLASSIFIERS) == "r_na_unite_padding"

    def test_r_na_unite_padding_when_several_sub_columns_are_populated(self):
        mismatch = _mismatch(
            r_value="NA,JAN,NA,FEB,NA", py_value="JAN,FEB", column="complication_screening"
        )

        assert classify(mismatch, PATIENT_NA_UNITE_PADDING_CLASSIFIERS) == "r_na_unite_padding"

    def test_r_na_unite_padding_when_python_trimmed_a_sub_value_before_merging(self):
        """Ticket 50, 2020 Kantha Bopha Dec20 KH_KB040: the padding cause and
        ticket 46's verified ``python_trims_merged_subvalue`` stack in one cell,
        so neither explained it while the parts were compared untrimmed."""
        mismatch = _mismatch(
            r_value="collection in January ,NA",
            py_value="collection in January",
            column="observations",
        )

        assert classify(mismatch, PATIENT_NA_UNITE_PADDING_CLASSIFIERS) == "r_na_unite_padding"

    def test_r_na_unite_padding_unclassified_when_the_surviving_values_differ(self):
        """Stripping R's padding must still leave a real difference unexplained."""
        mismatch = _mismatch(r_value="JAN,NA,NA", py_value="FEB", column="complication_screening")

        assert classify(mismatch, PATIENT_NA_UNITE_PADDING_CLASSIFIERS) == "unclassified"

    def test_r_na_unite_padding_unclassified_when_r_carries_no_na_token(self):
        mismatch = _mismatch(r_value="JAN", py_value="JAN,FEB", column="complication_screening")

        assert classify(mismatch, PATIENT_NA_UNITE_PADDING_CLASSIFIERS) == "unclassified"

    def test_r_richtext_space_dropped_on_a_value_split_across_formatting_runs(self):
        """2017 Yangon Feb17!L: the cell is a rich-text shared string whose
        middle run is the space alone."""
        mismatch = _mismatch(
            r_value="8.8(20.9.16)", py_value="8.8 (20.9.16)", column="hba1c_updated"
        )

        assert classify(mismatch, PATIENT_RICHTEXT_SPACE_CLASSIFIERS) == "r_drops_richtext_space"

    def test_r_richtext_space_dropped_in_free_text(self):
        mismatch = _mismatch(
            r_value="Unable tocontact since June'21",
            py_value="Unable to contact since June'21",
            column="observations",
        )

        assert classify(mismatch, PATIENT_RICHTEXT_SPACE_CLASSIFIERS) == "r_drops_richtext_space"

    def test_r_richtext_space_unclassified_when_r_is_the_side_with_more_spaces(self):
        """The opposite direction is Python's own sub-value trimming, not this."""
        mismatch = _mismatch(r_value="Normal ,No", py_value="Normal,No", column="observations")

        assert classify(mismatch, PATIENT_RICHTEXT_SPACE_CLASSIFIERS) == "unclassified"

    def test_r_richtext_space_unclassified_when_the_text_itself_differs(self):
        mismatch = _mismatch(
            r_value="8.8(20.9.16)", py_value="9.8 (20.9.16)", column="hba1c_updated"
        )

        assert classify(mismatch, PATIENT_RICHTEXT_SPACE_CLASSIFIERS) == "unclassified"

    def test_python_trims_merged_subvalue_when_r_keeps_the_source_trailing_space(self):
        mismatch = _mismatch(
            r_value="Normal ,Insulin", py_value="Normal,Insulin", column="observations"
        )

        assert (
            classify(mismatch, PATIENT_MERGED_SUBVALUE_TRIM_CLASSIFIERS)
            == "python_trims_merged_subvalue"
        )

    def test_python_trims_merged_subvalue_unclassified_without_a_merge_separator(self):
        mismatch = _mismatch(r_value="Normal ", py_value="Normal", column="observations")

        assert classify(mismatch, PATIENT_MERGED_SUBVALUE_TRIM_CLASSIFIERS) == "unclassified"

    def test_buddhist_era_typo_when_r_is_sentinel_and_python_has_an_implausible_be_year(self):
        mismatch = _mismatch(
            r_value=SENTINEL_DATE,
            py_value=datetime.date(2569, 6, 17),
            column="hba1c_updated_date",
        )

        assert classify(mismatch, PATIENT_BUDDHIST_ERA_CLASSIFIERS) == "buddhist_era_typo"

    def test_buddhist_era_typo_unclassified_when_python_year_is_a_plausible_gregorian_year(self):
        mismatch = _mismatch(
            r_value=SENTINEL_DATE,
            py_value=datetime.date(2026, 6, 17),
            column="hba1c_updated_date",
        )

        assert classify(mismatch, PATIENT_BUDDHIST_ERA_CLASSIFIERS) == "unclassified"

    def test_buddhist_era_typo_when_python_is_the_sentinelling_side(self):
        """blood_pressure_updated reverses the direction at the cleaned stage:
        R carries the BE year through, Python's future-date guard sentinels it.
        """
        mismatch = _mismatch(
            r_value=datetime.date(2569, 4, 24),
            py_value=SENTINEL_DATE,
            column="blood_pressure_updated",
        )

        assert classify(mismatch, PATIENT_BUDDHIST_ERA_CLASSIFIERS) == "buddhist_era_typo"

    def test_buddhist_era_typo_unclassified_when_r_is_not_the_sentinel(self):
        mismatch = _mismatch(
            r_value=datetime.date(2026, 6, 17),
            py_value=datetime.date(2569, 6, 17),
            column="hba1c_updated_date",
        )

        assert classify(mismatch, PATIENT_BUDDHIST_ERA_CLASSIFIERS) == "unclassified"


class TestCompareDirectory:
    def test_matched_file_gets_a_full_comparison(self):
        r_frames = {"a.parquet": pl.DataFrame({"id": [1], "balance": [10.0]})}
        py_frames = {"a.parquet": pl.DataFrame({"id": [1], "balance": [10.0]})}

        result = compare_directory(r_frames, py_frames, key_cols=["id"], numeric_cols=["balance"])

        assert result.files == [
            FileComparison(
                file_name="a.parquet",
                shape=ShapeResult(r_rows=1, py_rows=1, match=True),
                totals=[],
                columns=ColumnsResult(only_in_r=[], only_in_py=[], dtype_mismatches=[]),
                id_overlap=None,
                categorical_overlap=[],
                row_key_overlap=RowKeyOverlap(matched=1, r_unmatched=0, py_unmatched=0),
                cell_mismatches=[],
            )
        ]
        assert result.only_in_r == []
        assert result.only_in_py == []

    def test_computes_categorical_overlap_when_categorical_cols_given(self):
        r_frames = {"a.parquet": pl.DataFrame({"id": [1], "category": ["a"]})}
        py_frames = {"a.parquet": pl.DataFrame({"id": [1], "category": ["typo"]})}

        result = compare_directory(
            r_frames, py_frames, key_cols=["id"], categorical_cols=["category"]
        )

        assert result.files[0].categorical_overlap == [
            CategoricalOverlap(column="category", only_in_r=["a"], only_in_py=["typo"])
        ]

    def test_computes_id_overlap_when_id_col_given(self):
        r_frames = {"a.parquet": pl.DataFrame({"id": [1, 2], "balance": [10.0, 20.0]})}
        py_frames = {"a.parquet": pl.DataFrame({"id": [1, 3], "balance": [10.0, 30.0]})}

        result = compare_directory(r_frames, py_frames, key_cols=["id"], id_col="id")

        assert result.files[0].id_overlap == IdOverlapResult(
            only_in_r=[2], only_in_py=[3], common_count=1
        )

    def test_id_overlap_is_none_when_id_col_not_given(self):
        r_frames = {"a.parquet": pl.DataFrame({"id": [1]})}
        py_frames = {"a.parquet": pl.DataFrame({"id": [1]})}

        result = compare_directory(r_frames, py_frames, key_cols=["id"])

        assert result.files[0].id_overlap is None

    def test_flags_totals_mismatch_within_a_matched_file(self):
        r_frames = {"a.parquet": pl.DataFrame({"id": [1], "balance": [10.0]})}
        py_frames = {"a.parquet": pl.DataFrame({"id": [1], "balance": [999.0]})}

        result = compare_directory(r_frames, py_frames, key_cols=["id"], numeric_cols=["balance"])

        assert result.files[0].totals == [
            TotalsMismatch(column="balance", r_total=10.0, py_total=999.0)
        ]

    def test_flags_cell_mismatch_within_a_matched_file(self):
        r_frames = {"a.parquet": pl.DataFrame({"id": [1], "balance": [10.0]})}
        py_frames = {"a.parquet": pl.DataFrame({"id": [1], "balance": [99.0]})}

        result = compare_directory(r_frames, py_frames, key_cols=["id"])

        assert result.files[0].cell_mismatches == [
            CellMismatch(key={"id": 1}, column="balance", r_value=10.0, py_value=99.0)
        ]

    def test_tracks_files_present_on_only_one_side(self):
        r_frames = {
            "a.parquet": pl.DataFrame({"id": [1]}),
            "only_r.parquet": pl.DataFrame({"id": [1]}),
        }
        py_frames = {
            "a.parquet": pl.DataFrame({"id": [1]}),
            "only_py.parquet": pl.DataFrame({"id": [1]}),
        }

        result = compare_directory(r_frames, py_frames, key_cols=["id"])

        assert result.only_in_r == ["only_r.parquet"]
        assert result.only_in_py == ["only_py.parquet"]
        assert [f.file_name for f in result.files] == ["a.parquet"]


class TestBuildSummaryRows:
    def test_reports_per_column_and_per_cause_counts(self):
        comparison = DirectoryComparison(
            files=[
                FileComparison(
                    file_name="a.parquet",
                    shape=ShapeResult(r_rows=2, py_rows=2, match=True),
                    totals=[],
                    columns=ColumnsResult(only_in_r=[], only_in_py=[], dtype_mismatches=[]),
                    id_overlap=None,
                    categorical_overlap=[],
                    row_key_overlap=RowKeyOverlap(matched=2, r_unmatched=0, py_unmatched=0),
                    cell_mismatches=[
                        CellMismatch(
                            key={"id": 1},
                            column="product_entry_date",
                            r_value=None,
                            py_value=SENTINEL_DATE,
                        ),
                        CellMismatch(
                            key={"id": 2},
                            column="other_col",
                            r_value=1,
                            py_value=2,
                        ),
                    ],
                )
            ],
            only_in_r=["missing.parquet"],
            only_in_py=[],
        )

        summary = build_summary_rows(
            comparison, classifiers_by_column={"product_entry_date": PRODUCT_ENTRY_DATE_CLASSIFIERS}
        )

        assert {"column": "product_entry_date", "mismatches": 1} in summary["per_column"]
        assert {"column": "other_col", "mismatches": 1} in summary["per_column"]
        assert {
            "column": "product_entry_date",
            "cause": "sentinel_null",
            "mismatches": 1,
        } in summary["per_cause"]
        assert {
            "column": "other_col",
            "cause": "unclassified",
            "mismatches": 1,
        } in summary["per_cause"]
        assert summary["only_in_r"] == [{"file": "missing.parquet"}]
        assert summary["only_in_py"] == []


class TestSnapshotFromSummary:
    def test_reduces_to_column_and_cause_count_dicts(self):
        summary = {
            "per_column": [
                {"column": "product_entry_date", "mismatches": 559},
                {"column": "product_balance", "mismatches": 480},
            ],
            "per_cause": [
                {"column": "product_entry_date", "cause": "r_value_missing", "mismatches": 408},
            ],
            "only_in_r": [{"file": "x.parquet"}],
            "only_in_py": [],
        }

        snapshot = snapshot_from_summary(summary)

        assert snapshot == {
            "per_column": {"product_entry_date": 559, "product_balance": 480},
            "per_cause": {"product_entry_date|r_value_missing": 408},
        }

    def test_empty_summary_yields_empty_snapshot(self):
        summary = {"per_column": [], "per_cause": [], "only_in_r": [], "only_in_py": []}

        assert snapshot_from_summary(summary) == {"per_column": {}, "per_cause": {}}


class TestComputeDeltas:
    def test_only_reports_changed_keys(self):
        previous = {"a": 10, "b": 5, "c": 3}
        current = {"a": 10, "b": 2, "c": 3}

        deltas = compute_deltas(previous, current)

        assert deltas == [Delta(key="b", previous=5, current=2)]

    def test_key_missing_from_current_reads_as_resolved_to_zero(self):
        previous = {"product_sheet_name": 201}
        current = {}

        deltas = compute_deltas(previous, current)

        assert deltas == [Delta(key="product_sheet_name", previous=201, current=0)]

    def test_key_new_in_current_reads_as_regression_from_zero(self):
        previous = {}
        current = {"product_category": 214}

        deltas = compute_deltas(previous, current)

        assert deltas == [Delta(key="product_category", previous=0, current=214)]

    def test_no_deltas_when_snapshots_identical(self):
        snapshot = {"a": 1, "b": 2}

        assert compute_deltas(snapshot, snapshot) == []

    def test_deltas_sorted_by_key(self):
        previous = {"z": 1, "a": 1}
        current = {"z": 2, "a": 2}

        deltas = compute_deltas(previous, current)

        assert [d.key for d in deltas] == ["a", "z"]


class TestBuildMismatchRows:
    def _comparison(self):
        return DirectoryComparison(
            files=[
                FileComparison(
                    file_name="a.parquet",
                    shape=ShapeResult(r_rows=2, py_rows=2, match=True),
                    totals=[TotalsMismatch(column="balance", r_total=10.0, py_total=99.0)],
                    columns=ColumnsResult(only_in_r=[], only_in_py=[], dtype_mismatches=[]),
                    id_overlap=IdOverlapResult(only_in_r=["p1"], only_in_py=["p2"], common_count=1),
                    categorical_overlap=[
                        CategoricalOverlap(column="status", only_in_r=["x"], only_in_py=["y"])
                    ],
                    row_key_overlap=RowKeyOverlap(matched=1, r_unmatched=0, py_unmatched=0),
                    cell_mismatches=[
                        CellMismatch(
                            key={"id": 1},
                            column="product_entry_date",
                            r_value=None,
                            py_value=SENTINEL_DATE,
                        )
                    ],
                )
            ],
            only_in_r=[],
            only_in_py=[],
        )

    def test_id_overlap_rows_have_one_row_per_side_per_value(self):
        rows = build_mismatch_rows(self._comparison())

        assert rows["id_overlap"] == [
            {"file": "a.parquet", "side": "R only", "value": "p1"},
            {"file": "a.parquet", "side": "Python only", "value": "p2"},
        ]

    def test_categorical_overlap_rows_have_one_row_per_side_per_value(self):
        rows = build_mismatch_rows(self._comparison())

        assert rows["categorical_overlap"] == [
            {"file": "a.parquet", "column": "status", "side": "R only", "value": "x"},
            {"file": "a.parquet", "column": "status", "side": "Python only", "value": "y"},
        ]

    def test_row_key_overlap_rows_have_one_row_per_file(self):
        comparison = DirectoryComparison(
            files=[
                FileComparison(
                    file_name="a.parquet",
                    shape=ShapeResult(r_rows=3, py_rows=3, match=True),
                    totals=[],
                    columns=ColumnsResult(only_in_r=[], only_in_py=[], dtype_mismatches=[]),
                    id_overlap=None,
                    categorical_overlap=[],
                    row_key_overlap=RowKeyOverlap(matched=1, r_unmatched=2, py_unmatched=0),
                    cell_mismatches=[],
                )
            ],
            only_in_r=[],
            only_in_py=[],
        )

        rows = build_mismatch_rows(comparison)

        assert rows["row_key_overlap"] == [
            {"file": "a.parquet", "matched": 1, "r_unmatched": 2, "py_unmatched": 0}
        ]

    def test_totals_rows_include_the_diff(self):
        rows = build_mismatch_rows(self._comparison())

        assert rows["totals"] == [
            {
                "file": "a.parquet",
                "column": "balance",
                "r_total": 10.0,
                "py_total": 99.0,
                "diff": 89.0,
            }
        ]

    def test_cell_mismatch_rows_include_classified_cause(self):
        rows = build_mismatch_rows(
            self._comparison(),
            classifiers_by_column={"product_entry_date": PRODUCT_ENTRY_DATE_CLASSIFIERS},
        )

        assert rows["cell_mismatches"] == [
            {
                "file": "a.parquet",
                "key": "id=1",
                "column": "product_entry_date",
                "r_value": None,
                "py_value": SENTINEL_DATE,
                "cause": "sentinel_null",
            }
        ]

    def test_cell_mismatch_cause_is_unclassified_without_a_registry(self):
        rows = build_mismatch_rows(self._comparison())

        assert rows["cell_mismatches"][0]["cause"] == "unclassified"

    def test_column_divergence_rows_cover_existence_and_dtype(self):
        comparison = DirectoryComparison(
            files=[
                FileComparison(
                    file_name="a.parquet",
                    shape=ShapeResult(r_rows=1, py_rows=1, match=True),
                    totals=[],
                    columns=ColumnsResult(
                        only_in_r=["r_only"],
                        only_in_py=["py_only"],
                        dtype_mismatches=[("shared", pl.Int64, pl.Float64)],
                    ),
                    id_overlap=None,
                    categorical_overlap=[],
                    row_key_overlap=RowKeyOverlap(matched=1, r_unmatched=0, py_unmatched=0),
                    cell_mismatches=[],
                )
            ],
            only_in_r=[],
            only_in_py=[],
        )

        rows = build_mismatch_rows(comparison)

        assert rows["column_divergence"] == [
            {
                "file": "a.parquet",
                "column": "r_only",
                "kind": "only in R",
                "r_dtype": "",
                "py_dtype": "",
                "cause": "unclassified",
            },
            {
                "file": "a.parquet",
                "column": "py_only",
                "kind": "only in Python",
                "r_dtype": "",
                "py_dtype": "",
                "cause": "unclassified",
            },
            {
                "file": "a.parquet",
                "column": "shared",
                "kind": "dtype mismatch",
                "r_dtype": "Int64",
                "py_dtype": "Float64",
                "cause": "unclassified",
            },
        ]


class TestSummarizeDirectory:
    def _comparison(self):
        clean = FileComparison(
            file_name="clean.parquet",
            shape=ShapeResult(r_rows=2, py_rows=2, match=True),
            columns=ColumnsResult(only_in_r=[], only_in_py=[], dtype_mismatches=[]),
            totals=[],
            cell_mismatches=[],
            id_overlap=IdOverlapResult(only_in_r=[], only_in_py=[], common_count=2),
            categorical_overlap=[],
            row_key_overlap=RowKeyOverlap(matched=2, r_unmatched=0, py_unmatched=0),
        )
        dirty = FileComparison(
            file_name="dirty.parquet",
            shape=ShapeResult(r_rows=3, py_rows=2, match=False),
            columns=ColumnsResult(
                only_in_r=["a"], only_in_py=["b"], dtype_mismatches=[("c", "Int32", "Float64")]
            ),
            totals=[TotalsMismatch(column="c", r_total=1.0, py_total=2.0)],
            cell_mismatches=[CellMismatch(key={"id": 1}, column="c", r_value=1, py_value=2)],
            id_overlap=IdOverlapResult(only_in_r=["X"], only_in_py=["Y", "Z"], common_count=1),
            categorical_overlap=[
                CategoricalOverlap(column="s", only_in_r=["p"], only_in_py=[]),
            ],
            row_key_overlap=RowKeyOverlap(matched=1, r_unmatched=2, py_unmatched=1),
        )
        return DirectoryComparison(files=[clean, dirty], only_in_r=["gone.parquet"], only_in_py=[])

    def test_counts_files_affected_and_totals_per_measure(self):
        summary = summarize_directory(self._comparison())

        assert summary.files_compared == 2
        assert summary.shape_mismatch_files == 1
        assert summary.id_divergence == (1, 3)
        assert summary.column_divergence == (1, 3)
        assert summary.categorical_divergence == (1, 1)
        assert summary.totals_divergence == (1, 1)
        assert summary.row_key_divergence == (1, 3)
        assert summary.cell_divergence == (1, 1)
        assert summary.only_in_r == 1
        assert summary.only_in_py == 0

    def test_all_clean_directory_reports_zero_everywhere(self):
        comparison = self._comparison()
        clean_only = DirectoryComparison(files=[comparison.files[0]], only_in_r=[], only_in_py=[])

        summary = summarize_directory(clean_only)

        assert summary.files_compared == 1
        assert summary.shape_mismatch_files == 0
        assert summary.cell_divergence == (0, 0)
        assert summary.row_key_divergence == (0, 0)


@functools.cache
def _compare_outputs_module():
    """Cached: each exec of the script defines its own RowAlignment class, so
    two loads would make `is` comparisons between their members fail."""
    import importlib.util
    import sys
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts" / "compare_outputs.py"
    spec = importlib.util.spec_from_file_location("_compare_outputs_under_test", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestStageWiring:
    """Ticket 45: which columns a stage groups its row-alignment ordinal by
    decides whether the key still checks identity, so it is named per stage
    rather than inferred."""

    @staticmethod
    def _stages():
        return {stage.label: stage for stage in _compare_outputs_module().STAGES}

    def test_patient_stages_align_on_identity_with_the_ordinal_as_tiebreak(self):
        alignment = _compare_outputs_module().RowAlignment
        for label in ("Patient (raw)", "Patient (cleaned)"):
            stage = self._stages()[label]
            assert stage.ordinal_group_cols == ["patient_id", "sheet_name"]
            assert stage.alignment is alignment.IDENTITY

    def test_product_stages_align_positionally_within_a_sheet(self):
        alignment = _compare_outputs_module().RowAlignment
        for label in ("Product (raw)", "Product (cleaned)"):
            stage = self._stages()[label]
            assert stage.ordinal_group_cols == ["clinic_id", "product_sheet_name"]
            assert stage.alignment is alignment.POSITIONAL

    def test_row_order_divergence_detection_is_product_only(self):
        """`compare_cells`'s order_group_cols diagnostic asks whether a
        mismatched value appears elsewhere in its group -- meaningful for
        product, whose group is a whole sheet ordered differently by R
        (ticket 21), and noise for patient, whose group is one patient on one
        sheet."""
        stages = self._stages()

        assert [label for label, stage in stages.items() if stage.detect_row_order_divergence] == [
            "Product (raw)",
            "Product (cleaned)",
        ]


class TestClassifiersByColumnWiring:
    """Ticket 25: the script's column -> registry map is the single place a
    column can be silently under-classified.

    `product_units_released` carried only WIDE_FORMAT_FRAGMENT_CLASSIFIERS (a
    raw-stage-only cause, ticket 24) while every sibling column compared
    through the same positional row-alignment key also carried
    PRODUCT_ROW_ORDER_CLASSIFIERS -- leaving 2,144 cleaned-stage mismatches
    reported as `unclassified` even though the cause was already understood.
    """

    @staticmethod
    def _classifiers_by_column():
        return _compare_outputs_module().CLASSIFIERS_BY_COLUMN

    def test_every_positional_key_product_column_carries_row_order_classifier(self):
        """Product columns are aligned by ordinal position, so any within-group
        sort-order divergence surfaces on all of them -- none may omit it.

        Ticket 36: the column list is derived from the product schema rather
        than written out. The hand-written version this replaces named seven
        columns and omitted `product_entry_date`, which then reported 169
        cleaned-stage mismatches as `unclassified` for exactly the reason this
        test exists to prevent.
        """
        registries = self._classifiers_by_column()
        positional_columns = [
            column
            for column in get_product_data_schema()
            if column not in GROUP_INVARIANT_PRODUCT_COLUMNS
        ]

        missing = [
            column
            for column in positional_columns
            if not PRODUCT_ROW_ORDER_CLASSIFIERS.keys() <= registries.get(column, {}).keys()
        ]

        assert missing == []

    def test_units_released_row_order_mismatch_is_classified(self):
        registries = self._classifiers_by_column()
        mismatch = CellMismatch(
            key={"clinic_id": "MHS"},
            column="product_units_released",
            r_value=8.0,
            py_value=4.0,
            row_order_candidate=True,
        )

        assert classify(mismatch, registries["product_units_released"]) == "row_order_divergence"

    def test_entry_date_row_order_mismatch_is_classified(self):
        """Both sides hold a real date, so `r_value_missing` cannot fire: R's
        readxl nulled the *text*-formatted date cells in a mixed-type column,
        which drops R back to input-order sorting (ticket 36)."""
        registries = self._classifiers_by_column()
        mismatch = CellMismatch(
            key={"clinic_id": "VNC"},
            column="product_entry_date",
            r_value=datetime.date(2022, 7, 4),
            py_value=datetime.date(2022, 4, 20),
            row_order_candidate=True,
        )

        assert classify(mismatch, registries["product_entry_date"]) == "row_order_divergence"

    def test_units_received_stray_date_zeroed_is_classified(self):
        registries = self._classifiers_by_column()
        mismatch = CellMismatch(
            key={"clinic_id": "SBY"},
            column="product_units_received",
            r_value=43708.0,
            py_value=0.0,
            row_order_candidate=True,
        )

        assert classify(mismatch, registries["product_units_received"]) == "stray_date_zeroed"


class TestUntrimmedValidationClassifier:
    """Ticket 36: R sentinels a value for whitespace alone; Python recovers it."""

    def test_classified_when_r_holds_the_character_sentinel(self):
        mismatch = CellMismatch(key={"id": 1}, column="sex", r_value="Undefined", py_value="F")

        assert (
            classify(mismatch, PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS)
            == "r_validator_rejects_untrimmed"
        )

    def test_unclassified_when_both_sides_hold_real_but_different_values(self):
        mismatch = CellMismatch(key={"id": 1}, column="sex", r_value="M", py_value="F")

        assert classify(mismatch, PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS) == "unclassified"


class TestPatientInsulinTotalUnitsClassifier:
    """Ticket 29: R's insulin-column dedup drops TOTAL Insulin Units entirely."""

    def test_classified_when_r_is_null_and_python_has_the_value(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="insulin_total_units", r_value=None, py_value=20.0
        )

        assert classify(mismatch, PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS) == "r_insulin_dedup_drop"

    def test_unclassified_when_r_also_holds_a_value(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="insulin_total_units", r_value=18.0, py_value=20.0
        )

        assert classify(mismatch, PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS) == "unclassified"


class TestPatientJoinSuffixCollisionClassifier:
    """Ticket 29: R's join suffixes both sides on a column-name collision."""

    def test_classified_when_r_is_null_and_python_has_the_value(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="fbg_baseline_mg", r_value=None, py_value=126.0
        )

        assert (
            classify(mismatch, PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS)
            == "r_join_suffix_collision"
        )

    def test_unclassified_when_both_sides_hold_a_value(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="fbg_baseline_mg", r_value=100.0, py_value=126.0
        )

        assert classify(mismatch, PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS) == "unclassified"


class TestRNumericErrorSentinelClassifier:
    """Ticket 29: R sentinels an unusable source cell where Python nulls it."""

    def test_classified_when_r_holds_the_numeric_sentinel_and_python_is_null(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="hba1c_baseline", r_value=999999.0, py_value=None
        )

        assert (
            classify(mismatch, R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS) == "r_numeric_error_sentinel"
        )

    def test_classified_when_the_sentinel_arrives_as_text(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="hba1c_baseline", r_value="999999", py_value=None
        )

        assert (
            classify(mismatch, R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS) == "r_numeric_error_sentinel"
        )

    def test_unclassified_when_python_also_holds_a_value(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="hba1c_baseline", r_value=999999.0, py_value=7.5
        )

        assert classify(mismatch, R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_r_holds_an_ordinary_value(self):
        mismatch = CellMismatch(key={"id": 1}, column="hba1c_baseline", r_value=8.2, py_value=None)

        assert classify(mismatch, R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS) == "unclassified"


class TestPythonCanonicalLabelClassifier:
    """Ticket 29: Python collapses a retired spelling to its canonical label."""

    def test_classified_when_r_holds_a_declared_alias_of_pythons_value(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="status", r_value="Active - Remote", py_value="Active Remote"
        )

        assert classify(mismatch, PYTHON_CANONICAL_LABEL_CLASSIFIERS) == "python_canonical_label"

    def test_matches_case_insensitively(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="status", r_value="active-remote", py_value="Active Remote"
        )

        assert classify(mismatch, PYTHON_CANONICAL_LABEL_CLASSIFIERS) == "python_canonical_label"

    def test_unclassified_when_the_two_labels_are_genuinely_different_statuses(self):
        mismatch = CellMismatch(
            key={"id": 1}, column="status", r_value="Discontinued", py_value="Active"
        )

        assert classify(mismatch, PYTHON_CANONICAL_LABEL_CLASSIFIERS) == "unclassified"


class TestRDateErrorSentinelClassifier:
    """Ticket 38: R stamps its date sentinel on a cell recording an absence."""

    def test_classified_when_r_holds_the_date_sentinel_and_python_is_null(self):
        mismatch = CellMismatch(
            key={"id": 1},
            column="hospitalisation_date",
            r_value=datetime.date(9999, 9, 9),
            py_value=None,
        )

        assert classify(mismatch, R_DATE_ERROR_SENTINEL_CLASSIFIERS) == "r_date_error_sentinel"

    def test_classified_when_the_sentinel_arrives_as_a_datetime(self):
        mismatch = CellMismatch(
            key={"id": 1},
            column="hospitalisation_date",
            r_value=datetime.datetime(9999, 9, 9),
            py_value=None,
        )

        assert classify(mismatch, R_DATE_ERROR_SENTINEL_CLASSIFIERS) == "r_date_error_sentinel"

    def test_unclassified_when_python_also_holds_a_date(self):
        mismatch = CellMismatch(
            key={"id": 1},
            column="hospitalisation_date",
            r_value=datetime.date(9999, 9, 9),
            py_value=datetime.date(2020, 3, 1),
        )

        assert classify(mismatch, R_DATE_ERROR_SENTINEL_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_r_holds_a_real_date(self):
        mismatch = CellMismatch(
            key={"id": 1},
            column="hospitalisation_date",
            r_value=datetime.date(2020, 3, 1),
            py_value=None,
        )

        assert classify(mismatch, R_DATE_ERROR_SENTINEL_CLASSIFIERS) == "unclassified"


class TestClassifyColumnDivergence:
    """Ticket 30: name the two structural causes of raw-stage column divergence."""

    def test_r_blank_header_artifact(self):
        """R's make.names turns a blank header cell into the string "NA."."""
        assert (
            classify_column_divergence("only in R", "na", set(), set()) == "r_blank_header_artifact"
        )
        assert (
            classify_column_divergence("only in R", "na10064", set(), set())
            == "r_blank_header_artifact"
        )
        assert (
            classify_column_divergence("only in R", "na1.static", set(), set())
            == "r_blank_header_artifact"
        )

    def test_real_r_column_name_is_not_a_blank_header_artifact(self):
        assert classify_column_divergence("only in R", "name", set(), set()) == "unclassified"
        assert (
            classify_column_divergence("only in R", "national_id", set(), set()) == "unclassified"
        )

    def test_name_sanitization_only(self):
        """Both sides carry the column; only the name spelling differs."""
        r_only = {"instantmeterreceiveddate"}
        py_only = {"INSTANT Meter Received Date"}

        assert (
            classify_column_divergence("only in R", "instantmeterreceiveddate", r_only, py_only)
            == "name_sanitization_only"
        )
        assert (
            classify_column_divergence(
                "only in Python", "INSTANT Meter Received Date", r_only, py_only
            )
            == "name_sanitization_only"
        )

    def test_unmatched_column_stays_unclassified(self):
        assert (
            classify_column_divergence("only in Python", "BGM A4D", {"na"}, {"BGM A4D"})
            == "unclassified"
        )

    def test_blank_header_artifact_wins_over_a_python_name_that_sanitizes_to_it(self):
        """A Python column literally named "NA" must not mask R's artifact."""
        assert (
            classify_column_divergence("only in R", "na", {"na"}, {"N/A"})
            == "r_blank_header_artifact"
        )


class TestNonLatinHeaderMiss:
    def test_flags_r_null_where_python_read_the_column(self):
        m = CellMismatch(
            key="__key_patient_id=TH_MK001",
            column="last_clinic_visit_date",
            r_value=None,
            py_value="44609",
        )

        assert PATIENT_NON_LATIN_HEADER_CLASSIFIERS["r_non_latin_header_miss"](m)

    def test_does_not_fire_when_both_sides_read_the_column(self):
        m = CellMismatch(
            key="__key_patient_id=TH_MK001",
            column="last_clinic_visit_date",
            r_value="44600",
            py_value="44609",
        )

        assert not PATIENT_NON_LATIN_HEADER_CLASSIFIERS["r_non_latin_header_miss"](m)


class TestPythonReadsBareYear:
    """Ticket 52: a bare four-digit year typed into a date cell."""

    def test_flags_the_year_r_read_as_a_1905_serial(self):
        # Sarawak Patient List!G10 holds 2011. R reads it as Excel serial
        # 2011 -> 1905-07-03; Python reads the year and resolves it to 1 Jan.
        m = CellMismatch(
            key="__key_patient_id=MY_SW001",
            column="t1d_diagnosis_date",
            r_value=datetime.date(1905, 7, 3),
            py_value=datetime.date(2011, 1, 1),
        )

        assert classify(m, PATIENT_BARE_YEAR_CLASSIFIERS) == "python_reads_bare_year"

    def test_flags_a_bare_birth_year(self):
        # 2018 Yangon Children's writes MM_YC005's D.O.B. as 2003.
        m = CellMismatch(
            key="__key_patient_id=MM_YC005",
            column="dob",
            r_value=datetime.date(1905, 6, 25),
            py_value=datetime.date(2003, 1, 1),
        )

        assert classify(m, PATIENT_BARE_YEAR_CLASSIFIERS) == "python_reads_bare_year"

    def test_ignores_a_first_of_january_r_did_not_read_as_that_serial(self):
        # Both sides parsed a real date; the serial arithmetic must not match.
        m = CellMismatch(
            key="__key_patient_id=MY_SW004",
            column="t1d_diagnosis_date",
            r_value=datetime.date(2012, 6, 16),
            py_value=datetime.date(2012, 1, 1),
        )

        assert classify(m, PATIENT_BARE_YEAR_CLASSIFIERS) == "unclassified"


class TestPythonAgeFromBareYear:
    """Ticket 52: the ages derived from a bare-year date."""

    def test_flags_an_age_on_a_row_carrying_a_bare_year_date(self):
        m = CellMismatch(
            key="__key_patient_id=MM_YC005",
            column="age",
            r_value=999999.0,
            py_value=15.0,
            row_has_bare_year_date=True,
        )

        assert classify(m, PATIENT_AGE_FROM_BARE_YEAR_CLASSIFIERS) == "python_age_from_bare_year"

    def test_ignores_the_same_shape_without_a_bare_year_date_on_the_row(self):
        m = CellMismatch(
            key="__key_patient_id=MM_YC099",
            column="age",
            r_value=999999.0,
            py_value=15.0,
        )

        assert classify(m, PATIENT_AGE_FROM_BARE_YEAR_CLASSIFIERS) == "unclassified"

    def test_compare_cells_sets_the_flag_across_the_whole_row(self):
        # dob carries the bare year; age is derived from it and must inherit
        # the flag even though its own values say nothing about a serial.
        r_df = pl.DataFrame(
            {
                "patient_id": ["MM_YC005"],
                "dob": [datetime.date(1905, 6, 25)],
                "age": [999999.0],
            }
        )
        py_df = pl.DataFrame(
            {
                "patient_id": ["MM_YC005"],
                "dob": [datetime.date(2003, 1, 1)],
                "age": [15.0],
            }
        )

        by_col = {m.column: m for m in compare_cells(r_df, py_df, ["patient_id"])}

        assert by_col["dob"].row_has_bare_year_date
        assert by_col["age"].row_has_bare_year_date


class TestRYmdFirstMisparse:
    """Ticket 51: R's parse_date_string tries "ymd" before "dmy", so a source
    string written D.M.YY is read year-first."""

    def test_flags_the_day_year_swap(self):
        # Source "30.1.18": Python reads 2018-01-30, R reads 2030-01-18.
        m = CellMismatch(
            key="__key_patient_id=MM_YC001",
            column="fbg_updated_date",
            r_value=datetime.date(2030, 1, 18),
            py_value=datetime.date(2018, 1, 30),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "r_ymd_first_misparse"

    def test_flags_the_swap_when_r_lands_in_the_past(self):
        # Source "5.9.17": R reads year 05 -> 2005-09-17, Python 2017-09-05.
        m = CellMismatch(
            key="__key_patient_id=MM_YC002",
            column="hba1c_updated_date",
            r_value=datetime.date(2005, 9, 17),
            py_value=datetime.date(2017, 9, 5),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "r_ymd_first_misparse"

    def test_accepts_datetime_as_well_as_date(self):
        m = CellMismatch(
            key="__key_patient_id=MM_YC001",
            column="fbg_updated_date",
            r_value=datetime.datetime(2030, 1, 18),
            py_value=datetime.datetime(2018, 1, 30),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "r_ymd_first_misparse"

    def test_unclassified_when_the_month_differs(self):
        m = CellMismatch(
            key="__key_patient_id=MM_YC001",
            column="fbg_updated_date",
            r_value=datetime.date(2030, 2, 18),
            py_value=datetime.date(2018, 1, 30),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_the_digits_are_not_a_swap(self):
        m = CellMismatch(
            key="__key_patient_id=MM_YC001",
            column="fbg_updated_date",
            r_value=datetime.date(2019, 1, 18),
            py_value=datetime.date(2018, 1, 30),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_the_dates_agree_on_the_day(self):
        """A same-day pair is not a swap even when the years happen to line up
        -- an unambiguous D.M.YY date (day 18, year 18) reads the same either
        way, so a difference on it has some other cause."""
        m = CellMismatch(
            key="__key_patient_id=MM_YC001",
            column="fbg_updated_date",
            r_value=datetime.date(2018, 1, 18),
            py_value=datetime.date(2018, 1, 18),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_a_side_is_the_sentinel(self):
        m = CellMismatch(
            key="__key_patient_id=MM_YC001",
            column="fbg_updated_date",
            r_value=SENTINEL_DATE,
            py_value=datetime.date(2018, 1, 30),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_a_side_is_null(self):
        m = CellMismatch(
            key="__key_patient_id=MM_YC001",
            column="fbg_updated_date",
            r_value=None,
            py_value=datetime.date(2018, 1, 30),
        )

        assert classify(m, PATIENT_YMD_FIRST_CLASSIFIERS) == "unclassified"


class TestPythonRejectsBeyondTrackerYear:
    """Ticket 51: Python's _validate_dates stamps the error sentinel on a date
    later than its tracker year; R has no such guard and carries it through."""

    def test_flags_a_date_later_than_the_sheet_year(self):
        m = CellMismatch(
            key={"__key_patient_id": "VN_VC002", "__key_sheet_name": "Jan22"},
            column="t1d_diagnosis_date",
            r_value=datetime.date(2023, 2, 16),
            py_value=SENTINEL_DATE,
        )

        assert classify(m, PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS) == (
            "python_rejects_beyond_tracker_year"
        )

    def test_reads_the_year_through_an_apostrophe_in_the_sheet_name(self):
        m = CellMismatch(
            key={"__key_patient_id": "VN_VC002", "__key_sheet_name": "Oct'22"},
            column="t1d_diagnosis_date",
            r_value=datetime.date(2023, 2, 16),
            py_value=SENTINEL_DATE,
        )

        assert classify(m, PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS) == (
            "python_rejects_beyond_tracker_year"
        )

    def test_unclassified_when_r_date_is_within_the_tracker_year(self):
        """The parse-failure half of the same symptom -- Python sentinels a
        value it could not read at all, which this cause does not explain."""
        m = CellMismatch(
            key={"__key_patient_id": "LA_MH001", "__key_sheet_name": "Jan21"},
            column="fbg_updated_date",
            r_value=datetime.date(2020, 9, 1),
            py_value=SENTINEL_DATE,
        )

        assert classify(m, PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_python_is_not_the_sentinelling_side(self):
        m = CellMismatch(
            key={"__key_patient_id": "VN_VC002", "__key_sheet_name": "Jan22"},
            column="t1d_diagnosis_date",
            r_value=SENTINEL_DATE,
            py_value=datetime.date(2023, 2, 16),
        )

        assert classify(m, PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_the_sheet_name_carries_no_year(self):
        m = CellMismatch(
            key={"__key_patient_id": "VN_VC002", "__key_sheet_name": "Patient List"},
            column="t1d_diagnosis_date",
            r_value=datetime.date(2023, 2, 16),
            py_value=SENTINEL_DATE,
        )

        assert classify(m, PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS) == "unclassified"


class TestRUnicodeSanitizerRejectsAccent:
    """Ticket 51: R's `[^[:alnum:]]` keeps accented letters, so a misaccented
    spelling misses its allowed value; Python's `[^a-z0-9]` folds it home."""

    def test_flags_an_accented_canonical_value_r_called_undefined(self):
        m = CellMismatch(
            key={"patient_id": "VN_VC020", "sheet_name": "Jan22"},
            column="province",
            r_value="Undefined",
            py_value="Thái Nguyên",
        )

        assert classify(m, PATIENT_UNICODE_SANITIZER_CLASSIFIERS) == (
            "r_unicode_sanitizer_rejects_accent"
        )

    def test_unclassified_when_the_canonical_value_is_plain_ascii(self):
        """An unaccented canonical value cannot have been rejected for its
        accents, so some other cause is at work."""
        m = CellMismatch(
            key={"patient_id": "TH_BK001", "sheet_name": "Jan22"},
            column="province",
            r_value="Undefined",
            py_value="Bangkok",
        )

        assert classify(m, PATIENT_UNICODE_SANITIZER_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_r_did_not_sentinel_the_value(self):
        m = CellMismatch(
            key={"patient_id": "VN_VC020", "sheet_name": "Jan22"},
            column="province",
            r_value="Hà Nội",
            py_value="Thái Nguyên",
        )

        assert classify(m, PATIENT_UNICODE_SANITIZER_CLASSIFIERS) == "unclassified"

    def test_unclassified_when_python_has_nothing(self):
        m = CellMismatch(
            key={"patient_id": "VN_VC020", "sheet_name": "Jan22"},
            column="province",
            r_value="Undefined",
            py_value=None,
        )

        assert classify(m, PATIENT_UNICODE_SANITIZER_CLASSIFIERS) == "unclassified"
