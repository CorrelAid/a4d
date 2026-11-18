"""Accent-free copies of name columns.

The original column keeps the official spelling ("Takéo"); the copy, named
<column>_ascii, holds the same name without accents ("Takeo"). Case and spaces
are kept. The copy is safe for joins, filters and maps that may not handle
accented characters.
"""

import unicodedata

import polars as pl


def fold_accents(text: str | None) -> str | None:
    """Remove accents, keep case and spaces: "Hà Nội" -> "Ha Noi".

    "đ" and "Đ" are letters of their own in Unicode, not "d" with an accent,
    so they are mapped by hand.
    """
    if text is None:
        return None
    text = text.replace("đ", "d").replace("Đ", "D")
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def add_ascii_columns(df: pl.DataFrame, columns: list[str]) -> pl.DataFrame:
    """Add <column>_ascii, an accent-free copy, for each of ``columns`` present in df."""
    present = [c for c in columns if c in df.columns]
    return df.with_columns(
        [
            pl.col(c)
            .cast(pl.String)
            .map_elements(fold_accents, return_dtype=pl.String)
            .alias(f"{c}_ascii")
            for c in present
        ]
    )
