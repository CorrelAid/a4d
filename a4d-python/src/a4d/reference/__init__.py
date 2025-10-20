"""Reference data loaders and validators.

This package contains modules for loading and working with reference data
from the shared reference_data/ directory.
"""

# Loaders (internal utilities)
from a4d.reference.loaders import (
    find_reference_data_dir,
    get_reference_data_path,
    load_yaml,
)

# Synonyms (column mapping)
from a4d.reference.synonyms import (
    ColumnMapper,
    load_patient_mapper,
    load_product_mapper,
)

# Provinces (validation)
from a4d.reference.provinces import (
    get_country_for_province,
    is_valid_province,
    load_allowed_provinces,
    load_provinces_by_country,
)

__all__ = [
    # Loaders
    "find_reference_data_dir",
    "get_reference_data_path",
    "load_yaml",
    # Synonyms
    "ColumnMapper",
    "load_patient_mapper",
    "load_product_mapper",
    # Provinces
    "get_country_for_province",
    "is_valid_province",
    "load_allowed_provinces",
    "load_provinces_by_country",
]
