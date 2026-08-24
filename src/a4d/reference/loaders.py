"""Utilities for loading reference data files.

This module provides common utilities for loading YAML and other reference
data files under reference_data/.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from loguru import logger


def find_reference_data_dir() -> Path:
    """Find reference_data directory.

    Checks A4D_REFERENCE_DATA env var first (used in Docker/Cloud Run where
    the directory is at /app/reference_data). Falls back to walking up from
    this file to find the repo root for local development.

    Returns:
        Path to reference_data directory

    Raises:
        FileNotFoundError: If reference_data directory not found
    """
    # Explicit override for Docker/Cloud Run (set A4D_REFERENCE_DATA=/app/reference_data)
    if env_path := os.environ.get("A4D_REFERENCE_DATA"):
        path = Path(env_path)
        if path.exists():
            return path
        raise FileNotFoundError(f"reference_data directory not found at {path}")

    # Local dev: navigate from src/a4d/reference/loaders.py up to repo root
    # loaders.py -> reference -> a4d -> src -> repo root
    repo_root = Path(__file__).parents[3]
    reference_data_dir = repo_root / "reference_data"

    if not reference_data_dir.exists():
        raise FileNotFoundError(f"reference_data directory not found at {reference_data_dir}")

    return reference_data_dir


def load_yaml(
    yaml_path: Path,
    relative_to_reference_data: bool = False,
) -> Any:
    """Load and parse a YAML file.

    Args:
        yaml_path: Path to the YAML file
        relative_to_reference_data: If True, yaml_path is relative to
                                    reference_data directory

    Returns:
        Parsed YAML content

    Raises:
        FileNotFoundError: If the YAML file doesn't exist
        yaml.YAMLError: If the YAML file is malformed
    """
    if relative_to_reference_data:
        reference_data_dir = find_reference_data_dir()
        yaml_path = reference_data_dir / yaml_path

    if not yaml_path.exists():
        raise FileNotFoundError(f"YAML file not found: {yaml_path}")

    logger.debug(f"Loading YAML file: {yaml_path}")

    with open(yaml_path) as f:
        return yaml.safe_load(f)


def get_reference_data_path(*parts: str) -> Path:
    """Get path to a file in reference_data directory.

    Args:
        *parts: Path components relative to reference_data directory

    Returns:
        Absolute path to the file

    Example:
        >>> path = get_reference_data_path("synonyms", "synonyms_patient.yaml")
        >>> # Returns: /path/to/repo/reference_data/synonyms/synonyms_patient.yaml
    """
    reference_data_dir = find_reference_data_dir()
    return reference_data_dir.joinpath(*parts)
