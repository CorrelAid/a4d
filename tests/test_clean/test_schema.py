"""The output shape drops columns; every drop has to be a decision."""

import ast
from pathlib import Path

import pytest

from a4d.clean.schema import UNPUBLISHED_COLUMNS, get_patient_data_schema
from a4d.extract.patient import STATIC_SHEET_SUFFIXES
from a4d.reference.synonyms import load_patient_mapper

SRC = Path(__file__).resolve().parents[2] / "src" / "a4d"


@pytest.fixture(scope="module")
def recognised() -> set[str]:
    return set(load_patient_mapper().synonyms)


def test_every_recognised_column_is_published_or_declared(recognised):
    """A column the reference list names must reach the output or say why not.

    This is the check the pipeline lacked: the reference list and the output
    shape are two hand-maintained lists, and a column can sit in the first
    without the second noticing. Ticket 75's two screening columns were read
    out of every workbook and dropped here for exactly that reason.
    """
    undeclared = recognised - set(get_patient_data_schema()) - set(UNPUBLISHED_COLUMNS)

    assert not undeclared, (
        f"{sorted(undeclared)} are read out of every workbook and then dropped. "
        "Add them to the schema, or declare them in UNPUBLISHED_COLUMNS with why."
    )


def test_no_declaration_is_stale(recognised):
    """A declaration whose column no longer exists is a note about nothing."""
    for col in UNPUBLISHED_COLUMNS:
        assert col in recognised or col.endswith(STATIC_SHEET_SUFFIXES), (
            f"'{col}' is declared unpublished but nothing produces it any more"
        )


def test_no_declared_column_is_also_published():
    overlap = set(UNPUBLISHED_COLUMNS) & set(get_patient_data_schema())

    assert not overlap, f"{sorted(overlap)} are both published and declared dropped"


def test_every_declaration_gives_a_reason():
    for col, reason in UNPUBLISHED_COLUMNS.items():
        assert len(reason.split()) >= 4, f"'{col}' is declared without a real reason"


def test_static_sheets_report_their_unrecognised_columns():
    """Every tracker-facing harmonize call must name its sheet.

    ``report_unrecognised_columns`` switches itself off when it is not told
    which sheet the frame came from, so a call that omits ``sheet_name``
    drops unknown headings in silence. The Patient List and Annual calls did
    exactly that, which is why the 2026 template's new columns produced no
    finding. Checked statically because the omission is invisible at runtime.
    """
    tree = ast.parse((SRC / "extract" / "patient.py").read_text())

    calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "harmonize_patient_data_columns"
    ]
    assert calls, "no harmonize calls found -- has the function been renamed?"

    missing = [c.lineno for c in calls if not any(k.arg == "sheet_name" for k in c.keywords)]
    assert not missing, (
        f"harmonize_patient_data_columns at line(s) {missing} passes no sheet_name, "
        "so unrecognised columns on that sheet are dropped without a finding"
    )
