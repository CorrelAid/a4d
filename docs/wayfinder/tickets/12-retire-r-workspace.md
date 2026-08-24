---
id: 12
title: Retire R from the workspace once the pipeline is fully verified Python-only
labels: [wayfinder:task]
status: open
blocked_by: [62]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Standing rule for this ticket's blocking

**R is retired only when no open ticket, and nothing in the codebase, still
needs to read the old R source for comparison** (stated by the user
2026-08-20, confirming the wiring round 10 applied).

`blocked_by` is therefore a *derived* list, not a fixed one: it holds whichever
open tickets currently need R, and it is re-derived whenever a ticket closes or
a new one is spawned. A ticket spawned later that needs to read `r-archive/`
gets added here without further argument -- that is the rule working, not a
delay. The frozen output baseline on the data drive
(`/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r/`) is not part of this: it
lives outside the repo and this ticket never touches it. What is gated is the
**R source** in `r-archive/`, which past triage has repeatedly had to read to
root-cause a mismatch -- reading R's output alone has not been enough.

This ticket was unblocked prematurely once (2026-08-15) by treating spawned
residuals as out of scope, and the correction cost a session. When in doubt,
it stays blocked.

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

**2026-08-18 (ticket 49 closed).** `blocked_by` swaps `49` for `50`. Ticket 49
did not empty the patient raw-stage residual (229 -> 84) and, more to the
point, needed `r-archive/`'s own source to close: root-causing the Mukdahan
header gap meant reading `script1_helper_read_patient_data.R` and
`script2_sanitize_str.R` and *running* R's sanitizer against the real header to
confirm its Unicode behaviour. That is the same reason this ticket has waited
each round -- [ticket 50](50-triage-patient-raw-residual-6.md) inherits it.

## Premise update (session-2026-08-18b)

[Round 6](50-triage-patient-raw-residual-6.md) closed and the patient **raw**
stage is at **zero** unclassified mismatches -- the first stage of either arm to
reach it. That does not unblock this ticket: the cleaned stage still carries
7,967 unclassified mismatches across 27 columns, and that triage is exactly the
kind that has repeatedly had to read `r-archive/`'s own source to root-cause a
difference. `blocked_by` swaps `50` for [ticket
51](51-triage-patient-cleaned-residual-4.md), the cleaned-stage round the raw
work spawned. Same precedent as every swap above.

## Premise update (session-2026-08-19)

[Round 4](51-triage-patient-cleaned-residual-4.md) closed, cutting the
cleaned-stage in-scope residual from 5,031 to **2,538** and landing three named
causes -- and its work again turned on reading `r-archive/`'s own source
(`script2_helper_dates.R`'s `ymd`-before-`dmy` order, `script2_sanitize_str.R`'s
Unicode-aware character class, and a grep proving R has no future-date guard at
all). R cannot be retired while triage still needs to read it. `blocked_by`
swaps `51` for [ticket 52](52-triage-patient-cleaned-residual-5.md), the round
it spawned. Same precedent as every swap above.

**2026-08-19c (ticket 53 closed).** `blocked_by` swaps `53` for [ticket
54](54-triage-patient-cleaned-residual-7.md) on the same standing precedent:
round 6 read R's own `split_bp_in_sys_and_dias`
(`script2_helper_patient_data_fix.R:623-653`) to establish why R keeps a blood
pressure Python was discarding, so triage still depends on `r-archive/` being
present.

**2026-08-19d (ticket 54 closed).** `blocked_by` swaps `54` for [ticket
55](55-triage-patient-cleaned-residual-8.md) on the same standing precedent:
round 7 read R's own commented-out `fix_t1d_diagnosis_age` call site
(`script2_process_patient_data.R:251`) to establish why R never derives a
diagnosis age, and round 8's first task is reading R's `fix_fbg` for the same
kind of answer. Triage still depends on `r-archive/` being present.

**2026-08-19e (ticket 55 closed).** `blocked_by` swaps `55` for [ticket
56](56-triage-patient-cleaned-residual-9.md) on the same standing precedent:
round 8 read R's `fix_fbg`, `transform_cm_to_m`, `cut_numeric_value` and the
mutate that sequences them, all directly from `r-archive/`, to establish that
R manufactures glucose readings from text and that its height threshold is the
correct one. Round 9's leading shape points at R's own
`extract_date_from_measurement`. Triage still depends on `r-archive/` being
present.

**2026-08-19f (ticket 56 closed).** `blocked_by` swaps `56` for [ticket
57](57-triage-patient-cleaned-residual-10.md) on the same standing precedent,
and this round is the sharpest example yet of why R has to stay: closing it
required *installing lubridate and executing* R's `parse_dates` -- its
fourth-letter truncation and its eight-order fallback list -- over the actual
source strings, because reading the function was not enough to predict which
cells it would sentinel and which it would misread. Round 10's largest group is
R's `extract_date_from_measurement`, which will need the same treatment.
Triage still depends on `r-archive/` being present.

**2026-08-20 (ticket 57 closed -- the round chain ends).** Round 10 converged:
the patient cleaned-stage residual is 19 cells, all with written verdicts, and
there is no round 11. So `blocked_by` does not swap `57` for a successor -- it
drops `57` and gains `[32, 39, 44, 47]`.

That is a change of kind, not just of contents, so it is argued rather than
applied. This ticket has been swapping one round for the next on a standing
precedent: **R cannot be retired while triage still needs to read it.** With the
rounds finished, the four open tickets that still need R as a live reference
are the ones that inherit that precedent:

- [Re-audit every existing cause classifier](32-audit-classifiers-against-decision-bar.md)
  -- by definition it re-reads R's source to check each verdict.
- [Dates buried in clinical notes](39-recover-dates-embedded-in-free-text.md)
  -- 478 cells, still an open question, and round 6 measured 179 of them running
  the opposite direction.
- [The cleaned-stage FBG R-null residual](44-triage-cleaned-fbg-r-null-residual.md)
  -- 2,936 cells, the single largest unexplained population left anywhere.
- [Four trackers where cleaning merges several patients into one patient
  ID](47-patient-ids-merged-at-cleaning.md) -- a correctness question whose
  evidence includes R's own row handling.

The alternative -- treating all four as residuals of already-closed scope and
letting R retire now, which is the precedent this map used for tickets 24-28 --
was rejected because this ticket has already been unblocked prematurely once
(2026-08-15) on exactly that reasoning, and the correction cost a session.
Reversible: dropping any of the four from `blocked_by` is a one-line edit if the
user judges R unnecessary for it.

**2026-08-21 (ticket 39 closed).** `blocked_by` drops `39`, leaving `[32, 44]`
of the open tickets that still need `r-archive/`'s source. [Dates buried in
clinical notes](39-recover-dates-embedded-in-free-text.md) needed R read twice
-- to establish that `parse_dates` composes 2019-03-20 out of three separate
dates in one note, and that its order list ends in `y`, which is why a bare
year in prose becomes 1 January -- so it earned its place on this list and has
now spent it.

**2026-08-21b (ticket 44 closed).** `blocked_by` drops `44`, leaving **`[32]`
alone** -- [the classifier re-audit](32-audit-classifiers-against-decision-bar.md)
is the last open ticket on this map that needs `r-archive/`'s source, and it
needs it by definition, since re-auditing a classifier means re-reading the R
function it claims to describe. [The FBG R-null
residual](44-triage-cleaned-fbg-r-null-residual.md) spent its place on `fix_fbg`
and R's `fbg/18` cross-derivation, both read to establish that the mmol column
is derived rather than recorded on either side.

That makes this ticket **one decision away from the frontier** for the second
time. The first attempt was premature (see above), and the difference now is
that the reason for waiting has narrowed to a single named ticket rather than a
population of residuals nobody had counted.

**2026-08-22 (ticket 32 closed).** `blocked_by` was `[32]` in substance. Ticket
32 closed, but it split: [the second half of the
audit](60-audit-remaining-pre-bar-classifiers.md) inherits eight pre-bar causes
whose mechanisms are statements about R's own source (`r_extraction_gap`,
`r_validator_rejects_multivalue`, `r_category_lookup_miss`,
`buddhist_era_typo`), so it needs `r-archive/` by definition -- the same
standing precedent that has governed this list for ten rounds.

Re-derived rather than swapped, per this ticket's rule. `blocked_by` is now
**`[59, 60]`**:

- **60** for the reason above.
- **59** ([rows that pair with nothing](59-triage-unmatched-row-keys.md)) is
  added, and this is a *change of judgement* rather than a new fact: its largest
  population is 98 R-only rows in `2026_Preah Kossamak`, and explaining why R
  emits rows Python does not is a question about R's row handling, not about
  Python's output. Ticket 58 stays off the list on the distinction the previous
  session drew -- its evidence is Python's own join and the source workbooks.
- **61** ([Buddhist-era conversion](61-decide-buddhist-era-date-conversion.md))
  is deliberately *not* a blocker: the one fact it needs about R -- that R does
  not convert BE dates -- is already established from R's frozen output, and the
  decision itself is about what Python should publish.

**2026-08-24 ([rows that pair with nothing](59-triage-unmatched-row-keys.md)
closed).** `blocked_by` drops `59`, leaving **`[60]`**. The judgement that put
59 on the list held: answering it did require reading `r-archive/`'s source --
`script1_helper_read_patient_data.R:67`, R's hardcoded `+1` row offset for
2022+ trackers, which is what makes R drop `2024_Mandalay Children's` first
patient from 11 of 12 sheets. Re-derived rather than swapped: of the seven
tickets still open, only [the eight pre-bar
causes](60-audit-remaining-pre-bar-classifiers.md) needs the R source, and it
needs it by definition. **One ticket now stands between this map and retiring
R.**
