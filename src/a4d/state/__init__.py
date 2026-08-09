"""Incremental processing: skip trackers whose MD5 + completion state match a
previous run's manifest.
"""

from a4d.state.filter import FilterSummary, filter_unchanged_trackers
from a4d.state.manifest import Manifest, ManifestEntry
from a4d.state.source import load_previous_manifest

__all__ = [
    "FilterSummary",
    "Manifest",
    "ManifestEntry",
    "filter_unchanged_trackers",
    "load_previous_manifest",
]
