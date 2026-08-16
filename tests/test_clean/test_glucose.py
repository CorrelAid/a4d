"""Tests for glucose unit resolution (ticket 42)."""

import polars as pl

from a4d.clean.glucose import (
    MMOL_TO_MG_FACTOR,
    column_is_recorded_in_mmol,
    resolve_glucose_units,
)
from a4d.errors import ErrorCollector


def _frame(mg: list, mmol: list | None = None, column: str = "fbg_updated_mg") -> pl.DataFrame:
    mmol_column = column.replace("_mg", "_mmol")
    return pl.DataFrame(
        {
            "file_name": ["t.xlsx"] * len(mg),
            "patient_id": [f"KH_QD{i:03d}" for i in range(len(mg))],
            column: pl.Series(mg, dtype=pl.Float64),
            mmol_column: pl.Series(
                mmol if mmol is not None else [None] * len(mg), dtype=pl.Float64
            ),
        }
    )


class TestColumnIsRecordedInMmol:
    def test_true_when_nearly_every_reading_lands_in_mmol_territory(self):
        values = pl.Series([8.0, 9.4, 12.1, 7.2, 15.0, 6.6, 19.3, 11.0, 5.5, 22.0])

        assert column_is_recorded_in_mmol(values) is True

    def test_false_when_the_column_reads_as_ordinary_mg(self):
        values = pl.Series([120.0, 190.0, 233.0, 88.0, 310.0, 145.0, 99.0, 275.0, 180.0, 210.0])

        assert column_is_recorded_in_mmol(values) is False

    def test_false_when_only_some_readings_are_low(self):
        """The 50-90% band is per-patient mixing, not a mislabelled column."""
        values = pl.Series([8.0, 9.4, 12.1, 7.2, 15.0, 190.0, 233.0, 145.0, 180.0, 210.0])

        assert column_is_recorded_in_mmol(values) is False

    def test_false_when_too_few_readings_to_judge(self):
        values = pl.Series([8.0, 9.4, 12.1])

        assert column_is_recorded_in_mmol(values) is False

    def test_nulls_are_not_counted_as_readings(self):
        values = pl.Series([8.0, 9.4, 12.1, None, None, None, None, None, None, None])

        assert column_is_recorded_in_mmol(values) is False


class TestResolveGlucoseUnits:
    def test_a_wholly_mmol_column_is_moved_to_its_mmol_sibling(self):
        df = _frame([8.0, 9.4, 12.1, 7.2, 15.0, 6.6, 19.3, 11.0, 5.5, 22.0])
        collector = ErrorCollector()

        out = resolve_glucose_units(df, collector)

        assert out["fbg_updated_mmol"].to_list()[0] == 8.0
        assert out["fbg_updated_mg"].to_list()[0] == 8.0 * MMOL_TO_MG_FACTOR

    def test_a_swapped_column_is_reported_once_not_once_per_row(self):
        """The defect is the column's label, so the source fix is file-level."""
        df = _frame([8.0, 9.4, 12.1, 7.2, 15.0, 6.6, 19.3, 11.0, 5.5, 22.0])
        collector = ErrorCollector()

        resolve_glucose_units(df, collector)

        swapped = [e for e in collector.errors if e.error_code == "glucose_unit_swapped"]
        assert len(swapped) == 1
        assert swapped[0].column == "fbg_updated_mg"

    def test_an_existing_mmol_reading_is_not_overwritten(self):
        df = _frame(
            [8.0, 9.4, 12.1, 7.2, 15.0, 6.6, 19.3, 11.0, 5.5, 22.0],
            mmol=[4.4] + [None] * 9,
        )
        collector = ErrorCollector()

        out = resolve_glucose_units(df, collector)

        assert out["fbg_updated_mmol"].to_list()[0] == 4.4

    def test_a_stray_low_reading_in_a_clean_column_is_flagged_not_converted(self):
        """A genuine severe hypo is indistinguishable from a mis-entered unit,
        so a scattered value keeps its recorded number."""
        df = _frame([120.0, 190.0, 233.0, 88.0, 310.0, 145.0, 99.0, 275.0, 180.0, 12.0])
        collector = ErrorCollector()

        out = resolve_glucose_units(df, collector)

        assert out["fbg_updated_mg"].to_list()[-1] == 12.0
        assert out["fbg_updated_mmol"].to_list()[-1] is None
        suspect = [e for e in collector.errors if e.error_code == "glucose_unit_suspect"]
        assert len(suspect) == 1
        assert suspect[0].patient_id == "KH_QD009"

    def test_a_swapped_column_raises_no_row_level_suspicion(self):
        df = _frame([8.0, 9.4, 12.1, 7.2, 15.0, 6.6, 19.3, 11.0, 5.5, 22.0])
        collector = ErrorCollector()

        resolve_glucose_units(df, collector)

        assert not [e for e in collector.errors if e.error_code == "glucose_unit_suspect"]

    def test_zero_is_not_a_reading(self):
        """Zero sits below the analytical floor of both units, so it records
        'not measured' rather than profound hypoglycaemia."""
        df = _frame([120.0, 0.0, 233.0], mmol=[None, 0.0, None])
        collector = ErrorCollector()

        out = resolve_glucose_units(df, collector)

        assert out["fbg_updated_mg"].to_list() == [120.0, None, 233.0]
        assert out["fbg_updated_mmol"].to_list() == [None, None, None]

    def test_missing_columns_are_tolerated(self):
        df = pl.DataFrame({"file_name": ["t.xlsx"], "patient_id": ["KH_QD001"]})
        collector = ErrorCollector()

        assert resolve_glucose_units(df, collector).equals(df)
