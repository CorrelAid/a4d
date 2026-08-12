---
id: 12
title: Retire R from the workspace once the pipeline is fully verified Python-only
labels: [wayfinder:task]
status: open
blocked_by: [20, 21, 22, 23, 24, 25, 26, 28, 29, 30, 31, 36]
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
was dropped from that ticket entirely). [Build and run the R/Python output
comparison script, then triage every flagged
difference](15-build-and-run-comparison-script.md) is now closed too — it
built and ran the comparison tooling but split the actual triage into
[ticket 17](17-fix-product-row-alignment-and-triage.md) after finding
product's row-alignment key was broken. Ticket 17 is now closed too — it
fixed and validated the row-alignment key but the actual per-column triage
still didn't converge, splitting again into [ticket
18](18-triage-comparison-flagged-differences.md). Ticket 18 is now closed
too — it root-caused `product_category` and most of `product_entry_date`,
but the remaining columns and the entire patient arm still didn't converge,
splitting into [ticket 20](20-fix-raw-entry-date-representation.md),
[ticket 21](21-triage-remaining-product-columns.md), [ticket
22](22-triage-product-raw-columns.md), and [ticket
23](23-triage-patient-arm.md). This ticket is blocked on all four instead of
ticket 18 — not because retiring `r-archive/` needs R itself, but because
that triage work is still investigative and might turn up a need to consult
R's logic/behavior one more time before it's gone for good; safer to keep
this ticket blocked until that work concludes.

**Correction (2026-08-12c):** tickets 20-23 closing does not mean this
ticket is actually unblocked — that was a premise error caught mid-session,
before any commit landed. Tickets 20-23 spawned five further residual
tickets (24, 25, 26, 27, 28) that carry forward the exact same "might need
to consult R's source" risk this ticket already names as its reason for
waiting: past triage repeatedly needed to read `r-archive/`'s actual R
source to root-cause a mismatch (e.g. ticket 18 reading
`read_product_data.R`'s `add_product_categories()` join logic directly),
not just diff output. Ticket 28 in particular (patient cleaned-stage,
120,639 mismatches across 61 columns) is entirely untouched and most likely
to need the same. `blocked_by` corrected to `[20, 21, 22, 23, 24, 25, 26,
27, 28]`. No files were deleted as part of this correction — `r-archive/`
was briefly staged for removal outside this ticket's own execution and was
restored before anything was committed.

Not blocked on [ticket 11](11-cli-ux-observability.md): the user confirmed
`tools/LogViewerA4D` (an R Shiny app another developer wrote for viewing R
logs) needs no Python replacement — it can simply be deleted, independent of
whatever ticket 11 decides for the Python CLI's own observability.

**Same precedent applied again (2026-08-12f):** [ticket
27](27-triage-patient-raw-residual.md) closed for its two original leads
(fixed) but explicitly left `complication_screening` (12,566 mismatches,
84% of what remains) and roughly 50 smaller columns untouched, spawning
[ticket 31](31-triage-patient-raw-residual-2.md) to carry that forward.
`blocked_by` swaps `27` for `31`.

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
- ~~`test_full_pipeline_debug.R` (repo root) — stray debug script~~ —
  **already gone**: verified via `git log --all -- test_full_pipeline_debug.R`
  (2026-08-12c) it was removed by an earlier "remove deprecated files"
  commit, before this ticket was even written. No action needed.
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
