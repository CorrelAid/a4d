---
id: 10
title: Profile the combined pipeline's performance against the R baseline before promoting to dev
labels: [wayfinder:task]
status: closed
blocked_by: [3, 13]
assignee: session-2026-08-09d
claimed_at: 2026-08-09
resolution: decided
evidence: executed
closed_by: null
spawned_by: null
---

## Premise

Rests on [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md),
closed: `migration` now carries the combined patient + product pipeline, plus
everything else landed in that merge (the two logging-parity fixes, the
product-only coverage gate). The user's standing understanding is that the
Python pipeline is much faster than the archived R pipeline, but that
comparison predates this merge's additions and the product arm's own cost —
nobody has re-profiled since. This is a fresh concern raised mid-[ticket
5](05-production-verification-run.md) session, not derived from any ticket's
resolution.

Not blocked on [ticket 5](05-production-verification-run.md) itself — profiling
can run against local or production-scale data independent of that ticket's
verification outcome — but both are gating promotion (ticket 6), and ticket 5's
production run may end up a convenient source of real timing data if it's
still fresh when this ticket is worked.

**Now also blocked on** [Audit and update all dependencies and library
versions before rollout](13-dependency-audit.md) — added after it surfaced
mid-session too: profiling against a dependency set that's about to be
updated would make the numbers stale immediately, so the audit needs to land
first.

## Question

Define what "profile before going live" means concretely: which pipeline
stages to measure (extract/clean/tables per arm, or end-to-end), what data
volume to profile against (local fixtures vs. a full production-scale run),
what the R baseline comparison point is (the archived R pipeline's own past
timings, if any were recorded, or a fresh run of `r-archive/` for comparison),
and what regression or absolute-time threshold would block promotion to `dev`.
Then execute the profiling and record the result.

## Resolution

**Decision:** No R baseline comparison — the user corrected the ticket's
original framing mid-session: R is already known to be much slower, so
re-confirming that is a wasted exercise. Instead this ticket became a
function-level performance and robustness profile of the Python pipeline
itself, to help answer "is this strong enough to merge to dev" — not a
rewrite, but finding and fixing concrete issues surfaced by the profile
(the user's explicit framing).

**Method:** `pyinstrument` (statistical/sampling profiler, chosen for low
overhead and a readable call-tree vs. `cProfile`'s flat stats table) wrapped
around `a4d.cli process-patient` / `process-product`, run with `--workers 1`
so the profiler's single process sees inside the pipeline rather than losing
visibility into `ProcessPoolExecutor` subprocess workers. Data: the full
177-tracker real production dataset from the USB drive
(`/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload`), at the user's
suggestion, since the current production trackers aren't available locally
outside GCP.

**Found and fixed:** `find_data_start_row` (`src/a4d/extract/patient.py`)
looped calling `ws.cell(row_idx, 1).value` once per row until it found the
first numeric value in column A. On a `read_only=True` openpyxl worksheet,
`ReadOnlyWorksheet._get_cell` re-parses the sheet's XML from row 1 on *every*
call (`_cells_by_row` reopens the XML source and re-runs `WorkSheetParser`
each time) — read-only worksheets are built for sequential streaming, not
random access. A per-row `.cell()` loop is therefore O(n^2) in the row count
before data starts. Profiling one large real tracker
(`2019_Yangon Children's Hospital A4D Tracker.xlsx`) showed this function
alone consuming 7.885s of 8.965s total (88%) for that single file. Fixed by
replacing the loop with a single `ws.iter_rows(min_col=1, max_col=1,
values_only=True)` sequential scan (`_cells_by_row` called once regardless
of row count). Verified: same file now processes in 1.376s (6.8x), and the
full patient arm across all 171 real trackers (4 parallel workers, unprofiled
wall-clock, identical output row counts before/after — 1,457 static / 64,007
monthly / 2,218 annual / 37,030 errors) went from 145.8s to 22.0s (6.6x). Full
combined patient+product run (`run-pipeline --skip-download --skip-upload
--skip-drive-download --force`, 4 workers): 73.86s wall, ~556MB peak RSS
(macOS `/usr/bin/time -l` on the top-level process only — doesn't capture
`ProcessPoolExecutor` worker subprocess memory, so treat as a rough floor,
not exhaustive). Added a regression test
(`tests/test_extract/test_patient_helpers.py::test_scans_read_only_worksheet_in_one_pass`)
that spies on `ReadOnlyWorksheet._cells_by_row` and asserts it's called
exactly once on a dense sheet — confirmed it fails against the pre-fix code
and passes against the fix. All 489 tests, ruff, and `ty check src/` pass.
Pushed as part of this ticket's session.

**Other finding, not fixed here:** running `process-product` against the
same full dataset surfaced 4 trackers failing outright with `unable to find
column "product"; valid columns: ["index"]` (2020 Jayavarman VII, and 2018/
2019/2020 Kantha Bopha) — reproduces identically before and after this
ticket's fix, so unrelated to it, and not previously documented anywhere on
this map. Out of this ticket's scope (a correctness bug, not a performance
one); spawned [ticket 14](14-product-column-detection-failures.md) rather
than fixed inline, to keep this session to one ticket.

**Rejected:** a full architecture re-review beyond what the profile itself
surfaced — general code-quality review already happened in [ticket
3](03-merge-product-pipeline.md)'s merge review, and CLI/observability is
[ticket 11](11-cli-ux-observability.md)'s separate territory; re-litigating
either here would have sprawled past one ticket. A stricter regression/
absolute-time threshold to gate promotion — not set, since the R-comparison
framing that would have anchored one was explicitly dropped; 73.86s for the
full combined real-dataset run is judged fast enough on its own that no
threshold is needed to justify promotion on performance grounds.

**Evidence:** executed throughout — every number above (profile self-times,
before/after wall-clock timings, test pass/fail, memory) came from running
the actual code against real production-scale data, not read from docs or
inferred.

**Tense:** all current behaviour — the fix is merged into this branch's
working tree, not a proposal.
