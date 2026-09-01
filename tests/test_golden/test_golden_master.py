"""Golden-master test: the synthetic tracker's published output must not move.

The real-corpus check (``just snapshot-check``) is the thorough one, but it
needs the tracker drive and so can never run in CI -- it protects whoever
remembers to run it, not the branch. This is the half that runs everywhere:
one synthetic workbook, built in code, with its cleaned output for both arms
committed as CSV. Any change to extraction, cleaning or the schema that alters
what the pipeline publishes shows up here as a readable diff.

Values are committed in full because nothing in the workbook is real -- see
``tests/fixtures/golden_tracker.py``.

To accept a deliberate change: ``just golden-update``, then read the diff
before committing it.
"""

from pathlib import Path

import polars as pl
import pytest

from a4d.clean.patient import clean_patient_data
from a4d.clean.product import clean_product_data
from a4d.extract.patient import read_all_patient_sheets
from a4d.extract.product import read_all_product_sheets
from a4d.findings import FindingCollector, tracker_context

from .golden_tracker import build_golden_tracker

GOLDEN_DIR = Path(__file__).parent / "golden"

# Recorded per finding, in a stable order. The timestamp and the log file name
# are per-run by construction and are not part of what the pipeline publishes
# about a workbook, so they stay out.
_FINDING_FIELDS = ["error_code", "column", "sheet_name", "stage"]


def _run_arm(tracker: Path, output_root: Path, arm: str) -> tuple[pl.DataFrame, FindingCollector]:
    """Extract and clean one arm, returning its cleaned frame and findings."""
    with tracker_context(str(tracker), arm, output_root) as collector:
        if arm == "patient":
            return clean_patient_data(read_all_patient_sheets(tracker)), collector
        return clean_product_data(read_all_product_sheets(tracker)), collector


def _findings_summary(collector: FindingCollector) -> pl.DataFrame:
    """Count findings by kind, so a change in what gets reported is visible."""
    rows = [
        {field: getattr(finding, field, None) for field in _FINDING_FIELDS}
        for finding in collector.findings
    ]
    if not rows:
        return pl.DataFrame({field: [] for field in _FINDING_FIELDS} | {"count": []})
    return (
        pl.DataFrame(rows)
        .with_columns(pl.col(_FINDING_FIELDS).cast(pl.Utf8))
        .group_by(_FINDING_FIELDS)
        .len("count")
        .sort(_FINDING_FIELDS)
    )


def build_golden_output(output_root: Path) -> dict[str, pl.DataFrame]:
    """Produce every frame this test pins, keyed by its golden file's stem."""
    tracker = build_golden_tracker(output_root / "trackers")
    frames: dict[str, pl.DataFrame] = {}
    for arm in ("patient", "product"):
        cleaned, collector = _run_arm(tracker, output_root, arm)
        frames[f"{arm}_cleaned"] = cleaned
        frames[f"{arm}_findings"] = _findings_summary(collector)
    return frames


def _read_golden(name: str) -> pl.DataFrame:
    path = GOLDEN_DIR / f"{name}.csv"
    if not path.exists():
        pytest.fail(f"No golden file at {path}. Run `just golden-update` to create it.")
    return pl.read_csv(path, infer_schema_length=0)


def _as_text(df: pl.DataFrame) -> pl.DataFrame:
    """Compare as text: CSV has no dtypes, and dtype drift is pinned separately."""
    return df.select([pl.col(c).cast(pl.Utf8).alias(c) for c in df.columns])


@pytest.fixture(scope="module")
def golden_frames(tmp_path_factory) -> dict[str, pl.DataFrame]:
    return build_golden_output(tmp_path_factory.mktemp("golden"))


@pytest.mark.parametrize(
    "name", ["patient_cleaned", "product_cleaned", "patient_findings", "product_findings"]
)
def test_golden_output_has_not_moved(name: str, golden_frames: dict[str, pl.DataFrame]) -> None:
    """Every published cell of the synthetic tracker matches its golden copy."""
    actual = _as_text(golden_frames[name])
    expected = _read_golden(name)

    assert actual.columns == expected.columns, (
        f"{name}: published columns changed. "
        f"Added {set(actual.columns) - set(expected.columns)}, "
        f"removed {set(expected.columns) - set(actual.columns)}."
    )
    assert actual.height == expected.height, (
        f"{name}: row count moved from {expected.height} to {actual.height}."
    )
    diffs = [
        (col, row, exp, act)
        for col in expected.columns
        for row, (exp, act) in enumerate(zip(expected[col], actual[col], strict=True))
        if exp != act
    ]
    assert not diffs, f"{name}: {len(diffs)} cells moved, first five: {diffs[:5]}"


@pytest.mark.parametrize("arm", ["patient", "product"])
def test_golden_dtypes_have_not_moved(arm: str, golden_frames: dict[str, pl.DataFrame]) -> None:
    """The published types are pinned too -- CSV cannot carry them."""
    actual = {c: str(t) for c, t in golden_frames[f"{arm}_cleaned"].schema.items()}
    expected = dict(
        _read_golden(f"{arm}_dtypes").select(["column", "dtype"]).iter_rows()  # type: ignore[arg-type]
    )
    moved = {c: (expected.get(c), t) for c, t in actual.items() if expected.get(c) != t}
    assert not moved, f"{arm}: published dtypes changed (column: was, now) {moved}"
