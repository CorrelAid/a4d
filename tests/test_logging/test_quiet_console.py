"""Nothing configures logging until an arm starts, so the download steps shout.

The 2026-08-30 quiet-console run still emitted 256 DEBUG lines -- one per
tracker downloaded from GCS -- because `setup_logging` is called inside
`run_patient_pipeline`/`run_product_pipeline`, and Steps 0 and 1 (Drive and
GCS download) run before either. Until then loguru's default handler is still
installed, which writes everything from DEBUG up.
"""

from unittest.mock import Mock, patch

from typer.testing import CliRunner

from a4d.cli import app

runner = CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})


class TestConfigureQuietConsole:
    def test_installs_exactly_one_handler(self):
        from loguru import logger

        from a4d.logging import configure_quiet_console

        configure_quiet_console()
        assert len(logger._core.handlers) == 1

    def test_that_handler_drops_everything_below_error(self, capfd):
        from loguru import logger

        from a4d.logging import configure_quiet_console

        configure_quiet_console()
        logger.debug("downloading a tracker")
        logger.info("still chatty")
        logger.warning("a finding")
        logger.error("something actually broke")

        out = capfd.readouterr()
        combined = out.out + out.err
        assert "downloading a tracker" not in combined
        assert "still chatty" not in combined
        assert "a finding" not in combined
        assert "something actually broke" in combined


class TestRunQuietsBeforeDownloading:
    def test_the_console_is_quiet_before_the_first_download(self, tmp_path, monkeypatch):
        """Ordering is the whole point: quieting after the download is too late."""
        from a4d.config import settings

        # Otherwise the run discovers the real tracker drive and processes it.
        monkeypatch.setattr(settings, "data_root", tmp_path / "data")
        monkeypatch.setattr(settings, "output_dir", tmp_path / "out")
        (tmp_path / "data").mkdir()

        calls = Mock()
        # Step 0 formats this file's size, so it needs a real path back.
        clinic_data = tmp_path / "clinic_data.xlsx"
        clinic_data.write_bytes(b"x")
        calls.drive.return_value = clinic_data
        calls.gcs.return_value = []

        with (
            patch("a4d.cli.configure_quiet_console", calls.quiet),
            patch("a4d.gcp.drive.download_clinic_data", calls.drive),
            patch("a4d.gcp.storage.download_tracker_files", calls.gcs),
            patch("a4d.cli.run_patient_pipeline", side_effect=RuntimeError("stop here")),
        ):
            runner.invoke(app, ["run", "--skip-upload", "--force"])

        order = [name for name, _, _ in calls.mock_calls]
        assert order[0] == "quiet", f"call order was {order}"
        assert "drive" in order, f"Drive download never ran: {order}"
        assert "gcs" in order, f"GCS download never ran: {order}"
