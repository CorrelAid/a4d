"""Coarse sanity check of a production run against a `just backup-bq` snapshot.

Not a cell-by-cell R-vs-Python comparison (that lives in scripts/compare_r_vs_python.py
and the future automated report) -- this only catches gross regressions (a table going
near-empty, losing clinics, or changing shape) right after a real production run.
"""

from dataclasses import dataclass

from google.cloud import bigquery

from a4d.config import settings

VERIFIED_TABLES = [
    "patient_data_static",
    "patient_data_monthly",
    "patient_data_annual",
    "product_data",
]

ROW_COUNT_DROP_THRESHOLD = 0.10


@dataclass(frozen=True)
class TableStats:
    row_count: int
    distinct_clinics: int
    columns: frozenset[str]


@dataclass(frozen=True)
class TableAnomaly:
    table: str
    reason: str


def diff_table_stats(
    before: dict[str, TableStats], after: dict[str, TableStats]
) -> list[TableAnomaly]:
    anomalies = []
    for table, before_stats in before.items():
        after_stats = after.get(table)
        if after_stats is None:
            anomalies.append(TableAnomaly(table, "missing after the run"))
            continue

        if after_stats.columns != before_stats.columns:
            added = sorted(after_stats.columns - before_stats.columns)
            removed = sorted(before_stats.columns - after_stats.columns)
            anomalies.append(
                TableAnomaly(table, f"schema changed (added={added}, removed={removed})")
            )

        if before_stats.row_count > 0:
            drop = (before_stats.row_count - after_stats.row_count) / before_stats.row_count
            if drop > ROW_COUNT_DROP_THRESHOLD:
                anomalies.append(
                    TableAnomaly(
                        table,
                        f"row count dropped {drop:.0%} "
                        f"({before_stats.row_count} -> {after_stats.row_count})",
                    )
                )

        if after_stats.distinct_clinics < before_stats.distinct_clinics:
            anomalies.append(
                TableAnomaly(
                    table,
                    "distinct clinics dropped "
                    f"({before_stats.distinct_clinics} -> {after_stats.distinct_clinics})",
                )
            )

    return anomalies


def fetch_table_stats(
    client: bigquery.Client,
    table_name: str,
    dataset: str | None = None,
    project_id: str | None = None,
) -> TableStats:
    dataset = dataset or settings.dataset
    project_id = project_id or settings.project_id
    table_ref = f"{project_id}.{dataset}.{table_name}"

    table = client.get_table(table_ref)
    columns = frozenset(field.name for field in table.schema)

    query = (
        f"SELECT COUNT(*) AS row_count, COUNT(DISTINCT clinic_id) AS distinct_clinics "
        f"FROM `{table_ref}`"
    )
    row = next(iter(client.query(query).result()))

    return TableStats(
        row_count=row.row_count, distinct_clinics=row.distinct_clinics, columns=columns
    )
