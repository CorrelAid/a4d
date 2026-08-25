"""The single channel for data-quality findings about source workbooks.

A *finding* is something wrong with a tracker workbook: a column the pipeline
could not find, a cell it could not parse, a date it recovered out of a
clinical note. It is written for the operator and for A4D staff, who act on it
by correcting the workbook.

That is a different job from *operational logging* (``a4d.logging``), which
records what the pipeline did -- timings, progress, exceptions and tracebacks --
for a developer debugging a run. Operational lines go through ``logger`` as
usual and are not findings.

Every finding is emitted through :func:`report_finding`, which appends it to
the collector bound to the current context *and* writes it to that tracker's
log stream. There is deliberately no way to do one without the other: the two
used to be separate systems whose outputs could not even be joined, because
one wrote the bare tracker stem as ``file_name`` and the other the
``_patient``/``_product``-suffixed name.

A finding emitted with no context bound raises. Emitting into the void is
always a bug -- either a call site outside the tracker scope, or a missing
context -- and a silent drop is how findings went missing before.

Example:
    >>> with tracker_context("2024_Penang", "patient", output_root) as findings:
    ...     report_finding(
    ...         patient_id="MY_QD001",
    ...         column="age",
    ...         original_value="abc",
    ...         message="Could not convert 'abc' to Int32",
    ...         error_code="type_conversion",
    ...         function_name="safe_convert_column",
    ...     )
    >>> findings.summary()
    {'type_conversion': 1}
"""

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl
from loguru import logger
from pydantic import BaseModel, Field, field_validator

from a4d.logging import file_logger

Arm = Literal["patient", "product"]

# Error code taxonomy. Every finding carries one, so the table can be filtered
# by kind of problem. Codes for things that are not findings -- critical_abort,
# which is any unhandled exception with a traceback -- stay in the operational
# log and are deliberately absent here.
ErrorCode = Literal[
    # --- the workbook is wrong ---
    "blank_header_with_data",  # A column holds data under an empty header cell, so the
    # pipeline cannot know what the values mean
    "tracker_layout_changed",  # Sheet structure differs from the template the pipeline reads
    "duplicate_source_columns",  # Two columns in the sheet map to the same field
    "missing_column",  # A column the template defines is absent from this tracker
    "invalid_tracker",  # Tracker-level defect: unreadable sheet, missing section
    "empty_product_data",  # A product sheet exists but holds no stock rows
    "excel_error_patient_id",  # A row's patient ID cell holds a broken formula (#REF!), so the
    # patient cannot be identified and the row's measurements are dropped
    "missing_required_field",  # Critical field (patient_id, status) missing, row excluded
    "source_formula_error",  # The tracker's own formula errored (#NUM!, #DIV/0!) -- an input
    # it depended on was never recorded, so no value could be computed
    "glucose_unit_swapped",  # A whole column labelled mg/dL holds mmol/L readings; values
    # moved to the mmol column and rescaled. Reported once per column, not per row
    "glucose_unit_suspect",  # A single reading sits where the other unit's values land;
    # kept as recorded, because a severe hypoglycaemic reading is indistinguishable
    "balance_reconciliation",  # Recomputed closing stock disagrees with the balance the
    # tracker itself recorded -- the transactions and the recorded total do not add up
    # --- the pipeline recovered it, informational ---
    "typo_rescued",  # Known source-data typo substituted before parsing
    "date_recovered_from_text",  # A date was read out of a clinical note rather than from a
    # date-shaped cell -- carries the note, so the extraction stays auditable
    "date_multiple_in_cell",  # The cell named several dates and the first was published
    "date_year_inferred",  # The cell named a day and a month but no year, so the tracker's
    # own year was used -- the one component published that the source does not state
    "buddhist_era_converted",  # A Thai clinic's Buddhist-era date (BE = CE + 543) shifted to
    # Gregorian -- the calendar the clinic uses, not an error it made
    # --- a cell was unusable, data lost ---
    "type_conversion",  # Failed to convert type (e.g., "abc" -> int)
    "invalid_value",  # Value outside allowed range or not in allowed list
    "missing_value",  # Required value is missing/NA
    "implausible_era_date",  # A date past the Buddhist-era threshold that is not this
    # tracker's own BE year -- a corrupt Excel serial, so the cell is sentinelled
]

FindingCategory = Literal["fix_workbook", "recovered", "data_lost"]

# What the operator can do about a finding. Derived from the error code rather
# than passed at each call site, so the same code cannot be filed two ways in
# two modules. Kept exhaustive over ErrorCode by a test.
FINDING_CATEGORY: dict[ErrorCode, FindingCategory] = {
    # The workbook is wrong and a human must fix it.
    "blank_header_with_data": "fix_workbook",
    "tracker_layout_changed": "fix_workbook",
    "duplicate_source_columns": "fix_workbook",
    "missing_column": "fix_workbook",
    "invalid_tracker": "fix_workbook",
    "empty_product_data": "fix_workbook",
    "excel_error_patient_id": "fix_workbook",
    "missing_required_field": "fix_workbook",
    "source_formula_error": "fix_workbook",
    "glucose_unit_swapped": "fix_workbook",
    "glucose_unit_suspect": "fix_workbook",
    "balance_reconciliation": "fix_workbook",
    # The pipeline recovered the value; nothing to do, but the record stays
    # auditable because a recovery is still an inference.
    "typo_rescued": "recovered",
    "date_recovered_from_text": "recovered",
    "date_multiple_in_cell": "recovered",
    "date_year_inferred": "recovered",
    "buddhist_era_converted": "recovered",
    # The cell could not be used and its value is gone from the output.
    "type_conversion": "data_lost",
    "invalid_value": "data_lost",
    "missing_value": "data_lost",
    "implausible_era_date": "data_lost",
}

# A recovery is not a problem, so it does not deserve an operator's attention
# at the same level as a workbook defect.
_LEVEL_BY_CATEGORY: dict[FindingCategory, str] = {
    "fix_workbook": "WARNING",
    "recovered": "INFO",
    "data_lost": "WARNING",
}


class NoFindingContextError(RuntimeError):
    """Raised when a finding is reported with no collector bound.

    Always a bug at the call site: either it runs outside the tracker scope, or
    the scope was never opened. Use :func:`findings_discarded` where dropping
    findings is genuinely intended, so the intent is visible in the source.
    """


class Finding(BaseModel):
    """One data-quality finding about one source workbook.

    Attributes:
        file_name: Bare tracker stem, never blank and never arm-suffixed, so
            the table joins against tracker_metadata and the data tables
        arm: Which pipeline arm found it
        sheet_name: Sheet within the workbook, where the finding has one
        patient_id: Patient the finding concerns ("unknown" if not applicable)
        column: Column the finding concerns
        original_value: The value as the workbook holds it
        message: Human-readable description
        error_code: What kind of problem this is
        stage: Pipeline stage that found it (extract, clean, tables)
        function_name: Python function that emitted it
        tracker_year: Year of the tracker, for filtering
        tracker_month: Month of the sheet, where the finding has one
        timestamp: When it was recorded
    """

    file_name: str
    arm: Arm
    sheet_name: str = ""
    patient_id: str = "unknown"
    column: str = ""
    original_value: str = ""
    message: str
    error_code: ErrorCode
    stage: str = "clean"
    function_name: str = ""
    tracker_year: int | None = None
    tracker_month: int | None = None
    timestamp: datetime = Field(default_factory=datetime.now)

    @field_validator("file_name")
    @classmethod
    def _file_name_is_never_blank(cls, value: str) -> str:
        """A finding nobody can trace to a workbook cannot be acted on."""
        if not value.strip():
            raise ValueError("file_name must name a tracker; a finding cannot be unattributed")
        return value.strip()

    @property
    def category(self) -> FindingCategory:
        """What the operator can do about it, derived from the error code."""
        return FINDING_CATEGORY[self.error_code]


class FindingCollector:
    """Accumulates findings for one tracker (or one validation run).

    Stays the in-run accumulator that feeds the CLI's end-of-run summary, and
    is now also the source of the published findings table.
    """

    def __init__(self) -> None:
        self.findings: list[Finding] = []

    def __len__(self) -> int:
        return len(self.findings)

    def __bool__(self) -> bool:
        return bool(self.findings)

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def summary(self) -> dict[str, int]:
        """Count findings by error code, for the per-run CLI summary."""
        counts: dict[str, int] = {}
        for finding in self.findings:
            counts[finding.error_code] = counts.get(finding.error_code, 0) + 1
        return counts

    def to_dataframe(self) -> pl.DataFrame:
        """Findings as a DataFrame, with the derived category materialised."""
        if not self.findings:
            return pl.DataFrame(schema=FINDINGS_SCHEMA)
        records = [
            {**finding.model_dump(), "category": finding.category} for finding in self.findings
        ]
        return pl.DataFrame(records, schema=FINDINGS_SCHEMA)


# Column order and types of the published table. Declared once so an empty run
# writes the same schema as a full one -- BigQuery reads the parquet's schema,
# so an empty table with inferred types would change the published shape.
FINDINGS_SCHEMA: dict[str, Any] = {
    "file_name": pl.Utf8,
    "arm": pl.Categorical,
    "sheet_name": pl.Utf8,
    "patient_id": pl.Utf8,
    "column": pl.Utf8,
    "original_value": pl.Utf8,
    "message": pl.Utf8,
    "error_code": pl.Categorical,
    "category": pl.Categorical,
    "stage": pl.Categorical,
    "function_name": pl.Categorical,
    "tracker_year": pl.Int32,
    "tracker_month": pl.Int32,
    "timestamp": pl.Datetime,
}


_current: ContextVar[FindingCollector | None] = ContextVar("a4d_findings", default=None)
_current_tracker: ContextVar[dict[str, Any] | None] = ContextVar("a4d_tracker", default=None)
_discarding: ContextVar[bool] = ContextVar("a4d_findings_discarded", default=False)


def current_findings() -> FindingCollector | None:
    """The collector bound to this context, or None outside any."""
    return _current.get()


@contextmanager
def tracker_context(
    tracker_name: str,
    arm: Arm,
    output_root: Path,
    tracker_year: int | None = None,
    tracker_month: int | None = None,
) -> Iterator[FindingCollector]:
    """Open the per-tracker scope: findings collector plus log file.

    Supersedes calling :func:`a4d.logging.file_logger` directly. It takes the
    tracker stem and the arm *separately* rather than a pre-suffixed name: the
    log file keeps the arm in its name so the two arms do not overwrite each
    other, while findings carry the bare stem and the arm as its own field, so
    they join against every other table.

    Args:
        tracker_name: Bare tracker stem, e.g. "2024_Penang"
        arm: Which pipeline arm is running
        output_root: Root output directory (logs land in output_root/logs/)
        tracker_year: Year from the tracker, for filtering
        tracker_month: Month from the sheet, where there is one

    Yields:
        The collector for this tracker, to drain into the tracker's result.
    """
    collector = FindingCollector()
    context = {
        "file_name": tracker_name,
        "arm": arm,
        "tracker_year": tracker_year,
        "tracker_month": tracker_month,
    }
    token = _current.set(collector)
    tracker_token = _current_tracker.set(context)
    try:
        with file_logger(
            f"{tracker_name}_{arm}",
            output_root,
            tracker_year=tracker_year,
            tracker_month=tracker_month,
        ):
            yield collector
    finally:
        _current.reset(token)
        _current_tracker.reset(tracker_token)


@contextmanager
def findings_collected(
    file_name: str | None = None, arm: Arm = "patient"
) -> Iterator[FindingCollector]:
    """Collect findings outside any tracker scope, with no log file.

    For tools that walk a completed run rather than process a tracker -- the
    source-vs-output validators -- and for tests exercising one cleaning step.

    Args:
        file_name: Default attribution for findings emitted inside the block.
            Omit it where each finding names its own workbook; then a finding
            that names none raises, as it does anywhere else.
        arm: Default arm for findings emitted inside the block.
    """
    collector = FindingCollector()
    token = _current.set(collector)
    context_token = None
    if file_name is not None:
        context_token = _current_tracker.set(
            {"file_name": file_name, "arm": arm, "tracker_year": None, "tracker_month": None}
        )
    try:
        yield collector
    finally:
        _current.reset(token)
        if context_token is not None:
            _current_tracker.reset(context_token)


@contextmanager
def findings_discarded() -> Iterator[None]:
    """Throw away findings emitted inside this block.

    For the deliberate sacrificial re-parse in ``validate.common``: it re-runs
    a conversion purely to see what parses, and those findings are about the
    validator's own probe rather than about the workbook. Explicit, so a
    discard is visible in the source rather than being a collector nobody
    passed.

    Findings emitted here are dropped before they are built, so the probe's
    own file name and attribution do not have to be invented to satisfy
    validation that nothing will read.
    """
    token = _discarding.set(True)
    try:
        yield
    finally:
        _discarding.reset(token)


def report_finding(
    *,
    message: str,
    error_code: ErrorCode,
    file_name: str | None = None,
    arm: Arm | None = None,
    patient_id: str = "unknown",
    column: str = "",
    original_value: Any = "",
    sheet_name: str = "",
    stage: str = "clean",
    function_name: str = "",
) -> None:
    """Record one data-quality finding about a source workbook.

    Appends to the collector bound to the current context and writes the same
    finding to that tracker's log stream, so it cannot exist in one and not the
    other.

    ``file_name``, ``arm``, ``tracker_year`` and ``tracker_month`` are taken
    from the enclosing :func:`tracker_context` when it is open; pass
    ``file_name`` and ``arm`` explicitly under :func:`findings_collected`.

    Raises:
        NoFindingContextError: If no context is bound -- the finding would
            otherwise vanish.
        ValueError: If no file name is available from the context or the call.
    """
    if _discarding.get():
        return

    collector = _current.get()
    if collector is None:
        raise NoFindingContextError(
            f"report_finding({error_code!r}) outside a findings context: "
            f"{message!r}. Open tracker_context(...) around the call, or "
            f"findings_discarded() if dropping it is intended."
        )

    context = _current_tracker.get() or {}
    resolved_name = file_name if file_name is not None else context.get("file_name")
    if not resolved_name or not str(resolved_name).strip():
        raise ValueError(
            f"report_finding({error_code!r}) has no file_name: none was passed and "
            f"no tracker context is open. A finding must name the workbook it is about."
        )
    resolved_arm = arm if arm is not None else context.get("arm", "patient")

    finding = Finding(
        file_name=str(resolved_name),
        arm=resolved_arm,
        sheet_name=sheet_name,
        patient_id=patient_id,
        column=column,
        original_value="" if original_value is None else str(original_value),
        message=message,
        error_code=error_code,
        stage=stage,
        function_name=function_name,
        tracker_year=context.get("tracker_year"),
        tracker_month=context.get("tracker_month"),
    )
    collector.add(finding)

    # Every field of the record, so the log stream is a lossless copy of the
    # finding rather than a summary of it: `a4d create tables` rebuilds the
    # findings table from these files when no run is in memory, and ticket
    # 16's per-tracker drill-down reads them directly.
    logger.bind(
        error_code=error_code,
        category=finding.category,
        arm=finding.arm,
        sheet_name=sheet_name,
        column=column,
        patient_id=patient_id,
        original_value=finding.original_value,
        stage=stage,
        emitting_function=function_name,
        finding_file_name=finding.file_name,
    ).log(_LEVEL_BY_CATEGORY[finding.category], message)
