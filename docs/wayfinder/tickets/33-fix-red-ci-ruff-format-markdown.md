---
id: 33
title: Fix red CI — ruff format --check fails on Python snippets inside markdown docs
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-12g
claimed_at: 2026-08-12
resolution: decided
evidence: executed
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

## Resolution

**Decision:** Option 2 — `docs/migration` added to ruff's `extend-exclude`
in `pyproject.toml`, alongside the existing `r-archive` entry. The user
overrode this ticket's recommendation of option 1, and was right to:
`MIGRATION_GUIDE.md` is a **working spec document**, and there is nothing in
it for ruff to validate. Its fenced Python is illustrative prose — never
imported, never executed — so formatting it enforces code rules on something
that is not code, and only rewraps examples whose line breaks were chosen for
readability.

**Because:** scoped to the whole `docs/migration/` directory rather than
just the one failing file. Both markdown files in the repo containing
`” ```python ”` fences live there (`MIGRATION_GUIDE.md`,
`PYTHON_IMPROVEMENTS.md`, confirmed by grep across `docs/` and root); the
second is incidentally well-formatted today and would have re-broken CI on
any future edit. Excluding the directory fixes the cause rather than the
instance.

**Rejected:** option 1 (accept the reformatting and commit it), this
ticket's own recommendation, on the reasoning that docs should mirror real
code style. That confuses "code shown in a document" with "code" — the
snippets are explanatory and are allowed to prioritize clarity over
formatter rules. Also rejected: excluding all markdown repo-wide, which
would silently cover future docs that might genuinely want formatting;
`docs/migration/` is the meaningful boundary.

**Evidence:** executed — every CI step reproduced locally and passing:
`ruff check .` (all checks passed), `ruff format --check .` (144 files, was
"1 file would be reformatted"), `ty check src/`, `pytest -m "not slow and
not integration"` (555 passed, 1 skipped), and the product coverage gate
(88%, floor 85). `git status docs/migration/` confirms the markdown itself
is untouched. Final confirmation is a green run on `migration` after push —
the whole point of this ticket being that local and CI check sets had
diverged, so a local pass alone is not the proof.

**Tense:** current behaviour; all numbers from this session's actual runs.

**Guard, not yet done:** this ticket asked for a mechanism so the failure
cannot silently recur. The exclusion removes *this* trigger, but local and
CI check sets can still drift — nothing local runs the full CI set
automatically. Spawned as [ticket 34](34-local-ci-parity-guard.md) rather
than left as an untracked intention.
