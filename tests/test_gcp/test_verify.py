"""Tests for post-production-run verification against a backup snapshot."""

from types import SimpleNamespace
from unittest.mock import MagicMock

from a4d.gcp.verify import TableStats, diff_table_stats, fetch_table_stats


def _stats(row_count=100, distinct_clinics=10, columns=("clinic_id", "patient_id")):
    return TableStats(
        row_count=row_count, distinct_clinics=distinct_clinics, columns=frozenset(columns)
    )


class TestDiffTableStats:
    def test_no_anomalies_when_stats_match(self):
        before = {"patient_data_static": _stats()}
        after = {"patient_data_static": _stats()}

        assert diff_table_stats(before, after) == []

    def test_no_anomalies_when_row_count_grows(self):
        before = {"product_data": _stats(row_count=100)}
        after = {"product_data": _stats(row_count=200)}

        assert diff_table_stats(before, after) == []

    def test_flags_large_row_count_drop(self):
        before = {"product_data": _stats(row_count=100)}
        after = {"product_data": _stats(row_count=50)}

        anomalies = diff_table_stats(before, after)

        assert len(anomalies) == 1
        assert anomalies[0].table == "product_data"
        assert "row count dropped" in anomalies[0].reason

    def test_ignores_row_count_drop_within_threshold(self):
        before = {"product_data": _stats(row_count=100)}
        after = {"product_data": _stats(row_count=95)}

        assert diff_table_stats(before, after) == []

    def test_flags_schema_change(self):
        before = {"product_data": _stats(columns=("clinic_id", "patient_id"))}
        after = {"product_data": _stats(columns=("clinic_id",))}

        anomalies = diff_table_stats(before, after)

        assert len(anomalies) == 1
        assert "schema changed" in anomalies[0].reason

    def test_flags_distinct_clinic_drop(self):
        before = {"product_data": _stats(distinct_clinics=10)}
        after = {"product_data": _stats(distinct_clinics=5)}

        anomalies = diff_table_stats(before, after)

        assert len(anomalies) == 1
        assert "distinct clinics dropped" in anomalies[0].reason

    def test_skips_clinic_check_when_table_has_no_clinic_id(self):
        before = {"patient_data_annual": _stats(distinct_clinics=None, columns=("patient_id",))}
        after = {"patient_data_annual": _stats(distinct_clinics=None, columns=("patient_id",))}

        assert diff_table_stats(before, after) == []

    def test_flags_table_missing_after_run(self):
        before = {"product_data": _stats()}
        after = {}

        anomalies = diff_table_stats(before, after)

        assert len(anomalies) == 1
        assert anomalies[0].table == "product_data"
        assert "missing" in anomalies[0].reason

    def test_ignores_table_absent_from_before(self):
        before = {}
        after = {"product_data": _stats()}

        assert diff_table_stats(before, after) == []


class TestFetchTableStats:
    def test_queries_row_count_distinct_clinics_and_schema(self):
        mock_client = MagicMock()

        mock_field = MagicMock()
        mock_field.name = "clinic_id"
        mock_table = MagicMock()
        mock_table.schema = [mock_field]
        mock_client.get_table.return_value = mock_table

        mock_row = MagicMock(row_count=42, distinct_clinics=7)
        mock_client.query.return_value.result.return_value = [mock_row]

        stats = fetch_table_stats(mock_client, "product_data")

        assert stats == TableStats(
            row_count=42, distinct_clinics=7, columns=frozenset({"clinic_id"})
        )
        mock_client.get_table.assert_called_once_with("a4dphase2.tracker.product_data")

    def test_skips_distinct_clinic_query_when_no_clinic_id_column(self):
        mock_client = MagicMock()

        mock_field = MagicMock()
        mock_field.name = "patient_id"
        mock_table = MagicMock()
        mock_table.schema = [mock_field]
        mock_client.get_table.return_value = mock_table

        mock_row = MagicMock(row_count=42)
        mock_client.query.return_value.result.return_value = [mock_row]

        stats = fetch_table_stats(mock_client, "patient_data_annual")

        assert stats == TableStats(
            row_count=42, distinct_clinics=None, columns=frozenset({"patient_id"})
        )
        query = mock_client.query.call_args.args[0]
        assert "clinic_id" not in query


class TestVerifiedTables:
    """VERIFIED_TABLES must be derived from what the pipeline publishes.

    A hand-typed list drifted once already: it named `errors` (retired) and
    omitted `findings` (its replacement), so the two tables that changed most
    were the two nothing checked.
    """

    def test_covers_every_published_table(self):
        from a4d.gcp.bigquery import published_table_names
        from a4d.gcp.verify import VERIFIED_TABLES

        assert set(VERIFIED_TABLES) == set(published_table_names())

    def test_includes_findings_and_logs(self):
        from a4d.gcp.verify import VERIFIED_TABLES

        assert "findings" in VERIFIED_TABLES
        assert "logs" in VERIFIED_TABLES

    def test_excludes_the_retired_errors_table(self):
        from a4d.gcp.verify import VERIFIED_TABLES

        assert "errors" not in VERIFIED_TABLES


class TestFetchTableStatsIfPresent:
    """A table with no snapshot is new, not a failure.

    `findings` did not exist at the last backup, so demanding a snapshot for
    every verified table would make the first run after this deploy crash
    instead of reporting.
    """

    def test_returns_none_when_the_table_is_absent(self):
        from google.api_core.exceptions import NotFound

        from a4d.gcp.verify import fetch_table_stats_if_present

        client = MagicMock()
        client.get_table.side_effect = NotFound("no such table")

        assert fetch_table_stats_if_present(client, "findings_20260809") is None

    def test_returns_stats_when_the_table_exists(self):
        from a4d.gcp.verify import fetch_table_stats_if_present

        client = MagicMock()
        client.get_table.return_value = SimpleNamespace(
            schema=[SimpleNamespace(name="clinic_id"), SimpleNamespace(name="patient_id")]
        )
        client.query.return_value.result.return_value = iter(
            [MagicMock(row_count=42, distinct_clinics=7)]
        )

        stats = fetch_table_stats_if_present(client, "patient_data_static")

        assert stats is not None
        assert stats.row_count == 42
        assert stats.distinct_clinics == 7
