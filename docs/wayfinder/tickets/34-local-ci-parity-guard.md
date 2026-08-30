---
id: 34
title: Make the local pre-push check set actually match CI, and make running it automatic
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-30
claimed_at: 2026-08-30
resolution: decided
evidence: executed
closed_by: null
spawned_by: 33
---

## Premise

Rests on [Fix red CI — ruff format --check fails on Python snippets inside
markdown docs](33-fix-red-ci-ruff-format-markdown.md), closed: CI was red on
`migration` for four days and nobody noticed, because the checks actually
run locally between commits (`pytest`, `ruff check`, `ty check src/`) were a
*subset* of what CI runs. The missing one — `ruff format --check` — was the
one failing. Excluding `docs/archive` removed that specific trigger, but
not the drift that let it go unseen: the same class of failure recurs the
moment CI gains a step, or an existing step's arguments change.

## Question

A `just ci` recipe already exists and is meant to be this guard:

```
ci: format-check lint check test
```

Two things are wrong with relying on it as things stand.

**1. It does not actually match CI.** Compared against
`.github/workflows/`:

- `just test` runs `pytest -m "not slow"`; CI runs
  `pytest -m "not slow and not integration" --cov --cov-report=xml`. The
  local set therefore *includes* integration tests (which are
  USB-drive-gated and skip or fail depending on whether the drive is
  mounted) and CI does not — so the two can disagree in both directions.
- CI additionally enforces a **product-code coverage floor** (`coverage
  report --include=<7 product files> --fail-under=85`) that `just ci` never
  runs. A change that drops product coverage below 85% passes `just ci` and
  fails CI.

**2. Nothing makes anyone run it.** It is a recipe you have to remember,
and ticket 33 is the evidence that remembering does not happen — including
across a session that ran `ruff format` (silently rewriting the very file
CI was failing on) and then reverted the diff twice as unrelated noise.

Decide:

- **How to keep `just ci` honest about CI.** Options: (a) hand-maintain it
  and accept drift, (b) restructure the workflow so CI *calls* `just ci`,
  making the recipe the single definition, (c) generate one from the other.
  (b) is the standing-rules-compliant answer — never hand-maintain a list
  that can be derived — but it changes how CI is invoked and needs the
  coverage/codecov steps thought through, since those are CI-only concerns.
- **What makes it run without being remembered.** Options: a git pre-push
  hook, a pre-commit framework config, or accepting that the agent working
  this map runs `just ci` before every push as a standing rule in the map's
  Notes. The last is the cheapest and needs no tooling, but is exactly the
  kind of "remember to" that already failed once.

**Recommendation:** (b) plus a pre-push hook, but the hook's cost is real —
it runs the full suite on every push, and this repo's suite plus coverage
takes ~30s. Worth confirming that trade before building it, which is why
this is a grilling ticket rather than a task.

Scope note: this is about the *check set*, not about CI's own reliability.
Whether CI should also run the USB-drive-gated integration tests (it
cannot — no drive) is settled and out of scope.

## Standing bar (applies to this ticket)

Per the map's **triage means deciding, not labelling** preference: name the
mechanism, and decide explicitly whether the chosen approach actually
prevents recurrence rather than merely documenting the intention. "Add it to
the Notes" is a decision only if it is honestly judged sufficient.

## Resolution

**Decision.** (b) plus a pre-push hook, both as recommended, with the automation
half deliberately scoped down by the user.

*Parity.* Every check step in `.github/workflows/python-ci.yml` now invokes the
`just` recipe of the same name (`just lint` / `format-check` / `check` / `test`
/ `cov-floor`) instead of spelling the command out. One definition, two callers.
The workflow keeps its named steps, so a failure still says *which* check failed
on the run page -- the user asked for explicit steps over "hidden magic", which
ruled out collapsing CI into a single `just ci` call.

`just test` is now CI's exact selection (`-m "not slow and not integration"`,
with coverage) and `just test-integration` is the drive-dependent set, run
deliberately. The user chose two explicit commands over one command that adapts
to whether the USB drive happens to be mounted. `just ci` gained `cov-floor`,
the 85% product-code gate CI enforced and the local set never ran. `test-all`
was dropped (its selection was ambiguous); `test-fast` stays, relabelled as a
development-loop helper rather than a check.

*Automation.* `scripts/hooks/pre-push` runs `just ci`; `just hooks` installs it
(replacing the recipe that called `pre-commit`, whose config file never
existed -- `pre-commit` is also dropped from the dev dependencies). Measured
cost: ~40s per push, 37s of it the test suite.

**Honest judgement on whether this prevents recurrence, per the ticket's own
bar: partially, and the user accepted that knowingly.** A client-side hook is
not enforcement. It is bypassable with `git push --no-verify` and absent
entirely from a fresh clone, since git will not run hooks that arrive with a
repository. The only real guard is server-side: a ruleset requiring the check
to pass, which in practice forces a pull-request flow because a direct push has
no prior run to require. Presented as such; the user declined it on the grounds
that they are currently the only developer, and that pushing straight to `dev`
is worth keeping. **What would overturn this:** a second developer, a fresh
clone, or a push that reaches `dev` red. See *Assumptions in force*.

**Because.** The failure mode ticket 33 recorded was not "someone forgot" but
"the two lists were maintained by hand and silently diverged". Making CI call
the recipes removes the divergence mechanism outright; the hook only addresses
the weaker half (someone not running the checks at all), which is why it is
honestly recorded as a reminder rather than a guard.

**Rejected.**
- *(a) Keep two hand-maintained copies* -- the state that produced four days of
  red CI nobody noticed.
- *(c) Generate one from the other* -- more machinery than a five-step workflow
  justifies.
- *Collapsing CI to one `just ci` step* -- loses the per-check step names on the
  run page; the user explicitly wanted explicit.
- *A local check set that includes the drive tests when the drive is mounted* --
  makes the result depend on what is plugged into the laptop.
- *Server-side enforcement (branch ruleset requiring the check)* -- the only
  actual guard, declined by the user for the workflow cost; recorded above and
  in the map's assumptions so it can be revisited when a second developer
  arrives.

## What reviewing the whole workflow found

The user asked, mid-session, for the CI/CD pipeline to be reviewed and made
production-ready rather than only patched for parity. Eight defects, each
measured against the live repository or a real run, not read off the file:

1. **The coverage upload had never worked.** Run `33313542508` (2026-08-30,
   `dev`): `429 - Rate limit reached. Please upload with the Codecov repository
   upload token`, then `Codecov will exit with status code 0`. No token is
   configured (`No token specified or token is empty`), so it uploaded
   anonymously and was throttled -- a permanently green step that published
   nothing. Removed at the user's decision ("GitHub services only"); coverage
   now writes to `$GITHUB_STEP_SUMMARY`. The enforced 85% floor is untouched --
   it runs on the runner, not at Codecov.
2. **`uv sync --all-extras` did not respect the lock file**, so CI was free to
   resolve a different dependency set from every local machine. Now `--locked`,
   which fails if `uv.lock` is stale against `pyproject.toml`.
3. **Action versions were stale by majors**: `actions/checkout@v4` (current v7),
   `astral-sh/setup-uv@v2` (current v10). Bumped, and `.github/dependabot.yml`
   added (monthly, github-actions + uv) so this is noticed by machine.
4. **Nothing built the production image.** The container Cloud Run executes is
   built by hand on a laptop, so a broken `Dockerfile` or lock file could only
   surface at deploy time -- which is how ticket 79 went. A second job now
   builds it and runs `uv run --no-sync a4d --help` inside it, the same startup
   path the job takes. No registry push: deploying stays a human action per this
   map's guardrails. Verified on CI, not locally (the local Docker daemon is
   down): job `docker` succeeded in 24s on run `33314839468`.
5. **The workflow token was read/write.** The repository default is
   `default_workflow_permissions: write` (checked via the API), and the
   workflow declared no `permissions:` block, so every action it ran inherited
   write access to the repo. Now `contents: read` -- confirmed in the run log:
   `GITHUB_TOKEN Permissions / Contents: read`.
6. **No concurrency group and no timeout**: superseded pushes ran to completion,
   and a hung job could burn the 6h default. Now cancel-in-progress, 15/20 min
   caps.
7. **Triggers named a retired branch.** It ran on `migration` (merged, no longer
   trunk) and never on `main`. Now `dev` + `main` + `workflow_dispatch`.
8. **Five leftover R workflow backups** (`*.bak`) still sat in
   `.github/workflows/` after R was retired by ticket 12. Deleted.

Also added `.python-version` (3.14), so `uv python install` resolves the same
interpreter locally and on CI rather than each guessing.

**A defect this session introduced and fixed.** The first push failed:
`Unable to resolve action astral-sh/setup-uv@v10`. `setup-uv` publishes exact
version tags only -- there is no floating `v10` -- so it is pinned to
`v10.0.1`. Found by the run, not by review, which is itself the argument for
pushing rather than reasoning about the workflow.

**Evidence.** Executed: the codecov failure (run log), the token permission
(API + run log), the timings (`just ci` ~40s on an idle machine; 37s of it
pytest -- an earlier 2m03s reading was this machine under load average 14-23,
re-measured twice at 37s), the green run `33314839468` (both jobs, 53s
wall), the pre-push hook firing on a real `git push origin dev`, and the
Dependabot config taking effect (PR #7 opened within a minute).

**Tense.** Every numbered item above describes behaviour *before* this session's
commits (`cee1675`, `b8f33fe`); all eight are fixed on `dev` now.
