"""Tracker metadata table generator.

Mirrors R's ``run_script_5_create_metadata_table.R``: for each ``.xlsx`` tracker
under ``data_root``, emits a row with an MD5 hash and presence flags for the
four per-tracker output subdirs (``patient_data_{raw,cleaned}`` and
``product_data_{raw,cleaned}``).

The MD5 helper :func:`md5_file` is also imported by ``a4d.state.filter`` to
hash current trackers when filtering against the previous run's manifest.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from loguru import logger

# Order matches R's subdirs vector; BigQuery consumers may depend on it.
_SUBDIRS: tuple[str, ...] = (
    "patient_data_cleaned",
    "patient_data_raw",
    "product_data_cleaned",
    "product_data_raw",
)

_SCHEMA: dict[str, type[pl.DataType] | pl.DataType] = {
    "file_name": pl.String,
    "clinic_code": pl.String,
    "md5": pl.String,
    "patient_data_cleaned": pl.Boolean,
    "patient_data_raw": pl.Boolean,
    "product_data_cleaned": pl.Boolean,
    "product_data_raw": pl.Boolean,
    "complete": pl.Boolean,
    "timestamp": pl.Datetime("us"),
}


def md5_file(path: Path, chunk_size: int = 65536) -> str:
    """Stream-hash a file with MD5. ``usedforsecurity=False`` satisfies FIPS."""
    h = hashlib.md5(usedforsecurity=False)
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(chunk_size), b""):
            h.update(chunk)
    return h.hexdigest()


def create_table_tracker_metadata(
    data_root: Path,
    output_root: Path,
) -> Path:
    """Emit ``tracker_metadata.parquet`` to ``output_root/tables/``.

    Args:
        data_root: Directory holding tracker ``.xlsx`` files. Scanned recursively
            so clinic-folder layouts are supported.
        output_root: Pipeline output root. Per-tracker output presence is looked
            up in its four subdirs (``_SUBDIRS``); the metadata parquet is
            written to ``output_root/tables/``.

    Returns:
        Path to the written parquet file.
    """
    tracker_files = sorted(data_root.rglob("*.xlsx"))
    logger.info(f"Building tracker metadata for {len(tracker_files)} tracker(s)")

    # Index each subdir once so per-tracker lookups are O(1) prefix checks.
    subdir_names: dict[str, list[str]] = {}
    for subdir in _SUBDIRS:
        target = output_root / subdir
        subdir_names[subdir] = (
            [p.name for p in target.iterdir() if p.is_file()] if target.exists() else []
        )

    now = datetime.now(tz=UTC).replace(tzinfo=None)
    rows: list[dict] = []
    for tracker_path in tracker_files:
        file_name = tracker_path.stem
        row = {
            "file_name": file_name,
            "clinic_code": tracker_path.parent.name,
            "md5": md5_file(tracker_path),
        }
        for subdir in _SUBDIRS:
            row[subdir] = any(name.startswith(file_name) for name in subdir_names[subdir])
        row["complete"] = all(row[s] for s in _SUBDIRS)
        row["timestamp"] = now
        rows.append(row)

    df = pl.DataFrame(rows, schema=_SCHEMA)

    output_dir = output_root / "tables"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "tracker_metadata.parquet"
    df.write_parquet(output_file)
    logger.info(f"Tracker metadata saved: {output_file} ({df.height} rows)")
    return output_file
