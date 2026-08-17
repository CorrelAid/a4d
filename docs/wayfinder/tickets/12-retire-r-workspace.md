---
id: 12
title: Retire R from the workspace once the pipeline is fully verified Python-only
labels: [wayfinder:task]
status: open
blocked_by: [20, 21, 22, 23, 24, 25, 26, 28, 30, 31, 49]
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

**Same precedent applied a third time (2026-08-17b):** [ticket
43](43-triage-patient-raw-residual-3.md) closed for the two causes it
settled -- a comparison-tool rounding gap and a real Python defect that
invented 24 patient rows -- leaving 1,409 unclassified patient raw-stage
mismatches. Those split into [ticket
45](45-patient-row-alignment-duplicate-keys.md) (duplicate-key join fan-out,
57% of the residual) and [ticket
46](46-triage-patient-raw-residual-4.md) (the long tail). `blocked_by` swaps
`43` for `45, 46`. Ticket 43 itself again had to read
`script1_helper_read_patient_data.R` to establish how R bounds a sheet's
data block, so R's source remains a live reference for the triage that
remains -- the same reason this ticket has waited each time.

**2026-08-17c:** [Ticket 45](45-patient-row-alignment-duplicate-keys.md) closed
-- patient rows now align on `patient_id` + `sheet_name` with a content-matched
tie-break, and the duplicate-key fan-out is gone (raw unclassified 1,409 ->
601). `blocked_by` drops `45`, leaving **ticket 46 alone**. Ticket 45 also
spawned [ticket 47](47-patient-ids-merged-at-cleaning.md), deliberately *not*
added here: both pipelines merge those identities identically, so it is a
Python-only question that needs no R reference.

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

**Correction (session-2026-08-13b):** ticket 29 closed, spawning ticket 37
(the patient cleaned-stage residual it did not chase), so `blocked_by` swaps
`29` for `37`.

## Premise update (session-2026-08-14b)

[Ticket 38](38-triage-patient-cleaned-date-family.md) closed, so `blocked_by`
drops to `[20, 21, 22, 23, 24, 25, 26, 28, 30, 31]` — **tickets 30 and 31 are
now the only open blockers**, both patient raw-stage triage. Ticket 38's own
spawned residual, [ticket 39](39-recover-dates-embedded-in-free-text.md), is
deliberately *not* wired as a blocker here: it asks what Python should do with
a date buried in a clinical note, which is a question about Python's own
behaviour and needs no reference to R's source, so it survives R's retirement
intact.

## Premise update (session-2026-08-15b, ticket 31's session)

[Ticket 31](31-triage-patient-raw-residual-2.md) closed, but it spawned
[ticket 43](43-triage-patient-raw-residual-3.md) -- 1,879 patient raw-stage
mismatches still untriaged -- so `blocked_by` gains 43 rather than emptying.
The reason is the one that corrected this ticket's premise before: ticket 31
again had to read `r-archive/R/script1_read_patient_data.R` directly (R's
`tidyr::unite` call) to root-cause a divergence, so R's source is still a live
reference for the triage that remains. Ticket 43 is now this ticket's only
open blocker.

**2026-08-17 (ticket 48 closed).** `blocked_by` drops `48`: the merged-header
data loss is fixed, and its diagnosis needed R only as a reference for what the
right answer looks like -- confirmed by `2023_Chiang Mai`'s R output carrying
the same propagated column names. [Round-5 patient raw
triage](49-triage-patient-raw-residual-5.md) is now the single remaining
blocker.
