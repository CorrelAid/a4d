"""Product reference-data loaders, backing cleaning steps 2.19 and 2.20.

Loads the known-products list and product category mapping from the
``Stock_Summary`` sheet of ``master_tracker_variables.xlsx`` in the
shared ``reference_data/`` directory.
"""

from functools import lru_cache

import openpyxl
import polars as pl

from a4d.reference.loaders import get_reference_data_path


@lru_cache(maxsize=1)
def _read_stock_summary() -> pl.DataFrame:
    """Read the Stock_Summary sheet as a two-column DataFrame.

    Returns a frame with columns ``product`` (lowercased values) and
    ``product_category`` (original casing). Null rows and duplicates
    are dropped.
    """
    xlsx_path = get_reference_data_path("master_tracker_variables.xlsx")
    wb = openpyxl.load_workbook(xlsx_path, data_only=True, read_only=True)
    try:
        ws = wb["Stock_Summary"]
        rows = list(ws.iter_rows(min_row=2, values_only=True))
    finally:
        wb.close()

    products: list[str] = []
    categories: list[str | None] = []
    for row in rows:
        if not row:
            continue
        name = row[0]
        if name is None:
            continue
        name_str = str(name).strip()
        if not name_str:
            continue
        products.append(name_str.lower())
        cat = row[1] if len(row) > 1 else None
        categories.append(str(cat).strip() if cat is not None else None)

    return pl.DataFrame({"product": products, "product_category": categories}).unique(
        subset=["product"], keep="first", maintain_order=True
    )


def load_known_products() -> list[str]:
    """Load the lowercased list of known product names.

    Backs step 2.19 (flagging product names absent from the reference)
    (``report_unknown_products``). Reads the ``Stock_Summary`` sheet of
    ``reference_data/master_tracker_variables.xlsx`` and returns each
    product name lowercased.

    Returns:
        List of lowercased product names.
    """
    return _read_stock_summary()["product"].to_list()


def load_product_categories() -> pl.DataFrame:
    """Load the product-to-category mapping.

    Backs step 2.20 (joining each product's category)
    (``add_product_categories``). Reads the ``Stock_Summary`` sheet of
    ``reference_data/master_tracker_variables.xlsx`` and returns a
    two-column DataFrame.

    Returns:
        DataFrame with columns ``product`` and ``product_category``.
    """
    return _read_stock_summary()
