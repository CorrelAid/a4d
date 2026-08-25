"""Create the findings table from every data-quality finding in a run.

One row per finding, one schema, joinable on ``file_name`` against
``tracker_metadata`` and the data tables. Supersedes the errors table, which
held only the cell-level half of the findings and could not be joined to the
other half at all.
"""

import json
from datetime import datetime
from pathlib import Path

import polars as pl
from loguru import logger

from a4d.findings import FINDING_CATEGORY, FINDINGS_SCHEMA, Finding


def create_table_findings(findings: list[Finding], output_dir: Path) -> Path:
    """Write every finding collected during a run to one parquet.

    Args:
        findings: All findings collected across both arms and the table stage
        output_dir: Directory to write the findings table parquet

    Returns:
        Path to the created findings table parquet file

    Example:
        >>> path = create_table_findings(all_findings, Path("output/tables"))
        >>> path
        Path('output/tables/table_findings.parquet')
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "table_findings.parquet"

    if not findings:
        logger.info("No data-quality findings to write, creating empty findings table")
        pl.DataFrame(schema=FINDINGS_SCHEMA).write_parquet(output_file)
        return output_file

    records = [{**f.model_dump(), "category": f.category} for f in findings]
    df = pl.DataFrame(records, schema=FINDINGS_SCHEMA).sort("timestamp")
    df.write_parquet(output_file)

    logger.info(f"Findings table saved: {output_file} ({len(df):,} findings)")

    # Category first: it is what says whether anyone has to act, and a run
    # with 60,000 recoveries and no workbook defects reads very differently
    # from the reverse.
    by_category = (
        df.group_by("category").agg(pl.len().alias("count")).sort("count", descending=True)
    )
    logger.info(f"Findings by category: {by_category.to_dict(as_series=False)}")
    by_code = df.group_by("error_code").agg(pl.len().alias("count")).sort("count", descending=True)
    logger.info(f"Findings by code: {by_code.to_dict(as_series=False)}")

    return output_file


def rebuild_findings_from_logs(
    logs_dir: Path, output_dir: Path, extra_findings: list[Finding] | None = None
) -> Path:
    """Rebuild the findings table from a completed run's log files.

    ``a4d create tables`` re-derives every table from what is on disk, but
    findings live in memory during a run -- they are not in the cleaned
    parquets. Without this the command would rebuild everything else and leave
    whatever ``table_findings.parquet`` an earlier run wrote, which
    ``a4d upload tables`` would then publish alongside fresh data.

    Reconstruction is lossless because ``report_finding`` binds every field of
    the record onto the log line it emits, so this reads the findings back
    rather than approximating them.

    Args:
        logs_dir: Directory holding the run's per-tracker ``.log`` files
        output_dir: Directory to write the findings table parquet
        extra_findings: Findings emitted in this process rather than read back
            from the logs -- the product table stage's, which run under
            ``findings_collected`` and so write to no per-tracker log file

    Returns:
        Path to the created findings table parquet file
    """
    findings: list[Finding] = list(extra_findings or [])
    seen: set[tuple] = set()

    for log_file in sorted(logs_dir.glob("*.log")):
        with log_file.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line).get("record", {})
                except json.JSONDecodeError:
                    continue
                extra = record.get("extra", {})
                error_code = extra.get("error_code")
                if error_code is None or error_code not in FINDING_CATEGORY:
                    continue

                file_name = extra.get("finding_file_name") or extra.get("file_name")
                if not file_name:
                    continue

                timestamp = record.get("time", {}).get("timestamp")
                # loguru writes every line to both the per-tracker handler and
                # the worker's own file, so the same finding appears more than
                # once across the directory.
                key = (file_name, error_code, extra.get("column"), record.get("message"), timestamp)
                if key in seen:
                    continue
                seen.add(key)

                findings.append(
                    Finding(
                        file_name=file_name,
                        arm=extra.get("arm") or "patient",
                        sheet_name=extra.get("sheet_name") or "",
                        patient_id=extra.get("patient_id") or "unknown",
                        column=extra.get("column") or "",
                        original_value=extra.get("original_value") or "",
                        message=record.get("message", ""),
                        error_code=error_code,
                        stage=extra.get("stage") or "clean",
                        function_name=extra.get("emitting_function") or "",
                        tracker_year=extra.get("tracker_year"),
                        tracker_month=extra.get("tracker_month"),
                        timestamp=datetime.fromtimestamp(timestamp)
                        if timestamp
                        else datetime.now(),
                    )
                )

    logger.info(f"Rebuilt {len(findings):,} findings from {logs_dir}")
    return create_table_findings(findings, output_dir)
