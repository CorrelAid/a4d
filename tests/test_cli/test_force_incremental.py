"""Tests for --force and --incremental flag interaction across CLI commands."""

import hashlib
from pathlib import Path

from typer.testing import CliRunner

from a4d.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})


def _hash_dir(dir_path: Path) -> dict[str, str]:
    """Return {relative_path: sha256} for the deterministic data outputs.

    Restricted to ``patient_data_cleaned/*.parquet`` and the patient-table
    parquets. Skips ``logs/`` (per-tracker JSON contains timestamps) and
    ``table_logs.parquet`` (aggregated log timestamps).
    """
    out: dict[str, str] = {}
    cleaned = dir_path / "patient_data_cleaned"
    if cleaned.exists():
        for f in sorted(cleaned.glob("*.parquet")):
            out[f"patient_data_cleaned/{f.name}"] = hashlib.sha256(f.read_bytes()).hexdigest()
    tables = dir_path / "tables"
    if tables.exists():
        for f in sorted(tables.glob("patient_data_*.parquet")):
            out[f"tables/{f.name}"] = hashlib.sha256(f.read_bytes()).hexdigest()
    return out


class TestHelpExposesForce:
    """Every command that takes --incremental must also expose --force."""

    def test_process_patient_help_mentions_force(self):
        result = runner.invoke(app, ["run", "patient", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output

    def test_process_product_help_mentions_force(self):
        result = runner.invoke(app, ["run", "product", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output

    def test_run_pipeline_help_mentions_force(self):
        result = runner.invoke(app, ["run", "--help"])
        assert result.exit_code == 0
        assert "--force" in result.output


class TestForceFlag:
    """--force semantics on run patient (the one CLI command we can drive end-to-end)."""

    def test_force_produces_same_output_as_default(self, dummy_tracker_dir, tmp_path):
        """--force is an explicit synonym for the default — outputs must match byte-for-byte."""
        out_default = tmp_path / "out_default"
        out_force = tmp_path / "out_force"

        r1 = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--data-root",
                str(dummy_tracker_dir),
                "--output",
                str(out_default),
            ],
        )
        assert r1.exit_code == 0, f"default run failed:\n{r1.output}"

        r2 = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--data-root",
                str(dummy_tracker_dir),
                "--output",
                str(out_force),
                "--force",
            ],
        )
        assert r2.exit_code == 0, f"--force run failed:\n{r2.output}"

        assert _hash_dir(out_default) == _hash_dir(out_force)

    def test_force_is_deterministic(self, dummy_tracker_dir, tmp_path):
        """Two consecutive --force runs into separate dirs produce identical outputs."""
        out_a = tmp_path / "a"
        out_b = tmp_path / "b"

        for out in (out_a, out_b):
            r = runner.invoke(
                app,
                [
                    "run",
                    "patient",
                    "--data-root",
                    str(dummy_tracker_dir),
                    "--output",
                    str(out),
                    "--force",
                ],
            )
            assert r.exit_code == 0, f"run into {out} failed:\n{r.output}"

        assert _hash_dir(out_a) == _hash_dir(out_b)

    def test_force_wipes_existing_outputs(self, dummy_tracker_dir, tmp_path):
        """--force must trigger the orchestrator's clean_output=True wipe.

        Pre-seed sentinel files in all four dirs the orchestrator wipes
        (patient_data_raw, patient_data_cleaned, tables, logs — see
        pipeline/patient.py:176) and confirm they're gone after --force runs.
        Without this check the determinism tests would pass even if --force
        silently became a no-op (since they hash output equivalence into fresh
        empty dirs, not the wipe behavior itself).
        """
        out = tmp_path / "out"
        wipe_dirs = ("patient_data_raw", "patient_data_cleaned", "tables", "logs")
        for subdir in wipe_dirs:
            (out / subdir).mkdir(parents=True)
            (out / subdir / "_sentinel").write_text("from prior run")

        result = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--data-root",
                str(dummy_tracker_dir),
                "--output",
                str(out),
                "--force",
            ],
        )
        assert result.exit_code == 0, f"--force run failed:\n{result.output}"

        for subdir in wipe_dirs:
            assert not (out / subdir / "_sentinel").exists(), (
                f"--force did not wipe {subdir}/_sentinel"
            )


class TestForceIncrementalConflict:
    """--force overrides --incremental with a warning."""

    def test_warning_printed_when_both_set(self, dummy_tracker_dir, tmp_path):
        out = tmp_path / "out"
        result = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--data-root",
                str(dummy_tracker_dir),
                "--output",
                str(out),
                "--force",
                "--incremental",
            ],
        )
        assert result.exit_code == 0, f"combined run failed:\n{result.output}"
        assert "--incremental is ignored when --force is set" in result.output

    def test_combined_output_matches_force_alone(self, dummy_tracker_dir, tmp_path):
        """--force --incremental should behave exactly like --force (incremental ignored)."""
        out_force = tmp_path / "force"
        out_both = tmp_path / "both"

        r_force = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--data-root",
                str(dummy_tracker_dir),
                "--output",
                str(out_force),
                "--force",
            ],
        )
        assert r_force.exit_code == 0

        r_both = runner.invoke(
            app,
            [
                "run",
                "patient",
                "--data-root",
                str(dummy_tracker_dir),
                "--output",
                str(out_both),
                "--force",
                "--incremental",
            ],
        )
        assert r_both.exit_code == 0

        assert _hash_dir(out_force) == _hash_dir(out_both)


# Note: a "second incremental run skips unchanged" test would need to seed the
# tracker_metadata manifest first — run patient does not create it (only
# create tables / the bare run do). That code path is exercised by
# tests/test_state/test_integration.py, so we don't duplicate it here.
