"""Where a snapshot digest is kept, and how a new one is accepted.

The baseline lives beside the tracker corpus -- on the drive, not in the
repository. The repository is public, and a committed digest would publish
how many patients each named clinic has and how complete each of their fields
is; the check only ever runs where the corpus is, so the baseline belongs
there too.

Two files, and the pair is the whole workflow: a check writes ``current`` and
diffs it against ``baseline``; an update copies ``current`` forward. Nothing
can be promoted that no check has produced, so accepting output you have not
looked at is not an available move.
"""

from __future__ import annotations

import shutil
from pathlib import Path

import polars as pl


class NoCurrentDigestError(RuntimeError):
    """Raised when an update is attempted before any check has run."""


class SnapshotStore:
    """The baseline, the last check's result, and the accepted history."""

    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def for_data_root(cls, data_root: Path) -> SnapshotStore:
        """The conventional location: ``snapshot/`` beside the tracker corpus."""
        return cls(data_root / "snapshot")

    @property
    def baseline_path(self) -> Path:
        return self.root / "baseline.parquet"

    @property
    def current_path(self) -> Path:
        return self.root / "current.parquet"

    @property
    def history_dir(self) -> Path:
        return self.root / "history"

    def baseline(self) -> pl.DataFrame | None:
        """The accepted digest, or None before the first update."""
        if not self.baseline_path.exists():
            return None
        return pl.read_parquet(self.baseline_path)

    def current(self) -> pl.DataFrame | None:
        """The digest the last check computed, or None if none has run."""
        if not self.current_path.exists():
            return None
        return pl.read_parquet(self.current_path)

    def write_current(self, digest: pl.DataFrame) -> Path:
        self.root.mkdir(parents=True, exist_ok=True)
        digest.write_parquet(self.current_path)
        return self.current_path

    def promote(self, stamp: str) -> Path:
        """Accept the last check's digest as the new baseline.

        Returns the path of the dated history copy, which is what a later
        reader goes looking for when asking when a column last moved.
        """
        if not self.current_path.exists():
            raise NoCurrentDigestError(
                f"No digest to promote at {self.current_path}. Run the check first -- "
                "an update accepts what a check produced, it does not run the pipeline."
            )

        self.history_dir.mkdir(parents=True, exist_ok=True)
        archived = self._next_history_path(stamp)
        shutil.copy2(self.current_path, archived)
        shutil.copy2(self.current_path, self.baseline_path)
        return archived

    def _next_history_path(self, stamp: str) -> Path:
        """A same-day second acceptance gets its own file, not the first one's."""
        candidate = self.history_dir / f"baseline-{stamp}.parquet"
        attempt = 2
        while candidate.exists():
            candidate = self.history_dir / f"baseline-{stamp}-{attempt}.parquet"
            attempt += 1
        return candidate
