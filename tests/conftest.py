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
