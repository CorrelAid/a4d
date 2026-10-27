"""Guard: no tracked file carries a patient identifier with a real clinic code.

The repository is public. Patient identifiers are pseudonymous, but anyone
holding a clinic's patient list can resolve them, so tests, docstrings and docs
use stand-in clinic codes instead (country kept, clinic replaced). History was
rewritten on 2026-09-01 to remove the real ones; this keeps them from coming
back.

An identifier counts as real when its country and clinic code together match a
row of ``reference_data/clinic_data.xlsx``. Matching on the pair, not the clinic
code alone, matters because some real clinic codes start with Q, the letter the
stand-ins use. Identifiers built at runtime from a format string cannot be seen
here; review still has to catch those.
"""

import re
import subprocess
from pathlib import Path

import polars as pl

REPO_ROOT = Path(__file__).resolve().parents[1]

# Tracker spellings seen in the data: separator underscore or hyphen, an
# optional second separator before the number, any casing.
IDENTIFIER = re.compile(r"(?<![A-Za-z0-9])([A-Za-z]{2})[_-]([A-Za-z]{2})[_-]?(\d{1,4})(?!\d)")


def _real_clinics() -> set[tuple[str, str]]:
    clinics = pl.read_excel(REPO_ROOT / "reference_data" / "clinic_data.xlsx")
    return {
        (country.upper(), clinic.upper())
        for country, clinic in zip(clinics["country_code"], clinics["clinic_code"], strict=True)
        if country and clinic
    }


def _tracked_text_files() -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=True
    ).stdout.splitlines()
    return [REPO_ROOT / name for name in listed if not name.startswith("reference_data/")]


def test_no_tracked_file_names_a_patient_at_a_real_clinic() -> None:
    real = _real_clinics()
    assert real, "clinic reference file yielded no clinics; the check would pass vacuously"

    offenders = []
    for path in _tracked_text_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError, FileNotFoundError:
            continue
        for n, line in enumerate(text.splitlines(), start=1):
            for match in IDENTIFIER.finditer(line):
                if (match[1].upper(), match[2].upper()) in real:
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{n}: {match[0]}")

    assert not offenders, (
        "Use a stand-in clinic code (keep the country, replace the clinic) for:\n"
        + "\n".join(offenders)
    )
