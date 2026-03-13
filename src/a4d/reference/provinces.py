"""Province validation for patient data.

This module loads allowed provinces from the reference_data YAML file
and provides utilities for validation.
"""

from functools import lru_cache

from loguru import logger

from a4d.reference.loaders import get_reference_data_path, load_yaml


@lru_cache
def load_allowed_provinces() -> list[str]:
    """Load all allowed provinces from YAML file (lowercased for case-insensitive matching).

    Provinces are organized by country in the YAML file. This function
    flattens them into a single list and lowercases them for validation.

    The result is cached for performance since provinces don't change
    during runtime.

    Returns:
        List of all allowed province names (lowercased) across all countries

    Example:
        >>> provinces = load_allowed_provinces()
        >>> "bangkok" in provinces
        True
        >>> "BANGKOK" in provinces
        False  # List is lowercased, use is_valid_province() for validation
    """
    path = get_reference_data_path("provinces", "allowed_provinces.yaml")
    provinces_by_country: dict[str, list[str]] = load_yaml(path)

    # Flatten all provinces into single list and lowercase for matching
    all_provinces = []
    for _, provinces in provinces_by_country.items():
        all_provinces.extend(p.lower() for p in provinces)

    logger.info(f"Loaded {len(all_provinces)} provinces from {len(provinces_by_country)} countries")

    return all_provinces


@lru_cache
def load_provinces_by_country() -> dict[str, list[str]]:
    """Load provinces organized by country (lowercased for case-insensitive matching).

    Returns:
        Dict mapping country names to lists of their provinces (lowercased)

    Example:
        >>> provinces = load_provinces_by_country()
        >>> "bangkok" in provinces["THAILAND"]
        True
        >>> len(provinces["VIETNAM"])
        63
    """
    path = get_reference_data_path("provinces", "allowed_provinces.yaml")
    provinces_by_country_raw: dict[str, list[str]] = load_yaml(path)

    # Lowercase all province names for case-insensitive matching
    provinces_by_country = {
        country: [p.lower() for p in provinces]
        for country, provinces in provinces_by_country_raw.items()
    }

    logger.info(f"Loaded provinces for {len(provinces_by_country)} countries")

    return provinces_by_country


@lru_cache
def load_canonical_provinces() -> list[str]:
    """Load all allowed provinces with canonical casing (for validation).

    Unlike load_allowed_provinces() which lowercases for matching,
    this returns the original province names from the YAML with proper
    casing and accents to use as canonical values in validation.

    Returns:
        List of all allowed province names (original casing) across all countries

    Example:
        >>> provinces = load_canonical_provinces()
        >>> "Takéo" in provinces
        True
        >>> "Bangkok" in provinces
        True
    """
    path = get_reference_data_path("provinces", "allowed_provinces.yaml")
    provinces_by_country: dict[str, list[str]] = load_yaml(path)

    # Flatten all provinces into single list WITHOUT lowercasing
    all_provinces = []
    for _, provinces in provinces_by_country.items():
        all_provinces.extend(provinces)

    logger.info(
        f"Loaded {len(all_provinces)} canonical province names "
        f"from {len(provinces_by_country)} countries"
    )

    return all_provinces


def is_valid_province(province: str | None) -> bool:
    """Check if a province name is valid (case-insensitive).

    Args:
        province: Province name to validate (case-insensitive, None allowed)

    Returns:
        True if province is None or in the allowed list, False otherwise

    Example:
        >>> is_valid_province("Bangkok")
        True
        >>> is_valid_province("BANGKOK")
        True
        >>> is_valid_province("bangkok")
        True
        >>> is_valid_province(None)
        True
        >>> is_valid_province("Invalid Province")
        False
    """
    if province is None:
        return True

    allowed = load_allowed_provinces()
    return province.lower() in allowed


def get_country_for_province(province: str) -> str | None:
    """Get the country for a given province (case-insensitive).

    Args:
        province: Province name (case-insensitive)

    Returns:
        Country name if province is found, None otherwise

    Example:
        >>> get_country_for_province("Bangkok")
        'THAILAND'
        >>> get_country_for_province("bangkok")
        'THAILAND'
        >>> get_country_for_province("BANGKOK")
        'THAILAND'
    """
    provinces_by_country = load_provinces_by_country()
    province_lower = province.lower()

    for country, provinces in provinces_by_country.items():
        if province_lower in provinces:
            return country

    return None


if __name__ == "__main__":
    for c, p in load_provinces_by_country().items():
        print(f"{c}: {p}")
