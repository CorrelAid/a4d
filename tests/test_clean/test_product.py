"""Tests for product cleaning helpers."""

from datetime import date

import polars as pl

from a4d.clean.product import (
    YEAR_FLOOR_DELTA,
    _check_entry_dates_match_sheet,
    _clean_received_from,
    _compute_running_balance,
    _extract_balance_from_received,
    _fill_product_names_and_sort,
    _format_dates,
    _null_entry_date_residues,
    _split_multi_product_cells,
    _switch_misplaced_columns,
    _validate_entry_dates,
    clean_product_data,
)


def _entry_date_df(
    products: list[str],
    entry_dates: list[date | None],
    table_year: int = 2024,
) -> pl.DataFrame:
    n = len(products)
    return pl.DataFrame(
        {
            "product": products,
            "product_entry_date": entry_dates,
            "product_table_year": [table_year] * n,
            "product_sheet_name": ["Jun"] * n,
            "product_table_month": [6] * n,
            "file_name": ["t.xlsx"] * n,
        },
        schema={
            "product": pl.String,
            "product_entry_date": pl.Date,
            "product_table_year": pl.Int32,
            "product_sheet_name": pl.String,
            "product_table_month": pl.Int32,
            "file_name": pl.String,
        },
    )


def test_validate_entry_dates_flags_future_dates_within_window(collector):
    df = _entry_date_df(
        products=["P1", "P2", "P3"],
        entry_dates=[date(2024, 6, 1), date(2099, 3, 15), None],
    )

    result = _validate_entry_dates(df)

    parsed = result["product_entry_date"].to_list()
    assert parsed[0] == date(2024, 6, 1)
    assert parsed[1] == date(9999, 9, 9)
    assert parsed[2] is None
    assert len(collector) == 1
    err = collector.findings[0]
    assert err.column == "product_entry_date"
    assert err.error_code == "entry_date_outside_tracker_year"
    assert err.patient_id == "P2"


def test_validate_entry_dates_converts_buddhist_era_dates_to_gregorian(collector):
    """Ticket 61: a BE date is the clinic's calendar, not its error, so it is
    converted like any other recovery -- and logged, so the conversion is
    auditable rather than silent. The parse-failure sentinel stays put."""
    df = _entry_date_df(
        products=["P1", "P2"],
        entry_dates=[date(2567, 11, 11), date(9999, 9, 9)],
    )

    result = _validate_entry_dates(df)

    parsed = result["product_entry_date"].to_list()
    assert parsed[0] == date(2024, 11, 11)
    assert parsed[1] == date(9999, 9, 9)
    assert len(collector) == 1
    assert collector.findings[0].error_code == "buddhist_era_converted"
    assert collector.findings[0].original_value == "2567-11-11"


def test_validate_entry_dates_leaves_a_buddhist_leap_day_that_cannot_shift(collector):
    """543 is not a multiple of 4, so 2568-02-29 would have to become a
    29 February 2025 that does not exist. Left unconverted and sentinelled as
    an implausible era date rather than invented."""
    df = _entry_date_df(
        products=["P1"],
        entry_dates=[date(2568, 2, 29)],
        table_year=2025,
    )

    result = _validate_entry_dates(df)

    assert result["product_entry_date"].to_list() == [date(9999, 9, 9)]
    assert {e.error_code for e in collector.findings} == {"implausible_era_date"}


def test_validate_entry_dates_sentinels_far_future_outside_the_buddhist_band(collector):
    """A year above BUDDHIST_ERA_THRESHOLD is only exempt if it is this
    tracker's own Buddhist-era year. Ticket 32 found the blanket >= 2400 skip
    let two corrupt Excel serials (1339576, 411384) reach BigQuery as
    5567-08-19 and 3026-04-30, and a Hat Yai typo publish 2525 in a 2025
    tracker whose Buddhist year is 2568."""
    df = _entry_date_df(
        products=["P1", "P2", "P3"],
        entry_dates=[date(2567, 11, 11), date(5567, 8, 19), date(2525, 10, 2)],
    )

    result = _validate_entry_dates(df)

    parsed = result["product_entry_date"].to_list()
    assert parsed[0] == date(2024, 11, 11)
    assert parsed[1] == date(9999, 9, 9)
    assert parsed[2] == date(9999, 9, 9)
    assert len(collector) == 3
    assert {e.patient_id for e in collector.findings if e.error_code == "implausible_era_date"} == {
        "P2",
        "P3",
    }


def test_validate_entry_dates_converts_at_both_buddhist_band_edges(collector):
    """The band mirrors the Gregorian window: BE equivalents of
    [table_year - YEAR_FLOOR_DELTA, table_year]. Every year inside it converts;
    the edges are where an off-by-one would show."""
    df = _entry_date_df(
        products=["P1", "P2"],
        entry_dates=[date(2024 + 543 - YEAR_FLOOR_DELTA, 1, 1), date(2024 + 543, 12, 31)],
    )

    result = _validate_entry_dates(df)

    assert result["product_entry_date"].to_list() == [
        date(2024 - YEAR_FLOOR_DELTA, 1, 1),
        date(2024, 12, 31),
    ]
    assert {e.error_code for e in collector.findings} == {"buddhist_era_converted"}


def test_validate_entry_dates_does_not_relog_the_sentinel(collector):
    """9999-09-09 is the pipeline's own parse-failure sentinel, so re-flagging
    it would double-log a cell some earlier step already reported."""
    df = _entry_date_df(products=["P1"], entry_dates=[date(9999, 9, 9)])

    result = _validate_entry_dates(df)

    assert result["product_entry_date"].to_list() == [date(9999, 9, 9)]
    assert len(collector) == 0


def test_validate_entry_dates_missing_columns_is_noop(collector):
    df = pl.DataFrame({"product": ["P1"]})

    result = _validate_entry_dates(df)

    assert result.equals(df)
    assert len(collector) == 0


def test_validate_entry_dates_logs_year_floor_but_preserves_date(collector):
    """Year-floor violations (parsed.year < tracker_year - YEAR_FLOOR_DELTA) are
    logged via collector but the parsed date is preserved in
    product_entry_date. Sentinelling it instead would drop the row out of
    chronological order and distort the running balance accumulated in step
    2.15, so the date is preserved and the audit trail carries the flag."""
    df = _entry_date_df(
        products=["P1", "P2", "P3"],
        entry_dates=[date(2024, 6, 1), date(1967, 2, 5), None],
    )

    result = _validate_entry_dates(df)

    parsed = result["product_entry_date"].to_list()
    assert parsed[0] == date(2024, 6, 1)
    assert parsed[1] == date(1967, 2, 5)
    assert parsed[2] is None
    assert len(collector) == 1
    err = collector.findings[0]
    assert err.column == "product_entry_date"
    assert err.error_code == "entry_date_outside_tracker_year"
    assert err.patient_id == "P2"
    assert "before" in err.message


def test_null_entry_date_residues_nulls_amount_left_marker():
    """End-of-block "Amount Left" markers (case-insensitive, whitespace-trimmed)
    are nulled before parsing. Regression for 2018 Mahosot Nov18/Dec18 where
    six rows per sheet had "Amount Left" in the entry_date column, surfacing
    as 9999-09-09 parse-failure sentinels in cleaned output."""
    df = pl.DataFrame(
        {
            "product_entry_date": [
                "Amount Left",
                "amount left",
                " AMOUNT LEFT ",
                "2018-12-05",
            ],
        },
        schema={"product_entry_date": pl.String},
    )

    out = _null_entry_date_residues(df)

    assert out["product_entry_date"].to_list() == [None, None, None, "2018-12-05"]


def test_null_entry_date_residues_nulls_tiny_excel_serials():
    """Numeric cells below the 2000-01-01 floor (Excel serial 36526) are
    nulled. Regression for 2025 NPH Jul25/Aug25/Dec25 row 81 where a stray
    "30" surfaced as 1900-01-29 via the pre-Mar-1900 leap-year-bug epoch."""
    df = pl.DataFrame(
        {
            "product_entry_date": ["30", "59", "366", "36525", "36526", "45000"],
        },
        schema={"product_entry_date": pl.String},
    )

    out = _null_entry_date_residues(df)

    parsed = out["product_entry_date"].to_list()
    assert parsed[0] is None  # 30 — within Excel leap-year-bug range
    assert parsed[1] is None  # 59 — top of leap-year-bug range
    assert parsed[2] is None  # 366 — first day of 1901
    assert parsed[3] is None  # 36525 — 1999-12-31, just below floor
    assert parsed[4] == "36526"  # 2000-01-01 — at floor, preserved
    assert parsed[5] == "45000"  # ~2023, well above floor


def test_null_entry_date_residues_preserves_real_dates():
    """Standard date string formats survive the residue scrub unchanged.
    Regression guard: marker / tiny-serial detection must not catch
    legitimate inputs."""
    df = pl.DataFrame(
        {
            "product_entry_date": [
                "2018-12-05",
                "05/12/2018",
                "Mar-18",
                "24 Feb 2020",
                None,
            ],
        },
        schema={"product_entry_date": pl.String},
    )

    out = _null_entry_date_residues(df)

    assert out["product_entry_date"].to_list() == [
        "2018-12-05",
        "05/12/2018",
        "Mar-18",
        "24 Feb 2020",
        None,
    ]


def test_null_entry_date_residues_missing_column_is_noop():
    df = pl.DataFrame({"product": ["P1"]})
    out = _null_entry_date_residues(df)
    assert out.equals(df)


def test_format_dates_residue_cells_become_null_after_parsing(collector):
    """End-to-end: residue cells flowing through _format_dates emerge as
    NULL in the parsed Date column, not 9999-09-09 or 1900-01-29."""
    df = pl.DataFrame(
        {
            "product": ["P1", "P2", "P3", "P4", "P5"],
            "product_entry_date": [
                "Amount Left",
                "30",
                "2018-12-05",
                "45000",
                None,
            ],
            "file_name": ["t.xlsx"] * 5,
        },
        schema={
            "product": pl.String,
            "product_entry_date": pl.String,
            "file_name": pl.String,
        },
    )

    out = _format_dates(df)

    parsed = out["product_entry_date"].to_list()
    assert parsed[0] is None  # "Amount Left" — nulled
    assert parsed[1] is None  # tiny serial 30 — nulled
    assert parsed[2] == date(2018, 12, 5)
    assert parsed[3] is not None  # 45000 → real post-2000 date
    assert parsed[3].year >= 2000
    assert parsed[4] is None
    # No parse-failure errors logged because residue cells were nulled
    # before parse_date_flexible saw them.
    assert all(err.error_code != "type_conversion" for err in collector.findings)


def test_switch_misplaced_columns_scoped_per_sheet():
    """Swap fires only for sheets with 'Remaining Stock'; clean sheets in
    the same file pass through untouched (regression for 2018_Penang_DC)."""
    df = pl.DataFrame(
        {
            "product_sheet_name": ["Jul18", "Jul18", "Nov18", "Nov18"],
            "product": ["A", "A", "A", "A"],
            "product_units_received": ["70", None, "Remaining Stock", None],
            "product_received_from": ["DKSH", None, "72", None],
        },
        schema={
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_units_received": pl.String,
            "product_received_from": pl.String,
        },
    )

    out = _switch_misplaced_columns(df)

    jul = out.filter(pl.col("product_sheet_name") == "Jul18")
    assert jul["product_units_received"].to_list() == ["70", None]
    assert jul["product_received_from"].to_list() == ["DKSH", None]

    nov = out.filter(pl.col("product_sheet_name") == "Nov18")
    assert nov["product_units_received"].to_list() == ["72", None]
    assert nov["product_received_from"].to_list() == ["Remaining Stock", None]


def test_extract_balance_from_received_scoped_per_sheet():
    """Rewrite fires only for sheets containing 'Balance' markers; clean
    sheets in the same file pass through untouched (regression for 2018
    Preah Kossamak / 2019 Sultanah Bahiyah_DC / 2020 LFHC_DC, where Aug18
    donor names were blanked because Sep18+ used the Balance convention)."""
    df = pl.DataFrame(
        {
            "product_sheet_name": ["Aug18", "Sep18", "Sep18"],
            "product": ["A", "A", "A"],
            "product_units_received": ["20", "Start Balance", None],
            "product_units_released": [None, "2", None],
            "product_received_from": ["GE100", None, None],
        },
        schema={
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_units_received": pl.String,
            "product_units_released": pl.String,
            "product_received_from": pl.String,
        },
    )

    out = _extract_balance_from_received(df)

    aug = out.filter(pl.col("product_sheet_name") == "Aug18")
    assert aug["product_received_from"].to_list() == ["GE100"]
    assert aug["product_units_released"].to_list() == [None]

    sep = out.filter(pl.col("product_sheet_name") == "Sep18")
    assert sep["product_received_from"].to_list() == ["2", None]
    assert sep["product_units_released"].to_list() == [None, None]


def test_extract_balance_from_received_clears_released_on_all_balance_sheet():
    """Sheets where every row is a Balance marker still get units_released
    cleared. Regression for 2019 PKH Oct19 / 2020 PKH May20 (18 rows): the
    sheet_triggered predicate uses received_from.is_null().any().over(sheet),
    which flips False after the first .with_columns() populates received_from
    on every Balance row — so without caching, the second call's released-
    clear pass becomes a no-op."""
    df = pl.DataFrame(
        {
            "product_sheet_name": ["Oct19", "Oct19"],
            "product": ["GE100", "GE100"],
            "product_units_received": ["Start Balance", "End Balance"],
            "product_units_released": ["1", "1"],
            "product_received_from": [None, None],
        },
        schema={
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_units_received": pl.String,
            "product_units_released": pl.String,
            "product_received_from": pl.String,
        },
    )

    out = _extract_balance_from_received(df)

    assert out["product_received_from"].to_list() == ["1", "1"]
    assert out["product_units_released"].to_list() == [None, None]


def test_extract_balance_from_received_preserves_supplier_on_triggered_sheet():
    """Non-Balance rows on a triggered sheet keep their supplier name.
    Regression for the Mahosot 2020 DKSH stock-receipt rows: the
    ``(?i)Balance`` trigger substring-matches "START BALANCE" / "END BALANCE",
    firing on every standard sheet. Before the fix, the case_when's catch-all
    nulled ``product_received_from`` on every non-Balance row in the triggered
    sheet, blanking legitimate supplier names. After the fix the catch-all
    preserves received_from."""
    df = pl.DataFrame(
        {
            "product_sheet_name": ["Mar20", "Mar20", "Mar20"],
            "product": ["Performa", "Performa", "Performa"],
            "product_units_received": ["START BALANCE", "100", "END BALANCE"],
            "product_units_released": [None, None, None],
            "product_received_from": ["43", "DKSH", "87"],
        },
        schema={
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_units_received": pl.String,
            "product_units_released": pl.String,
            "product_received_from": pl.String,
        },
    )

    out = _extract_balance_from_received(df)

    # Balance-marker rows pass through unchanged (received_from non-null,
    # so no released value to relocate; arm 2 is a no-op rewrite).
    # Change row in the middle keeps DKSH instead of being nulled.
    assert out["product_received_from"].to_list() == ["43", "DKSH", "87"]
    # units_released stays null on all rows (was null going in).
    assert out["product_units_released"].to_list() == [None, None, None]


def test_extract_balance_from_received_nulls_total_subtotal_label():
    """Typist subtotal-row labels ("Total" in product_received_from) are
    nulled, while legitimate supplier names on the same triggered sheet
    survive. Regression for the 47 corpus-wide subtotal rows in 2019
    Penang DC / VNCH / Mandalay etc. that the supplier-preservation fix
    inadvertently kept. "Total" is the label the typist puts on the
    end-of-product-block subtotal row, never a supplier."""
    # Sheet must be "triggered": need at least one Balance marker AND at
    # least one row with null received_from. Last row supplies the null.
    df = pl.DataFrame(
        {
            "product_sheet_name": ["Mar20", "Mar20", "Mar20", "Mar20", "Mar20"],
            "product": ["Performa", "Performa", "Performa", "Performa", "Performa"],
            "product_units_received": ["START BALANCE", "100", "0", "END BALANCE", "50"],
            "product_units_released": [None, None, None, None, None],
            "product_received_from": ["43", "DKSH", "Total", "87", None],
        },
        schema={
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_units_received": pl.String,
            "product_units_released": pl.String,
            "product_received_from": pl.String,
        },
    )

    out = _extract_balance_from_received(df)

    # DKSH (legitimate supplier) survives; Total (subtotal label) is nulled;
    # null stays null; balance markers' received_from is unchanged.
    assert out["product_received_from"].to_list() == ["43", "DKSH", None, "87", None]


def test_clean_received_from_copies_start_balance_and_strips_numeric_supplier():
    """Pin _clean_received_from's two paths: (1) START rows copy
    received_from into product_balance; non-START rows preserve their
    existing balance (defensive — earlier code wiped them, which only
    happened to be a no-op because nothing populates product_balance
    before this step). (2) numeric-only product_received_from is nulled
    while alphabetic / mixed-alphanumeric values survive."""
    df = pl.DataFrame(
        {
            "product_units_received": ["START", "5", "3", "2"],
            "product_received_from": ["DKSH", "DKSH", "43", "DKSH 43"],
            "product_balance": [None, None, None, None],
            "product_sheet_name": ["Jan", "Jan", "Jan", "Jan"],
        },
        schema={
            "product_units_received": pl.String,
            "product_received_from": pl.String,
            "product_balance": pl.String,
            "product_sheet_name": pl.String,
        },
    )

    out = _clean_received_from(df)

    # START row gets received_from copied into balance; other rows keep their
    # original (null in production after apply_schema seed).
    assert out["product_balance"].to_list() == ["DKSH", None, None, None]
    # Alpha-strip on received_from: numeric-only "43" → null, alpha + mixed survive.
    assert out["product_received_from"].to_list() == ["DKSH", "DKSH", None, "DKSH 43"]


def test_clean_received_from_no_start_preserves_balance():
    """When no row contains START, product_balance must be untouched.
    Only the alpha-strip on received_from runs."""
    df = pl.DataFrame(
        {
            "product_units_received": ["5", "3"],
            "product_received_from": ["DKSH", "43"],
            "product_balance": ["100", "200"],  # pre-existing sentinels
            "product_sheet_name": ["Jan", "Jan"],
        },
        schema={
            "product_units_received": pl.String,
            "product_received_from": pl.String,
            "product_balance": pl.String,
            "product_sheet_name": pl.String,
        },
    )

    out = _clean_received_from(df)

    assert out["product_balance"].to_list() == ["100", "200"]
    assert out["product_received_from"].to_list() == ["DKSH", None]


def test_clean_received_from_preserves_balance_on_sheets_without_start():
    """Two-sheet frame, START only in sheet A. Sheet B's pre-existing
    product_balance must be preserved — a START in one sheet must not
    propagate balance assignments (or wipes) to other sheets."""
    df = pl.DataFrame(
        {
            "product_units_received": ["START", "5", "3", "2"],
            "product_received_from": ["DKSH", "DKSH", "Acme", "BMS"],
            "product_balance": [None, None, "50", "75"],
            "product_sheet_name": ["Jan", "Jan", "Feb", "Feb"],
        },
        schema={
            "product_units_received": pl.String,
            "product_received_from": pl.String,
            "product_balance": pl.String,
            "product_sheet_name": pl.String,
        },
    )

    out = _clean_received_from(df)

    # Sheet Jan: START row copies received_from to balance; other Jan row keeps null.
    # Sheet Feb: no START → both rows preserve their existing balance ("50", "75").
    assert out["product_balance"].to_list() == ["DKSH", None, "50", "75"]


def test_format_dates_normalizes_separator_typos():
    """Cells with non-standard separators (period after day, underscore
    before year, repeated dashes) parse to the intended date after
    pre-normalization (regression for 2020 CDA Feb20, 2024 Likas Jan24,
    2022 Mukdahan Apr22). The Excel-datetime time-strip ('YYYY-MM-DD
    HH:MM:SS') and the canonical 'dd-Mon-yyyy' format must continue to
    parse correctly."""
    df = pl.DataFrame(
        {
            "product": ["P1", "P2", "P3", "P4", "P5"],
            "product_entry_date": [
                "24.Feb 2020",  # CDA period-after-day typo
                "22-Jan_2024",  # Likas underscore-before-year typo
                "16-Apr--2022",  # Mukdahan double-dash typo
                "2020-02-24 00:00:00",  # Excel datetime cast — time must strip
                "16-Apr-2022",  # canonical dd-Mon-yyyy — must parse
            ],
        },
        schema={
            "product": pl.String,
            "product_entry_date": pl.String,
        },
    )

    out = _format_dates(df)

    assert out["product_entry_date"].to_list() == [
        date(2020, 2, 24),
        date(2024, 1, 22),
        date(2022, 4, 16),
        date(2020, 2, 24),
        date(2022, 4, 16),
    ]


def test_format_dates_preserves_year_typo_sentinels():
    """Year typos (real Excel datetime with wrong year, 5-digit year
    strings) must continue to fail parsing — separator normalization
    must not accidentally recover them. Mahosot's datetime(2009,12,4)
    parses to a real 2009 date (Python validates it later via
    _validate_entry_dates); NPH's 5-digit year falls through to the
    error path."""
    df = pl.DataFrame(
        {
            "product": ["Mahosot", "NPH"],
            "product_sheet_name": ["Jun", "Jun"],
            "product_entry_date": [
                "2009-12-04 00:00:00",  # Mahosot Excel datetime, year typo
                "1 jun 20203",  # NPH 5-digit year
            ],
        },
        schema={
            "product": pl.String,
            "product_sheet_name": pl.String,
            "product_entry_date": pl.String,
        },
    )

    out = _format_dates(df)

    parsed = out["product_entry_date"].to_list()
    # Mahosot: real datetime parses to 2009-12-04 (year-floor catches later).
    assert parsed[0] == date(2009, 12, 4)
    # NPH: 5-digit year is unparseable; parse_date_column emits a sentinel
    # error_val_date or None — either way, not a valid 2020/2023 date.
    assert parsed[1] is None or parsed[1] != date(2023, 6, 1)
    assert parsed[1] != date(2020, 6, 1)


def test_split_multi_product_cells_extracts_box_count_to_units_received():
    """Pins the \\d+ count regex: a count starting with the digit '1'
    followed by '0' must be extracted whole as '10', not '1'."""
    df = pl.DataFrame(
        {
            "product": ["Accu-Check Strips (10 box)"],
            "product_received_from": ["DKSH"],
            "product_released_to": [None],
            "product_units_received": [None],
            "product_units_released": [None],
        },
        schema={
            "product": pl.String,
            "product_received_from": pl.String,
            "product_released_to": pl.String,
            "product_units_received": pl.String,
            "product_units_released": pl.String,
        },
    )

    out = _split_multi_product_cells(df)

    assert out["product_units_notes"].to_list() == ["10 box"]
    assert out["product_units_received"].to_list() == ["10"]
    assert out["product_units_released"].to_list() == [None]


def test_split_multi_product_cells_extracts_unit_count_to_released_when_released_to_set():
    """Same shape as the box test but routes the count to product_units_released
    when product_released_to is set and product_received_from is null."""
    df = pl.DataFrame(
        {
            "product": ["Accu-Check Strips (10 unit)"],
            "product_received_from": [None],
            "product_released_to": ["KD_EW001"],
            "product_units_received": [None],
            "product_units_released": [None],
        },
        schema={
            "product": pl.String,
            "product_received_from": pl.String,
            "product_released_to": pl.String,
            "product_units_received": pl.String,
            "product_units_released": pl.String,
        },
    )

    out = _split_multi_product_cells(df)

    assert out["product_units_notes"].to_list() == ["10 unit"]
    assert out["product_units_released"].to_list() == ["10"]
    assert out["product_units_received"].to_list() == [None]


def test_misplaced_datetime_cell_in_units_received_logs_and_recodes_to_zero(collector):
    """Pin the handling of a date typo'd into the units_received column.

    Reading the cell's underlying Excel serial (43644.0 for 2019-06-28) would
    pollute the balance trajectory by tens of thousands. Instead the value
    stringifies, the Float64 cast in step 2.11 fails, and step 2.12 recodes the
    null to 0.0. Step 2.11 also emits one ``type_conversion`` ErrorCollector
    entry, so the discarded cell is recoverable from the log.
    Regression for the 22 real-divergence rows in
    2019_Sultanah Bahiyah_DC / 2019_Penang_DC / 2020 Mandalay
    surfaced by Ali_internship/product_balance_diff_v1.ipynb."""
    df = pl.DataFrame(
        {
            "file_name": ["2019_SB.xlsx"],
            "product_sheet_name": ["Jun19"],
            "product": ["Accu-Chek Performa Test Strip"],
            "product_entry_date": [None],
            "product_units_received": ["2019-06-28 00:00:00"],  # typo cell
            "product_units_released": [None],
            "product_received_from": [None],
            "product_released_to": [None],
            "product_units_returned": [None],
            "product_returned_by": [None],
            "product_balance": [None],
            "product_table_month": ["06"],
            "product_table_year": [2019.0],
            "product_balance_status": [None],
            "product_category": [None],
            "product_unit_capacity": [None],
            "product_units_notes": [None],
            "orig_product_released_to": [None],
            "product_remarks": [None],
        },
        schema={
            "file_name": pl.String,
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_entry_date": pl.String,
            "product_units_received": pl.String,
            "product_units_released": pl.String,
            "product_received_from": pl.String,
            "product_released_to": pl.String,
            "product_units_returned": pl.String,
            "product_returned_by": pl.String,
            "product_balance": pl.String,
            "product_table_month": pl.String,
            "product_table_year": pl.Float64,
            "product_balance_status": pl.String,
            "product_category": pl.String,
            "product_unit_capacity": pl.String,
            "product_units_notes": pl.String,
            "orig_product_released_to": pl.String,
            "product_remarks": pl.String,
        },
    )

    out = clean_product_data(df)

    assert out["product_units_received"].to_list() == [0.0]

    units_errors = [
        e
        for e in collector.findings
        if e.column == "product_units_received" and e.function_name == "_clean_units_received"
    ]
    assert len(units_errors) == 1
    err = units_errors[0]
    assert err.error_code == "type_conversion"
    assert err.original_value == "2019-06-28 00:00:00"
    assert err.file_name == "2019_SB.xlsx"
    assert err.patient_id == "Accu-Chek Performa Test Strip"


def test_running_balance_eliminates_float_residue():
    """Pin .round(10) on the cumsum result. Without it, Python's vectorized
    cumsum yields 2.220446e-16 instead of 0 on rows where the running delta
    sum hits a non-binary-clean target (e.g. 1.8 - 0.4 - 1.4 = 2.22e-16
    because 0.4+1.4 in float64 is 1.7999999999999998). Regression for the 600
    FP-noise rows surfaced
    by Ali_internship/product_balance_diff_v3.ipynb (V3 corpus example:
    2021_Lao Friends, Feb21, Mixtard 30 Penfill 3ml (5s))."""
    df = pl.DataFrame(
        {
            "product_sheet_name": ["Feb21"] * 4,
            "product": ["Mixtard"] * 4,
            "product_balance": [1.8, None, None, None],
            "product_balance_status": ["start", "change", "change", "end"],
            "product_units_received": [0.0, 0.0, 0.0, 0.0],
            "product_units_released": [0.0, 0.4, 1.4, 0.0],
            "product_units_returned": [0.0, 0.0, 0.0, 0.0],
            "product_table_year": [2020, 2020, 2020, 2020],  # < 2021 to skip end-row zeroing
        },
        schema={
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_balance": pl.Float64,
            "product_balance_status": pl.String,
            "product_units_received": pl.Float64,
            "product_units_released": pl.Float64,
            "product_units_returned": pl.Float64,
            "product_table_year": pl.Int32,
        },
    )

    out = _compute_running_balance(df)

    # Strict equality — without .round(10) the 3rd row would be 2.22e-16.
    assert out["product_balance"].to_list() == [1.8, 1.4, 0.0, 0.0]


def test_fill_product_names_and_sort_treats_sentinel_as_null_for_rank():
    """Pin the sentinel-rank fix. The 9999-09-09 parse-failure sentinel must
    be treated as null when computing the per-(sheet, product) rank, so it
    falls into the 'preserve input order' branch rather than sorting to the
    dense_d+1 end-of-changes position. Real-world driver: the 11 Tier-2 rows
    in product_balance documented in product_balance_investigation.md: the
    sentinel was sorting after every valid date, distorting the cumulative
    balance order."""
    df = pl.DataFrame(
        {
            "product_sheet_name": ["Jun24"] * 5,
            "product": ["P"] * 5,
            "product_entry_date": [
                None,
                date(2024, 1, 15),
                date(9999, 9, 9),
                date(2024, 3, 15),
                None,
            ],
            "product_balance_status": ["start", "change", "change", "change", "end"],
            "product_table_month": [6] * 5,
            "index": [1, 2, 3, 4, 5],
        },
        schema={
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_entry_date": pl.Date,
            "product_balance_status": pl.String,
            "product_table_month": pl.Int32,
            "index": pl.Int64,
        },
    )

    out = _fill_product_names_and_sort(df)

    # After fix: sentinel sits between the two valid mid-rows in input order
    # (rank=row_n=3 ties with rank for 2024-03-15=dense_d+1=3, stable sort
    # keeps the sentinel at input position 3, valid date at position 4).
    statuses = out["product_balance_status"].to_list()
    assert statuses == ["start", "change", "change", "change", "end"]
    dates = out["product_entry_date"].to_list()
    assert dates[0] is None  # start
    assert dates[1] == date(2024, 1, 15)  # earlier valid date
    assert dates[2] == date(9999, 9, 9)  # sentinel — between A and B
    assert dates[3] == date(2024, 3, 15)  # later valid date
    assert dates[4] is None  # end


def _check_dates_df(
    entry_dates: list[date | None],
    table_month: int = 6,
    table_year: int = 2024,
) -> pl.DataFrame:
    """Fixture for _check_entry_dates_match_sheet. Mirrors the post-2.6 schema:
    table_month is still String, table_year is still Float64 (the schema cast
    at step 2.16 hasn't run yet)."""
    n = len(entry_dates)
    return pl.DataFrame(
        {
            "product": [f"P{i}" for i in range(n)],
            "product_entry_date": entry_dates,
            "product_table_year": [float(table_year)] * n,
            "product_table_month": [f"{table_month:02d}"] * n,
            "product_sheet_name": [f"{table_month:02d}"] * n,
            "file_name": ["t.xlsx"] * n,
        },
        schema={
            "product": pl.String,
            "product_entry_date": pl.Date,
            "product_table_year": pl.Float64,
            "product_table_month": pl.String,
            "product_sheet_name": pl.String,
            "file_name": pl.String,
        },
    )


def test_check_entry_dates_logs_month_mismatch(collector):
    df = _check_dates_df(
        entry_dates=[date(2024, 6, 15), date(2024, 3, 15)],
        table_month=6,
        table_year=2024,
    )

    _check_entry_dates_match_sheet(df)

    assert len(collector) == 1
    err = collector.findings[0]
    assert err.column == "product_entry_date"
    assert err.error_code == "entry_date_outside_sheet_month"
    assert err.function_name == "check_entry_dates"
    assert err.patient_id == "P1"


def test_check_entry_dates_logs_year_mismatch(collector):
    df = _check_dates_df(
        entry_dates=[date(2023, 6, 15)],  # year mismatch even though month matches
        table_month=6,
        table_year=2024,
    )
    _check_entry_dates_match_sheet(df)
    assert len(collector) == 1


def test_check_entry_dates_skips_sentinel_buddhist_and_null(collector):
    df = _check_dates_df(
        entry_dates=[
            None,  # null — skip
            date(9999, 9, 9),  # parse-failure sentinel — skip
            date(2567, 11, 11),  # Buddhist-era — skip
            date(2024, 6, 15),  # match — skip
        ],
        table_month=6,
        table_year=2024,
    )
    _check_entry_dates_match_sheet(df)
    assert len(collector) == 0


def test_check_entry_dates_no_log_on_match(collector):
    df = _check_dates_df(
        entry_dates=[date(2024, 6, 1), date(2024, 6, 30)],
        table_month=6,
        table_year=2024,
    )
    _check_entry_dates_match_sheet(df)
    assert len(collector) == 0


def test_fat_finger_future_falls_into_input_order_rank_after_validation(collector):
    """Pin the deliberate _validate_entry_dates × _fill_product_names_and_sort
    interaction. `2099-03-15` is clobbered to the 9999-09-09 sentinel inside
    _validate_entry_dates, and the sentinel is then treated as null when
    ranking -- so a fat-fingered year holds its input position instead of
    sorting to the end of the ledger and distorting the running balance.

    The test exists so any future revert of either _validate_entry_dates'
    future-year guard or the sentinel-rank fix in
    _fill_product_names_and_sort breaks loudly."""
    df = pl.DataFrame(
        {
            "product": ["P", "P", "P", "P"],
            "product_entry_date": [None, date(2099, 3, 15), date(2024, 6, 1), None],
            "product_balance_status": ["start", "change", "change", "end"],
            "product_table_year": [2024] * 4,
            "product_table_month": [6] * 4,
            "product_sheet_name": ["Jun24"] * 4,
            "file_name": ["t.xlsx"] * 4,
            "index": [1, 2, 3, 4],
        },
        schema={
            "product": pl.String,
            "product_entry_date": pl.Date,
            "product_balance_status": pl.String,
            "product_table_year": pl.Int32,
            "product_table_month": pl.Int32,
            "product_sheet_name": pl.String,
            "file_name": pl.String,
            "index": pl.Int64,
        },
    )

    validated = _validate_entry_dates(df)
    out = _fill_product_names_and_sort(validated)

    # _validate_entry_dates rewrote the 2099 future to the sentinel.
    assert validated["product_entry_date"].to_list()[1] == date(9999, 9, 9)
    assert len(collector) == 1

    # In the sorted output, the (now-sentinel) row sits at its input position
    # 2 — not the dense-rank tail. Statuses confirm row ordering.
    assert out["product_balance_status"].to_list() == [
        "start",
        "change",
        "change",
        "end",
    ]
    dates = out["product_entry_date"].to_list()
    assert dates[0] is None  # start
    assert dates[1] == date(9999, 9, 9)  # was 2099-03-15, now sentinel-as-null
    assert dates[2] == date(2024, 6, 1)  # valid mid-row
    assert dates[3] is None  # end


def test_clean_product_data_handles_columnless_raw_frame(collector):
    """Trackers from pre-product-tracking years extract to a 0-column,
    0-row frame (no product section in any sheet). Cleaning must hand back
    an empty, schema-conformant frame rather than crash on a missing
    "product" column (ticket 14)."""
    df_raw = pl.DataFrame()

    out = clean_product_data(df_raw)

    assert out.height == 0
    assert out.width == 20
    assert "product" in out.columns
    assert len(collector) == 0


def _balance_reconciliation_frame(source_closing, released, status=None):
    """Fixture for the closing-balance reconciliation check (ticket 36).

    Two transactions off a start balance of 100, with the source's own
    recorded closing balance supplied by the caller so a test can make it
    agree or disagree with what step 2.15 computes.
    """
    n = 3
    return pl.DataFrame(
        {
            "file_name": ["2024_Test.xlsx"] * n,
            "index": [1, 2, 3],
            "product_sheet_name": ["Jan24"] * n,
            "product": ["Test Strips"] * n,
            "product_balance": [100.0, None, source_closing],
            "product_balance_status": status or ["start", "change", "end"],
            "product_units_received": [0.0, 0.0, 0.0],
            "product_units_released": released,
            "product_units_returned": [0.0] * n,
            "product_table_year": [2020] * n,
        },
        schema={
            "file_name": pl.String,
            "index": pl.Int64,
            "product_sheet_name": pl.String,
            "product": pl.String,
            "product_balance": pl.Float64,
            "product_balance_status": pl.String,
            "product_units_received": pl.Float64,
            "product_units_released": pl.Float64,
            "product_units_returned": pl.Float64,
            "product_table_year": pl.Int32,
        },
    )


def _reconciliation_errors(collector):
    return [e for e in collector.findings if e.error_code == "balance_reconciliation"]


def test_running_balance_logs_when_closing_disagrees_with_source(collector):
    """Ticket 36: the running balance is recomputed from the start balance plus
    transactions, in Python's chronological row order rather than the source's
    data-entry order, so intermediate balances legitimately differ from the
    tracker's. The *closing* balance is order-independent, so a disagreement
    there is a real source arithmetic or data-entry problem and must surface."""
    # 100 - 8 - 4 = 88 computed, but the tracker recorded 90.
    df = _balance_reconciliation_frame(source_closing=90.0, released=[0.0, 8.0, 4.0])

    out = _compute_running_balance(df)

    assert out["product_balance"].to_list() == [100.0, 92.0, 88.0]
    errors = _reconciliation_errors(collector)
    assert len(errors) == 1
    assert errors[0].column == "product_balance"
    assert errors[0].function_name == "_compute_running_balance"
    assert "90" in errors[0].message
    assert "88" in errors[0].message


def test_running_balance_silent_when_closing_matches_source(collector):
    """No warning when the recomputed ledger lands where the tracker says."""
    df = _balance_reconciliation_frame(source_closing=88.0, released=[0.0, 8.0, 4.0])

    _compute_running_balance(df)

    assert _reconciliation_errors(collector) == []


def test_running_balance_silent_when_source_records_no_closing_balance(collector):
    """Most groups record only a start balance and leave the rest blank -- that
    is not a disagreement, and warning on it would drown the real signal."""
    df = _balance_reconciliation_frame(source_closing=None, released=[0.0, 8.0, 4.0])

    _compute_running_balance(df)

    assert _reconciliation_errors(collector) == []


def test_running_balance_reconciliation_is_optional():
    """Callers without an ErrorCollector (existing tests, ad-hoc use) still work."""
    df = _balance_reconciliation_frame(source_closing=90.0, released=[0.0, 8.0, 4.0])

    out = _compute_running_balance(df)

    assert out["product_balance"].to_list() == [100.0, 92.0, 88.0]
