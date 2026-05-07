"""Meta schema definition for product data - matches R pipeline's preparing_product_fields()."""

import polars as pl


def get_product_data_schema() -> dict[str, type[pl.DataType] | pl.DataType]:
    """Get the complete meta schema for product data.

    This schema matches the R pipeline's preparing_product_fields() in
    script3_create_table_product_data.R. Column order matches R's field list.

    Returns:
        Dictionary mapping column names to Polars data types
    """
    return {
        "product": pl.String,  # character() in R
        "product_units_notes": pl.String,
        "product_entry_date": pl.Date,  # Date in R
        "product_units_released": pl.Float64,  # numeric() in R
        "product_released_to": pl.String,
        "product_units_received": pl.Float64,
        "product_received_from": pl.String,
        "product_balance": pl.Float64,
        "product_units_returned": pl.Float64,
        "product_returned_by": pl.String,
        "product_table_month": pl.Int32,  # integer() in R
        "product_table_year": pl.Int32,
        "product_sheet_name": pl.String,
        "file_name": pl.String,
        "product_balance_status": pl.String,
        "product_category": pl.String,
        "orig_product_released_to": pl.String,
        "product_unit_capacity": pl.Int32,
        "product_remarks": pl.String,
        "clinic_id": pl.String,
    }


def apply_schema(df: pl.DataFrame) -> pl.DataFrame:
    """Apply the meta schema to a DataFrame.

    This function:
    1. Adds missing columns with NULL values typed per the schema.
    2. Reorders columns to match schema order.

    Casting is the caller's responsibility (see ``safe_convert_column``).

    Args:
        df: Input DataFrame (may be missing columns)

    Returns:
        DataFrame with complete schema applied
    """
    schema = get_product_data_schema()

    # Start with existing columns
    df_result = df

    # Add missing columns with NULL values
    missing_cols = set(schema.keys()) - set(df.columns)
    for col in missing_cols:
        df_result = df_result.with_columns(pl.lit(None, dtype=schema[col]).alias(col))

    # Reorder columns to match schema order
    df_result = df_result.select(list(schema.keys()))

    return df_result


def get_string_columns() -> list[str]:
    """Get list of string columns from schema."""
    schema = get_product_data_schema()
    return [col for col, dtype in schema.items() if dtype == pl.String]
