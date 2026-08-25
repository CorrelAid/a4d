"""The findings table is the single channel, so a real run must prove it.

Before ticket 66 the pipeline reported data-quality problems two ways that
never met: ``ErrorCollector.add_error`` became ``table_errors``, and
``logger.bind(error_code=...)`` became ``table_logs``. The two could not be
joined -- 252 distinct ``file_name`` against 233, overlap zero, because one
wrote the bare tracker stem and the other the ``_patient``/``_product``
suffixed name -- and the workbook-structural findings A4D staff act on existed
only in the logs.

These tests run both arms end to end and assert the properties that make one
channel one channel: both arms present, every finding attributed to a workbook
by its bare name, and every finding carrying a category an operator can act on.
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
    """Run the full pipeline with every network step skipped, return the findings."""
    result = runner.invoke(
        app,
        ["run", "--skip-download", "--skip-upload", "--skip-drive-download", "--force"],
    )
    assert result.exit_code == 0, f"run failed:\n{result.output}"

    findings_table = output_root / "tables" / "table_findings.parquet"
    assert findings_table.exists(), f"no findings table written:\n{result.output}"
    return pl.read_parquet(findings_table)


def test_findings_table_covers_both_arms(local_run):
    """A both-arms table built inside one arm is how the logs table lost product."""
    findings = _run_both_arms(local_run)
    arms = set(findings.get_column("arm").unique().to_list())
    assert arms == {"patient", "product"}, f"findings table arms: {arms}"


def test_every_finding_names_a_workbook(local_run):
    """The user's rule (2026-08-24): a finding without a file_name cannot exist."""
    findings = _run_both_arms(local_run)
    unattributed = findings.filter(
        pl.col("file_name").is_null() | (pl.col("file_name").str.strip_chars() == "")
    )
    assert unattributed.height == 0, (
        f"{unattributed.height} findings carry no file_name: {unattributed.head(5).to_dicts()}"
    )


def test_file_name_is_the_bare_stem_so_the_table_joins(local_run):
    """The arm suffix on one side is what made the two old tables unjoinable."""
    findings = _run_both_arms(local_run)
    suffixed = findings.filter(pl.col("file_name").str.contains(r"_(?:patient|product)$"))
    assert suffixed.height == 0, (
        f"{suffixed.height} findings carry an arm-suffixed file_name: "
        f"{suffixed.get_column('file_name').unique().to_list()[:5]}"
    )


def test_findings_join_against_the_logs_table(local_run):
    """The point of the unification: one run's two artifacts share a key."""
    findings = _run_both_arms(local_run)
    logs = pl.read_parquet(local_run / "tables" / "table_logs.parquet")

    finding_files = set(findings.get_column("file_name").unique().to_list())
    log_files = {
        name.removesuffix("_patient").removesuffix("_product")
        for name in logs.get_column("file_name").drop_nulls().unique().to_list()
    }
    assert finding_files & log_files, (
        f"findings and logs share no file_name: findings={sorted(finding_files)[:5]}, "
        f"logs={sorted(log_files)[:5]}"
    )


def test_every_finding_carries_an_actionable_category(local_run):
    """Category is what tells an operator whether anyone has to do anything."""
    findings = _run_both_arms(local_run)
    categories = set(findings.get_column("category").unique().to_list())
    assert categories, "findings table has no categories"
    assert categories <= {"fix_workbook", "recovered", "data_lost"}, categories
    assert None not in categories


def test_no_finding_names_an_r_script(local_run):
    """Ticket 65, folded in: published values name Python, not the retired R."""
    findings = _run_both_arms(local_run)
    stages = set(findings.get_column("stage").unique().to_list())
    functions = set(findings.get_column("function_name").unique().to_list())
    assert not {s for s in stages if s and s.startswith("script")}, stages
    assert "read_product_data_step1" not in functions


def test_findings_rebuild_from_logs_is_lossless(local_run):
    """`a4d create tables` rebuilds findings from the logs, so it must match.

    Findings are collected in memory during a run and are not in the cleaned
    parquets, so without a rebuild `create tables` would refresh every other
    table and leave a stale findings table for `upload tables` to publish.
    The rebuild is exact because report_finding binds every field of the
    record onto the log line. Verified on the real 254-tracker set too:
    118,175 findings both ways, zero rows differing on any field.
    """
    from a4d.tables.findings import rebuild_findings_from_logs

    from_run = _run_both_arms(local_run)
    rebuilt_path = rebuild_findings_from_logs(local_run / "logs", local_run / "rebuilt")
    rebuilt = pl.read_parquet(rebuilt_path)

    compared = [
        "file_name",
        "arm",
        "sheet_name",
        "patient_id",
        "column",
        "original_value",
        "message",
        "error_code",
        "category",
        "stage",
        "function_name",
    ]
    assert rebuilt.height == from_run.height
    assert sorted(rebuilt.select(compared).rows()) == sorted(from_run.select(compared).rows())
