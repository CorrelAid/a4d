---
id: 3
title: Merge product-pipeline (PR #6) into migration
labels: [wayfinder:task]
status: closed
blocked_by: [8]
assignee: session-2026-08-08b
claimed_at: 2026-08-08
resolution: decided
evidence: executed
closed_by: null
spawned_by: null
---

## Premise

Depends on [Does the pytest suite reach unit/integration/e2e/regression
parity between patient and product, excluding any R-comparison/USB-drive-dependent
tests?](08-pytest-suite-parity.md) (itself blocked on [Is the product pipeline
(and patient's own claimed completeness) actually complete and sound, audited
against R's product logic and patient's structure?](07-pipeline-completeness-audit.md))
being resolved first — the user's stated order is product-pipeline readiness
before the merge, not merge-then-fix. (Originally blocked on [Does
product-pipeline's test suite meet the same cell-by-cell rigor as
patient's?](01-product-pipeline-test-rigor.md), closed as superseded and
replaced by tickets 7/8 above.)

**No longer blocked on** [Retire the PDF/notebook analysis docs for an
automated, script-based report](02-documentation-strategy.md) — the user
corrected this sequencing: the R-vs-Python comparison script only makes
sense to build once patient and product live on one branch, not before, so
it belongs *after* this merge rather than gating it. Ticket 2 is now blocked
by this ticket instead of the reverse. The merge's actual readiness bar is
tests green (ticket 8) plus ordinary pre-merge hygiene the user named
explicitly: code style, a review pass on the implementation itself (are all
of R's steps actually migrated, not just tested), and doc alignment with the
patient pipeline's conventions — not proof of R/Python output parity, which
this ticket's own review process (green tests + a clean implementation
review) is judged sufficient grounds to trust without first.

Facts on record: PR #6 (`product-pipeline` -> `migration`) is `mergeable:
CONFLICTING`. `migration` carries two commits (`2069a4d`, `faa3c28`) not on
`product-pipeline` — error-log-table work touching `tables/logs.py` and
`tables/errors.py` — while `product-pipeline` independently changed
`tables/logs.py` and added `tables/metadata.py`. This is the real source of the
conflict.

## Question

Resolve the merge: reconcile `migration`'s error-log-table commits with
`product-pipeline`'s `logs.py`/`errors.py`/`state/` changes, land PR #6, and
confirm the merged `migration` branch has both arms (patient + product +
state/incremental) working together, not just side by side. Before landing
it, also confirm the pre-merge hygiene bar the user set: ticket 8's tests
green, a code-style pass, an implementation review confirming all of R's
product-side steps are actually migrated (not just individually tested), and
doc alignment with the patient pipeline's conventions.

## Resolution

**Decision:** All four readiness-bar items are done and pushed to
`product-pipeline`; PR #6 is now `mergeable: MERGEABLE` with its conflicts
resolved. Landing the merge itself (clicking the button) is left to the user
per the map's human-only-merge guardrail.

**What was implemented (in a `../a4d-product-pipeline` worktree, on the
`product-pipeline` branch, then merged forward from `origin/migration`):**

1. **Ticket 8's test-parity decision, implemented:** the three missing
   product integration/e2e test classes (extract, clean, e2e) added to the
   existing patient files, mirroring patient's fixture/skip-if-missing
   convention exactly (verified against real tracker files — the USB drive
   was mounted this session); `tests/test_extract/test_wide_format.py` added
   (wide_format.py was 16% covered, now 97%); `tests/test_tables/test_product.py`
   added (`create_table_product_data` was previously only reached indirectly);
   `tests/test_pipeline/test_product.py` added (pipeline/product.py
   orchestration had zero tests before this session). `test_r_validation.py`
   removed from pytest entirely, no product equivalent, per ticket 8.
2. **Coverage gate, narrowed to product-only (user correction mid-session):**
   ticket 8's 85% figure was judgement-only and never checked against the
   actual baseline — repo-wide coverage was 73%, and most of the gap
   (`clean/patient.py`, `cli.py` argument parsing, `pipeline/tracker.py`)
   is patient/CLI code unrelated to product parity. The user redirected: gate
   85% for product-pipeline files only (`extract/product.py`, `clean/product.py`,
   `clean/schema_product.py`, `extract/wide_format.py`, `pipeline/product.py`,
   `tables/product.py`, `validate/source_vs_output_product.py`) via a separate
   `coverage report --include=... --fail-under=85` CI step, alongside the
   existing whole-package `--cov` for codecov reporting. Product-only
   coverage: 73% baseline → 88% after the new tests. Patient/CLI coverage is
   explicitly deferred to a future pass once merged onto `migration`.
3. **Code style + type checking:** `ruff check .` / `ruff format --check .` /
   `ty check src/` all clean repo-wide (not just product files) — CI runs
   them unscoped, so pre-existing violations anywhere blocked the merge.
   Fixed: `r-archive/` was being linted despite CLAUDE.md's do-not-modify
   rule (excluded via `extend-exclude`, not edited); ~26 line-length/
   composite-assertion/broad-exception issues across patient and shared
   test files; 2 pre-existing `ty` diagnostics (`cli.py`'s
   `_render_pipeline_header` typed `data_root: str` but always called with
   a `Path`; `tables/metadata.py`'s schema dict mixed bare dtype classes
   with an instance under too-narrow an annotation — fixed with the same
   `type[pl.DataType] | pl.DataType` pattern `clean/schema_product.py`
   already uses).
4. **Implementation review, done via the logging-approach comparison this
   session started with (see "Where this map stands"):** found and fixed two
   real gaps, not just confirmed the audit — `process_tracker_product` wasn't
   populating `TrackerResult.data_errors` (migration added that field after
   product-pipeline branched, so neither arm wired it on this branch), and
   `process_product_cmd` never created a logs or errors table at all, unlike
   `process_patient_cmd` (Step 1/2, Step 2/2 vs. patient's Step 1/4..4/4).
   Both fixed to mirror patient exactly, locked in by a new
   `TestProcessProductE2E` CLI test class. Also fixed a latent bug caught
   while writing `wide_format.py`'s unit tests: `_rows_to_df` pinned output
   dtype from the pre-split schema, so an all-null source column (e.g.
   "Units Released" on 2017-2019 Mandalay comma-cell trackers, which have no
   populated units column before the split writes into it) inferred `Null`
   and silently dropped the split's new string values — same root cause and
   fix (`schema_overrides`-equivalent) as an existing fix in `tables/logs.py`.
5. **Doc alignment:** verified, no changes needed — `product-pipeline`'s
   `docs/CLAUDE.md`/`MIGRATION_GUIDE.md` are already a clean superset of
   `migration`'s stale copies (`migration` never independently touched those
   files since divergence), so they merge automatically.
6. **Merge conflicts resolved:** `gcp/bigquery.py` (both `PARQUET_TO_TABLE`
   entries kept, purely additive) and `cli.py` (merged imports, merged
   `_display_tables_summary`'s table list, kept `product-pipeline`'s
   `_render_pipeline_header`-based run-pipeline banner as the strict
   superset of `migration`'s inline version).

**Rejected:**
- Chasing the whole-repo 85% coverage floor as originally decided in ticket
  8 — rejected per the user's mid-session correction; the number was never
  checked against the 73% baseline and most of the gap is unrelated to
  product parity.
- Leaving the repo-wide ruff/ty violations for ticket 4 — rejected: unlike
  the coverage floor (real effort, genuinely out of this ticket's scope),
  these were mechanical one-line fixes directly blocking *this* PR's CI,
  cheaper to fix than to defer.
- Chasing the CI failure to green fully — rejected: after the ruff/ty fixes,
  CI's remaining failure is 7 `--help`-output assertion tests failing only
  in the GitHub Actions runner (Typer/Rich renders differently there than
  locally, even with `CliRunner(env={"NO_COLOR": "1", "COLUMNS": "200"})`
  already set) — unrelated to product code, affects patient/CLI help tests
  broadly, and is a genuine investigation matching ticket 4's exact remit
  ("diagnose and fix why CI is red"), not a fact this ticket can close by
  deciding.

**Evidence:** executed — every claim above was verified by running the
actual command (`pytest`, `ruff`, `ty`, `coverage report --fail-under`,
`gh pr view`) against the real branches, not read from a plan or inferred.
Real tracker files on the mounted USB drive were used to derive exact
expected row/column counts for the new integration/e2e tests rather than
guessing.

**Tense:** current as of 2026-08-08 — PR #6 is `mergeable: MERGEABLE` right
now; CI's remaining failure is current, not a predicted consequence.

**Spawned:** none directly, but ticket 4 (CI still red) is now unblocked and
has a concrete lead (the Typer/Rich `--help` rendering diagnostic above) to
start from instead of a cold investigation.
