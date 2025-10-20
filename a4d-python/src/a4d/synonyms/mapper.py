"""Column name mapper for standardizing tracker file columns.

This module handles the mapping of various column name variants (synonyms)
to standardized column names used throughout the pipeline.
"""

from pathlib import Path

import polars as pl
from loguru import logger

from a4d.utils import get_reference_data_path, load_yaml


class ColumnMapper:
    """Maps synonym column names to standardized names.

    Loads column synonyms from YAML files and provides methods to rename
    DataFrame columns to their standardized names.

    Example YAML structure:
        age:
          - Age
          - Age*
          - age on reporting
          - Age (Years)
        patient_id:
          - ID
          - Patient ID
          - Patient ID*

    Attributes:
        yaml_path: Path to the synonym YAML file
        synonyms: Dict mapping standard names to lists of synonyms
        _lookup: Reverse lookup dict mapping synonyms to standard names
    """

    def __init__(self, yaml_path: Path):
        """Initialize the mapper by loading synonyms from YAML.

        Args:
            yaml_path: Path to the synonym YAML file

        Raises:
            FileNotFoundError: If the YAML file doesn't exist
            yaml.YAMLError: If the YAML file is malformed
        """
        self.yaml_path = yaml_path
        self.synonyms: dict[str, list[str]] = load_yaml(yaml_path)

        # Build reverse lookup: synonym -> standard_name
        self._lookup: dict[str, str] = self._build_lookup()

        logger.info(
            f"Loaded {len(self.synonyms)} standard columns with "
            f"{len(self._lookup)} total synonyms from {yaml_path.name}"
        )

    def _build_lookup(self) -> dict[str, str]:
        """Build reverse lookup dictionary from synonyms to standard names.

        Returns:
            Dict mapping each synonym to its standard column name
        """
        lookup = {}
        for standard_name, synonym_list in self.synonyms.items():
            # Handle empty lists (columns with no synonyms)
            if not synonym_list:
                continue

            for synonym in synonym_list:
                if synonym in lookup:
                    logger.warning(
                        f"Duplicate synonym '{synonym}' found for both "
                        f"'{lookup[synonym]}' and '{standard_name}'. "
                        f"Using '{standard_name}'."
                    )
                lookup[synonym] = standard_name

        return lookup

    def get_standard_name(self, column: str) -> str:
        """Get the standard name for a column.

        Args:
            column: Column name (may be a synonym)

        Returns:
            Standard column name, or original if no mapping exists
        """
        return self._lookup.get(column, column)

    def rename_columns(
        self,
        df: pl.DataFrame,
        strict: bool = False,
    ) -> pl.DataFrame:
        """Rename DataFrame columns using synonym mappings.

        Args:
            df: Input DataFrame with potentially non-standard column names
            strict: If True, raise error if unmapped columns exist
                   If False, keep unmapped columns as-is

        Returns:
            DataFrame with standardized column names

        Raises:
            ValueError: If strict=True and unmapped columns exist
        """
        # Build rename mapping for columns that need renaming
        rename_map = {}
        unmapped_columns = []

        for col in df.columns:
            standard_name = self.get_standard_name(col)

            if standard_name == col and col not in self.synonyms:
                # Column is not in lookup and not a standard name
                unmapped_columns.append(col)
            elif standard_name != col:
                # Column needs to be renamed
                rename_map[col] = standard_name

        # Log unmapped columns
        if unmapped_columns:
            if strict:
                raise ValueError(
                    f"Unmapped columns found: {unmapped_columns}. "
                    "These columns do not appear in the synonym file."
                )
            else:
                logger.debug(
                    f"Keeping {len(unmapped_columns)} unmapped columns as-is: "
                    f"{unmapped_columns}"
                )

        # Log successful mappings
        if rename_map:
            logger.debug(
                f"Renaming {len(rename_map)} columns: {list(rename_map.items())}"
            )

        return df.rename(rename_map) if rename_map else df

    def get_expected_columns(self) -> set[str]:
        """Get set of all standard column names.

        Returns:
            Set of standard column names defined in the synonym file
        """
        return set(self.synonyms)

    def get_missing_columns(self, df: pl.DataFrame) -> set[str]:
        """Get standard columns that are missing from the DataFrame.

        Args:
            df: DataFrame to check

        Returns:
            Set of standard column names not present in the DataFrame
        """
        current_columns = set(df.columns)
        expected_columns = self.get_expected_columns()
        return expected_columns - current_columns

    def validate_required_columns(
        self,
        df: pl.DataFrame,
        required: list[str],
    ) -> None:
        """Validate that required columns are present after renaming.

        Args:
            df: DataFrame to validate
            required: List of required standard column names

        Raises:
            ValueError: If any required columns are missing
        """
        missing = set(required) - set(df.columns)
        if missing:
            raise ValueError(
                f"Required columns missing after renaming: {missing}"
            )


def load_patient_mapper() -> ColumnMapper:
    """Load the patient data column mapper.

    Returns:
        ColumnMapper for patient data

    Example:
        >>> mapper = load_patient_mapper()
        >>> df = mapper.rename_columns(raw_df)
    """
    path = get_reference_data_path("synonyms", "synonyms_patient.yaml")
    return ColumnMapper(path)


def load_product_mapper() -> ColumnMapper:
    """Load the product data column mapper.

    Returns:
        ColumnMapper for product data

    Example:
        >>> mapper = load_product_mapper()
        >>> df = mapper.rename_columns(raw_df)
    """
    path = get_reference_data_path("synonyms", "synonyms_product.yaml")
    return ColumnMapper(path)
