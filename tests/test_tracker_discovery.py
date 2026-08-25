"""Which files under ``data_root`` count as trackers.

``output_root`` is ``data_root / output_dir`` by construction (config.py), so
the pipeline's own output always sits inside the tree it walks for trackers.
Once the findings report started writing ``findings.xlsx`` there, a run
ingested its own report -- and Excel's ``~$findings.xlsx`` lock file -- as two
extra trackers, reporting 257 against 255 real files.
"""

from pathlib import Path

from a4d.discovery import discover_tracker_files


def _tracker(root: Path, name: str) -> Path:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not really a workbook")
    return path


class TestDiscoverTrackerFiles:
    def test_it_finds_trackers_in_clinic_subfolders(self, tmp_path):
        _tracker(tmp_path, "Cambodia/2024_CDA A4D Tracker.xlsx")
        _tracker(tmp_path, "Laos/2024_Mahosot A4D Tracker.xlsx")

        found = discover_tracker_files(tmp_path)

        assert [p.name for p in found] == [
            "2024_CDA A4D Tracker.xlsx",
            "2024_Mahosot A4D Tracker.xlsx",
        ]

    def test_the_pipelines_own_report_is_not_a_tracker(self, tmp_path):
        _tracker(tmp_path, "Cambodia/2024_CDA A4D Tracker.xlsx")
        _tracker(tmp_path, "output/findings.xlsx")

        found = discover_tracker_files(tmp_path)

        assert [p.name for p in found] == ["2024_CDA A4D Tracker.xlsx"]

    def test_nothing_under_the_output_root_is_a_tracker(self, tmp_path):
        """Not just the report: every stage writes under output_root, and a
        future artifact must not become a tracker by being added."""
        _tracker(tmp_path, "Cambodia/2024_CDA A4D Tracker.xlsx")
        _tracker(tmp_path, "output/tables/some_export.xlsx")
        _tracker(tmp_path, "output/anything.xlsx")

        assert len(discover_tracker_files(tmp_path)) == 1

    def test_an_excel_lock_file_is_not_a_tracker(self, tmp_path):
        """``~$`` files appear beside any open workbook, including a real
        tracker a staff member is editing while the run happens -- so this is
        not confined to the output directory."""
        _tracker(tmp_path, "Cambodia/2024_CDA A4D Tracker.xlsx")
        _tracker(tmp_path, "Cambodia/~$2024_CDA A4D Tracker.xlsx")

        assert [p.name for p in discover_tracker_files(tmp_path)] == ["2024_CDA A4D Tracker.xlsx"]

    def test_a_custom_output_dir_is_excluded_rather_than_the_literal_name(self, tmp_path):
        """The exclusion comes from settings, so renaming output_dir moves it."""
        _tracker(tmp_path, "Cambodia/2024_CDA A4D Tracker.xlsx")
        _tracker(tmp_path, "results/findings.xlsx")

        found = discover_tracker_files(tmp_path, output_root=tmp_path / "results")

        assert [p.name for p in found] == ["2024_CDA A4D Tracker.xlsx"]

    def test_an_output_root_outside_data_root_excludes_nothing(self, tmp_path):
        """Deployments may put output elsewhere; that must not silently drop
        a clinic folder that happens to share a name."""
        _tracker(tmp_path, "data/Cambodia/2024_CDA A4D Tracker.xlsx")

        found = discover_tracker_files(tmp_path / "data", output_root=tmp_path / "out")

        assert len(found) == 1
