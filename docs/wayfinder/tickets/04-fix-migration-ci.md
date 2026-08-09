---
id: 4
title: Diagnose and fix why CI is red at migration HEAD
labels: [wayfinder:task]
status: closed
blocked_by: [3]
assignee: session-2026-08-09
claimed_at: 2026-08-09
resolution: decided
evidence: executed
closed_by: null
spawned_by: null
---

## Premise

Depends on [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md)
being done first — the user wants migration-readiness work sequenced after the
merge, since the merge itself will change what's running through CI.

Facts on record: `gh run list --branch migration` shows the last 3 runs of the
"Python CI" workflow all failed, including the current tip `faa3c28`
(2026-04-01 and later). PR #2 (`migration` -> `dev`) is `mergeable: MERGEABLE`
but shows the same failing "test" check.

## Question

Find out why CI fails at `migration` HEAD (post-merge) and fix it — is this a
transient environment issue, a real test failure, a lint/type-check break, or
something the merge itself needs to resolve?

## Resolution

**Decision:** Added `tests/conftest.py` on `product-pipeline` (PR #6) setting
`os.environ.setdefault("_TYPER_FORCE_DISABLE_TERMINAL", "1")` before any test
module can import `a4d.cli`. Pushed as `b970cf6`. CI run
[31285797606](https://github.com/CorrelAid/a4d/actions/runs/31285797606) is
green — all 7 previously-failing `--help` tests pass, full suite (428 tests)
passes, coverage gate holds. PR #6 is `mergeable: MERGEABLE` with a passing
`test` check.

**Because:** Root-caused by reading Typer's own source
(`typer.rich_utils`), not by guessing from symptoms. At **import time**,
`typer/rich_utils.py` computes a module-level `FORCE_TERMINAL` constant:
`True if getenv("GITHUB_ACTIONS") or getenv("FORCE_COLOR") or
getenv("PY_COLORS") else None`. GitHub Actions sets `GITHUB_ACTIONS=true`
for every job, so on the Actions runner `FORCE_TERMINAL` freezes to `True`
the moment `a4d.cli` (which imports `typer`) is first imported — regardless
of anything `CliRunner(env={...})` sets afterward at invoke time, and
regardless of `NO_COLOR`/`COLUMNS`. With `FORCE_TERMINAL=True`, Typer's
`--help` renderer applies full Rich styling, and Rich's highlighter styles
each hyphen of a long option separately — e.g. `--file` becomes
`\x1b[1m-\x1b[0m\x1b[1m-file\x1b[0m` — which breaks a plain `"--file" in
result.output` substring check even though the visible text is unchanged.
Locally `GITHUB_ACTIONS` is unset, so `FORCE_TERMINAL` stays `None` and
plain text renders, which is why the tests only ever failed on the runner.
Confirmed by reproducing the exact failure locally with
`GITHUB_ACTIONS=true uv run pytest ...` (fails without the fix, 428 pass
with it), and by inspecting `typer.rich_utils` source directly rather than
trusting docs or memory. Typer ships its own escape hatch for exactly this,
`_TYPER_FORCE_DISABLE_TERMINAL` (also read once at import time, same
module), which forces `FORCE_TERMINAL = False` regardless of `GITHUB_ACTIONS`
— so the fix is to set that env var before `typer.rich_utils` is first
imported, which for a pytest run means a `conftest.py` at the top of the
collected tree (`tests/conftest.py`), not a fixture (fixtures run too late,
after collection has already imported the test modules).

**Rejected:**
- *The original lead — `cli.py`'s module-level `console = Console()`
  snapshotting width at import.* Investigated first since it was the
  starting hypothesis, but disproved by reading Rich's `Console.size`
  property: `COLUMNS` from `os.environ` is re-read live on every access, not
  cached at construction, and Click's `CliRunner.isolation()` mutates the
  real `os.environ` in place (not a copy), so `Console()`'s construction
  timing doesn't matter for width. `Console.no_color` *is* frozen at
  construction, but that's a red herring here too: the failing `--help`
  output isn't rendered by `cli.py`'s `console` object at all — Typer
  renders `--help` through its own internal `Console` (`typer.rich_utils
  ._get_rich_console`), built fresh on every call. `cli.py`'s console was
  never the culprit.
- *Stripping ANSI codes in the test assertions instead.* Would fix the
  symptom but leaves color rendering nondeterministic between local and CI
  runs for every future `--help` test, and doesn't explain why coverage
  differed either — the config-level fix removes the actual source of
  divergence.
- *Setting `COLUMNS`/`NO_COLOR` more aggressively in the CI workflow YAML.*
  Already true in the failing runs (`CliRunner(env={"NO_COLOR": "1",
  "COLUMNS": "200"})`) — proven not to matter, since `FORCE_TERMINAL` is
  decided by `GITHUB_ACTIONS`/`FORCE_COLOR`, not by those two.

**Tense:** All claims above describe current, verified behavior (executed
against the actual `product-pipeline` code and the actual GitHub Actions
runner via a real CI run), not a hypothesis about a still-open lead.

**Where applied:** `tests/conftest.py` was added on `product-pipeline`
(PR #6's branch), not `migration` directly — `migration`'s own tip
(`faa3c28`) predates the product-pipeline code entirely (patient-only), and
the map's Notes record that ticket 3's merge work already landed on
`product-pipeline` rather than `migration`. This fix rides along with that
same merge. `migration`'s CI will be green once the merge is landed
(human-only action, per this map's guardrails).
