"""Filter discovered tracker files against the previous run's manifest.

The pipeline currently re-processes every ``.xlsx`` under ``data_root`` on every
run. With the ``--incremental`` flag, the CLI calls
:func:`filter_unchanged_trackers` between discovery and the worker loop to drop
trackers whose bytes haven't changed AND whose previous run completed all four
output stages.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from loguru import logger

from a4d.state.manifest import Manifest
from a4d.tables.metadata import md5_file


@dataclass(frozen=True)
class FilterSummary:
    queued: int
    skipped: int
    new: int
    changed: int
    previously_incomplete: int


def filter_unchanged_trackers(
    tracker_files: list[Path],
    manifest: Manifest,
) -> tuple[list[Path], FilterSummary]:
    """Return trackers needing reprocessing, plus a counts summary.

    A tracker is **queued** (not skipped) when any of:

    * ``(clinic_code, file_name)`` is absent from the manifest (new tracker),
    * current MD5 differs from the manifest MD5 (changed tracker), or
    * manifest entry has ``complete=False`` (previous run didn't finish all
      four output stages — re-run to fill the gaps).

    ``clinic_code`` is the parent folder name and ``file_name`` is the path
    stem, matching ``tables/metadata.py``'s schema. MD5 is computed via the
    same chunked helper used by the metadata producer, so hashes are
    bit-comparable.
    """
    queued: list[Path] = []
    new = changed = incomplete = 0

    for path in tracker_files:
        clinic_code = path.parent.name
        file_name = path.stem
        entry = manifest.get(clinic_code, file_name)

        if entry is None:
            queued.append(path)
            new += 1
            continue
        if not entry.complete:
            queued.append(path)
            incomplete += 1
            continue
        if md5_file(path) != entry.md5:
            queued.append(path)
            changed += 1
            continue
        # Unchanged + complete: skip.

    summary = FilterSummary(
        queued=len(queued),
        skipped=len(tracker_files) - len(queued),
        new=new,
        changed=changed,
        previously_incomplete=incomplete,
    )
    logger.info(
        f"Incremental filter: queued {summary.queued} "
        f"(new={summary.new}, changed={summary.changed}, "
        f"incomplete={summary.previously_incomplete}); "
        f"skipped {summary.skipped} unchanged"
    )
    return queued, summary
