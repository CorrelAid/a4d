"""The production run's console shows summaries, not one line per finding.

The 2026-08-30 Cloud Run execution emitted 3,765 log lines. 2,987 were
WARNING, and 2,972 of those were the *same* sentence -- "Invalid patient ID
format (expected XX_YY###) and no unambiguous match in this tracker" -- because
findings log at WARNING and the bare `a4d run` ran its console at that level.
The console format binds none of the finding's fields, so the 2,972 lines were
indistinguishable from one another too: no file, no sheet, no patient.

Nothing is lost by silencing them. All 2,993 are published to the findings
table as `patient_id_unrepairable`, to the per-tracker log files, and to the
findings workbook. `a4d run patient` and `a4d run product` were already quiet
at ERROR; the production entry point was the only one that was not.

The console level is asserted at the call, not by scraping stdout: loguru binds
its sink to the real stdout object, so neither CliRunner nor pytest's capture
sees a single log line -- which is how a console flooding in production looked
clean to every test written against CliRunner.
"""

from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from a4d.cli import app
from a4d.config import settings

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})

QUIET = "ERROR"


@pytest.fixture
def local_run(monkeypatch, dummy_tracker_dir, tmp_path) -> Path:
    output_root = tmp_path / "run_output"
    monkeypatch.setattr(settings, "data_root", dummy_tracker_dir)
    monkeypatch.setattr(settings, "output_dir", output_root)
    monkeypatch.setattr(settings, "max_workers", 1)
    return output_root


def test_both_arms_are_asked_for_a_quiet_console(local_run):
    with (
        patch("a4d.cli.run_patient_pipeline") as patient,
        patch("a4d.cli.run_product_pipeline") as product,
    ):
        runner.invoke(
            app,
            ["run", "--skip-download", "--skip-upload", "--skip-drive-download", "--force"],
        )

    assert patient.call_args.kwargs["console_log_level"] == QUIET
    assert product.call_args.kwargs["console_log_level"] == QUIET


def test_the_single_arm_commands_use_the_same_level(local_run):
    """The production entry point drifting off these is the original defect."""
    with patch("a4d.cli.run_patient_pipeline") as patient:
        runner.invoke(app, ["run", "patient", "--skip-tables"])
    assert patient.call_args.kwargs["console_log_level"] == QUIET

    with patch("a4d.cli.run_product_pipeline") as product:
        runner.invoke(app, ["run", "product", "--skip-tables"])
    assert product.call_args.kwargs["console_log_level"] == QUIET


def test_the_summaries_are_still_rendered(local_run):
    result = runner.invoke(
        app,
        ["run", "--skip-download", "--skip-upload", "--skip-drive-download", "--force"],
    )
    assert result.exit_code == 0, f"run failed:\n{result.output}"
    assert "Combined Run Summary" in result.output
    assert "Dataset Overview" in result.output
    assert "Full pipeline completed successfully" in result.output


class TestPerYearTableInTheRunSummary:
    """The per-year view is the one that answers "is the newest template ok?".

    Nothing in the run summary said whether a year had been processed at all,
    nor how a year compared per tracker -- the only per-file view ranked on raw
    count, which put the newest, biggest, cleanest-per-tracker years at the top
    of a list titled by error count.
    """

    def test_the_run_renders_findings_by_tracker_year(self, local_run):
        result = runner.invoke(
            app,
            ["run", "--skip-download", "--skip-upload", "--skip-drive-download", "--force"],
        )
        assert result.exit_code == 0, f"run failed:\n{result.output}"
        assert "Findings by Tracker Year" in result.output
        assert "Needs action" in result.output
        assert "Recovered" in result.output
