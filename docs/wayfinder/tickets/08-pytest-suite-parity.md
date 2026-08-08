---
id: 8
title: Does the pytest suite reach unit/integration/e2e/regression parity between patient and product, excluding any R-comparison/USB-drive-dependent tests?
labels: [wayfinder:grilling]
status: closed
blocked_by: [7]
assignee: session-2026-08-08
claimed_at: 2026-08-08
resolution: decided
evidence: judgement
closed_by: null
spawned_by: 1
---

## Premise

Rests on [Does product-pipeline's test suite meet the same cell-by-cell rigor
as patient's?](01-product-pipeline-test-rigor.md), closed as superseded: that
session decided R-vs-Python comparison does not belong in pytest (it's
analysis, owned by [Retire the PDF/notebook analysis docs for an automated,
script-based report](02-documentation-strategy.md)), and that pytest's job is
the ordinary category of unit/integration/e2e/regression tests that don't
require the USB drive.

Blocked on [Is the product pipeline (and patient's own claimed completeness)
actually complete and sound, audited against R's product logic and patient's
structure?](07-pipeline-completeness-audit.md) — that ticket produces the
file-by-file test-coverage inventory this ticket needs as its starting fact
base; deciding pytest-suite parity before the inventory exists would mean
re-deriving it from scratch mid-discussion.

## Question

Given the inventory from ticket 7: what, concretely, does pytest-suite parity
between patient and product require — same module-level unit test coverage,
same integration/e2e shape, same regression-test discipline for known fixed
issues? Decide what to do with patient's `test_r_validation.py` specifically
(move out of pytest entirely, e.g. into whatever ticket 2's automated report
becomes, or keep as an opt-in `@pytest.mark.slow` marker but stop treating it
as part of "the test suite" proper) and whether product needs an equivalent
non-R-comparison regression suite before this ticket can close.

## Resolution

**Decision:** Parity means: (1) a 85%+ line-coverage floor across the pipeline,
enforced in CI via `--cov-fail-under=85` added to the existing
`pytest -m "not slow and not integration" --cov --cov-report=xml` line in
`.github/workflows/python-ci.yml`; (2) product gets the three integration/e2e
files it is currently missing entirely — `test_integration/test_extract_integration.py`,
`test_integration/test_clean_integration.py`, `test_integration/test_e2e.py` —
built with the exact same convention patient already uses (fixtures pointing
at real tracker files on the USB drive via `TRACKER_BASE`, `skip_if_missing()`
skipping cleanly when the drive isn't mounted, `@pytest.mark.integration`/`e2e`
excluding them from CI); the new extract-integration test covers
`wide_format.py` (currently zero references anywhere in the product suite);
(3) `tests/test_tables/test_product.py` is added, testing
`create_table_product_data` directly rather than only reaching it indirectly
through `test_link_product_patient.py`.

**`test_r_validation.py`:** removed from pytest entirely — no opt-in marker,
no product equivalent. It moves out to wherever ticket 2's automated
analysis report ends up living; "the test suite" (patient or product) no
longer contains any R-comparison code, confirming ticket 1's original split.

**Regression tests — reframed, and split into a new ticket.** The initial
framing (a non-R-comparison edge-case regression suite, "the crown," needing
investigation because of the sensitive-data constraint) was based on a
misunderstanding of what the user meant by "regression test." The actual ask
is golden-master/snapshot testing: a fixed synthetic input tracker, with
every pipeline stage's output (raw extract, cleaned, tables) committed as a
snapshot; any future code change that alters output unexpectedly fails the
test, and an intended change gets its snapshot deliberately updated. This
needs no real/sensitive data at all — the point is output stability across
changes, not correctness against source, so a small synthetic fixture
tracker suffices (correctness against source truth is what
`test_validate/test_*_source_vs_output.py` already checks). No snapshot
library exists in the repo yet (`syrupy`/similar absent from
`pyproject.toml`/`uv.lock`). This is real, separate infrastructure work
(pick and add `syrupy`, design the fixture, wire snapshots per pipeline
stage) rather than a fact this ticket can close by deciding — spun off as
[Add golden-master/snapshot regression tests for patient and product](09-snapshot-regression-tests.md),
explicitly deferred by the user until both pipelines' other test suites are
in place and green, so there is a stable base to snapshot against.

**Because:** The integration/e2e approach mirrors what patient already does
successfully rather than inventing a new pattern — same fixture convention,
same CI exclusion, same drive-gating. The coverage floor gives "parity" a
checkable number instead of leaving it qualitative. Splitting snapshot
testing out keeps this ticket's decision (what parity requires) separate
from a design/build task (how to implement golden-master tests), consistent
with the map's own split-rather-than-sprawl rule.

**Rejected:**
- A product equivalent of `test_r_validation.py` — rejected per ticket 1's
  standing decision (R-comparison is analysis, not a pytest concern); would
  have re-introduced exactly what was ruled out.
- Deciding golden-master/snapshot testing's design inline in this ticket —
  rejected: it's build work (pick a library, design fixtures, wire multi-stage
  snapshots) not a fact to establish, and the user explicitly wants it
  deferred until both pipelines are green, so deciding its shape now would be
  premature relative to when it will actually be built.
- No coverage floor / qualitative-only parity — rejected: "same test
  categories" without a number leaves parity unfalsifiable; 85% gives CI
  something to actually enforce.

**Evidence:** judgement (the parity bar and the split decisions are user
calls; the supporting facts — CI's current pytest invocation, patient's
fixture/skip-if-missing convention, the absence of a snapshot library — were
verified via `grep`/`git show`, i.e. read/executed, but the resolution as a
whole is stamped at the weaker judgement level).

**Tense:** current for all cited facts (CI config, patient's fixture
convention, dependency list) as of 2026-08-08; the parity requirements and
the snapshot-test plan are consequences of this decision, not yet built.

**Spawned:**
[Add golden-master/snapshot regression tests for patient and product](09-snapshot-regression-tests.md).
