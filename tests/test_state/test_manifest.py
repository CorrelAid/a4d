"""Tests for the Manifest dataclasses."""

from a4d.state.manifest import Manifest, ManifestEntry


def test_empty_manifest():
    m = Manifest.empty()
    assert len(m) == 0
    assert m.get("CLINIC_A", "tracker") is None


def test_lookup_by_composite_key():
    entries = {
        ("CLINIC_A", "2024_T1"): ManifestEntry(md5="abc123", complete=True),
        ("CLINIC_B", "2024_T1"): ManifestEntry(md5="def456", complete=False),
    }
    m = Manifest(entries=entries)

    assert m.get("CLINIC_A", "2024_T1") == ManifestEntry(md5="abc123", complete=True)
    assert m.get("CLINIC_B", "2024_T1") == ManifestEntry(md5="def456", complete=False)
    # Same file_name in a third clinic must miss — composite key isolates by clinic.
    assert m.get("CLINIC_C", "2024_T1") is None
    assert len(m) == 2


def test_manifest_entry_is_frozen():
    """Frozen dataclass: equality + immutability are part of the contract."""
    e1 = ManifestEntry(md5="abc", complete=True)
    e2 = ManifestEntry(md5="abc", complete=True)
    assert e1 == e2

    import dataclasses

    try:
        e1.md5 = "different"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("ManifestEntry must be frozen")
