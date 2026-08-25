"""Which files under ``data_root`` are trackers.

One function, because two call sites walked the tree independently and
disagreed: the patient pipeline skipped Excel lock files and the metadata table
did not, and neither excluded the output directory. Since ``output_root`` is
``data_root / output_dir`` (see :class:`a4d.config.Settings`), the pipeline's
own output always sits inside the tree being walked -- so once the findings
report started writing ``findings.xlsx`` there, a run read its own report as a
tracker and reported 257 against 255 real files.
"""

from __future__ import annotations

from pathlib import Path

from a4d.config import settings


def discover_tracker_files(data_root: Path, output_root: Path | None = None) -> list[Path]:
    """Every tracker workbook under ``data_root``, sorted.

    Args:
        data_root: Root to walk. Trackers may sit in clinic subfolders.
        output_root: The run's output root, excluded from the walk. Defaults
            to ``data_root / settings.output_dir`` -- derived from the root
            actually being walked, so it holds for a caller passing a
            non-default root, and from settings, so renaming ``output_dir``
            moves the exclusion with it.

    Returns:
        Tracker paths in sorted order, excluding anything under ``output_root``
        and any Excel lock file.

    Example:
        >>> discover_tracker_files(Path("/data"))[0].name
        '2017_Mahosot Hospital A4D Tracker.xlsx'
    """
    excluded = (
        output_root if output_root is not None else data_root / settings.output_dir
    ).resolve()
    trackers = []
    for path in data_root.rglob("*.xlsx"):
        # "~$" prefixes Excel's lock file, which appears beside any workbook
        # someone has open -- including a real tracker being edited mid-run.
        if path.name.startswith("~$"):
            continue
        if path.resolve().is_relative_to(excluded):
            continue
        trackers.append(path)
    return sorted(trackers)
