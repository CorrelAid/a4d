"""The rebuild counts a finding once, even when it arrives by both routes.

``rebuild_findings_from_logs`` reads a completed run's log files, and takes
``extra_findings`` for findings emitted in the calling process rather than read
back -- the product table stage's. But that stage emits through
``report_finding``, which also writes to whatever loguru sink is active, so its
findings are usually in ``main_pipeline_product.log`` as well. Measured
2026-08-27 over the 255-tracker local corpus: the log-only rebuild returned
105,464, exactly the run, while ``a4d create tables`` returned 108,466 -- the
excess being 2,972 ``patient_id_unrepairable`` plus 30 ``patient_id_recovered``
counted twice.
"""

import json
from pathlib import Path

import polars as pl

from a4d.findings import Finding
from a4d.tables.findings import create_table_findings, rebuild_findings_from_logs


def _log_line(finding: Finding, timestamp: float) -> str:
    """One serialized loguru record carrying a finding, as report_finding writes it."""
    return json.dumps(
        {
            "record": {
                "message": finding.message,
                "time": {"timestamp": timestamp},
                "extra": {
                    "error_code": finding.error_code,
                    "finding_file_name": finding.file_name,
                    "arm": finding.arm,
                    "sheet_name": finding.sheet_name,
                    "patient_id": finding.patient_id,
                    "column": finding.column,
                    "original_value": finding.original_value,
                    "stage": finding.stage,
                    "emitting_function": finding.function_name,
                    "tracker_year": finding.tracker_year,
                    "tracker_month": finding.tracker_month,
                },
            }
        }
    )


def _a_finding(patient_id: str = "MY_PJ001") -> Finding:
    return Finding(
        file_name="2024_Putrajaya",
        arm="product",
        sheet_name="Jan24",
        patient_id=patient_id,
        column="patient_id",
        original_value="MY-PJ-001",
        message=f"Patient ID {patient_id} could not be repaired",
        error_code="patient_id_unrepairable",
        stage="tables",
        function_name="create_table_product_data",
    )


def test_a_finding_in_both_the_log_and_extra_findings_is_counted_once(tmp_path: Path):
    logs = tmp_path / "logs"
    logs.mkdir()
    finding = _a_finding()
    (logs / "main_pipeline_product.log").write_text(_log_line(finding, 1_756_000_000.0))

    out = rebuild_findings_from_logs(logs, tmp_path / "tables", extra_findings=[finding])

    assert len(pl.read_parquet(out)) == 1


def test_an_extra_finding_absent_from_the_logs_is_still_kept(tmp_path: Path):
    """The parameter exists for findings no log holds -- those must survive."""
    logs = tmp_path / "logs"
    logs.mkdir()
    logged = _a_finding("MY_PJ001")
    (logs / "main_pipeline_product.log").write_text(_log_line(logged, 1_756_000_000.0))

    out = rebuild_findings_from_logs(
        logs, tmp_path / "tables", extra_findings=[logged, _a_finding("MY_PJ002")]
    )

    df = pl.read_parquet(out)
    assert len(df) == 2
    assert set(df.get_column("patient_id").to_list()) == {"MY_PJ001", "MY_PJ002"}


class TestThePublishedTableCarriesTheDerivedFields:
    """Both writers materialise them, because both used to derive their own.

    ``scope`` shipped as an all-null column on its first real run: the
    collector's ``to_dataframe`` learned about it and ``create_table_findings``
    built its own record dicts, so the published table -- the one BigQuery
    reads -- silently had nothing in it.
    """

    @staticmethod
    def _finding(**overrides) -> Finding:
        fields = {
            "file_name": "2024_Penang",
            "arm": "patient",
            "sheet_name": "Jan24",
            "message": "m",
            "error_code": "type_conversion",
        }
        return Finding(**{**fields, **overrides})

    def test_create_table_findings_writes_scope_and_category(self, tmp_path):
        path = create_table_findings([self._finding()], tmp_path)
        df = pl.read_parquet(path)
        assert df["scope"].to_list() == ["row"]
        assert df["category"].to_list() == ["data_lost"]

    def test_the_rebuild_writes_them_too(self, tmp_path):
        logs = tmp_path / "logs"
        logs.mkdir()
        (logs / "t_patient.log").write_text(_log_line(self._finding(), 1.0) + "\n")

        df = pl.read_parquet(rebuild_findings_from_logs(logs, tmp_path))

        assert df["scope"].to_list() == ["row"]
        assert df["tracker_month"].to_list() == [None]

    def test_a_workbook_scoped_finding_says_so(self, tmp_path):
        """The distinction the field exists for: a blank sheet that means
        "the whole workbook", not "we lost which sheet"."""
        finding = self._finding(error_code="empty_product_data", arm="product", sheet_name="")
        df = pl.read_parquet(create_table_findings([finding], tmp_path))
        assert df["scope"].to_list() == ["tracker"]
        assert df["sheet_name"].to_list() == [""]
