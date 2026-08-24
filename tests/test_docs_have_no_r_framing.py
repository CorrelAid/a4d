"""Guard: no module explains itself by what the retired R pipeline did.

The R pipeline was retired on 2026-08-24 and its source deleted. A comment
saying a rule exists "to match R" no longer explains anything -- it points at
code nobody can read from here -- and it can also be wrong about R: one
docstring claimed a future-date guard "matches R pipeline behavior" when R had
no such guard at all. Documentation should say what the code does now and why,
with the source evidence that made it necessary.

``src/a4d/migration/`` and its tests are exempt: that package is the archived
R-vs-Python comparison, so R divergence is its actual subject. See its module
docstring.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]

# Exempt: R is the legitimate subject there, not a stand-in for a reason.
EXEMPT = (
    REPO_ROOT / "src" / "a4d" / "migration",
    REPO_ROOT / "tests" / "test_migration",
    Path(__file__).resolve(),
)

# Phrases that justify Python by R rather than by evidence, plus the R
# libraries and source files that only ever appear in such a justification.
# Assembled from parts so this file does not trip its own check.
_R = "R"
FORBIDDEN = re.compile(
    "|".join(
        [
            rf"\b{_R}'s\b",
            rf"\b{_R} pipeline\b",
            rf"\bmatch(?:es|ing)? {_R}\b",
            rf"\blike {_R}\b",
            rf"\bmirror(?:s|ing)? {_R}\b",
            rf"\bas {_R} does\b",
            rf"\b{_R} does\b",
            rf"\b{_R}-parity\b",
            rf"\b{_R} behaviou?r\b",
            r"\bscript\d_[a-z_]+\.R\b",
            r"\breadxl\b",
            r"\bopenxlsx\b",
            r"\bmake\.names\b",
            r"\btidyr::",
            r"\blubridate\b",
        ]
    )
)


def _python_files() -> list[Path]:
    """Every tracked Python file outside the exempt paths, derived not listed."""
    files = []
    for base in ("src", "tests"):
        for path in (REPO_ROOT / base).rglob("*.py"):
            if any(path == e or e in path.parents for e in EXEMPT):
                continue
            files.append(path)
    return sorted(files)


@pytest.mark.parametrize("path", _python_files(), ids=lambda p: str(p.relative_to(REPO_ROOT)))
def test_module_does_not_explain_itself_by_the_retired_r_pipeline(path: Path) -> None:
    offenders = [
        f"{path.relative_to(REPO_ROOT)}:{n}: {line.strip()}"
        for n, line in enumerate(path.read_text().splitlines(), start=1)
        if FORBIDDEN.search(line)
    ]
    assert not offenders, (
        "Documentation must explain the current behaviour and its evidence, not "
        "defer to the retired R pipeline:\n" + "\n".join(offenders)
    )
