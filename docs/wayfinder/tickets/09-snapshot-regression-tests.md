---
id: 9
title: Add golden-master/snapshot regression tests for patient and product
labels: [wayfinder:task]
status: open
blocked_by: [6]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 8
---

## Premise

Rests on [Does the pytest suite reach unit/integration/e2e/regression parity
between patient and product, excluding any R-comparison/USB-drive-dependent
tests?](08-pytest-suite-parity.md): "regression test" here means
golden-master/snapshot testing, not R-comparison or edge-case testing — a
fixed synthetic input tracker, with every pipeline stage's output (raw
extract, cleaned, tables) committed as a snapshot, so an unintended output
change from a future code edit fails the test while an intended one gets its
snapshot deliberately updated. It needs no real/sensitive data — correctness
against source truth is already covered by
`test_validate/test_*_source_vs_output.py`; this only checks output
stability across changes. No snapshot library exists in the repo yet
(`syrupy`/similar absent from `pyproject.toml`/`uv.lock`).

Blocked on [Promote migration into dev via PR #2](06-promote-migration-to-dev.md)
per the user's explicit instruction: build this only once both pipelines'
other test suites (unit/integration/e2e per ticket 8, plus whatever ticket 2
and the rest of the merge/CI/production-verification chain settles) are in
place and green, so there is a stable, trusted base to snapshot against
rather than freezing a moving target.

The fixture tracker is likely the same synthetic source data already used
elsewhere in the suite (per the user, "yes it will be the same source data
likely") rather than a new one purpose-built for this ticket — confirm
against whatever fixture tracker(s) exist in `tests/` by the time this is
picked up.

## Question

Pick and add a snapshot-testing library (`syrupy` is the standard choice for
pytest — confirm or reconsider at pickup time), design one fixed synthetic
input fixture per pipeline (patient, product) reusing existing test fixture
data where possible, and wire snapshot tests covering each pipeline stage's
output (raw extract, cleaned, final tables) so that any future code change
producing an unintended output delta fails the test, with a clear,
documented path to intentionally update a snapshot when the change is
deliberate.
