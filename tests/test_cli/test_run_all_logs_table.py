"""The logs table must cover both pipeline arms, not just patient.

`create_table_logs` snapshots whatever `.log` files exist under
``output_root/logs/`` at the moment it is called. Building it inside the
patient arm therefore captures patient logs only -- the product arm has not
run yet and its files do not exist. Measured against the 2026-08-09 production
run: BigQuery `logs` held 248 patient files and zero product ones, while the
same run uploaded 249 `_product.log` files to GCS carrying 10,237 lines with an
`error_code` (including four ERROR-level `critical_abort`). Those findings
never reached a queryable table.
"""

from pathlib import Path

import polars as pl
import pytest
from typer.testing import CliRunner

from a4d.cli import app
from a4d.config import settings

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})


@pytest.fixture
def local_run(monkeypatch, dummy_tracker_dir, tmp_path) -> Path:
    """Point `a4d run` at the dummy tracker and a throwaway output root."""
    output_root = tmp_path / "run_output"
    monkeypatch.setattr(settings, "data_root", dummy_tracker_dir)
    monkeypatch.setattr(settings, "output_dir", output_root)
    monkeypatch.setattr(settings, "max_workers", 1)
    return output_root


def _run_both_arms(output_root: Path) -> pl.DataFrame:
    """Run the full pipeline with every network step skipped, return the logs table."""
    result = runner.invoke(
        app,
        ["run", "--skip-download", "--skip-upload", "--skip-drive-download", "--force"],
    )
    assert result.exit_code == 0, f"run failed:\n{result.output}"

    logs_table = output_root / "tables" / "table_logs.parquet"
    assert logs_table.exists(), f"no logs table written:\n{result.output}"
    return pl.read_parquet(logs_table)


def test_both_arms_write_log_files(local_run):
    """Precondition: the run produces per-tracker logs for both arms on disk."""
    _run_both_arms(local_run)
    written = {p.stem.rsplit("_", 1)[-1] for p in (local_run / "logs").glob("*.log")}
    assert "patient" in written
    assert "product" in written


def test_logs_table_covers_the_product_arm(local_run):
    """The published logs table must contain product rows, not patient only."""
    logs = _run_both_arms(local_run)
    arms = logs.get_column("file_name").str.extract(r"_(patient|product)$", 1)
    counts = arms.value_counts().to_dict(as_series=False)
    by_arm = dict(zip(counts["file_name"], counts["count"], strict=True))

    assert by_arm.get("product", 0) > 0, (
        f"logs table has no product rows -- arm counts: {by_arm}. "
        "create_table_logs is running before the product arm."
    )
