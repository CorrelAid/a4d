"""Tests for filter_unchanged_trackers."""

import hashlib
from pathlib import Path

from a4d.state.filter import filter_unchanged_trackers
from a4d.state.manifest import Manifest, ManifestEntry


def _md5(payload: bytes) -> str:
    return hashlib.md5(payload, usedforsecurity=False).hexdigest()


def _make_tracker(parent: Path, clinic: str, name: str, payload: bytes) -> Path:
    folder = parent / clinic
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{name}.xlsx"
    path.write_bytes(payload)
    return path


def test_empty_manifest_queues_everything(tmp_path: Path):
    t1 = _make_tracker(tmp_path, "A", "2024_T1", b"alpha")
    t2 = _make_tracker(tmp_path, "B", "2024_T2", b"beta")

    queued, summary = filter_unchanged_trackers([t1, t2], Manifest.empty())

    assert queued == [t1, t2]
    assert summary.queued == 2
    assert summary.skipped == 0
    assert summary.new == 2
    assert summary.changed == 0
    assert summary.previously_incomplete == 0


def test_all_match_skips_everything(tmp_path: Path):
    t1 = _make_tracker(tmp_path, "A", "2024_T1", b"alpha")
    t2 = _make_tracker(tmp_path, "B", "2024_T2", b"beta")
    manifest = Manifest(
        entries={
            ("A", "2024_T1"): ManifestEntry(md5=_md5(b"alpha"), complete=True),
            ("B", "2024_T2"): ManifestEntry(md5=_md5(b"beta"), complete=True),
        }
    )

    queued, summary = filter_unchanged_trackers([t1, t2], manifest)

    assert queued == []
    assert summary.queued == 0
    assert summary.skipped == 2


def test_changed_md5_queues(tmp_path: Path):
    t1 = _make_tracker(tmp_path, "A", "2024_T1", b"new content")
    manifest = Manifest(
        entries={("A", "2024_T1"): ManifestEntry(md5=_md5(b"old content"), complete=True)},
    )

    queued, summary = filter_unchanged_trackers([t1], manifest)

    assert queued == [t1]
    assert summary.changed == 1
    assert summary.new == 0


def test_previously_incomplete_queues(tmp_path: Path):
    """complete=False means the previous run didn't finish all four output stages."""
    t1 = _make_tracker(tmp_path, "A", "2024_T1", b"alpha")
    manifest = Manifest(
        entries={("A", "2024_T1"): ManifestEntry(md5=_md5(b"alpha"), complete=False)},
    )

    queued, summary = filter_unchanged_trackers([t1], manifest)

    assert queued == [t1]
    assert summary.previously_incomplete == 1
    assert summary.changed == 0
    assert summary.new == 0


def test_mixed_classification(tmp_path: Path):
    new = _make_tracker(tmp_path, "A", "2024_NEW", b"new")
    changed = _make_tracker(tmp_path, "A", "2024_CHANGED", b"new bytes")
    incomplete = _make_tracker(tmp_path, "A", "2024_INCOMPLETE", b"same")
    unchanged = _make_tracker(tmp_path, "A", "2024_UNCHANGED", b"frozen")

    manifest = Manifest(
        entries={
            ("A", "2024_CHANGED"): ManifestEntry(md5=_md5(b"old bytes"), complete=True),
            ("A", "2024_INCOMPLETE"): ManifestEntry(md5=_md5(b"same"), complete=False),
            ("A", "2024_UNCHANGED"): ManifestEntry(md5=_md5(b"frozen"), complete=True),
        }
    )

    queued, summary = filter_unchanged_trackers(
        [new, changed, incomplete, unchanged], manifest
    )

    assert set(queued) == {new, changed, incomplete}
    assert summary.queued == 3
    assert summary.skipped == 1
    assert summary.new == 1
    assert summary.changed == 1
    assert summary.previously_incomplete == 1


def test_clinic_isolation(tmp_path: Path):
    """Same file stem in two clinic folders must be treated as two distinct trackers."""
    t_a = _make_tracker(tmp_path, "CLINIC_A", "shared_name", b"clinic A bytes")
    t_b = _make_tracker(tmp_path, "CLINIC_B", "shared_name", b"clinic B bytes")

    manifest = Manifest(
        entries={
            ("CLINIC_A", "shared_name"): ManifestEntry(md5=_md5(b"clinic A bytes"), complete=True),
            ("CLINIC_B", "shared_name"): ManifestEntry(md5=_md5(b"clinic B bytes"), complete=True),
        }
    )

    queued, summary = filter_unchanged_trackers([t_a, t_b], manifest)

    assert queued == []
    assert summary.skipped == 2
