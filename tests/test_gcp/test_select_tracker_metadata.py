"""Tests for select_tracker_metadata."""

from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import GoogleAPIError, NotFound

from a4d.gcp.bigquery import select_tracker_metadata


def _query_result(rows: list[dict]) -> MagicMock:
    """Build a MagicMock that mimics client.query(...).result()."""
    job = MagicMock()
    job.result.return_value = rows
    return job


def test_happy_path_returns_dataframe():
    rows = [{"file_name": "T1", "clinic_code": "A", "md5": "abc", "complete": True}]
    client = MagicMock()
    client.query.return_value = _query_result(rows)

    result = select_tracker_metadata(client=client, dataset="tracker", project_id="proj")

    assert result is not None
    assert result.height == 1
    assert result["complete"].to_list() == [True]


def test_not_found_returns_none():
    client = MagicMock()
    client.query.side_effect = NotFound("table not found")

    result = select_tracker_metadata(client=client, dataset="tracker", project_id="proj")

    assert result is None


def test_schema_fallback_when_complete_column_missing():
    """Older deployments may have shipped without the `complete` column."""
    client = MagicMock()
    # First query (with `complete`) raises a column-missing GoogleAPIError;
    # second query (without `complete`) succeeds with the legacy schema.
    fallback_rows = [{"file_name": "T1", "clinic_code": "A", "md5": "abc"}]
    client.query.side_effect = [
        GoogleAPIError("Unrecognized name: complete at [1:14]"),
        _query_result(fallback_rows),
    ]

    result = select_tracker_metadata(client=client, dataset="tracker", project_id="proj")

    assert result is not None
    assert result["complete"].to_list() == [False], (
        "Schema fallback must synthesise complete=False to force a full reprocess"
    )
    assert client.query.call_count == 2


def test_unrelated_google_api_error_returns_none():
    client = MagicMock()
    client.query.side_effect = GoogleAPIError("Network unreachable")

    result = select_tracker_metadata(client=client, dataset="tracker", project_id="proj")

    assert result is None


def test_auth_failure_during_client_construction_returns_none():
    """When no client is supplied and `get_bigquery_client` raises (e.g. missing
    credentials), the function must fall through with a warning, not raise."""
    with patch(
        "a4d.gcp.bigquery.get_bigquery_client",
        side_effect=Exception("DefaultCredentialsError: no creds"),
    ):
        result = select_tracker_metadata(dataset="tracker", project_id="proj")

    assert result is None
