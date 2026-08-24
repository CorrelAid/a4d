"""Unit tests for Mandalay wide-format tracker reshaping (steps 1.4a/1.4b)."""

import polars as pl

from a4d.extract.wide_format import handle_wide_format_cells, handle_wide_format_columns

# --- handle_wide_format_columns (step 1.4a: 2020-2021 wide columns) ---

_TOTAL = "Total Units Released"
_PER_PERSON = "Units Released per person"
_RELEASED_TO_WIDE = "Released To (select from drop down list)"


def _columns_df(rows: list[dict], extra_cols: list[str] | None = None) -> pl.DataFrame:
    # Real tracker layout: Total precedes Released To; the intermediate
    # per-recipient columns sit between Released To and Units Released per
    # person (that's the span handle_wide_format_columns expands).
    cols = [
        "Date",
        _TOTAL,
        _RELEASED_TO_WIDE,
        *(extra_cols or ["Recipient A", "Recipient B"]),
        _PER_PERSON,
    ]
    data = {c: [r.get(c) for r in rows] for c in cols}
    return pl.DataFrame(data)


def test_columns_gate_missing_required_column_returns_unchanged():
    df = pl.DataFrame({"Date": ["2020-01-01"], _TOTAL: [5]})

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    assert result.equals(df)


def test_columns_gate_empty_dataframe_returns_unchanged():
    df = _columns_df([])

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    assert result.height == 0
    assert result.columns == df.columns


def test_columns_no_split_when_total_equals_per_person():
    row = {
        "Date": "2020-01-01",
        _RELEASED_TO_WIDE: "Clinic X",
        "Recipient A": "5",
        "Recipient B": None,
        _TOTAL: 5,
        _PER_PERSON: 5,
    }
    df = _columns_df([row])

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    assert result.height == 1


def test_columns_no_split_when_total_or_per_person_missing():
    row = {
        "Date": "2020-01-01",
        _RELEASED_TO_WIDE: "Clinic X",
        "Recipient A": "5",
        "Recipient B": None,
        _TOTAL: None,
        _PER_PERSON: None,
    }
    df = _columns_df([row])

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    assert result.height == 1


def test_columns_expands_intermediate_cells_into_rows():
    row = {
        "Date": "2020-01-01",
        _RELEASED_TO_WIDE: "Clinic X",
        "Recipient A": "5",
        "Recipient B": "3",
        _TOTAL: 8,
        _PER_PERSON: 4,
    }
    df = _columns_df([row])

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    # Original row + one new row per non-empty intermediate cell.
    assert result.height == 3
    expanded = result.tail(2)
    assert expanded[_RELEASED_TO_WIDE].to_list() == ["5", "3"]
    assert expanded[_PER_PERSON].to_list() == [4, 4]
    assert expanded["Date"].to_list() == ["2020-01-01", "2020-01-01"]


def test_columns_skips_blank_intermediate_cells():
    row = {
        "Date": "2020-01-01",
        _RELEASED_TO_WIDE: "Clinic X",
        "Recipient A": "  ",
        "Recipient B": None,
        _TOTAL: 8,
        _PER_PERSON: 4,
    }
    df = _columns_df([row])

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    assert result.height == 1


def test_columns_start_after_end_returns_unchanged():
    # Recipient columns fall between _RELEASED_TO_WIDE and _PER_PERSON; if
    # they're adjacent (no intermediate columns), start > end and nothing splits.
    cols = ["Date", _RELEASED_TO_WIDE, _PER_PERSON, _TOTAL]
    df = pl.DataFrame(dict(zip(cols, [["2020-01-01"], ["Clinic X"], [4], [8]], strict=True)))

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    assert result.height == 1


def test_columns_handles_missing_date_column():
    cols = [_TOTAL, _RELEASED_TO_WIDE, "Recipient A", _PER_PERSON]
    row_no_split = dict(zip(cols, [5, "Clinic X", "5", 5], strict=True))
    row_splits = dict(zip(cols, [8, "Clinic Y", "3", 4], strict=True))
    df = pl.DataFrame({c: [row_no_split[c], row_splits[c]] for c in cols})

    result = handle_wide_format_columns(df, "2020_Mandalay.xlsx")

    assert "Date" not in result.columns
    # Row 1 unchanged (total == per_person); row 2 unchanged + 1 split row.
    assert result.height == 3


# --- handle_wide_format_cells (step 1.4b: 2017-2019 comma-separated cells) ---


def _cells_df(rows: list[dict]) -> pl.DataFrame:
    cols = ["Date", "Received From", "Released To", "Units Released"]
    data = {c: [r.get(c) for r in rows] for c in cols}
    return pl.DataFrame(data)


def test_cells_gate_filename_not_mandalay_2017_2019_returns_unchanged():
    df = _cells_df([{"Released To": "A - 5, B - 3"}])

    result = handle_wide_format_cells(df, "2020_Mandalay.xlsx")

    assert result.equals(df)


def test_cells_gate_empty_dataframe_returns_unchanged():
    df = _cells_df([])

    result = handle_wide_format_cells(df, "2019_Mandalay.xlsx")

    assert result.height == 0


def test_cells_gate_missing_required_column_returns_unchanged():
    df = pl.DataFrame({"Date": ["2019-01-01"]})

    result = handle_wide_format_cells(df, "2019_Mandalay.xlsx")

    assert result.equals(df)


def test_cells_gate_no_comma_or_dash_pattern_returns_unchanged():
    df = _cells_df(
        [
            {
                "Date": "2019-01-01",
                "Received From": "HQ",
                "Released To": "Clinic X",
                "Units Released": 5,
            }
        ]
    )

    result = handle_wide_format_cells(df, "2019_Mandalay.xlsx")

    assert result.equals(df)


def test_cells_splits_comma_separated_fragments():
    df = _cells_df(
        [
            {
                "Date": "2019-01-01",
                "Received From": "HQ",
                "Released To": "Clinic A - 5, Clinic B - 3",
                "Units Released": None,
            }
        ]
    )

    result = handle_wide_format_cells(df, "2019_Mandalay.xlsx")

    # Original row (nulled at released_to/units_released) + two split rows.
    assert result.height == 3
    split_rows = result.tail(2)
    assert split_rows["Released To"].to_list() == ["Clinic A", "Clinic B"]
    assert split_rows["Units Released"].to_list() == ["5", "3"]
    assert split_rows["Received From"].to_list() == ["HQ", "HQ"]
    assert split_rows["Date"].to_list() == ["2019-01-01", "2019-01-01"]

    original_row = result.head(1)
    assert original_row["Released To"].to_list() == [None]
    assert original_row["Units Released"].to_list() == [None]


def test_cells_fragment_without_dash_has_no_quantity():
    df = _cells_df(
        [
            {
                "Date": "2019-01-01",
                "Received From": "HQ",
                "Released To": "Clinic A, Clinic B - 3",
                "Units Released": None,
            }
        ]
    )

    result = handle_wide_format_cells(df, "2019_Mandalay.xlsx")

    split_rows = result.tail(2)
    assert split_rows["Released To"].to_list() == ["Clinic A", "Clinic B"]
    assert split_rows["Units Released"].to_list() == [None, "3"]


def test_cells_leaves_non_comma_cells_untouched():
    df = _cells_df(
        [
            {
                "Date": "2019-01-01",
                "Received From": "HQ",
                "Released To": "Clinic A - 5",
                "Units Released": None,
            },
            {
                "Date": "2019-01-02",
                "Received From": "HQ",
                "Released To": "Clinic C, Clinic D",
                "Units Released": None,
            },
        ]
    )

    result = handle_wide_format_cells(df, "2018_Mandalay.xlsx")

    # First row has no comma -> not split, appended as-is.
    first_row = result.head(1)
    assert first_row["Released To"].to_list() == ["Clinic A - 5"]
