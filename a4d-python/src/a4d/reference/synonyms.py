"""Column name mapper for standardizing tracker file columns.

This module handles the mapping of various column name variants (synonyms)
to standardized column names used throughout the pipeline.
"""

import re
from pathlib import Path

import polars as pl
from loguru import logger

from a4d.reference.loaders import get_reference_data_path, load_yaml


def sanitize_str(text: str) -> str:
    """Sanitize a string for column name matching.

    Converts to lowercase, removes all spaces and special characters,
    keeping only alphanumeric characters. This matches the R implementation.

    Args:
        text: String to sanitize

    Returns:
        Sanitized string with only lowercase alphanumeric characters

    Examples:
        >>> sanitize_str("Patient ID*")
        'patientid'
        >>> sanitize_str("Age* On Reporting")
        'ageonreporting'
        >>> sanitize_str("Date 2022")
        'date2022'
        >>> sanitize_str("My Awesome 1st Column!!")
        'myawesome1stcolumn'
    """
    # Convert to lowercase
    text = text.lower()
    # Remove spaces
    text = text.replace(" ", "")
    # Remove all non-alphanumeric characters
    text = re.sub(r"[^a-z0-9]", "", text)
    return text


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
        _lookup: Reverse lookup dict mapping SANITIZED synonyms to standard names

    Note:
        Synonym matching is case-insensitive and ignores special characters.
        This matches the R implementation which uses sanitize_str() for both
        column names and synonym keys before matching.
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

        # Build reverse lookup: sanitized_synonym -> standard_name
        # This matches R's behavior: sanitize both column names and synonym keys
        self._lookup: dict[str, str] = self._build_lookup()

        logger.info(
            f"Loaded {len(self.synonyms)} standard columns with "
            f"{len(self._lookup)} total synonyms from {yaml_path.name}"
        )

    def _build_lookup(self) -> dict[str, str]:
        """Build reverse lookup dictionary from SANITIZED synonyms to standard names.

        Sanitizes all synonym keys before adding to lookup, matching R's behavior.

        Returns:
            Dict mapping each SANITIZED synonym to its standard column name

        Example:
            >>> # YAML has: patient_id: ["Patient ID", "Patient ID*", "ID"]
            >>> # Lookup will have: {"patientid": "patient_id", "id": "patient_id"}
        """
        lookup = {}
        for standard_name, synonym_list in self.synonyms.items():
            # Handle empty lists (columns with no synonyms)
            if not synonym_list:
                continue

            for synonym in synonym_list:
                # Sanitize the synonym key before adding to lookup
                sanitized_key = sanitize_str(synonym)

                if sanitized_key in lookup:
                    logger.warning(
                        f"Duplicate sanitized synonym '{sanitized_key}' "
                        f"(from '{synonym}') found for both "
                        f"'{lookup[sanitized_key]}' and '{standard_name}'. "
                        f"Using '{standard_name}'."
                    )
                lookup[sanitized_key] = standard_name

        return lookup

    def get_standard_name(self, column: str) -> str:
        """Get the standard name for a column.

        Sanitizes the input column name before lookup to match R behavior.

        Args:
            column: Column name (may be a synonym, with special characters/spaces)

        Returns:
            Standard column name, or original if no mapping exists

        Example:
            >>> mapper.get_standard_name("Patient ID*")
            'patient_id'  # "Patient ID*" → "patientid" → "patient_id"
            >>> mapper.get_standard_name("Age* On Reporting")
            'age'  # "Age* On Reporting" → "ageonreporting" → "age"
        """
        # Sanitize input column name before lookup (matches R behavior)
        sanitized_col = sanitize_str(column)
        return self._lookup.get(sanitized_col, column)

    def is_known_column(self, column: str) -> bool:
        """Check if column name maps to a known standard name.

        Used for validating forward-filled headers during Excel extraction.
        Returns True if the column is either a known synonym or a standard name.

        Args:
            column: Column name to check

        Returns:
            True if column maps to a known standard name

        Example:
            >>> mapper.is_known_column("Current Patient Observations Category")
            True  # Maps to observations_category
            >>> mapper.is_known_column("Level of Support Status")
            False  # No such column in synonyms
        """
        sanitized = sanitize_str(column)
        return sanitized in self._lookup or column in self.synonyms

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
                    f"Unmapped columns found: {unmapped_columns}. These columns do not appear in the synonym file."
                )
            else:
                logger.warning(
                    f"Keeping {len(unmapped_columns)} unmapped columns as-is: {unmapped_columns}"
                )

        # Handle duplicate mappings: multiple source columns mapping to same target
        # Keep only first occurrence, drop the rest (edge case from discontinued 2023 format)
        target_counts: dict[str, int] = {}
        for target in rename_map.values():
            target_counts[target] = target_counts.get(target, 0) + 1

        if any(count > 1 for count in target_counts.values()):
            duplicates = {t: c for t, c in target_counts.items() if c > 1}
            logger.warning(
                f"Multiple source columns map to same target name: {duplicates}. "
                f"Keeping first occurrence only. This is an edge case from discontinued 2023 format."
            )

            # Keep only first occurrence of each target
            seen_targets: set[str] = set()
            columns_to_drop = []

            for source_col, target_col in rename_map.items():
                if target_col in duplicates:
                    if target_col in seen_targets:
                        # Duplicate - drop it
                        columns_to_drop.append(source_col)
                        logger.debug(
                            f"Dropping duplicate source column '{source_col}' "
                            f"(maps to '{target_col}')"
                        )
                    else:
                        # First occurrence - keep it
                        seen_targets.add(target_col)

            # Drop duplicates before renaming
            if columns_to_drop:
                df = df.drop(columns_to_drop)
                # Remove dropped columns from rename_map
                for col in columns_to_drop:
                    del rename_map[col]

        # Log successful mappings
        if rename_map:
            logger.debug(f"Renaming {len(rename_map)} columns: {list(rename_map.items())}")

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
            raise ValueError(f"Required columns missing after renaming: {missing}")


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


if __name__ == "__main__":
    # Example usage
    patient_mapper = load_patient_mapper()
    product_mapper = load_product_mapper()

    # Example DataFrame
    df = pl.DataFrame(
        {
            "Age": [25, 30],
            "Patient ID": [1, 2],
            "Product Name": ["A", "B"],
        }
    )

    renamed_df = patient_mapper.rename_columns(df)
    print(renamed_df)
