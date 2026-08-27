"""A run starts from a clean output directory, so no table sums two runs.

Both consumers of ``output/logs/`` -- ``create_table_logs`` and
``rebuild_findings_from_logs`` -- read every ``*.log`` file present. Per-tracker
logs are deleted and rewritten by name, so they are safe; the aggregate logs
(``main_pipeline_*.log``, ``main_worker_*.log``) are not. Their names carry a
run timestamp and pid, and loguru's file sink appends, so nothing removes or
overwrites the previous run's. Measured 2026-08-27 over the 255-tracker local
corpus: with two runs' logs on disk the findings rebuild returned 213,921 for a
run that produced 105,464, and the logs table 326,092 against a true 217,022.

The rule these tests pin: a run wipes its outputs unless ``--incremental`` says
otherwise, and even ``--incremental`` drops the aggregate logs -- a skipped
tracker's findings live in its own per-tracker log, never only in last run's
worker log.
"""

from pathlib import Path

import pytest
from typer.testing import CliRunner

from a4d.cli import app
from a4d.config import settings

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})

WIPED_DIRS = (
    "patient_data_raw",
    "patient_data_cleaned",
    "product_data_raw",
    "product_data_cleaned",
    "tables",
)


@pytest.fixture
def local_run(monkeypatch, dummy_tracker_dir, tmp_path) -> Path:
    """Point `a4d run` at the dummy tracker and a throwaway output root."""
    output_root = tmp_path / "run_output"
    monkeypatch.setattr(settings, "data_root", dummy_tracker_dir)
    monkeypatch.setattr(settings, "output_dir", output_root)
    monkeypatch.setattr(settings, "max_workers", 1)
    return output_root


def _seed_prior_run(output_root: Path) -> None:
    """Write the residue a previous run would have left on disk."""
    for subdir in WIPED_DIRS:
        (output_root / subdir).mkdir(parents=True, exist_ok=True)
        (output_root / subdir / "_sentinel").write_text("from prior run")
    logs = output_root / "logs"
    logs.mkdir(parents=True, exist_ok=True)
    (logs / "main_worker_20260101_000000_pid1.log").write_text("")
    (logs / "main_pipeline_patient.log").write_text("")
    (logs / "PriorTracker_patient.log").write_text("")


def _invoke_run(*extra: str):
    result = runner.invoke(
        app,
        ["run", "--skip-download", "--skip-upload", "--skip-drive-download", *extra],
    )
    assert result.exit_code == 0, f"run failed:\n{result.output}"
    return result


def _aggregate_logs(output_root: Path) -> set[str]:
    return {p.name for p in (output_root / "logs").glob("main_*.log")}


class TestCleanSlateByDefault:
    """`a4d run` with no flags starts from an empty output directory."""

    def test_bare_run_wipes_prior_data_outputs(self, local_run):
        _seed_prior_run(local_run)
        _invoke_run()
        for subdir in WIPED_DIRS:
            assert not (local_run / subdir / "_sentinel").exists(), (
                f"bare run did not wipe {subdir}/_sentinel"
            )

    def test_bare_run_wipes_prior_logs(self, local_run):
        _seed_prior_run(local_run)
        _invoke_run()
        assert not (local_run / "logs" / "PriorTracker_patient.log").exists()
        assert "main_worker_20260101_000000_pid1.log" not in _aggregate_logs(local_run)

    def test_skip_patient_still_wipes_prior_logs(self, local_run):
        """Only the patient arm ever cleared logs, so --skip-patient never did."""
        _seed_prior_run(local_run)
        _invoke_run("--skip-patient")
        assert not (local_run / "logs" / "PriorTracker_patient.log").exists()
        assert "main_worker_20260101_000000_pid1.log" not in _aggregate_logs(local_run)


class TestIncrementalKeepsOnlyWhatItNeeds:
    """--incremental preserves per-tracker outputs, never the aggregate logs."""

    def test_incremental_keeps_prior_per_tracker_outputs(self, local_run):
        _seed_prior_run(local_run)
        _invoke_run("--incremental")
        assert (local_run / "patient_data_cleaned" / "_sentinel").exists(), (
            "--incremental wiped the cleaned parquets it must reuse"
        )
        assert (local_run / "logs" / "PriorTracker_patient.log").exists(), (
            "--incremental wiped a skipped tracker's only record of its findings"
        )

    def test_incremental_drops_prior_aggregate_logs(self, local_run):
        _seed_prior_run(local_run)
        _invoke_run("--incremental")
        assert "main_worker_20260101_000000_pid1.log" not in _aggregate_logs(local_run)


class TestSecondRunDoesNotDoubleTheTables:
    """The defect itself: two runs in one directory summed into one table."""

    def test_two_runs_produce_the_same_findings_count_as_one(self, local_run):
        import polars as pl

        findings_table = local_run / "tables" / "table_findings.parquet"

        _invoke_run()
        first = len(pl.read_parquet(findings_table))

        _invoke_run()
        second = len(pl.read_parquet(findings_table))

        assert second == first, (
            f"second run reported {second} findings against the first run's {first}"
        )

    def test_rebuild_after_two_runs_matches_the_run(self, local_run):
        import polars as pl

        findings_table = local_run / "tables" / "table_findings.parquet"

        _invoke_run()
        _invoke_run()
        from_run = len(pl.read_parquet(findings_table))

        rebuilt = runner.invoke(app, ["create", "tables"])
        assert rebuilt.exit_code == 0, f"create tables failed:\n{rebuilt.output}"

        assert len(pl.read_parquet(findings_table)) == from_run
