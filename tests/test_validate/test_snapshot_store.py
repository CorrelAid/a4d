"""Tests for where a snapshot digest is kept and how it is promoted.

The baseline lives beside the tracker corpus, never in the repository, so
these tests only ever touch ``tmp_path``.
"""

from __future__ import annotations

import polars as pl
import pytest

from a4d.validate.snapshot import _DIGEST_SCHEMA, DIGEST_COLUMNS
from a4d.validate.snapshot_store import (
    NoCurrentDigestError,
    SnapshotStore,
)


def a_digest(value_hash: str = "0" * 16) -> pl.DataFrame:
    return pl.DataFrame(
        [
            {
                "source": "T",
                "stage": "patient_cleaned",
                "column": "age",
                "dtype": "Int64",
                "n_rows": 3,
                "n_null": 0,
                "n_distinct": 3,
                "value_hash": value_hash,
                "input_md5": "aaa",
            }
        ],
        schema=_DIGEST_SCHEMA,
    ).select(DIGEST_COLUMNS)


@pytest.fixture
def store(tmp_path) -> SnapshotStore:
    return SnapshotStore(tmp_path / "snapshot")


class TestLocations:
    def test_snapshot_dir_sits_beside_the_corpus(self, tmp_path):
        assert SnapshotStore.for_data_root(tmp_path).root == tmp_path / "snapshot"

    def test_no_baseline_before_the_first_update(self, store):
        assert store.baseline() is None


class TestWriteAndPromote:
    def test_current_survives_a_round_trip(self, store):
        digest = a_digest()
        store.write_current(digest)
        assert store.current().equals(digest)

    def test_promote_makes_current_the_baseline(self, store):
        store.write_current(a_digest())
        store.promote(stamp="2026-08-30")
        assert store.baseline().equals(a_digest())

    def test_promote_files_a_dated_copy(self, store):
        store.write_current(a_digest())
        store.promote(stamp="2026-08-30")
        assert (store.root / "history" / "baseline-2026-08-30.parquet").exists()

    def test_a_second_promotion_the_same_day_does_not_clobber_the_first(self, store):
        store.write_current(a_digest("a" * 16))
        first = store.promote(stamp="2026-08-30")
        store.write_current(a_digest("b" * 16))
        second = store.promote(stamp="2026-08-30")

        assert first != second
        assert pl.read_parquet(first)["value_hash"][0] == "a" * 16
        assert pl.read_parquet(second)["value_hash"][0] == "b" * 16

    def test_promote_without_a_current_refuses(self, store):
        """You cannot accept output you have not looked at."""
        with pytest.raises(NoCurrentDigestError):
            store.promote(stamp="2026-08-30")

    def test_promote_leaves_current_in_place(self, store):
        """A promotion is a copy forward, so a re-check needs no re-run."""
        store.write_current(a_digest())
        store.promote(stamp="2026-08-30")
        assert store.current() is not None
