"""Test-session setup that must run before any test module imports a4d.cli.

GitHub Actions sets GITHUB_ACTIONS=1 for every job, and Typer reads that at
import time (typer.rich_utils.FORCE_TERMINAL) to force colored --help
rendering. That splits multi-character options like "--file" into separate
ANSI-styled spans (e.g. "-" then "-file"), breaking plain `"--file" in
result.output` assertions in CLI tests even though the same tests pass
locally where GITHUB_ACTIONS is unset. Typer's own escape hatch,
_TYPER_FORCE_DISABLE_TERMINAL, disables that forced styling; it must be set
before typer.rich_utils is first imported, hence here rather than in a
fixture.
"""

import os

os.environ.setdefault("_TYPER_FORCE_DISABLE_TERMINAL", "1")

import pytest  # noqa: E402

from a4d.findings import findings_collected  # noqa: E402


@pytest.fixture
def collector():
    """A findings collector bound for the duration of one test.

    The pipeline reports findings into whatever context is open, so a test that
    exercises a cleaning step needs one bound. Autouse below, and also
    requestable by name where the test asserts on what was reported.
    """
    with findings_collected(file_name="test_tracker") as c:
        yield c


@pytest.fixture(autouse=True)
def _findings_context(request):
    """Bind a findings context around every test that does not manage its own.

    report_finding raises outside a context by design, so without this every
    test touching a cleaning step would fail on attribution rather than on the
    behaviour it is checking. Tests of the context machinery itself opt out
    with the ``no_findings_context`` marker.
    """
    if request.node.get_closest_marker("no_findings_context"):
        yield
        return
    if "collector" in request.fixturenames:
        yield
        return
    with findings_collected(file_name="test_tracker"):
        yield
