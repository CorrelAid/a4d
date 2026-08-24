"""Wide-format Mandalay tracker reshaping (extraction steps 1.4a and 1.4b).

Two distinct formats exist in the Mandalay Children's Hospital trackers
that need long-format conversion before the main extraction flow
continues.
"""

import re

import polars as pl


def _rows_to_df(rows: list[dict], schema: dict) -> pl.DataFrame:
    """Build a DataFrame from row-dicts using explicit schema (avoids inference pitfalls).

    A source column that was entirely null (e.g. "Units Released" before the
    comma-cell split populates it) infers dtype ``Null`` from ``df.schema``;
    pinning the output to that dtype would silently drop the new string
    values this function writes into it. Widen ``Null`` columns to ``Utf8``
    (same fix as ``tables/logs.py``'s ``schema_overrides``, same root cause).
    """
    if not rows:
        return pl.DataFrame(schema=schema)
    safe_schema = {name: (pl.Utf8 if dtype == pl.Null else dtype) for name, dtype in schema.items()}
    columns = {name: [row.get(name) for row in rows] for name in schema}
    return pl.DataFrame(columns, schema=safe_schema)


_RELEASED_TO_WIDE = "Released To (select from drop down list)"
_TOTAL = "Total Units Released"
_PER_PERSON = "Units Released per person"


def handle_wide_format_columns(df: pl.DataFrame, filename: str) -> pl.DataFrame:
    """Expand 2020-2021 Mandalay wide-format columns into rows (step 1.4a).

    Gate: both ``Total Units Released`` and ``Units Released per person``
    columns must be present. Otherwise return ``df`` unchanged.
    """
    del filename  # gate is column-based, not filename-based

    cols = df.columns
    if _TOTAL not in cols or _PER_PERSON not in cols or _RELEASED_TO_WIDE not in cols:
        return df
    if df.height == 0:
        return df

    start_col_idx = cols.index(_RELEASED_TO_WIDE) + 1
    end_col_idx = cols.index(_PER_PERSON) - 1
    if start_col_idx > end_col_idx:
        return df

    intermediate_cols = cols[start_col_idx : end_col_idx + 1]

    date_col = "Date" if "Date" in cols else next((c for c in cols if "Date" in c), None)

    new_rows: list[dict] = []
    for row in df.iter_rows(named=True):
        new_rows.append(dict(row))

        total = row.get(_TOTAL)
        per_person = row.get(_PER_PERSON)

        if total is None or per_person is None:
            continue
        if str(total).strip() == "" or str(per_person).strip() == "":
            continue
        if total == per_person:
            continue

        for col in intermediate_cols:
            cell = row.get(col)
            if cell is None:
                continue
            if isinstance(cell, str) and cell.strip() == "":
                continue

            new_row = dict.fromkeys(cols)
            if date_col is not None:
                new_row[date_col] = row.get(date_col)
            new_row[_RELEASED_TO_WIDE] = cell
            new_row[_PER_PERSON] = per_person
            new_rows.append(new_row)

    return _rows_to_df(new_rows, dict(df.schema))


def handle_wide_format_cells(df: pl.DataFrame, filename: str) -> pl.DataFrame:
    """Split 2017-2019 Mandalay comma-separated ``Released To`` cells (step 1.4b)."""
    if not any(pat in filename for pat in ("2017_Mandalay", "2018_Mandalay", "2019_Mandalay")):
        return df
    if df.height == 0:
        return df

    def _find_col(substr: str) -> str | None:
        return next((c for c in df.columns if substr in c), None)

    released_to = _find_col("Released To")
    units_released = _find_col("Units Released")
    date_col = _find_col("Date")
    received_from = _find_col("Received From")

    # Individual None checks (not all([...])) so ty/mypy narrow each name to
    # `str` below instead of leaving them as `str | None`.
    if released_to is None or units_released is None or date_col is None or received_from is None:
        return df

    pattern = re.compile(r"(-\s*\d)|(,\s*)")
    if not any(v is not None and pattern.search(str(v)) for v in df[released_to].to_list()):
        return df

    cols = df.columns
    new_rows: list[dict] = []
    for row in df.iter_rows(named=True):
        new_rows.append(dict(row))

        cell = row.get(released_to)
        if cell is None or "," not in str(cell):
            continue

        for fragment in str(cell).split(","):
            fragment = fragment.strip()
            if not fragment:
                continue

            if "-" in fragment:
                name, qty = fragment.split("-", 1)
                name = name.strip()
                qty = qty.strip()
            else:
                name, qty = fragment, None

            new_row = dict.fromkeys(cols)
            new_row[date_col] = row.get(date_col)
            new_row[received_from] = row.get(received_from)
            new_row[released_to] = name or None
            new_row[units_released] = qty
            new_rows.append(new_row)

    result = _rows_to_df(new_rows, dict(df.schema))

    comma_mask = pl.col(released_to).str.contains(",", literal=True).fill_null(False)
    result = result.with_columns(
        [
            pl.when(comma_mask).then(None).otherwise(pl.col(units_released)).alias(units_released),
            pl.when(comma_mask).then(None).otherwise(pl.col(released_to)).alias(released_to),
        ]
    )

    return result
