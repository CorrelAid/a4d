---
id: 6
title: Promote migration into dev via PR #2
labels: [wayfinder:task]
status: closed
blocked_by: [8, 3, 4, 5, 10, 11, 12, 13, 14, 20, 21, 22, 23, 64]
assignee: session-2026-08-24h
claimed_at: 2026-08-24
resolution: decided
evidence: executed
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

## Prepared, not merged (session-2026-08-24h)

The merge itself is a human-only action per the map's Notes, so this session
prepared it and stopped.

State verified rather than assumed, at head `ec12f48`:

- `mergeable: MERGEABLE`, `mergeStateStatus: CLEAN`.
- CI green on the head commit (both `test` jobs SUCCESS).
- `origin/dev` is an ancestor of `migration` and has **zero** commits
  `migration` lacks, so there is nothing to reconcile.
- Local and remote `migration` identical; working tree clean.
- Both recovery tags are on the remote:
  `r-archive-removed` -> `87530b1`, `migration-archive-frozen` -> `0dcc02d`.
- `dev` has **no branch protection**, so no review is required by the repo and
  nothing will block the button.
- `delete_branch_on_merge` is **false**, so `migration` survives the merge.

The PR body was replaced with the current `docs/archive/MR_DESCRIPTION.md`
(43,815 chars, was 23,547 and stale). Two claims in that document were false and
were corrected first: it opened with "**This MR is not ready to merge yet**",
and its "Still open" section said the listed work "blocks the merge". Neither
is true now.

**Open question for whoever merges: squash or merge commit.** Both are enabled.
Squashing collapses 285 commits whose messages are the migration's own
evidence trail and which the wayfinder tickets cite by SHA. The R-recovery
recipe survives either way -- an annotated tag pins its commit regardless of
merge strategy -- **provided the two tags above are never deleted**. That is
the one thing that would make `r-archive/` genuinely unrecoverable.

## Resolution (session-2026-08-24h)

**Decision.** `migration` is merged into `dev`. PR #2 is **MERGED**
(2026-08-24T20:55:49Z, by pmayd), and its recorded merge commit is
`9977228` -- the head commit itself, not a new merge node, because the merge
was done as a **local fast-forward** rather than through any of GitHub's three
buttons.

**Because.** GitHub offers no fast-forward option: "Create a merge commit"
always creates a merge node even when the branch is strictly ahead, "Rebase and
merge" rewrites every SHA, and "Squash and merge" collapses 288 commits into
one. A local `git merge --ff-only` was the only way to get a linear `dev`
*without* rewriting history, and the user preferred linear.

Verified after the fact rather than assumed:
- `origin/dev` and `origin/migration` are both `9977228`; `dev` has **zero**
  commits `migration` lacks, and no merge node was created.
- PR state is `MERGED`, not `CLOSED` -- GitHub matched the preserved head SHA,
  which is exactly what a fast-forward makes possible and what a local squash
  or rebase would have broken.
- Both recovery tags are **still ancestors of `dev`**: `r-archive-removed`
  (`87530b1`) and `migration-archive-frozen` (`0dcc02d`).
- `git show r-archive-removed^:r-archive/R/script2_process_patient_data.R`
  executed against the merged `dev` and returned the file, so the recovery
  recipe in `CLAUDE.md` is true of the mainline, not just of a tag-pinned
  orphan.

**Rejected.**
- *GitHub "Squash and merge"* -- would collapse 288 commit messages that are
  the migration's own evidence trail, and which wayfinder tickets cite by SHA.
- *GitHub "Rebase and merge"* -- rewrites all 288 SHAs, which would have
  detached both recovery tags from `dev`'s history and left the `CLAUDE.md`
  recipe depending solely on the tags never being deleted.
- *GitHub "Create a merge commit"* -- safe for tags and SHAs, and a perfectly
  good outcome, but adds a merge node that is not needed on a single-developer
  repo where the branch is strictly ahead.

**Evidence.** Executed. All checks above run against `origin` after fetching.
CI was green on `9977228` before the merge (both `test` jobs SUCCESS,
`mergeStateStatus: CLEAN`).

**Found on the way, and not what was predicted.** The two Dependabot alerts on
`dev` did **not** clear on the merge. They are not real exposure: both name
`scripts/python/poetry.lock`, a file that **does not exist on `dev`** -- it was
removed by `24125ae` ("Promote Python pipeline to root; archive R code"), long
before this map began. They are stale alerts against a deleted manifest, not a
gap in [the dependency audit](13-dependency-audit.md), which covered `uv.lock`.
Either the next Dependabot scan dismisses them, or they need dismissing by hand
as "no longer in use". No code change is warranted.
