"""Turn a run's findings into one Excel workbook a person can act on.

The audience is two people who currently have no way to see this data: an A4D
staff member who needs to know which trackers a clinic must correct, and an
operator debugging why a particular tracker produced the output it did. Both
questions are answered by the same rows -- ``table_findings`` -- seen through
different filters, which is why this is one workbook and not two.

Three sheets:

- **Summary**, one row per tracker, ranked by how many ``fix_workbook``
  findings it carries. The first thing visible is which workbooks need a human,
  not the hundred thousand rows behind them.
- **Findings**, every finding with an autofilter. Deliberately not one sheet
  per tracker: 254 tabs is unnavigable, and filtering ``file_name`` gives the
  same view while still allowing questions a per-tracker tab cannot answer
  ("every tracker with a swapped glucose unit").
- **Glossary**, every error code with what it means and what to do about it,
  generated from :data:`a4d.findings.FINDING_GLOSSARY` so it cannot drift from
  the taxonomy.
"""

from datetime import datetime
from pathlib import Path

import polars as pl
import xlsxwriter
from loguru import logger

from a4d.findings import FINDING_CATEGORY, FINDING_GLOSSARY

# Actionability first, then enough to find the cell in the workbook, then the
# provenance an operator needs and a clinic does not. The order is the reading
# order of the sheet, so a staff member never scrolls right to learn whether a
# row matters.
_FINDINGS_COLUMN_ORDER = [
    "category",
    "file_name",
    "sheet_name",
    "patient_id",
    "column",
    "original_value",
    "error_code",
    "message",
    "arm",
    "tracker_year",
    "tracker_month",
    "stage",
    "function_name",
    "timestamp",
]

# Ranking key for the summary sheet. "Fix the workbook" outranks "data was
# lost" because a lost cell is usually the consequence of a defect one column
# over, and a recovery is not a problem at all.
_CATEGORY_RANK = ["fix_workbook", "data_lost", "recovered"]

_COLUMN_WIDTHS = {
    "category": 13,
    "file_name": 46,
    "sheet_name": 12,
    "patient_id": 14,
    "column": 24,
    "original_value": 28,
    "error_code": 24,
    "message": 70,
    "arm": 9,
    "tracker_year": 8,
    "tracker_month": 8,
    "stage": 9,
    "function_name": 26,
    "timestamp": 19,
}


def summarise_by_tracker(findings: pl.DataFrame) -> pl.DataFrame:
    """One row per tracker, ranked so the workbooks needing a human come first.

    Args:
        findings: The findings table, as written by ``create_table_findings``

    Returns:
        One row per ``file_name`` with a count per category and a total,
        sorted by ``fix_workbook`` descending

    Example:
        >>> summarise_by_tracker(findings).head(1)["file_name"].item()
        '2021_Kantha Bopha A4D Tracker'
    """
    # No tracker_year column: the findings table declares one but nothing
    # populates it (measured 2026-08-25: 0 of 122,590 rows), so it would render
    # as a column of blanks. Every tracker name starts with its year, and
    # file_name is the first thing on the sheet, so filtering by year still
    # works. Filling the field is part of the source-defect report ticket.
    if findings.is_empty():
        return pl.DataFrame(
            schema={
                "file_name": pl.Utf8,
                "arms": pl.Utf8,
                **dict.fromkeys(_CATEGORY_RANK, pl.UInt32),
                "total": pl.UInt32,
            }
        )

    counts = [
        pl.col("category").cast(pl.Utf8).eq(category).sum().cast(pl.UInt32).alias(category)
        for category in _CATEGORY_RANK
    ]
    return (
        findings.group_by("file_name")
        .agg(
            pl.col("arm").cast(pl.Utf8).unique().sort().str.join(", ").alias("arms"),
            *counts,
            pl.len().cast(pl.UInt32).alias("total"),
        )
        .sort(["fix_workbook", "data_lost", "total"], descending=True)
    )


def glossary_frame(findings: pl.DataFrame) -> pl.DataFrame:
    """Every error code, what it means, and how often it fired in this run.

    Generated from the taxonomy rather than from the run, so a code that fired
    zero times still appears -- a reader looking up a code they saw last month
    should find it whether or not this run happened to produce one.

    Args:
        findings: The findings table, used only for the per-code counts

    Returns:
        One row per error code with category, meaning and count
    """
    observed = (
        {}
        if findings.is_empty()
        else dict(
            findings.group_by("error_code")
            .agg(pl.len().alias("count"))
            .select(pl.col("error_code").cast(pl.Utf8), "count")
            .iter_rows()
        )
    )
    return pl.DataFrame(
        {
            "error_code": list(FINDING_GLOSSARY),
            "category": [FINDING_CATEGORY[code] for code in FINDING_GLOSSARY],
            "what_it_means_and_what_to_do": list(FINDING_GLOSSARY.values()),
            "count_in_this_run": [int(observed.get(code, 0)) for code in FINDING_GLOSSARY],
        }
    ).sort(
        [
            pl.col("category").replace_strict(
                {name: rank for rank, name in enumerate(_CATEGORY_RANK)}, default=99
            ),
            pl.col("count_in_this_run") * -1,
        ]
    )


def build_findings_report(
    findings: pl.DataFrame,
    output_path: Path,
    tracker: str | None = None,
) -> Path:
    """Write the three-sheet findings workbook.

    Args:
        findings: The findings table, as written by ``create_table_findings``
        output_path: Where to write the .xlsx
        tracker: Restrict to one tracker (substring match on ``file_name``),
            for the drill-down case where an operator has one file in hand

    Returns:
        The path written

    Raises:
        ValueError: If ``tracker`` matches no tracker in the findings

    Example:
        >>> build_findings_report(findings, Path("findings.xlsx"))
        Path('findings.xlsx')
    """
    findings = _ordered(findings)
    if tracker is not None:
        findings = findings.filter(pl.col("file_name").str.contains(tracker, literal=True))
        if findings.is_empty():
            raise ValueError(f"No findings for a tracker matching {tracker!r}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = summarise_by_tracker(findings)
    glossary = glossary_frame(findings)

    with xlsxwriter.Workbook(str(output_path)) as workbook:
        _write_sheet(workbook, summary, "Summary", autofilter=True)
        _write_sheet(workbook, findings, "Findings", autofilter=True)
        _write_sheet(workbook, glossary, "Glossary", autofilter=False)

    logger.info(
        f"Findings report written: {output_path} "
        f"({len(findings):,} findings across {summary.height:,} trackers)"
    )
    return output_path


def _ordered(findings: pl.DataFrame) -> pl.DataFrame:
    """Findings in reading order, tolerating a table missing optional columns."""
    present = [column for column in _FINDINGS_COLUMN_ORDER if column in findings.columns]
    extra = [column for column in findings.columns if column not in _FINDINGS_COLUMN_ORDER]
    return findings.select([*present, *extra])


def _write_sheet(
    workbook: xlsxwriter.Workbook, frame: pl.DataFrame, name: str, *, autofilter: bool
) -> None:
    """Write one frame as a formatted sheet with a frozen header row."""
    sheet = workbook.add_worksheet(name)
    header_format = workbook.add_format(
        {"bold": True, "bg_color": "#D9E1F2", "border": 1, "text_wrap": True, "valign": "top"}
    )
    wrap_format = workbook.add_format({"text_wrap": True, "valign": "top"})
    date_format = workbook.add_format({"num_format": "yyyy-mm-dd hh:mm:ss"})

    for index, column in enumerate(frame.columns):
        sheet.write(0, index, column, header_format)
        width = _COLUMN_WIDTHS.get(column, max(12, len(column) + 2))
        wraps = column in {"message", "what_it_means_and_what_to_do"}
        sheet.set_column(index, index, width, wrap_format if wraps else None)

    for row_index, row in enumerate(frame.iter_rows(), start=1):
        for column_index, value in enumerate(row):
            if value is None:
                continue
            if isinstance(value, datetime):
                sheet.write_datetime(row_index, column_index, value, date_format)
            elif isinstance(value, (int, float)):
                sheet.write_number(row_index, column_index, value)
            else:
                sheet.write_string(row_index, column_index, str(value))

    sheet.freeze_panes(1, 0)
    if autofilter and frame.width:
        sheet.autofilter(0, 0, max(frame.height, 1), frame.width - 1)


def load_findings(path: Path) -> pl.DataFrame:
    """Read a findings table parquet, or an empty frame with the right schema.

    Args:
        path: Path to ``table_findings.parquet``

    Returns:
        The findings table

    Raises:
        FileNotFoundError: If the parquet does not exist
    """
    if not path.exists():
        raise FileNotFoundError(
            f"No findings table at {path}. Run `a4d run` first, or "
            f"`a4d create tables` to rebuild it from a completed run's logs."
        )
    return pl.read_parquet(path)
