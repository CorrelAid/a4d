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

from collections.abc import Iterable, Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import polars as pl
from loguru import logger
from pydantic import BaseModel, Field, field_validator, model_validator

from a4d.extract.common import extract_tracker_month
from a4d.logging import file_logger

Arm = Literal["patient", "product"]

# Error code taxonomy. Every finding carries one, so the table can be filtered
# by kind of problem. Codes for things that are not findings -- critical_abort,
# which is any unhandled exception with a traceback -- stay in the operational
# log and are deliberately absent here.
ErrorCode = Literal[
    # --- the workbook's structure is wrong ---
    "blank_header_with_data",
    "tracker_layout_changed",
    "duplicate_source_columns",
    "unrecognised_column",
    "sheet_skipped",
    "month_sheet_missing",
    "month_sheets_end_early",
    "static_sheet_missing",
    "static_sheet_duplicate_id",
    "empty_product_data",
    "product_section_not_found",
    # --- the patient cannot be identified ---
    "excel_error_patient_id",
    "missing_required_field",
    "patient_id_unrepairable",
    # --- a recorded value contradicts the workbook itself ---
    "source_formula_error",
    "glucose_unit_swapped",
    "glucose_unit_suspect",
    "balance_reconciliation",
    "negative_stock_balance",
    "released_units_without_recipient",
    "released_units_to_unknown_patient",
    "product_not_in_catalogue",
    "entry_date_outside_sheet_month",
    "entry_date_outside_tracker_year",
    "age_negative_from_dob",
    "diagnosis_age_negative_from_dob",
    # --- the pipeline published a value the workbook did not state ---
    "typo_rescued",
    "date_recovered_from_text",
    "date_multiple_in_cell",
    "date_year_inferred",
    "buddhist_era_converted",
    "age_derived_from_dob",
    "age_corrected_from_dob",
    "patient_id_recovered",
    "testing_frequency_averaged",
    # --- the cell was unusable and its value is gone ---
    "type_conversion",
    "implausible_era_date",
    "date_beyond_tracker_year",
    "value_out_of_range",
    "value_not_in_allowed_list",
    "blood_pressure_unparseable",
    "source_row_not_in_output",
]

FindingScope = Literal[
    "tracker",
    "sheet",
    "sheet_column",
    "tracker_column",
    "tracker_value",
    "sheet_value",
    "patient",
    "row",
]

# What one row of the findings table counts, derived from the error code the
# same way the category is. Two things depend on it.
#
# First, counts become comparable. ``validate_allowed_values`` iterates
# ``unique()``, so it emits one finding per *distinct* bad value per tracker:
# 1,170 province findings across 124 trackers, against 26,124 cleaned rows
# carrying the ``Undefined`` province sentinel in those same trackers.
# ``type_conversion`` is per *row* -- 3,579 findings against 3,692
# ``hba1c_baseline`` sentinels. Both emitters are right; the table could not
# tell them apart, so the report's Summary sheet ranked trackers by a count
# that weighted one 22x above the other.
#
# Second, a blank ``sheet_name`` becomes readable. It used to mean either
# "this finding is about the whole workbook" or "this finding is about a sheet
# and we lost which one", and that ambiguity is what kept 102,967 findings
# with no sheet invisible. Scopes in :data:`SCOPES_INSIDE_A_SHEET` must name
# one; the rest must not.
#
# Kept exhaustive over ErrorCode by a test.
FINDING_SCOPE: dict[ErrorCode, FindingScope] = {
    # The workbook as a whole. These have no sheet to name because the finding
    # is that a sheet is absent, or that no sheet held what was looked for.
    "empty_product_data": "tracker",
    "month_sheet_missing": "tracker",
    "month_sheets_end_early": "tracker",
    # One sheet.
    "sheet_skipped": "sheet",
    "static_sheet_missing": "sheet",
    "static_sheet_duplicate_id": "sheet",
    "product_section_not_found": "sheet",
    "released_units_without_recipient": "sheet",
    "duplicate_source_columns": "sheet",
    # One column of one sheet.
    "blank_header_with_data": "sheet_column",
    "unrecognised_column": "sheet_column",
    # One column across every month sheet of the tracker, so no one sheet owns
    # it. These are aggregates by construction: the emitter has already looked
    # at the whole column before deciding there is anything to say.
    "tracker_layout_changed": "tracker_column",
    "glucose_unit_swapped": "tracker_column",
    "blood_pressure_unparseable": "tracker_column",
    "testing_frequency_averaged": "tracker_column",
    # One patient, deduplicated across the months they appear in. A diagnosis
    # date before a date of birth is a property of the patient; saying it once
    # per monthly row would say it 58 times for 8 patients.
    "diagnosis_age_negative_from_dob": "patient",
    # One distinct offending value, deduplicated across every row carrying it
    # -- the right call for a column where one misspelling repeats down a
    # sheet. Which extent owns the deduplication is the emitter's choice and
    # has to be stated: a province spelled wrong is reported once for the
    # whole workbook, an unknown product once per sheet, because correcting
    # the latter is a per-sheet edit.
    "value_not_in_allowed_list": "tracker_value",
    "product_not_in_catalogue": "sheet_value",
    # One source row.
    "excel_error_patient_id": "row",
    "missing_required_field": "row",
    "patient_id_unrepairable": "row",
    "patient_id_recovered": "row",
    "source_formula_error": "row",
    "glucose_unit_suspect": "row",
    "balance_reconciliation": "row",
    "negative_stock_balance": "row",
    "released_units_to_unknown_patient": "row",
    "entry_date_outside_sheet_month": "row",
    "entry_date_outside_tracker_year": "row",
    "age_negative_from_dob": "row",
    "typo_rescued": "row",
    "date_recovered_from_text": "row",
    "date_multiple_in_cell": "row",
    "date_year_inferred": "row",
    "buddhist_era_converted": "row",
    "age_derived_from_dob": "row",
    "age_corrected_from_dob": "row",
    "type_conversion": "row",
    "implausible_era_date": "row",
    "date_beyond_tracker_year": "row",
    "value_out_of_range": "row",
    "source_row_not_in_output": "row",
}

# The scopes that sit inside one sheet, and so must name it. Everything else
# spans the workbook and must leave ``sheet_name`` blank, so the blank is a
# statement rather than a loss.
SCOPES_INSIDE_A_SHEET: frozenset[str] = frozenset({"sheet", "sheet_column", "sheet_value", "row"})


FindingCategory = Literal["fix_workbook", "recovered", "data_lost"]

# What the operator can do about a finding. Derived from the error code rather
# than passed at each call site, so the same code cannot be filed two ways in
# two modules. Kept exhaustive over ErrorCode by a test.
#
# Where a value is both lost and correctable at the clinic, ``fix_workbook``
# wins: the workbook exists to tell A4D staff which files to correct, and
# filing a repairable defect as "gone" buries the ones that matter most. So
# ``data_lost`` means specifically that nobody can get the value back --
# unreadable contents, not a wrong entry someone could retype.
FINDING_CATEGORY: dict[ErrorCode, FindingCategory] = {
    "blank_header_with_data": "fix_workbook",
    "tracker_layout_changed": "fix_workbook",
    "duplicate_source_columns": "fix_workbook",
    "unrecognised_column": "fix_workbook",
    "sheet_skipped": "fix_workbook",
    "month_sheet_missing": "fix_workbook",
    "month_sheets_end_early": "fix_workbook",
    "static_sheet_missing": "fix_workbook",
    "static_sheet_duplicate_id": "fix_workbook",
    "empty_product_data": "fix_workbook",
    "product_section_not_found": "fix_workbook",
    "excel_error_patient_id": "fix_workbook",
    "missing_required_field": "fix_workbook",
    "patient_id_unrepairable": "fix_workbook",
    "source_formula_error": "fix_workbook",
    "glucose_unit_swapped": "fix_workbook",
    "glucose_unit_suspect": "fix_workbook",
    "balance_reconciliation": "fix_workbook",
    "negative_stock_balance": "fix_workbook",
    "released_units_without_recipient": "fix_workbook",
    "released_units_to_unknown_patient": "fix_workbook",
    "product_not_in_catalogue": "fix_workbook",
    "entry_date_outside_sheet_month": "fix_workbook",
    "entry_date_outside_tracker_year": "fix_workbook",
    "age_negative_from_dob": "fix_workbook",
    "diagnosis_age_negative_from_dob": "fix_workbook",
    # The pipeline published a value the workbook did not state. Nothing to do,
    # but the record stays auditable because a recovery is still an inference.
    "typo_rescued": "recovered",
    "date_recovered_from_text": "recovered",
    "date_multiple_in_cell": "recovered",
    "date_year_inferred": "recovered",
    "buddhist_era_converted": "recovered",
    "age_derived_from_dob": "recovered",
    "age_corrected_from_dob": "recovered",
    "patient_id_recovered": "recovered",
    "testing_frequency_averaged": "recovered",
    # The cell could not be read and nobody can recover what it held.
    "type_conversion": "data_lost",
    "implausible_era_date": "data_lost",
    "date_beyond_tracker_year": "data_lost",
    "value_out_of_range": "data_lost",
    "value_not_in_allowed_list": "data_lost",
    "blood_pressure_unparseable": "data_lost",
    "source_row_not_in_output": "data_lost",
}

# What each code means and what to do about it, written for whoever opens the
# workbook -- an A4D staff member correcting a tracker, not a Python developer.
# It is a dict rather than comments beside ErrorCode because the report's
# glossary sheet is generated from it; a glossary transcribed by hand drifts
# from the taxonomy the moment a code is added. Kept exhaustive in both
# directions by a test, exactly as FINDING_CATEGORY is.
FINDING_GLOSSARY: dict[ErrorCode, str] = {
    "blank_header_with_data": (
        "A column holds values but its header cell is empty, and no other month "
        "sheet labels the same column, so nothing says what the values mean and "
        "the column is dropped. Type the column's name into the header row."
    ),
    "tracker_layout_changed": (
        "A column means different things in different month sheets of this "
        "workbook. A tracker covers one clinic-year and should keep one layout "
        "throughout; make the header match the other sheets."
    ),
    "duplicate_source_columns": (
        "Several columns in the sheet map to the same field, so their values are "
        "comma-joined in column order (empty cells skipped) rather than dropped. "
        "Sometimes intended, as with the five complication-screening columns; "
        "check the joined value is what the column should hold."
    ),
    "unrecognised_column": (
        "A column header in this tracker matches nothing in the reference column "
        "list, so the column is kept under its own name and reaches no mapped "
        "field. Either it is a new column the reference data should learn, or "
        "the header is misspelled."
    ),
    "sheet_skipped": (
        "A sheet, or one section of it, could not be read and was skipped; the "
        "rest of the workbook still processed. Usually a sheet with no header "
        "row, no data, no patient ID column, or a name no month can be read "
        "from. The named sheet is where to look."
    ),
    "month_sheet_missing": (
        "A month sheet is missing from the middle of this tracker's own range, "
        "so no data was read for that month. Add the sheet, or confirm the "
        "clinic recorded nothing that month. A tracker that simply starts late "
        "because the clinic joined mid-year is not reported here."
    ),
    "month_sheets_end_early": (
        "The tracker's year is over but its month sheets stop before December, "
        "so no data exists for the rest of the year. Confirm the clinic stopped "
        "reporting rather than the sheets being missing."
    ),
    "static_sheet_missing": (
        "The workbook has no Patient List or Annual sheet, although every "
        "tracker from that sheet's introduction year on carries one, so none of "
        "the data it holds reached the output. Where the workbook holds the "
        "sheet under a different name -- 'Annual_2025' rather than 'Annual' -- "
        "the message names it, and renaming it is the fix."
    ),
    "static_sheet_duplicate_id": (
        "The Patient List or Annual sheet lists the same patient more than once "
        "under IDs that differ only by a hyphen or a transfer-clinic suffix. The "
        "first entry was kept; merge the rows so one patient has one entry."
    ),
    "empty_product_data": (
        "No product/stock section was found in any sheet of this workbook, so the "
        "tracker contributes no stock data at all. Expected for trackers that "
        "predate stock tracking; otherwise the INV section is missing."
    ),
    "product_section_not_found": (
        "This sheet has a product/stock area in the other months but none here, "
        "so the sheet's stock movements are skipped. Copy the INV block in from "
        "a month that has it."
    ),
    "excel_error_patient_id": (
        "The patient ID cell holds a broken formula (#REF!), so the row cannot be "
        "attributed to anyone and its measurements are discarded. Repoint the "
        "formula, or type the ID in directly."
    ),
    "missing_required_field": (
        "A row has no patient ID, so it cannot be attributed to anyone and is "
        "excluded. Fill the ID in, or delete the row if it was started by "
        "accident."
    ),
    "patient_id_unrepairable": (
        "The patient ID does not match the XX_YY### template and no other row in "
        "this tracker spells it closely enough to match, so the row publishes "
        "under 'Undefined' and that patient's month is not attributed to them. "
        "This is the costliest defect a tracker can carry -- correct the ID and "
        "the whole history comes back."
    ),
    "source_formula_error": (
        "The workbook's own formula returned an error (#NUM!, #DIV/0!) because a "
        "cell it depends on was never filled in. Fill the input cell; the formula "
        "will then compute."
    ),
    "glucose_unit_swapped": (
        "A whole column labelled mg/dL holds readings in mmol/L. The pipeline has "
        "moved and rescaled them, but the column header should be corrected so it "
        "stops disagreeing with its own values. Reported once per column."
    ),
    "glucose_unit_suspect": (
        "A single reading sits in the range the other unit's values occupy. It is "
        "published as recorded, because a genuinely severe reading looks the same "
        "-- check the patient's record and confirm the number."
    ),
    "balance_reconciliation": (
        "The stock movements recorded for this product do not add up to the "
        "closing balance the tracker itself states. Either a receipt/release row "
        "is missing or the balance was typed over."
    ),
    "negative_stock_balance": (
        "The running stock balance for this product goes below zero, which no "
        "physical stock can do. Usually a release recorded without its matching "
        "receipt, or a quantity entered in the wrong column."
    ),
    "released_units_without_recipient": (
        "Units were recorded as released but no recipient is named beside them, "
        "so the stock left the clinic with no record of where it went. Fill in "
        "the 'released to' cell."
    ),
    "released_units_to_unknown_patient": (
        "Units were recorded as released to a patient ID that appears nowhere "
        "in this tracker's own patient sheets, so the stock left the clinic "
        "against a patient the workbook does not know. Either the ID is "
        "mistyped on the stock row, or the patient is missing from the "
        "Patient List."
    ),
    "product_not_in_catalogue": (
        "The product name in this row matches nothing in the product reference "
        "list, so the row cannot be grouped with the same product elsewhere. "
        "Either a new product the reference data should learn, or a misspelling."
    ),
    "entry_date_outside_sheet_month": (
        "The entry date on this stock row falls outside the month its own sheet "
        "covers. Either the date is mistyped or the row was entered on the wrong "
        "month's sheet."
    ),
    "entry_date_outside_tracker_year": (
        "The entry date on this stock row falls outside the tracker's own year "
        "-- either later than the year allows, or more than five years before "
        "it, which is typically a placeholder Excel serial. Retype the date."
    ),
    "age_negative_from_dob": (
        "The age calculated from this patient's date of birth is negative, so the "
        "date of birth is after the visit. One of the two dates is wrong; check "
        "them against the patient's record."
    ),
    "diagnosis_age_negative_from_dob": (
        "This patient's diagnosis date falls before their date of birth, so "
        "the age at diagnosis cannot be calculated. One of the two dates is "
        "wrong; check them against the patient's record. Any diagnosis age "
        "already typed into the workbook is published unchanged -- it is the "
        "two dates that contradict each other, not the age."
    ),
    "typo_rescued": (
        "A date was written with a known misspelling and the correction was "
        "applied before reading it, so nothing was lost. Correcting the spelling "
        "in the workbook removes the guess."
    ),
    "date_recovered_from_text": (
        "A date was read out of a free-text note rather than from a date cell. The "
        "note is kept alongside it so the reading can be checked; entering the date "
        "in its own cell removes the inference."
    ),
    "date_multiple_in_cell": (
        "The cell named more than one date and the first was published. If a "
        "different one was meant, split them into separate rows or cells."
    ),
    "date_year_inferred": (
        "The cell gave a day and month but no year, so the tracker's own year was "
        "used. That is the one part of the published date the workbook does not "
        "state -- write the year out to be sure it is right."
    ),
    "buddhist_era_converted": (
        "A Buddhist-era year (BE = CE + 543) was converted to Gregorian. This is "
        "the calendar the clinic uses, not a mistake; no action needed unless the "
        "converted date looks wrong."
    ),
    "age_derived_from_dob": (
        "The patient's age cell was empty, so the age was calculated from their "
        "date of birth and published. Nothing is lost, but the workbook should "
        "carry the age so the pipeline does not have to derive it."
    ),
    "age_corrected_from_dob": (
        "The age in the workbook disagrees with the age its own date of birth "
        "gives, so the calculated age was published instead. Correct whichever of "
        "the two is wrong."
    ),
    "patient_id_recovered": (
        "The patient ID does not match the XX_YY### template, but another row in "
        "this tracker spells the same ID correctly, so the row was attributed to "
        "that patient. Correct the spelling so the match is not inferred."
    ),
    "testing_frequency_averaged": (
        "The testing frequency was written as a range (for example '3-4') rather "
        "than a single number, so the mean was published. Record one number."
    ),
    "type_conversion": (
        "The cell's contents could not be read as the kind of value the column "
        "holds -- text where a number belongs, an unparseable date -- so the "
        "value is lost. Retype it in the column's own format."
    ),
    "implausible_era_date": (
        "The date cell holds a year that is neither Gregorian nor this tracker's "
        "Buddhist-era year -- usually a corrupted Excel serial. The day and month "
        "are normally right; retype the whole date."
    ),
    "date_beyond_tracker_year": (
        "The date is later than the tracker's own year allows, so it cannot be a "
        "date this workbook recorded and the cell is dropped. Usually a mistyped "
        "year."
    ),
    "value_out_of_range": (
        "The value falls outside the range the column allows -- a height, weight "
        "or glucose reading no patient could have -- so it is dropped. Often a "
        "reading typed into the wrong column, or a unit mix-up."
    ),
    "value_not_in_allowed_list": (
        "The cell holds something the column does not allow -- a free-text note "
        "in a Y/N column, or a spelling not on the list -- so it is dropped. Use "
        "one of the column's own values."
    ),
    "blood_pressure_unparseable": (
        "The blood pressure cell is not in systolic/diastolic form (for example "
        "'120/80'), so neither number could be read and both are lost. Retype it "
        "with a slash."
    ),
    "source_row_not_in_output": (
        "A row present in the source workbook reached no output row, or an "
        "output row corresponds to no source row. Emitted only by the "
        "source-vs-output validation tool, which is run by hand and is not part "
        "of a pipeline run."
    ),
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

    @model_validator(mode="after")
    def _sheet_name_agrees_with_the_scope(self) -> Finding:
        """A finding inside a sheet names it; one about the workbook does not.

        Raising rather than warning, for the reason ``file_name`` does: the
        gap this closes was 102,967 findings deep and stayed invisible for
        two months precisely because a missing sheet name looked exactly like
        a finding that legitimately had none. A test only catches the emit
        sites a test exercises; this catches all of them.
        """
        inside = FINDING_SCOPE[self.error_code] in SCOPES_INSIDE_A_SHEET
        named = bool(self.sheet_name.strip())
        if inside and not named:
            raise ValueError(
                f"{self.error_code} is scoped to {FINDING_SCOPE[self.error_code]!r} "
                "but carries no sheet_name. Pass the sheet the finding came from, "
                "or give the code a workbook-wide scope in FINDING_SCOPE."
            )
        if not inside and named:
            raise ValueError(
                f"{self.error_code} is scoped to {FINDING_SCOPE[self.error_code]!r}, "
                f"which spans the workbook, but carries sheet_name={self.sheet_name!r}. "
                "Drop the sheet, or give the code a sheet-level scope."
            )
        return self

    @property
    def category(self) -> FindingCategory:
        """What the operator can do about it, derived from the error code."""
        return FINDING_CATEGORY[self.error_code]

    @property
    def scope(self) -> FindingScope:
        """What one row of the findings table counts, derived from the code."""
        return FINDING_SCOPE[self.error_code]


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
        """Findings as a DataFrame, with the derived fields materialised."""
        return findings_dataframe(self.findings)


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
    "scope": pl.Categorical,
    "stage": pl.Categorical,
    "function_name": pl.Categorical,
    "tracker_year": pl.Int32,
    "tracker_month": pl.Int32,
    "timestamp": pl.Datetime,
}


def findings_dataframe(findings: list[Finding]) -> pl.DataFrame:
    """Findings as a DataFrame, with every derived field materialised.

    The one place the derived fields are written out. The published table used
    to build its own record dicts, which is how ``scope`` shipped as an
    all-null column on its first run: the derivation existed twice and only
    one copy learned about the new field.

    Args:
        findings: The findings to materialise

    Returns:
        A frame with exactly :data:`FINDINGS_SCHEMA`'s columns and types
    """
    if not findings:
        return pl.DataFrame(schema=FINDINGS_SCHEMA)
    records = [
        {**finding.model_dump(), "category": finding.category, "scope": finding.scope}
        for finding in findings
    ]
    return pl.DataFrame(records, schema=FINDINGS_SCHEMA)


_current: ContextVar[FindingCollector | None] = ContextVar("a4d_findings", default=None)
_current_tracker: ContextVar[dict[str, Any] | None] = ContextVar("a4d_tracker", default=None)
_discarding: ContextVar[bool] = ContextVar("a4d_findings_discarded", default=False)


def current_findings() -> FindingCollector | None:
    """The collector bound to this context, or None outside any."""
    return _current.get()


# The cleaned frames name the same three things differently: the patient arm
# carries sheet_name/tracker_month/tracker_year, the product arm
# product_sheet_name/product_table_month/product_table_year. Reading both here
# rather than at each of the ~34 emit sites is what keeps a new emitter from
# quietly filling neither.
_SHEET_COLUMNS = ("sheet_name", "product_sheet_name")
_MONTH_COLUMNS = ("tracker_month", "product_table_month")
_YEAR_COLUMNS = ("tracker_year", "product_table_year")

# Every column :func:`sheet_context` reads. An emitter that narrows a frame
# with ``.select(...)`` before iterating it has to keep these, or the place is
# gone by the time the finding is built.
PLACE_COLUMNS: tuple[str, ...] = _SHEET_COLUMNS + _MONTH_COLUMNS + _YEAR_COLUMNS


def present_place_columns(columns: Iterable[str]) -> list[str]:
    """The place columns a frame actually has, for widening a ``select``.

    Args:
        columns: The frame's column names

    Returns:
        The subset of :data:`PLACE_COLUMNS` present, in declaration order
    """
    have = set(columns)
    return [c for c in PLACE_COLUMNS if c in have]


def sheet_context(row: Mapping[str, Any]) -> dict[str, Any]:
    """Where in the workbook a row-scoped finding came from.

    Splat into :func:`report_finding` -- ``**sheet_context(row)`` -- so a call
    site names the place once instead of copying two ``row.get`` calls that
    then have to know which arm's column names it is looking at.

    Args:
        row: One row of a cleaned frame, as ``iter_rows(named=True)`` yields it

    Returns:
        ``sheet_name``, and ``tracker_month`` / ``tracker_year`` where the
        frame carries them. Each is omitted rather than passed as None, so a
        frame without the column leaves the tracker context's value standing.
    """
    sheet = next((row[c] for c in _SHEET_COLUMNS if row.get(c) is not None), "")
    month = next((row[c] for c in _MONTH_COLUMNS if row.get(c) is not None), None)
    year = next((row[c] for c in _YEAR_COLUMNS if row.get(c) is not None), None)
    place: dict[str, Any] = {"sheet_name": str(sheet)}
    if month is not None:
        place["tracker_month"] = int(month)
    # The year normally rides on the tracker context, but the table stage runs
    # across every tracker at once under findings_collected, where there is no
    # one tracker to have opened a context for -- so the row is the only source.
    if year is not None:
        place["tracker_year"] = int(year)
    return place


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
    # Bound even when file_name is None, so `arm` takes effect on its own. It
    # used to be bound only alongside a file name, which silently filed every
    # finding from a caller that named its own workbooks -- the product table
    # stage -- under the default arm instead of the one it asked for.
    # A None file_name still raises at emit time if the call does not carry one.
    context_token = _current_tracker.set(
        {"file_name": file_name, "arm": arm, "tracker_year": None, "tracker_month": None}
    )
    try:
        yield collector
    finally:
        _current.reset(token)
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
    tracker_month: int | None = None,
    tracker_year: int | None = None,
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

    # A sheet named "Jan24" states its own month, and every extract-stage
    # emitter has the sheet but not the frame that would carry the month --
    # so derive it once here rather than at each site. Static sheets
    # ("Patient List", "Annual") name no month and correctly keep None.
    if tracker_month is None and sheet_name.strip():
        try:
            tracker_month = extract_tracker_month(sheet_name)
        except ValueError:
            tracker_month = None

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
        tracker_year=tracker_year if tracker_year is not None else context.get("tracker_year"),
        # The year is constant for a whole tracker and rides on the context;
        # the month varies sheet by sheet, so a per-row emitter passes it.
        tracker_month=tracker_month if tracker_month is not None else context.get("tracker_month"),
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
        # Bound explicitly rather than left to file_logger's per-tracker
        # contextualize: the month is per sheet, so the context's value would
        # overwrite it with the tracker-wide one on the way back out of the
        # log-driven rebuild.
        tracker_year=finding.tracker_year,
        tracker_month=finding.tracker_month,
    ).log(_LEVEL_BY_CATEGORY[finding.category], message)
