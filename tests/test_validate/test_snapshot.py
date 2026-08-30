"""Tests for the golden-master snapshot digest and its diff.

The digest never holds tracker values, only per-column statistics and a
one-way fingerprint, so these tests build tiny parquet trees on ``tmp_path``
rather than reading anything real.
"""

from __future__ import annotations

from pathlib import Path

import polars as pl
import pytest

from a4d.validate.snapshot import (
    DIGEST_COLUMNS,
    build_digest,
    column_fingerprint,
    diff_digests,
    format_diff,
)


def write_stage(output_root: Path, stage_dir: str, stem: str, df: pl.DataFrame) -> Path:
    """Write ``df`` where the pipeline would write it for one tracker."""
    target = output_root / stage_dir
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"{stem}.parquet"
    df.write_parquet(path)
    return path


def make_tracker(data_root: Path, clinic: str, stem: str, body: bytes = b"x") -> Path:
    """Create a stand-in tracker file, only ever read for its MD5."""
    clinic_dir = data_root / clinic
    clinic_dir.mkdir(parents=True, exist_ok=True)
    path = clinic_dir / f"{stem}.xlsx"
    path.write_bytes(body)
    return path


@pytest.fixture
def corpus(tmp_path):
    """A two-tracker output tree with both arms, plus the trackers themselves."""
    data_root = tmp_path / "data"
    output_root = data_root / "output"

    make_tracker(data_root, "TST", "2024_Test Clinic A4D Tracker")

    write_stage(
        output_root,
        "patient_data_cleaned",
        "2024_Test Clinic A4D Tracker_patient_cleaned",
        pl.DataFrame(
            {
                "patient_id": ["A1", "A2", "A3"],
                "age": [10, None, 30],
            },
            schema={"patient_id": pl.Utf8, "age": pl.Int64},
        ),
    )
    write_stage(
        output_root,
        "product_data_cleaned",
        "2024_Test Clinic A4D Tracker_product_cleaned",
        pl.DataFrame({"product": ["Insulin A"]}, schema={"product": pl.Utf8}),
    )
    return data_root, output_root


class TestColumnFingerprint:
    def test_equal_series_fingerprint_alike(self):
        a = pl.Series("x", [1, 2, 3])
        b = pl.Series("x", [1, 2, 3])
        assert column_fingerprint(a) == column_fingerprint(b)

    def test_different_values_fingerprint_differently(self):
        a = pl.Series("x", [1, 2, 3])
        b = pl.Series("x", [1, 2, 4])
        assert column_fingerprint(a) != column_fingerprint(b)

    def test_null_is_distinct_from_the_empty_string(self):
        a = pl.Series("x", [None, "b"], dtype=pl.Utf8)
        b = pl.Series("x", ["", "b"], dtype=pl.Utf8)
        assert column_fingerprint(a) != column_fingerprint(b)

    def test_order_matters(self):
        a = pl.Series("x", [1, 2])
        b = pl.Series("x", [2, 1])
        assert column_fingerprint(a) != column_fingerprint(b)

    def test_fingerprint_carries_no_values(self):
        """A fingerprint may be committed nowhere, but must still not leak."""
        fp = column_fingerprint(pl.Series("x", ["Kantha Bopha", "secret"]))
        assert "Kantha" not in fp
        assert len(fp) == 16
        assert all(c in "0123456789abcdef" for c in fp)


class TestBuildDigest:
    def test_one_row_per_stage_column(self, corpus):
        data_root, output_root = corpus
        digest = build_digest(output_root=output_root, data_root=data_root)

        assert digest.columns == list(DIGEST_COLUMNS)
        keys = set(zip(digest["stage"], digest["column"], strict=True))
        assert keys == {
            ("patient_cleaned", "patient_id"),
            ("patient_cleaned", "age"),
            ("product_cleaned", "product"),
        }

    def test_statistics_describe_the_column(self, corpus):
        data_root, output_root = corpus
        digest = build_digest(output_root=output_root, data_root=data_root)
        age = digest.filter(pl.col("column") == "age").to_dicts()[0]

        assert age["n_rows"] == 3
        assert age["n_null"] == 1
        assert age["n_distinct"] == 2  # nulls excluded
        assert age["dtype"] == "Int64"
        assert age["source"] == "2024_Test Clinic A4D Tracker"

    def test_input_md5_is_recorded_per_source(self, corpus):
        data_root, output_root = corpus
        digest = build_digest(output_root=output_root, data_root=data_root)
        assert digest["input_md5"].n_unique() == 1
        assert digest["input_md5"][0] is not None

    def test_missing_tracker_leaves_input_md5_null(self, corpus):
        data_root, output_root = corpus
        for path in data_root.rglob("*.xlsx"):
            path.unlink()
        digest = build_digest(output_root=output_root, data_root=data_root)
        assert digest["input_md5"].null_count() == digest.height

    def test_tables_are_digested_without_an_input(self, corpus):
        data_root, output_root = corpus
        write_stage(output_root, "tables", "table_findings", pl.DataFrame({"code": ["a", "b"]}))
        digest = build_digest(output_root=output_root, data_root=data_root)
        findings = digest.filter(pl.col("stage") == "tables").to_dicts()

        assert len(findings) == 1
        assert findings[0]["source"] == "table_findings"
        assert findings[0]["input_md5"] is None

    def test_empty_output_root_yields_an_empty_digest(self, tmp_path):
        digest = build_digest(output_root=tmp_path / "nothing", data_root=tmp_path)
        assert digest.height == 0
        assert digest.columns == list(DIGEST_COLUMNS)

    def test_digest_is_deterministic(self, corpus):
        data_root, output_root = corpus
        first = build_digest(output_root=output_root, data_root=data_root)
        second = build_digest(output_root=output_root, data_root=data_root)
        assert first.equals(second)


def digest_of(rows: list[dict]) -> pl.DataFrame:
    """Build a digest frame directly, for diff tests."""
    base = {
        "source": "T",
        "stage": "patient_cleaned",
        "column": "age",
        "dtype": "Int64",
        "n_rows": 3,
        "n_null": 0,
        "n_distinct": 3,
        "value_hash": "0" * 16,
        "input_md5": "aaa",
    }
    return pl.DataFrame([{**base, **row} for row in rows]).select(DIGEST_COLUMNS)


class TestDiffDigests:
    def test_identical_digests_have_no_movement(self):
        d = digest_of([{}])
        diff = diff_digests(d, d)
        assert not diff.moved
        assert diff.changed == []
        assert diff.added == []
        assert diff.removed == []

    def test_a_changed_value_hash_is_movement(self):
        before = digest_of([{}])
        after = digest_of([{"value_hash": "f" * 16}])
        diff = diff_digests(before, after)

        assert diff.moved
        assert len(diff.changed) == 1
        assert diff.changed[0].fields == ["value_hash"]

    def test_a_changed_statistic_names_the_field(self):
        """Fields are listed in reading order -- shape, then nulls, then spread."""
        before = digest_of([{}])
        after = digest_of([{"n_null": 2, "n_distinct": 1}])
        diff = diff_digests(before, after)
        assert diff.changed[0].fields == ["n_null", "n_distinct"]

    def test_added_and_removed_columns_are_reported(self):
        before = digest_of([{"column": "age"}, {"column": "gone"}])
        after = digest_of([{"column": "age"}, {"column": "fresh"}])
        diff = diff_digests(before, after)

        assert [k.column for k in diff.added] == ["fresh"]
        assert [k.column for k in diff.removed] == ["gone"]

    def test_same_input_movement_is_a_possible_regression(self):
        before = digest_of([{}])
        after = digest_of([{"value_hash": "f" * 16}])
        diff = diff_digests(before, after)

        assert diff.changed[0].input_changed is False
        assert diff.regression_sources == ["T"]
        assert diff.edited_sources == []

    def test_changed_input_movement_is_an_edited_workbook(self):
        before = digest_of([{}])
        after = digest_of([{"value_hash": "f" * 16, "input_md5": "bbb"}])
        diff = diff_digests(before, after)

        assert diff.changed[0].input_changed is True
        assert diff.edited_sources == ["T"]
        assert diff.regression_sources == []

    def test_an_edited_workbook_with_identical_output_is_still_movement(self):
        """The workbook changed but nothing downstream did -- worth saying."""
        before = digest_of([{}])
        after = digest_of([{"input_md5": "bbb"}])
        diff = diff_digests(before, after)

        assert diff.moved
        assert diff.edited_sources == ["T"]
        assert diff.changed == []

    def test_a_wholly_new_source_is_added_not_changed(self):
        before = digest_of([{"source": "T"}])
        after = digest_of([{"source": "T"}, {"source": "U", "input_md5": "ccc"}])
        diff = diff_digests(before, after)

        assert [k.source for k in diff.added] == ["U"]
        assert diff.changed == []


class TestFormatDiff:
    def test_a_clean_diff_says_so(self):
        d = digest_of([{}])
        assert "no movement" in format_diff(diff_digests(d, d)).lower()

    def test_regressions_and_edits_are_reported_separately(self):
        before = digest_of([{"source": "T"}, {"source": "U", "input_md5": "u1"}])
        after = digest_of(
            [
                {"source": "T", "n_null": 9},
                {"source": "U", "input_md5": "u2", "n_null": 9},
            ]
        )
        text = format_diff(diff_digests(before, after))

        regression_at = text.index("same workbook")
        edited_at = text.index("workbook edited")
        assert regression_at < edited_at, "regressions come first -- they are the alarm"
        assert "T" in text
        assert "U" in text
