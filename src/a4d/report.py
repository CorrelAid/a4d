"""Turn a run's findings into one Excel workbook a person can act on.

The audience is two people who currently have no way to see this data: an A4D
staff member who needs to know which trackers a clinic must correct, and an
operator debugging why a particular tracker produced the output it did. Both
questions are answered by the same rows -- ``table_findings`` -- seen through
different filters, which is why this is one workbook and not two.

Four sheets:

- **Overview**, the run's statistics: how many trackers completed every stage,
  which stage lost the rest, and how the findings split by what a person can do
  about them.
- **Trackers**, one row per tracker, joining the processing record from
  ``tracker_metadata`` (did each arm's extract and clean stage succeed?) to the
  finding counts. Ordered newest year first, clinics alphabetical within a
  year, because the latest trackers are the ones a clinic can still correct.
  Every tracker appears, including the clean ones -- a tracker missing from a
  findings-only view looks identical whether it was perfect or never processed.
- **Findings**, every finding with an autofilter. Deliberately not one sheet
  per tracker: 254 tabs is unnavigable, and filtering ``file_name`` gives the
  same view while still allowing questions a per-tracker tab cannot answer
  ("every tracker with a swapped glucose unit").
- **Glossary**, every error code with what it means and what to do about it,
  generated from :data:`a4d.findings.FINDING_GLOSSARY` so it cannot drift from
  the taxonomy.
"""

import math
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

# The per-tracker processing record, as tracker_metadata publishes it: one
# boolean per arm per stage. Named for a reader rather than for the parquet,
# because "product_data_raw = false" does not say "product extraction failed".
_STAGE_COLUMNS = {
    "patient_data_raw": "patient extract",
    "patient_data_cleaned": "patient clean",
    "product_data_raw": "product extract",
    "product_data_cleaned": "product clean",
}

# Sheet headers. The frames keep snake_case names because code and tests read
# them; the workbook shows these, because its readers are A4D staff rather than
# developers and a header like "arms" does not say whether it means the arms
# that ran or the arms that found something.
_HEADERS = {
    # Trackers
    "file_name": "Tracker file",
    "clinic_code": "Clinic",
    "processed_completely": "Processed fully?",
    "stages_failed": "Stages that failed",
    "patient extract": "Patient: extract",
    "patient clean": "Patient: clean",
    "product extract": "Product: extract",
    "product clean": "Product: clean",
    "arms": "Arms that reported findings",
    "fix_workbook": "Findings: fix the workbook",
    "data_lost": "Findings: data lost",
    "recovered": "Findings: recovered",
    "total": "Findings: total",
    # Findings
    "category": "What to do",
    "sheet_name": "Sheet",
    "patient_id": "Patient ID",
    "column": "Field",
    "original_value": "Value in the workbook",
    "error_code": "Problem code",
    "message": "What happened",
    "arm": "Pipeline arm",
    "tracker_year": "Tracker year",
    "tracker_month": "Sheet month",
    "stage": "Pipeline stage",
    "function_name": "Reported by",
    "timestamp": "When",
    # Glossary
    "what_it_means_and_what_to_do": "What it means and what to do",
    "findings_in_this_run": "Findings in this run",
    "trackers_affected": "Trackers affected",
    "of_trackers_total": "of trackers total",
    "share_of_trackers": "Share of trackers",
    # Overview
    "measure": "Measure",
    "value": "Value",
}

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
    "what_it_means_and_what_to_do": 78,
    "clinic_code": 9,
    "processed_completely": 16,
    "stages_failed": 30,
    "patient extract": 15,
    "patient clean": 14,
    "product extract": 15,
    "product clean": 14,
    "arms": 26,
    "fix_workbook": 24,
    "data_lost": 18,
    "recovered": 18,
    "total": 14,
    "measure": 46,
    "value": 14,
    "findings_in_this_run": 12,
    "trackers_affected": 11,
    "of_trackers_total": 11,
    "share_of_trackers": 10,
}


def _recency_keys() -> list[pl.Expr]:
    """Sort keys putting the newest tracker year first, then clinic A-Z.

    The findings table declares a ``tracker_year`` column but nothing
    populates it (0 of 122,590 rows on the 2026-08-25 run), so the year is
    read off ``file_name``, which carries it in all 255 real trackers.
    254 are written ``2021_Kantha Bopha Hospital A4D Tracker``; one is
    ``2023 Kantha Bopha Hospital A4D Tracker``, with a space, which is why the
    separator is a character class rather than an underscore.

    A name with no leading year sorts last rather than first: an unparseable
    name is not evidence of recency.
    """
    year = pl.col("file_name").str.extract(r"^(\d{4})[ _]", 1).cast(pl.Int32, strict=False)
    clinic = pl.col("file_name").str.replace(r"^\d{4}[ _]", "")
    return [year, clinic]


def order_by_recency(frame: pl.DataFrame) -> pl.DataFrame:
    """Newest tracker year first, clinics alphabetical within a year.

    Latest trackers are the ones still being filled in, so a defect in one can
    still be corrected at the clinic; a 2017 workbook is history. Row order
    within a single tracker is preserved -- that is extraction order, which is
    the order the rows appear in the source sheet.

    Args:
        frame: Any frame carrying a ``file_name`` column

    Returns:
        The same rows, ordered newest-first

    Example:
        >>> order_by_recency(findings)["file_name"][0]
        '2026_CDA A4D Tracker'
    """
    return frame.sort(
        _recency_keys(), descending=[True, False], nulls_last=True, maintain_order=True
    )


def summarise_by_tracker(
    findings: pl.DataFrame, metadata: pl.DataFrame | None = None
) -> pl.DataFrame:
    """One row per tracker: did it process, and what did it report.

    Two questions an operator asks together and that live in two tables. The
    findings say what is wrong with the data; ``tracker_metadata`` says whether
    the pipeline got through the file at all, per arm and per stage. Joined
    here so a tracker that failed extraction outright is not silently absent --
    it produces few findings precisely because it produced little of anything.

    Ordered newest first (see :func:`order_by_recency`): a defect in a 2026
    tracker can still be corrected at the clinic, where a 2017 one is history.
    ``processed_completely`` and the category counts are columns on the sheet,
    so a reader wanting the old "who needs a human" ranking sorts on them with
    the autofilter.

    Args:
        findings: The findings table, as written by ``create_table_findings``
        metadata: ``tracker_metadata``, if available. Without it the sheet
            covers only trackers that produced at least one finding.

    Returns:
        One row per tracker with its processing status, which stages failed,
        and a count per finding category

    Example:
        >>> summarise_by_tracker(findings, metadata).head(1)["file_name"].item()
        '2021_Kantha Bopha A4D Tracker'
    """
    # No tracker_year column: the findings table declares one but nothing
    # populates it (measured 2026-08-25: 0 of 122,590 rows), so it would render
    # as a column of blanks. Every tracker name starts with its year, and
    # file_name is the first thing on the sheet, so filtering by year still
    # works. Filling the field is part of the source-defect report ticket.
    if findings.is_empty():
        per_tracker = pl.DataFrame(
            schema={
                "file_name": pl.Utf8,
                "arms": pl.Utf8,
                **dict.fromkeys(_CATEGORY_RANK, pl.UInt32),
                "total": pl.UInt32,
            }
        )
    else:
        counts = [
            pl.col("category").cast(pl.Utf8).eq(category).sum().cast(pl.UInt32).alias(category)
            for category in _CATEGORY_RANK
        ]
        per_tracker = findings.group_by("file_name").agg(
            pl.col("arm").cast(pl.Utf8).unique().sort().str.join(", ").alias("arms"),
            *counts,
            pl.len().cast(pl.UInt32).alias("total"),
        )

    if metadata is None:
        return order_by_recency(per_tracker)

    status = _tracker_status(metadata)
    # Left from the metadata, not from the findings: a tracker that produced no
    # findings at all still belongs on this sheet, and is the one an operator
    # most wants to see when it also failed to process.
    joined = status.join(per_tracker, on="file_name", how="left").with_columns(
        pl.col("arms").fill_null(""),
        *[pl.col(category).fill_null(0).cast(pl.UInt32) for category in _CATEGORY_RANK],
        pl.col("total").fill_null(0).cast(pl.UInt32),
    )
    return order_by_recency(joined)


def _tracker_status(metadata: pl.DataFrame) -> pl.DataFrame:
    """Per-tracker processing record, with the failed stages named."""
    present = [column for column in _STAGE_COLUMNS if column in metadata.columns]
    stage_labels = [
        pl.when(pl.col(column).not_()).then(pl.lit(_STAGE_COLUMNS[column])).otherwise(None)
        for column in present
    ]
    complete = (
        pl.col("complete")
        if "complete" in metadata.columns
        else pl.all_horizontal([pl.col(column) for column in present])
    )
    return metadata.select(
        "file_name",
        pl.col("clinic_code")
        if "clinic_code" in metadata.columns
        else pl.lit("").alias("clinic_code"),
        complete.fill_null(False).alias("processed_completely"),
        pl.concat_list(stage_labels).list.drop_nulls().list.join(", ").alias("stages_failed"),
        *[
            pl.when(pl.col(column))
            .then(pl.lit("ok"))
            .otherwise(pl.lit("FAILED"))
            .alias(_STAGE_COLUMNS[column])
            for column in present
        ],
    )


def glossary_frame(findings: pl.DataFrame, total_trackers: int | None = None) -> pl.DataFrame:
    """Every error code, what it means, and how widespread it is in this run.

    Generated from the taxonomy rather than from the run, so a code that fired
    zero times still appears -- a reader looking up a code they saw last month
    should find it whether or not this run happened to produce one.

    Carries a tracker count beside the cell count, because the two say very
    different things: 20,064 findings across 251 of 255 trackers is a
    systemic problem with the template, while the same number on three
    trackers is three workbooks to go and fix. A raw cell count cannot tell
    those apart.

    Args:
        findings: The findings table, used for the per-code counts
        total_trackers: Denominator for the "X of Y" column. Defaults to the
            number of trackers present in ``findings``, which under-counts
            when a tracker produced no findings at all -- pass the run's real
            tracker count where it is known.

    Returns:
        One row per error code with category, meaning, cell count, affected
        tracker count and the share of trackers affected
    """
    if findings.is_empty():
        counts: dict[str, tuple[int, int]] = {}
        denominator = total_trackers or 0
    else:
        counts = {
            code: (int(n), int(files))
            for code, n, files in findings.group_by("error_code")
            .agg(pl.len().alias("n"), pl.col("file_name").n_unique().alias("files"))
            .select(pl.col("error_code").cast(pl.Utf8), "n", "files")
            .iter_rows()
        }
        denominator = total_trackers or findings["file_name"].n_unique()

    return pl.DataFrame(
        {
            "error_code": list(FINDING_GLOSSARY),
            "category": [FINDING_CATEGORY[code] for code in FINDING_GLOSSARY],
            "what_it_means_and_what_to_do": list(FINDING_GLOSSARY.values()),
            "findings_in_this_run": [counts.get(code, (0, 0))[0] for code in FINDING_GLOSSARY],
            "trackers_affected": [counts.get(code, (0, 0))[1] for code in FINDING_GLOSSARY],
            "of_trackers_total": [denominator] * len(FINDING_GLOSSARY),
            # Floored, not rounded: 254 of 255 trackers is not "100%", and a
            # share that reads as "every tracker" when one is clean invites
            # exactly the wrong conclusion about how systemic a problem is.
            "share_of_trackers": [
                f"{math.floor(100 * counts.get(code, (0, 0))[1] / denominator)}%"
                if denominator
                else ""
                for code in FINDING_GLOSSARY
            ],
        }
    ).sort(
        [
            pl.col("category").replace_strict(
                {name: rank for rank, name in enumerate(_CATEGORY_RANK)}, default=99
            ),
            pl.col("trackers_affected") * -1,
            pl.col("findings_in_this_run") * -1,
        ]
    )


def overview_frame(findings: pl.DataFrame, metadata: pl.DataFrame | None = None) -> pl.DataFrame:
    """Run-level statistics, as label/value rows.

    The first thing to look at: how many trackers went through cleanly, which
    stage lost the ones that did not, and how the findings split by what a
    person can do about them. Everything here is derivable from the other
    sheets -- it is here so nobody has to derive it.

    Args:
        findings: The findings table
        metadata: ``tracker_metadata``, if available; the processing rows are
            omitted without it, since findings alone cannot say whether a
            tracker processed

    Returns:
        Two columns, ``measure`` and ``value``
    """
    rows: list[tuple[str, int]] = []

    if metadata is not None and not metadata.is_empty():
        status = _tracker_status(metadata)
        total = status.height
        complete = int(status["processed_completely"].sum())
        rows += [
            ("Trackers processed", total),
            ("Trackers that completed every stage", complete),
            ("Trackers with a failed stage", total - complete),
        ]
        for label in _STAGE_COLUMNS.values():
            if label in status.columns:
                failed = int((status[label] == "FAILED").sum())
                rows.append((f"Failed at {label}", failed))

    rows.append(("Trackers with at least one finding", findings["file_name"].n_unique()))
    rows.append(("Findings total", findings.height))
    for category in _CATEGORY_RANK:
        count = (
            0
            if findings.is_empty()
            else int(findings.filter(pl.col("category").cast(pl.Utf8) == category).height)
        )
        rows.append((f"Findings: {category.replace('_', ' ')}", count))
    if not findings.is_empty():
        for arm, count in (
            findings.group_by("arm")
            .agg(pl.len().alias("n"))
            .select(pl.col("arm").cast(pl.Utf8), "n")
            .sort("arm")
            .iter_rows()
        ):
            rows.append((f"Findings from the {arm} arm", int(count)))

    return pl.DataFrame({"measure": [r[0] for r in rows], "value": [r[1] for r in rows]})


def build_findings_report(
    findings: pl.DataFrame,
    output_path: Path,
    tracker: str | None = None,
    total_trackers: int | None = None,
    metadata: pl.DataFrame | None = None,
) -> Path:
    """Write the three-sheet findings workbook.

    Args:
        findings: The findings table, as written by ``create_table_findings``
        output_path: Where to write the .xlsx
        tracker: Restrict to one tracker (substring match on ``file_name``),
            for the drill-down case where an operator has one file in hand
        total_trackers: The run's real tracker count, for the glossary's
            "X of Y trackers" column. Without it the denominator is the
            trackers that produced at least one finding, which flatters a
            code by excluding the clean trackers from the comparison.
        metadata: ``tracker_metadata``, which carries the per-arm, per-stage
            processing record. Without it the Overview loses its processing
            rows and the Trackers sheet covers only trackers that reported
            something.

    Returns:
        The path written

    Raises:
        ValueError: If ``tracker`` matches no tracker in the findings

    Example:
        >>> build_findings_report(findings, Path("findings.xlsx"))
        Path('findings.xlsx')
    """
    findings = order_by_recency(_ordered(findings))
    # The glossary describes the whole run even when the sheets are filtered to
    # one tracker: its point is how widespread each problem is, and "1 of 1
    # trackers" answers nothing.
    whole_run = findings
    if tracker is not None:
        findings = findings.filter(pl.col("file_name").str.contains(tracker, literal=True))
        if findings.is_empty():
            raise ValueError(f"No findings for a tracker matching {tracker!r}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    # Overview and Glossary describe the whole run even in a drill-down: the
    # Trackers and Findings sheets are the filtered view.
    overview = overview_frame(whole_run, metadata)
    trackers = summarise_by_tracker(findings, metadata)
    glossary = glossary_frame(whole_run, total_trackers=total_trackers)

    with xlsxwriter.Workbook(str(output_path)) as workbook:
        _write_sheet(workbook, overview, "Overview", autofilter=False)
        _write_sheet(workbook, trackers, "Trackers", autofilter=True)
        _write_sheet(workbook, findings, "Findings", autofilter=True)
        _write_sheet(workbook, glossary, "Glossary", autofilter=False)

    logger.info(
        f"Findings report written: {output_path} "
        f"({len(findings):,} findings across {trackers.height:,} trackers)"
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
        sheet.write(0, index, _HEADERS.get(column, column), header_format)
        width = _COLUMN_WIDTHS.get(column, max(12, len(column) + 2))
        wraps = column in {"message", "what_it_means_and_what_to_do"}
        sheet.set_column(index, index, width, wrap_format if wraps else None)

    for row_index, row in enumerate(frame.iter_rows(), start=1):
        for column_index, value in enumerate(row):
            if value is None:
                continue
            if isinstance(value, datetime):
                sheet.write_datetime(row_index, column_index, value, date_format)
            elif isinstance(value, bool):
                # Before the int branch: bool is a subclass of int, so a
                # "Processed fully?" column would otherwise read 1 and 0.
                sheet.write_string(row_index, column_index, "yes" if value else "NO")
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
