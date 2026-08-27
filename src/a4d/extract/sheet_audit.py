"""Report the sheets a workbook holds that the pipeline never opens.

Sheet selection runs before any finding could be raised. ``find_month_sheets``
keeps a name only if it *starts with* a capitalised month abbreviation, and
:func:`a4d.extract.patient.read_all_patient_sheets` matches the static sheets by
exact string. A sheet neither rule selects is skipped in total silence -- which
is how ``Annual_2025`` in the 2026 Vietnam National Children Hospital tracker
came to hold the only annual screening data that clinic has for 2025 (26 kidney
function tests, 21 eye exams, 21 blood-pressure pairs) with nothing anywhere
saying it was never read.

Two things close that gap, and they are deliberately different in kind:

* :func:`unopened_sheets` lists every unselected sheet for the operational log.
  A list, not a finding -- 517 of the 255-tracker corpus's sheets are unopened
  and 499 of them are ``Lookup List``/``Inventory``/``INV`` and their spelling
  variants, which are genuinely not tracker data. Recording them all keeps the
  question answerable without a recogniser deciding which names look important,
  because a recogniser can only ever match names somebody already thought of.
* :func:`audit_workbook_sheets` asserts that the sheets a tracker *should* hold
  are present, and reports a finding when one is not. The assertion runs on
  what is expected rather than on what an odd name might mean, so it has no
  such blind spot -- an unopened sheet named anything at all still surfaces,
  because the sheet it should have been is reported missing.
"""

from __future__ import annotations

import calendar
from typing import Protocol

from loguru import logger

from a4d.extract.common import find_month_sheets
from a4d.findings import report_finding

MONTH_ABBRS: tuple[str, ...] = tuple(calendar.month_abbr)[1:]

# The static sheets the pipeline reads, and the first tracker year in which the
# template carried them. Measured across the 255-tracker corpus rather than
# declared: no tracker before 2022 has a Patient List (0 of 62) and every one
# from 2022 on does (145 of 145); no tracker before 2024 has an Annual sheet
# (0 of 122) and every one from 2024 on does (132 of 133 -- the exception is
# the case this module exists to report). Without these years the check would
# demand an Annual sheet of a 2017 tracker, which never had one.
STATIC_SHEET_INTRODUCED: dict[str, int] = {
    "Patient List": 2022,
    "Annual": 2024,
}


class _HasSheetnames(Protocol):
    """The only part of an openpyxl workbook this module needs."""

    @property
    def sheetnames(self) -> list[str]: ...


def unopened_sheets(workbook: _HasSheetnames) -> list[str]:
    """Sheet names in ``workbook`` that no extraction code path opens.

    Returns them in workbook order. Mirrors the selection rules rather than
    re-stating them: whatever ``find_month_sheets`` and the static-sheet names
    leave behind is, by definition, never read.
    """
    selected = set(find_month_sheets(workbook)) | set(STATIC_SHEET_INTRODUCED)
    return [name for name in workbook.sheetnames if name not in selected]


def log_unopened_sheets(workbook: _HasSheetnames, tracker_name: str) -> list[str]:
    """Record every unopened sheet on the operational log, and return them.

    The logs table answers "what did the pipeline do"; "these sheets existed
    and I did not open them" is exactly that. Keeping it out of the findings
    table is deliberate -- the findings table is what A4D staff work from, and
    499 rows of ``Lookup List`` would bury the defects that need acting on.
    """
    unopened = unopened_sheets(workbook)
    if unopened:
        logger.info(
            f"{tracker_name}: {len(unopened)} sheet(s) not opened by any code path: "
            f"{', '.join(unopened)}"
        )
    return unopened


def _month_numbers(month_sheets: list[str]) -> list[int]:
    """Month numbers behind the selected month-sheet names, sorted and unique."""
    numbers = set()
    for name in month_sheets:
        prefix = name[:3]
        if prefix in MONTH_ABBRS:
            numbers.add(MONTH_ABBRS.index(prefix) + 1)
    return sorted(numbers)


def _report_month_gaps(months: list[int], is_year_complete: bool) -> None:
    """Report months absent from within the tracker's own range, and an early stop.

    Deliberately not "all twelve months must be present": 31 of the corpus's
    255 trackers start after January because the clinic joined the programme
    mid-year, and reporting those would be 31 false alarms against the one real
    gap (2017 Mahosot, which has Feb17 then Apr17).
    """
    missing = [n for n in range(months[0], months[-1] + 1) if n not in months]
    if missing:
        names = ", ".join(calendar.month_abbr[n] for n in missing)
        report_finding(
            error_code="month_sheet_missing",
            message=(
                f"The workbook has month sheets for "
                f"{calendar.month_abbr[months[0]]} through "
                f"{calendar.month_abbr[months[-1]]} but none for {names}, so no data "
                f"was read for that month. Add the missing sheet, or confirm the "
                f"clinic recorded nothing that month."
            ),
            stage="extract",
            function_name="audit_workbook_sheets",
        )

    if is_year_complete and months[-1] < 12:
        report_finding(
            error_code="month_sheets_end_early",
            message=(
                f"The tracker's last month sheet is "
                f"{calendar.month_abbr[months[-1]]}, but its year is over, so no data "
                f"exists for the rest of it. Confirm the clinic stopped reporting "
                f"rather than the sheets being missing."
            ),
            stage="extract",
            function_name="audit_workbook_sheets",
        )


def _report_missing_static_sheets(present: set[str], unopened: list[str], year: int) -> None:
    """Report a static sheet the tracker's year expects but the workbook lacks.

    Where an unopened sheet's name starts with the expected one -- ``Annual_2025``
    for ``Annual`` -- it is named in the message. That is what makes the finding
    actionable: the data is in the workbook, under a name the pipeline's exact
    match cannot see, and renaming the sheet is the fix.
    """
    for sheet, introduced in STATIC_SHEET_INTRODUCED.items():
        if year < introduced or sheet in present:
            continue
        candidates = [name for name in unopened if name.startswith(sheet)]
        if candidates:
            hint = (
                f" The workbook does hold {', '.join(repr(c) for c in candidates)}, "
                f"which nothing reads because the pipeline looks for the exact name "
                f"'{sheet}'. Rename the one covering this tracker's own year "
                f"({year}) to '{sheet}'. If another of them holds a different "
                f"year's data, that data belongs in that year's tracker -- it is "
                f"not read from this workbook and no report will show it."
            )
        else:
            hint = (
                f" Every tracker from {introduced} on carries this sheet; add it, or "
                f"confirm the clinic does not use it."
            )
        report_finding(
            error_code="static_sheet_missing",
            message=(
                f"The workbook has no '{sheet}' sheet, so none of the data that "
                f"sheet holds reached the output.{hint}"
            ),
            sheet_name=sheet,
            stage="extract",
            function_name="audit_workbook_sheets",
        )


def audit_workbook_sheets(workbook: _HasSheetnames, year: int, *, is_year_complete: bool) -> None:
    """Report every sheet a tracker of this year should have and does not.

    Args:
        workbook: The tracker's workbook.
        year: The tracker year, as resolved from its sheet names or filename.
        is_year_complete: Whether ``year`` has finished. An in-progress year
            legitimately stops at the current month -- every 2026 tracker in the
            corpus does -- so the early-stop check only applies once it is over.
    """
    months = _month_numbers(find_month_sheets(workbook))
    if months:
        _report_month_gaps(months, is_year_complete)

    _report_missing_static_sheets(
        present=set(workbook.sheetnames),
        unopened=unopened_sheets(workbook),
        year=year,
    )
