"""Tests for `link_product_patient` — product↔patient link validation."""

from collections.abc import Iterator
from pathlib import Path

import polars as pl
import pytest
from loguru import logger

from a4d.findings import current_findings
from a4d.tables.product import link_product_patient


@pytest.fixture
def captured_warnings() -> Iterator[list[str]]:
    """Capture loguru WARNING messages emitted during the test."""
    sink: list[str] = []
    handler_id = logger.add(
        lambda msg: sink.append(str(msg)),
        level="WARNING",
        format="{message}",
    )
    yield sink
    logger.remove(handler_id)


def _write_patient_static(path: Path, rows: list[tuple[str, str]]) -> Path:
    """Write a minimal patient_data_static.parquet with (file_name, patient_id) rows."""
    pl.DataFrame(
        {"file_name": [r[0] for r in rows], "patient_id": [r[1] for r in rows]}
    ).write_parquet(path)
    return path


def test_all_match_returns_zero_no_warnings(tmp_path: Path, captured_warnings: list[str]) -> None:
    patient_path = _write_patient_static(
        tmp_path / "patient.parquet",
        [
            ("tracker_a.xlsx", "KD_QB001"),
            ("tracker_a.xlsx", "KD_QB002"),
            ("tracker_b.xlsx", "KD_QB003"),
        ],
    )
    product_df = pl.DataFrame(
        {
            "file_name": [
                "tracker_a.xlsx",
                "tracker_a.xlsx",
                "tracker_a.xlsx",
                "tracker_b.xlsx",
                "tracker_b.xlsx",
            ],
            "product_sheet_name": "Jun24",
            "product_released_to": [
                "KD_QB001",
                "KD_QB001",
                "KD_QB002",
                "KD_QB003",
                "KD_QB003",
            ],
        }
    )

    count, _ = link_product_patient(product_df, patient_path)

    assert count == 0
    assert captured_warnings == []


def test_mixed_filters_null_and_sentinel(tmp_path: Path, captured_warnings: list[str]) -> None:
    patient_path = _write_patient_static(
        tmp_path / "patient.parquet",
        [("tracker_a.xlsx", "KD_QB001"), ("tracker_a.xlsx", "KD_QB002")],
    )
    product_df = pl.DataFrame(
        {
            "file_name": [
                "tracker_a.xlsx",  # match
                "tracker_a.xlsx",  # match
                "tracker_a.xlsx",  # match
                "tracker_a.xlsx",  # mismatch
                "tracker_a.xlsx",  # mismatch
                "tracker_a.xlsx",  # null — filtered
                "tracker_a.xlsx",  # "Undefined" — filtered
            ],
            "product_sheet_name": "Jun24",
            "product_released_to": [
                "KD_QB001",
                "KD_QB001",
                "KD_QB002",
                "KD_QB999",
                "KD_QB999",
                None,
                "Undefined",
            ],
        }
    )

    count, _ = link_product_patient(product_df, patient_path)

    assert count == 2
    # Per-pair detail ("Unmatched product_released_to") is DEBUG-only now —
    # console/WARNING-level output gets one aggregate line instead, so a run
    # with hundreds of distinct mismatched pairs doesn't flood the terminal.
    mismatch_warnings = [w for w in captured_warnings if "Unmatched product_released_to" in w]
    assert mismatch_warnings == []
    summary_warnings = [w for w in captured_warnings if "Product-patient link validation" in w]
    assert len(summary_warnings) == 1
    assert "2 mismatched rows" in summary_warnings[0]
    assert "1 distinct (file × id) pairs" in summary_warnings[0]
    assert "5 candidate product rows examined" in summary_warnings[0]


def test_cross_file_isolation(tmp_path: Path, captured_warnings: list[str]) -> None:
    """Same patient_id matches in one file but not in another."""
    patient_path = _write_patient_static(
        tmp_path / "patient.parquet",
        [("tracker_a.xlsx", "KD_QB001")],
    )
    product_df = pl.DataFrame(
        {
            "file_name": ["tracker_a.xlsx", "tracker_b.xlsx"],
            "product_sheet_name": "Jun24",
            "product_released_to": ["KD_QB001", "KD_QB001"],
        }
    )

    count, _ = link_product_patient(product_df, patient_path)

    assert count == 1
    mismatch_warnings = [w for w in captured_warnings if "Unmatched product_released_to" in w]
    assert mismatch_warnings == []
    summary_warnings = [w for w in captured_warnings if "Product-patient link validation" in w]
    assert len(summary_warnings) == 1
    assert "1 mismatched rows" in summary_warnings[0]
    assert "1 distinct (file × id) pairs" in summary_warnings[0]
    assert "2 candidate product rows examined" in summary_warnings[0]


def test_missing_patient_table_returns_zero_with_warning(
    tmp_path: Path, captured_warnings: list[str]
) -> None:
    product_df = pl.DataFrame(
        {
            "file_name": ["tracker_a.xlsx"],
            "product_sheet_name": ["Jun24"],
            "product_released_to": ["KD_QB001"],
        }
    )
    missing_path = tmp_path / "does_not_exist.parquet"

    count, _ = link_product_patient(product_df, missing_path)

    assert count == 0
    skip_warnings = [w for w in captured_warnings if "skipping" in w.lower()]
    assert len(skip_warnings) == 1


class TestUnmatchedRecipientsBecomeFindings:
    """Stock released to a patient ID that tracker's own patient sheets do not
    contain used to be counted, logged at DEBUG, and reported to nobody.

    On the real run that is 14 rows across 2 trackers, out of 44,591 that name
    a recipient -- rare, but it means insulin left the clinic recorded against
    a patient the tracker has never heard of (ticket 73). One finding per row
    rather than per distinct pair: each row is its own stock movement, and the
    null-recipient defect beside it (``released_units_without_recipient``)
    counts the same way.
    """

    @pytest.mark.no_findings_context
    def test_it_emits_without_a_context_already_bound(self, tmp_path: Path) -> None:
        """The call sites are CLI steps, not tracker scopes, so the function
        opens its own context -- the same shape `create_product_data_table`
        uses. Exercised outside the suite's per-test fixture on purpose: an
        emit with nothing bound raises, and the exception used to be swallowed
        by the caller's try/except."""
        assert current_findings() is None

        patient_path = _write_patient_static(
            tmp_path / "patient.parquet", [("tracker_a", "KH_QD001")]
        )
        product_df = pl.DataFrame(
            {
                "file_name": ["tracker_a", "tracker_a", "tracker_a"],
                "product_sheet_name": "Jun24",
                "product_released_to": ["KH_QD001", "KH_QD093", "KH_QD093"],
            }
        )

        count, findings = link_product_patient(product_df, patient_path)

        assert count == 2
        assert [f.error_code for f in findings] == ["released_units_to_unknown_patient"] * 2
        assert {f.file_name for f in findings} == {"tracker_a"}
        assert {f.arm for f in findings} == {"product"}
        assert {f.patient_id for f in findings} == {"KH_QD093"}
        assert current_findings() is None

    @pytest.mark.no_findings_context
    def test_a_clean_link_emits_nothing(self, tmp_path: Path) -> None:
        patient_path = _write_patient_static(
            tmp_path / "patient.parquet", [("tracker_a", "KH_QD001")]
        )
        product_df = pl.DataFrame(
            {
                "file_name": ["tracker_a"],
                "product_sheet_name": ["Jun24"],
                "product_released_to": ["KH_QD001"],
            }
        )

        count, findings = link_product_patient(product_df, patient_path)

        assert (count, findings) == (0, [])
