"""Create clinic static data table from reference data.

Replicates R pipeline's create_table_clinic_static_data() function:
reads clinic_data.xlsx, fills down hierarchical columns, exports as parquet.
"""

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.reference.loaders import find_reference_data_dir

# Text columns filled downward to handle merged/blank cells in the Excel sheet.
# R: tidyr::fill(country_code:clinic_id, .direction = "down")
_FILL_COLUMNS = [
    "country",
    "clinic_province",
    "clinic_name",
    "clinic_status",
    "clinic_id",
    "country_code",
    "clinic_code",
    "patient_id_example",
]


def create_table_clinic_static(output_dir: Path) -> Path:
    """Create clinic static data table from reference data.

    Reads clinic_data.xlsx from reference_data/, fills hierarchical columns
    downward (matching R's tidyr::fill behaviour), and writes parquet.

    Args:
        output_dir: Directory to write the parquet file

    Returns:
        Path to created clinic_data_static.parquet
    """
    reference_dir = find_reference_data_dir()
    clinic_file = reference_dir / "clinic_data.xlsx"

    if not clinic_file.exists():
        raise FileNotFoundError(f"Clinic data file not found: {clinic_file}")

    logger.info(f"Reading clinic data from: {clinic_file}")

    df = pl.read_excel(clinic_file, sheet_id=1)

    # Drop unnamed index column — R: select(2:11)
    unnamed_cols = [c for c in df.columns if c.startswith("__UNNAMED")]
    if unnamed_cols:
        df = df.drop(unnamed_cols)

    # Fill nulls downward for hierarchical columns — R: tidyr::fill(..., .direction = "down")
    fill_cols = [c for c in _FILL_COLUMNS if c in df.columns]
    if fill_cols:
        df = df.with_columns([pl.col(c).forward_fill() for c in fill_cols])

    logger.info(f"Clinic static data: {df.shape[0]} rows, {df.shape[1]} columns")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "clinic_data_static.parquet"
    df.write_parquet(output_file)

    logger.info(f"Clinic static table saved: {output_file}")
    return output_file
