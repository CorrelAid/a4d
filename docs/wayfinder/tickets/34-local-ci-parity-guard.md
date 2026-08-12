---
id: 34
title: Make the local pre-push check set actually match CI, and make running it automatic
labels: [wayfinder:grilling]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 33
---

## Premise

Rests on [Fix red CI — ruff format --check fails on Python snippets inside
markdown docs](33-fix-red-ci-ruff-format-markdown.md), closed: CI was red on
`migration` for four days and nobody noticed, because the checks actually
run locally between commits (`pytest`, `ruff check`, `ty check src/`) were a
*subset* of what CI runs. The missing one — `ruff format --check` — was the
one failing. Excluding `docs/migration` removed that specific trigger, but
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
