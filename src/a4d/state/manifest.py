"""Previous-run manifest used by incremental processing.

A ``Manifest`` is an in-memory snapshot of ``tracker_metadata.parquet``: one
entry per (clinic_code, file_name) pair, capturing the previous run's MD5 and
whether the run completed (all four per-tracker output presence flags were
True). The filter step compares this snapshot against the current on-disk
trackers to decide which to re-process.
"""

from __future__ import annotations

from dataclasses import dataclass, field

ManifestKey = tuple[str, str]
"""(clinic_code, file_name) — file_name is the path stem, matching
``tracker_metadata.parquet``'s ``file_name`` column."""


@dataclass(frozen=True)
class ManifestEntry:
    md5: str
    complete: bool


@dataclass(frozen=True)
class Manifest:
    entries: dict[ManifestKey, ManifestEntry] = field(default_factory=dict)

    @classmethod
    def empty(cls) -> Manifest:
        return cls(entries={})

    def get(self, clinic_code: str, file_name: str) -> ManifestEntry | None:
        return self.entries.get((clinic_code, file_name))

    def __len__(self) -> int:
        return len(self.entries)
