"""Create clinic static data table from reference data.

Reads clinic_data.xlsx, fills down hierarchical columns, exports as parquet.
"""

import warnings
from pathlib import Path

import polars as pl
from loguru import logger

from a4d.reference.loaders import find_reference_data_dir

# polars' own calamine+pyarrow "eager sheet load" path in read_excel() calls
# from_arrow() on an ArrowStreamExportable without disambiguating DataFrame
# vs Series, and warns about its own internal call — nothing in our
# read_excel() arguments can influence it. Upstream issue, not ours to fix;
# narrowly suppress rather than let it flood every run's console output.
warnings.filterwarnings(
    "ignore",
    message=r"from_arrow\(<ArrowStreamExportable>\) will return a Series",
    category=FutureWarning,
)

# Text columns filled downward. The source sheet merges these cells, so only
# the first row of each country/province block carries a value.
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
    downward, and writes parquet.

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

    # Drop the sheet's unnamed index column
    unnamed_cols = [c for c in df.columns if c.startswith("__UNNAMED")]
    if unnamed_cols:
        df = df.drop(unnamed_cols)

    # Fill nulls downward for the merged hierarchical columns
    fill_cols = [c for c in _FILL_COLUMNS if c in df.columns]
    if fill_cols:
        df = df.with_columns([pl.col(c).forward_fill() for c in fill_cols])

    logger.info(f"Clinic static data: {df.shape[0]} rows, {df.shape[1]} columns")

    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "clinic_data_static.parquet"
    df.write_parquet(output_file)

    logger.info(f"Clinic static table saved: {output_file}")
    return output_file
