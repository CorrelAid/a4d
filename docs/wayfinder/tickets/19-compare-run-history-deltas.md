---
id: 19
title: Persist comparison run history and show run-over-run deltas
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-11
claimed_at: 2026-08-11
resolution: decided
evidence: executed
closed_by: null
spawned_by: 17
---

## Premise

Rests on [Fix the product comparison's row-alignment key, then triage every
flagged R/Python difference](17-fix-product-row-alignment-and-triage.md),
closed, and the same session's follow-up conversation about how to work
[Triage every flagged R/Python difference for both arms, and resolve the
189-vs-155-tracker discrepancy](18-triage-comparison-flagged-differences.md):
`build_summary_rows()` (`src/a4d/migration/compare.py`) already computes
`per_column`/`per_cause` mismatch counts per stage on every
`just compare-outputs` run, but nothing persists them — each run only ever
sees the current numbers, with no way to tell whether a fix made in ticket
18 (or any later triage session) actually reduced the count it targeted, or
whether an unrelated pipeline change regressed one that was previously
clean.

Agreed in the same conversation: ticket 18's triage will classify causes
opportunistically (start `unclassified`, add a named classifier the moment
a real pattern is noticed, drop it if it turns out not to earn its keep) —
this run-over-run comparison is what will make a fix's actual effect
visible directly (count before vs. after), rather than needing classifiers
to prove a fix worked.

## Question

Design and implement: after each `compare_outputs.py` run, persist a
compact snapshot of that run's `per_column`/`per_cause` counts (per stage),
and on the next run, load the most recent prior snapshot for that stage and
report a delta (previous vs. current, per column and per cause) alongside
the normal report -- both in the console summary and as an extra sheet in
the stage's Excel workbook. Keep a short history (not just the single most
recent run) so a regression introduced gradually over several runs stays
visible rather than only showing the last hop.

This is tooling to support ticket 18's triage, not triage itself -- keep it
scoped to the persistence/delta mechanism.

## Resolution

**Decision.** Implemented run-over-run history exactly as scoped:
`snapshot_from_summary()`/`compute_deltas()`/`Delta`
(`src/a4d/migration/compare.py`) are pure, unit-tested (11 new tests) --
`snapshot_from_summary` reduces a `build_summary_rows()` result to a plain
`{"per_column": {...}, "per_cause": {...}}` dict; `compute_deltas` diffs two
such count-dicts and returns only the changed keys (a key dropping to zero
or appearing new from zero both show up, since either side defaults to 0).

**Refined further in the same session, after the user reviewed the first
cut:** the CLI's output layout changed twice more. First, `--report-out`
(a single filename the tool then derived four sibling files from, e.g.
`compare_report_product_data_cleaned.xlsx`) was renamed to `--output-dir`
(default `output/comparison`) -- naming a file was misleading when the tool
always writes several. Then, on the user's explicit request ("each run
lands in its own folder"), every stage of one `compare_outputs.py`
invocation now writes into a single shared subfolder named by that
invocation's UTC timestamp (`output/comparison/<run-timestamp>/`) rather
than a flat `compare_history/<subdir>/` tree -- each run is now a
self-contained unit on disk (its four Excel reports and four
`snapshot_<subdir>.json` files together), which is also simpler to browse
and to `rm` wholesale if ever needed. `_load_latest_snapshot` walks
sibling run directories (excluding the one just created), newest first,
and returns the first one that has a snapshot for the requested stage --
still tolerant of a stage missing from some earlier run. The CLI both
prints a delta table to the console (red for a regression, green for an
improvement) and adds `history_column_deltas`/`history_cause_deltas`
sheets to that stage's Excel workbook. History isn't pruned -- every run's
folder stays on disk, so a multi-run trend is reconstructable later even
though this ticket only wires up latest-vs-current by default.

Also, prompted by the same review: did a pass over `scripts/` and removed
ten stale one-off debug scripts left over from before this map's work
started (`check_sheets.py`, `compare_r_vs_python.py`,
`export_single_tracker.py`, `profile_extraction.py`,
`profile_extraction_detailed.py`, `reprocess_tracker.py`,
`test_cleaning.py`, `test_extended_trackers.py`,
`test_multiple_trackers.py`, `verify_fixes.py`) -- all hardcoded to a
drive layout (`.../A4D/data/a4dphase2_upload/...`,
`output/patient_data_raw/R/`) that no longer matches the real one, and all
superseded by either the real `tests/` pytest suite, ticket 10's
`pyinstrument`-based profiling, or this ticket's own comparison tool.
Fixed two now-dangling references to the deleted
`compare_r_vs_python.py` (in `verify_production_run.py` and
`src/a4d/gcp/verify.py`, both now pointing at `compare_outputs.py`) and
one stale hardcoded path in the kept `analyze_logs.sql`.

**Because.** This was a small, self-contained, already-agreed design (settled
in conversation before this ticket was even opened) with no open questions
left to resolve -- straight implementation was the right size for the
ticket, consistent with this map's task-ticket convention of implementing
immediately rather than stopping at a decision.

**Rejected.**
- Diffing every pair of historical snapshots (not just latest-vs-current) on
  every run -- rejected as unnecessary scope: the ticket's own text asked for
  history to be *retained* so a multi-run trend stays visible, not for
  automatic multi-way analysis; latest-vs-current is what a triage session
  actually needs turn to turn, and the retained files support a manual
  deeper look later if ever needed.
- Pruning old snapshots (e.g. keep last N) -- rejected: the files are tiny
  (a few KB of JSON per stage per run) and this migration-only tool has a
  defined end-of-life (R's retirement, ticket 12), so unbounded retention
  isn't a real storage concern for its lifetime.

**Evidence.** *Executed*: ran `just compare-outputs` against the real
R/Python output pair on the USB drive multiple times across both the
flat-history and final per-run-folder layouts, each time confirming the
full lifecycle end to end -- first run correctly reports "no previous run
to compare against," a second run (identical inputs) correctly reports "no
change from the previous run" for all four stages and lands in its own new
timestamped folder, and a synthetic edit to a snapshot file (simulating a
triage fix plus a regression) confirmed the delta table and Excel sheets
render correctly (`product_category` 18,638 -> 13,638 shown as `-5000`;
`product_sheet_name` 0 -> 201 shown as `+201`). Confirmed no remaining
references to any deleted script (`grep` across the repo). Full suite (552
tests, up from 545), ruff, `ty check` all pass.

**Tense.** All claims describe current, implemented, merged behavior
(executed) -- not a design proposal.

Commits: `7c90645` (initial), `5d62865` (`--output-dir` / per-run-folder
refinement and `scripts/` cleanup).
