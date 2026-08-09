---
id: 12
title: Retire R from the workspace once the pipeline is fully verified Python-only
labels: [wayfinder:task]
status: open
blocked_by: [15]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Rests on the same destination redraw as [ticket 10](10-performance-profiling.md)
and [ticket 11](11-cli-ux-observability.md): the user confirmed workspace
cleanup is part of "are we really ready to roll out", not separate follow-on
work.

[Retire the PDF/notebook analysis docs for an automated, script-based
report](02-documentation-strategy.md) is now closed: the comparison script's
design decided the R baseline is the already-frozen
`/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r/`, which lives on the data
drive, not in this repo — so this ticket's original premise ("need R
available as a live reference to check against") no longer applies, since
retiring `r-archive/` was never going to touch that frozen baseline.
[Profile the combined pipeline's performance against the R baseline before
promoting to dev](10-performance-profiling.md) is also closed (R comparison
was dropped from that ticket entirely). This ticket is now blocked instead on
[ticket 15](15-build-and-run-comparison-script.md) — not because retiring
`r-archive/` needs R itself, but because the triage work in ticket 15 is
still investigative and might turn up a need to consult R's logic/behavior
one more time before it's gone for good; safer to keep this ticket blocked
until that work concludes.

Not blocked on [ticket 11](11-cli-ux-observability.md): the user confirmed
`tools/LogViewerA4D` (an R Shiny app another developer wrote for viewing R
logs) needs no Python replacement — it can simply be deleted, independent of
whatever ticket 11 decides for the Python CLI's own observability.

**Conflict on record, not resolved here:** `CLAUDE.md` currently states
`r-archive/` is "preserved for reference. Do not modify." — that instruction
will need to change (or be explicitly overridden) as part of resolving this
ticket, not before. The user has confirmed intent to remove R once everything
is verified, and noted the deletion is low-risk regardless — it stays in git
history (this branch's own history, pre-squash) even after removal.

Inventory of what "remove R" touches (verified via `git ls-files`, not
assumed):
- `r-archive/` (1.9M, git-tracked) — the archived R package — **remaining**
- ~~`tools/LogViewerA4D/` (git-tracked) — R Shiny log-viewing app~~ —
  **deleted early** (2026-08-09, out of sequence): the user confirmed it
  needed no Python replacement before this ticket's other blockers closed, so
  it was removed immediately rather than waiting; its feature set was first
  captured in [ticket 11](11-cli-ux-observability.md) as prior art. This
  ticket stays open for the rest of the inventory.
- `test_full_pipeline_debug.R` (git-tracked, repo root) — stray debug script
  — **remaining**
- `docs/CLAUDE.md`'s note that `reference_data/` is "shared with the archived
  R pipeline" — needs re-wording once R is gone — **remaining**
- `CLAUDE.md`'s own "R Archive" section and its "do not modify" instruction
  — **remaining**

## Question

Once tickets 2 and 10 are closed and the user is confident in rollout: decide
what "remove R" means concretely (delete outright vs. move to a separate
archive location/repo vs. keep read-only in git history only) for each
remaining item in the inventory above, update `CLAUDE.md` and `docs/CLAUDE.md`
to match, and execute the cleanup.
