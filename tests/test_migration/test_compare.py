"""Tests for the R-vs-Python output comparison (ticket 15)."""

import datetime

import polars as pl

from a4d.migration.compare import (
    PRODUCT_ENTRY_DATE_CLASSIFIERS,
    SENTINEL_DATE,
    CategoricalOverlap,
    CellMismatch,
    ColumnsResult,
    DirectoryComparison,
    FileComparison,
    IdOverlapResult,
    ShapeResult,
    TotalsMismatch,
    build_mismatch_rows,
    classify,
    compare_categorical_overlap,
    compare_cells,
    compare_columns,
    compare_directory,
    compare_id_overlap,
    compare_shape,
    compare_totals,
    render_html_report,
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


def _mismatch(r_value, py_value, column="product_entry_date"):
    return CellMismatch(key={"id": 1}, column=column, r_value=r_value, py_value=py_value)


class TestClassify:
    def test_sentinel_null_when_r_is_null_and_python_is_sentinel(self):
        mismatch = _mismatch(r_value=None, py_value=SENTINEL_DATE)

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "sentinel_null"

    def test_typo_rescue_when_r_is_null_and_python_parsed_a_real_date(self):
        mismatch = _mismatch(r_value=None, py_value=datetime.date(2021, 3, 10))

        assert classify(mismatch, PRODUCT_ENTRY_DATE_CLASSIFIERS) == "typo_rescue"

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


class TestRenderHtmlReport:
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

        html = render_html_report(
            comparison, classifiers_by_column={"product_entry_date": PRODUCT_ENTRY_DATE_CLASSIFIERS}
        )

        assert "product_entry_date" in html
        assert "other_col" in html
        assert "sentinel_null" in html
        assert "unclassified" in html
        assert "missing.parquet" in html
        # per-column mismatch counts
        assert html.count("<td>1</td>") >= 2

    def test_includes_a_legend_explaining_each_measure(self):
        comparison = DirectoryComparison(files=[], only_in_r=[], only_in_py=[])

        html = render_html_report(comparison)

        assert "Shape match" in html
        assert "ID divergence" in html
        assert "Totals mismatches" in html
        assert "Column diffs" in html
        assert "Categorical divergence" in html
        assert "Cell mismatches" in html


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
