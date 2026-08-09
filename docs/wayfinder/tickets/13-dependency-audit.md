---
id: 13
title: Audit and update all dependencies and library versions before rollout
labels: [wayfinder:task]
status: closed
blocked_by: [3]
assignee: session-2026-08-09c
claimed_at: 2026-08-09
resolution: decided
evidence: executed
closed_by: null
spawned_by: null
---

## Premise

Rests on the same destination redraw as [ticket 10](10-performance-profiling.md),
[ticket 11](11-cli-ux-observability.md) and [ticket 12](12-retire-r-workspace.md):
the user confirmed rollout readiness covers more than merge/verify/promote,
and dependency hygiene is part of that bar.

Needs [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md)
closed (it is) so there's one `pyproject.toml`/`uv.lock` to audit, not two
branches' worth.

## Question

Audit every dependency in `pyproject.toml`/`uv.lock` (and the `Dockerfile`'s
base image, `python:3.14-slim`) against current upstream versions: what's
outdated, what has known security advisories, what's safe to bump now versus
what needs a deprecation/breaking-change check first. Update what's safe,
record what's deliberately deferred and why (e.g. a major version needing
migration work of its own).

**Sequencing note**: this should land before [ticket
10](10-performance-profiling.md)'s profiling run, not after — profiling
against a dependency set that's about to change makes the numbers stale
immediately. Ticket 10 has been wired `blocked_by: [3, 13]` to reflect this.

## Resolution

**Decision**: ran `uv lock --upgrade` to move every dependency (`pyproject.toml`'s
constraints are all `>=` lower bounds, so the lock file — not the manifest —
was the thing actually stale) to its current latest resolvable version,
including three majors: `pandera` 0.26.1 -> 0.32.1, `pytest` 8.4.2 -> 9.1.1,
`typer` 0.19.2 -> 0.27.1 (`rich` came along transitively, 14.2.0 -> 15.0.0).
`ty` (dev-only type checker) moved 0.0.1a23 -> 0.0.69 — a huge alpha jump,
called out separately below since it changed what CI's `ty check src/` gate
actually catches. The `Dockerfile`'s `python:3.14-slim` floating tag was
checked against Docker Hub directly (not just read) and already resolves to
3.14.7-slim as of 2026-08-05 — no pin to move.

**Because**: `pyproject.toml` uses unbounded `>=` everywhere, so nothing was
capping these versions — the lock file had just never been refreshed since
the constraints were written. `uv tree --outdated` before the bump showed
every dependency 1-3 versions behind latest; `pip-audit` against that
pre-upgrade lock found 19 known vulnerabilities across 8 packages (`click`,
`protobuf`, `requests`, `idna`, `urllib3`, `pyasn1`, `pygments`,
`python-dotenv`) — all fixed by versions already within the existing `>=`
constraints, so there was no reason to defer any of them.

**Rejected**: pinning `pyproject.toml`'s floors up to match the new lock
(e.g. `pytest>=9.1.1`) was considered and rejected — the existing `>=`
floors already resolve to the versions now locked, so bumping them would
only narrow future resolution without changing today's behavior; the lock
file is the actual source of truth `uv sync --frozen` installs from.
Pinning the Dockerfile's Python image to an exact patch (`3.14.7-slim`
instead of the floating `3.14-slim` tag) was considered for build
reproducibility and rejected as out of this ticket's "outdated versions"
scope — the floating tag is already current, and pinning-for-reproducibility
is a separate, deliberate tradeoff (loses automatic security patches) the
user hasn't asked for.

**Evidence (executed, not just read)**:
- `uv lock --upgrade` + `uv sync --frozen`, then the full suite:
  `uv run pytest -q` -> 488 passed, 0 failed (was 488 passed before the bump
  too — no regressions). `uv run ruff check .` and `uv run ruff format
  --check .` both clean (the one "unformatted" hit is a markdown code
  example in `docs/migration/MIGRATION_GUIDE.md`, not real source).
- `uv run --with pip-audit pip-audit -r <exported requirements>`:
  19 known vulnerabilities before the upgrade, 0 after.
- `uv run ty check src/` (the CI-gating command — CI only checks `src/`, not
  `tests/`) surfaced 2 real diagnostics the old 0.0.1a23 alpha never caught:
  1. `src/a4d/gcp/storage.py:43` — `blob.name` is typed `str | None` in
     `google-cloud-storage`'s stubs; `_download_blob` used it unguarded.
     Fixed with an `assert blob.name is not None` (true in practice — this
     function is only called on blobs yielded by `list_blobs()`, which
     always populate `name`) rather than silencing the checker.
  2. `src/a4d/validate/common.py:95` — `emit_finding`'s `error_code`
     parameter was typed `str` with a `# type: ignore[arg-type]` comment
     that (mypy syntax) `ty` never honored, masking that all nine call sites
     already pass one of the `ErrorCode` `Literal` values the function's own
     docstring documents. Retyped the parameter to `ErrorCode` and dropped
     the dead ignore comment — this is what the function was always meant to
     accept.
  Both fixes verified: `uv run ty check src/` -> "All checks passed!" after.
- Product-only coverage gate re-run exactly as CI computes it
  (`uv run coverage report --include=... --fail-under=85`) -> 88% total,
  unaffected by the dependency bump.
- Checked `typer` 0.27's one documented breaking change (metavar printing in
  `--help` output — the same surface that broke CI in
  [ticket 4](04-fix-migration-ci.md)) via web search of the release notes;
  the full test suite (which includes `tests/test_cli/test_cli.py`'s
  `--help` assertions) passing after the bump is direct evidence it isn't
  triggered here.

**Deferred, not fixed (out of this ticket's CI-gated scope)**: `ty` also
surfaced 14 additional diagnostics confined to `tests/` (a read-only-property
assignment in a test, two `list[str]` vs `list[str | None]` invariance
complaints, several `ManifestEntry | None` attribute accesses left
unnarrowed in test assertions) — CI's `ty check src/` never checks `tests/`,
so these are pre-existing test-code type looseness the alpha version was too
weak to see, not a regression. Left as-is: fixing test-only type annotations
is general hygiene, not a dependency-version decision, and doesn't block
anything on this map. Also left as-is: `polars`'s own `empty_as_null` /
`str.to_date()` / `from_arrow` deprecation warnings (visible in the pytest
run) — these are `polars` 1.x's own forward notice of its *upcoming* 2.0
breaking changes; 2.0 isn't released (`uv tree --outdated` shows `polars`
1.34.0 -> latest 1.43.2, no 2.0), so there is no version to bump toward yet
and no action this ticket's scope covers.

**Tense**: all claims above describe current, executed behavior on
`migration` HEAD after this session's commit, not a proposed design.
