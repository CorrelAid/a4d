---
id: 33
title: Fix red CI — ruff format --check fails on Python snippets inside markdown docs
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Rests on [Diagnose and fix why CI is red at migration
HEAD](04-fix-migration-ci.md), closed: that ticket fixed a *different*
red-CI cause (Typer's `FORCE_TERMINAL` freezing at import time under
`GITHUB_ACTIONS=true`, breaking `--help` substring assertions) and left CI
green on the PR #6 merge commit — run `31286057254`, 2026-08-09, the last
success on `migration`.

CI has failed on **every** push to `migration` since, starting with
`31343020352` (2026-08-09, "Give run product parity with run patient's
console output"). This is a new, unrelated cause; ticket 4's fix is not
regressed.

Also rests on the map's rule that the destination requires **CI green**
before [ticket 6](06-promote-migration-to-dev.md) can promote `migration`
into `dev`. Every triage ticket closed since 2026-08-09 was verified with a
locally-green suite while CI itself was red the whole time.

## Question

CI's `Run ruff formatting check` step fails — and only that step; the test
suite never runs, which is why each run dies in ~15s. Diagnosed
(2026-08-12g, read from `gh run view 31643782401 --log-failed`), the single
current cause is:

**`ruff format --check` wants to reformat the Python code blocks embedded in
`docs/migration/MIGRATION_GUIDE.md`** (4 blocks: the `settings.*`
configuration example around line 158, the vectorized `with_columns`
example around 194, and the GCS/BigQuery/loguru snippets around 214-230).
Ruff formats fenced Python in markdown, and this file has never been run
through it.

Nothing else is failing. An earlier run (`31591513197`) additionally showed
`src/a4d/migration/compare.py`'s `except TypeError, ValueError:` — that is
**valid** Python 3.14 (PEP 758 permits unparenthesized except tuples), ruff
was normalizing *to* it, and it is already applied. Do not "fix" that line.

**Why this survived four days of green local runs:** `uv run pytest`, `ruff
check`, and `ty check src/` all pass locally; only `ruff format --check`
fails, and it is easy to run `ruff format` (which silently rewrites the
markdown) without noticing. Twice during ticket 27's session the resulting
`MIGRATION_GUIDE.md` diff was actively reverted as "incidental
reformatting unrelated to this work" — which is exactly the change CI was
asking for. Any fix must make that failure mode impossible to repeat, not
just clear the current red.

Decide between:

1. **Accept the reformatting** — run `ruff format`, commit the
   `MIGRATION_GUIDE.md` changes. Simplest; keeps doc snippets in the same
   style as real code. Check the reformatted blocks still read as intended
   (the "R (slow) vs Python (fast)" comparison in particular loses some of
   its visual contrast when the Python side is rewrapped).
2. **Exclude markdown from `ruff format`** — via `extend-exclude` or a
   format-specific setting in `pyproject.toml`. Keeps illustrative snippets
   free to diverge from formatter rules (they are prose, not code, and are
   never executed or imported).

**Recommendation: (1)**, plus a guard so this cannot silently recur — the
docs are meant to mirror real pipeline code, so formatting them the same way
is consistent rather than arbitrary, and option 2 would let doc snippets
drift stylistically from the code they document. The guard matters more than
the choice: add `ruff format --check` to whatever local pre-commit/`just`
path is actually run before pushing, so the checks run locally are the same
set CI runs.

Verify by pushing and confirming a green run on `migration`, not by a local
`ruff format --check` alone — the point of this ticket is that local and CI
checks had diverged.
