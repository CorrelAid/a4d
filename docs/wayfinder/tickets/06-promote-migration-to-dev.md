---
id: 6
title: Promote migration into dev via PR #2
labels: [wayfinder:task]
status: open
blocked_by: [8, 2, 3, 4, 5, 10, 11, 12, 13, 14]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Depends on every other ticket on this map: [Does the pytest suite reach
unit/integration/e2e/regression parity between patient and product, excluding
any R-comparison/USB-drive-dependent tests?](08-pytest-suite-parity.md) (and,
transitively, [Is the product pipeline (and patient's own claimed
completeness) actually complete and sound, audited against R's product logic
and patient's structure?](07-pipeline-completeness-audit.md)), [Retire the
PDF/notebook analysis docs for an automated, script-based
report](02-documentation-strategy.md), [Merge product-pipeline (PR #6) into
migration](03-merge-product-pipeline.md), [Diagnose and fix why CI is red at
migration HEAD](04-fix-migration-ci.md), [Define and execute the real GCP
production verification run](05-production-verification-run.md), [Profile
the combined pipeline's performance against the R baseline before promoting to
dev](10-performance-profiling.md), [Decide what CLI/TUI UX and error-log
observability improvements admins/developers need before
rollout](11-cli-ux-observability.md), [Retire R from the workspace once
the pipeline is fully verified Python-only](12-retire-r-workspace.md), and
[Audit and update all dependencies and library versions before
rollout](13-dependency-audit.md).

PR #2 (`migration` -> `dev`) already exists and is `mergeable: MERGEABLE`; it is
gated only on the work above landing first.

## Question

With the merge done, CI green, and a real production run validated, close out
PR #2 and merge `migration` into `dev`. This is the destination.
