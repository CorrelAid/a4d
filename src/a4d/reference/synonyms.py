"""Column name mapper for standardizing tracker file columns.

This module handles the mapping of various column name variants (synonyms)
to standardized column names used throughout the pipeline.
"""

import re
from functools import lru_cache
from pathlib import Path

import polars as pl
from loguru import logger

from a4d.findings import report_finding
from a4d.reference.loaders import get_reference_data_path, load_yaml


def sanitize_str(text: str) -> str:
    """Sanitize a string for column name matching.

    Converts to lowercase, removes all spaces and special characters,
    keeping only alphanumeric characters, so a header's punctuation, casing and
    spacing cannot decide whether a column is recognised.

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
        Both sides of the lookup are sanitized, because a synonym file written
        by hand and a header typed into Excel will not agree on punctuation.
        Historically this used sanitize_str() for both
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
        # Sanitize both the column name and the synonym keys, so neither side's
        # punctuation or casing decides the match.
        self._lookup: dict[str, str] = self._build_lookup()

        logger.info(
            f"Loaded {len(self.synonyms)} standard columns with "
            f"{len(self._lookup)} total synonyms from {yaml_path.name}"
        )

    def _build_lookup(self) -> dict[str, str]:
        """Build reverse lookup dictionary from SANITIZED synonyms to standard names.

        Sanitizes all synonym keys before adding them to the lookup.

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

            if isinstance(synonym_list, str):
                synonym_list = [synonym_list]

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

        Sanitizes the input column name before lookup.

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
        # Sanitize input column name before lookup
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
                    f"Unmapped columns found: {unmapped_columns}. "
                    "These columns do not appear in the synonym file."
                )
            else:
                report_finding(
                    error_code="missing_column",
                    message=(
                        f"Keeping {len(unmapped_columns)} unmapped columns as-is: "
                        f"{unmapped_columns}"
                    ),
                    original_value=", ".join(sorted(unmapped_columns)),
                    stage="extract",
                    function_name="rename_columns",
                )

        # Several source columns can map to one canonical name: the 2023 template
        # splits complication screening into B.P./Kidney/Eye/Foot/Lipids sub-columns,
        # each carrying an independent value. Merge them -- as
        # merge_duplicate_columns_data() already merges repeated raw headers --
        # rather than keeping the first, which silently discarded
        # 2,489 recorded values across 27 trackers.
        sources_by_target: dict[str, list[str]] = {}
        for source_col, target_col in rename_map.items():
            sources_by_target.setdefault(target_col, []).append(source_col)

        merge_groups = {t: cols for t, cols in sources_by_target.items() if len(cols) > 1}

        if merge_groups:
            report_finding(
                error_code="duplicate_source_columns",
                message=(
                    f"Merging source columns that share a target name: {merge_groups}. "
                    "Values are comma-joined in column order; empty cells are skipped."
                ),
                original_value=", ".join(sorted(merge_groups)),
                stage="extract",
                function_name="rename_columns",
            )

            for source_cols in merge_groups.values():
                parts = [
                    pl.when(pl.col(col).cast(pl.String, strict=False).str.strip_chars() != "")
                    .then(pl.col(col).cast(pl.String, strict=False).str.strip_chars())
                    .otherwise(None)
                    for col in source_cols
                ]
                merged = pl.concat_str(parts, separator=",", ignore_nulls=True)
                # concat_str yields "" when every part is null; an absent value is null.
                merged = pl.when(merged != "").then(merged).otherwise(None)
                df = df.with_columns(merged.alias(source_cols[0])).drop(source_cols[1:])
                for col in source_cols[1:]:
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


@lru_cache(maxsize=1)
def load_patient_mapper() -> ColumnMapper:
    """Load the patient data column mapper.

    Cached so callers on the per-tracker hot path don't re-read the YAML.
    Cache is per-process; ProcessPoolExecutor workers get their own.

    Returns:
        ColumnMapper for patient data

    Example:
        >>> mapper = load_patient_mapper()
        >>> df = mapper.rename_columns(raw_df)
    """
    path = get_reference_data_path("synonyms", "synonyms_patient.yaml")
    return ColumnMapper(path)


@lru_cache(maxsize=1)
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
