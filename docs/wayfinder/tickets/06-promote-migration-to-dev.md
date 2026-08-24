---
id: 6
title: Promote migration into dev via PR #2
labels: [wayfinder:task]
status: open
blocked_by: [8, 3, 4, 5, 10, 11, 12, 13, 14, 20, 21, 22, 23, 64]
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
and patient's structure?](07-pipeline-completeness-audit.md)), [Merge
product-pipeline (PR #6) into migration](03-merge-product-pipeline.md),
[Diagnose and fix why CI is red at migration HEAD](04-fix-migration-ci.md),
[Define and execute the real GCP production verification
run](05-production-verification-run.md), [Profile the combined pipeline's
performance against the R baseline before promoting to
dev](10-performance-profiling.md), [Decide what CLI/TUI UX and error-log
observability improvements admins/developers need before
rollout](11-cli-ux-observability.md), [Retire R from the workspace once the
pipeline is fully verified Python-only](12-retire-r-workspace.md), [Audit and
update all dependencies and library versions before
rollout](13-dependency-audit.md), and [Triage every flagged R/Python
difference for both arms, and resolve the 189-vs-155-tracker
discrepancy](18-triage-comparison-flagged-differences.md) — this last one
replaced [Retire the PDF/notebook analysis docs for an automated,
script-based report](02-documentation-strategy.md) in this list once that
ticket closed, was itself replaced by [Fix the product comparison's
row-alignment key, then triage every flagged R/Python
difference](17-fix-product-row-alignment-and-triage.md) once [Build and run
the R/Python output comparison script, then triage every flagged
difference](15-build-and-run-comparison-script.md) closed having built and
run the tooling but found product's row alignment broken before any triage
could happen, and was replaced again by ticket 18 once ticket 17 closed
having fixed and validated the alignment key but not converged on the
actual triage. The destination's own requirement that "every Python/R
difference [be] documented and explicitly decided" isn't satisfied until
ticket 18's triage is done.

PR #2 (`migration` -> `dev`) already exists and is `mergeable: MERGEABLE`; it is
gated only on the work above landing first.

## Question

With the merge done, CI green, and a real production run validated, close out
PR #2 and merge `migration` into `dev`. This is the destination.

## Premise update (session-2026-08-24f)

[Retiring R from the workspace](12-retire-r-workspace.md) closed, and with it
**every ticket in this list was closed** -- the first time this ticket has been
fully unblocked. It was re-blocked in the same session, on one new ticket, and
that is argued rather than applied.

`blocked_by` gains **64** ([Rewrite every docstring and doc that explains the
code by what R did](64-documentation-overhaul-drop-r-framing.md)). The user's
statement closing ticket 12 was that documentation justifying a behaviour by
"to match R" is not merely stale but **wrong**, now that the migration has
reached its end and R is gone. Thirty-five such citations are live in twelve
Python modules, including production cleaning code. Promoting `migration` into
`dev` is the act that turns this branch's documentation into the project's
documentation, so shipping it while it is wrong is the one thing this gate
exists to prevent -- the destination's own words are that the migration is
"detail-sensitive enough that things get missed unless checked".

The alternative -- promote now and fix the docs on `dev` afterwards -- was
rejected because it inverts the map's whole sequencing preference (make it
ready, *then* promote) and because a docstring citing a directory that no
longer exists is a defect a reviewer of PR #2 would reasonably raise.
Reversible: dropping `64` from this list is a one-line edit.

## Premise update (session-2026-08-24g)

[The documentation overhaul](64-documentation-overhaul-drop-r-framing.md) is
closed, so **every ticket in `blocked_by` is now closed and this ticket is
genuinely unblocked** -- for the first time, and this time without a
replacement. It is the last ticket on the route to the destination.

`blocked_by` is kept as the historical record of what gated the promotion; the
renderer reads it as satisfied because every entry is closed.

One open ticket was deliberately **not** wired here: [the logs table's two
R-named values](65-logs-table-r-named-values.md). The gate that ticket 64
satisfied was argued on documentation being *wrong*; ticket 65 is about
published field values being *inconsistent*, which is a different and lesser
claim, and fixing it changes BigQuery output rather than correcting a falsehood.
Reversible if the data owner would rather have it in before promotion.
