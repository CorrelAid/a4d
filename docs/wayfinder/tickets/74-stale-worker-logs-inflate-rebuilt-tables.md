---
id: 74
title: A second local run doubles the rebuilt findings table, because last run's worker logs are still there
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-27
claimed_at: 2026-08-27T02:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 73
---

## Premise

Rests on [Unify the two separate channels that report data-quality
findings](66-unify-finding-channels.md), closed 2026-08-25, which built
`rebuild_findings_from_logs` so `a4d create tables` cannot refresh every table
and leave a stale findings table behind, and measured it **exact** -- 118,175
findings both ways, zero rows differing on eleven fields.

Rests on [Three workbook defects the pipeline detects, acts on, and never
reports](73-three-defects-detected-but-never-reported.md), closed 2026-08-27,
which found this while re-measuring: the rebuild returned 213,921 findings for
a run that produced 105,464.

Void if the per-run log directory stops being reused across runs -- which is
already true of production, and is exactly why this has never been seen there.
Merely in need of rewriting if the worker log naming changes.

## What was measured

Both consumers of `output/logs/` glob `*.log` and read **every file present**,
including the ones a previous run left behind. Per-tracker logs are overwritten
by name and so are safe; the worker logs are not, because their names carry a
run timestamp and a pid:

```text
main_worker_20260826_003142_pid21846.log      <- yesterday's run
main_worker_20260827_013742_pid79721.log      <- today's run
```

Nothing deletes the first. Measured on 2026-08-27 over the 255-tracker local
corpus, same trackers both times:

| | one run's logs present | two runs' logs present |
|---|---|---|
| `rebuild_findings_from_logs` | **105,464** (exact vs the run) | **213,921** |
| `create_table_logs` | **217,022** | **326,092** |

The findings table `a4d run` publishes is built from memory, not from the logs,
so it is correct either way -- which is what has kept this invisible. It is the
**rebuild** path that inflates, and `a4d upload tables` publishes whatever that
path wrote.

Production is unaffected today: each Cloud Run execution starts from a fresh
container, so `logs/` holds one run. This bites the local corpus, which is
where every triage number on this map was measured.

## Question

1. **What owns the cleanup?** Candidates: `run_all_cmd` clearing `logs/` at
   the start of a run; the log writers themselves reusing a fixed name per
   worker index rather than timestamp+pid; the two readers filtering to the
   current run's files. They differ in what they cost a user who *wants* the
   previous run's logs on disk.
2. **Should either reader refuse to read a directory holding more than one
   run,** rather than silently summing them? A wrong number that looks
   plausible is what this ticket is about.
3. **Does anything actually want the timestamp+pid in the name?** If the
   worker file is only ever read back in bulk, a stable name would fix this
   with no logic at all.

## Resolution

**Decision: a run starts from a clean output directory, and only
`--incremental` preserves anything.** The user set this from the destination
side -- every pipeline run should own its output folder, and all logs should
come from the last run -- and it turns the ticket's three questions into one
rule rather than three mechanisms.

Three changes, all in the run's own wiring:

1. **`a4d run` now wipes by default**, `clean_output = force or not
   incremental`, the same expression `a4d run patient` and `a4d run product`
   already used ([cli.py](../../../src/a4d/cli.py)). The bare `run` was the
   only entry point wired `clean_output=force`, on an explicit
   backwards-compatibility argument in its own comment -- and it is the only
   invocation production uses.
2. **`logs/` is cleared once per run, by the CLI, not by an arm.**
   `clear_run_logs(output_root, keep_per_tracker=...)` is new in
   [logging.py](../../../src/a4d/logging.py) and is called by all three entry
   points. The patient orchestrator no longer wipes `logs/`: it is shared with
   the product arm, so an arm that wiped it could delete the other arm's files
   mid-run, and `a4d run --skip-patient` cleared them never.
3. **`--incremental` drops the aggregate logs and keeps the per-tracker ones.**
   `main_pipeline_*.log` and `main_worker_*.log` are per-run; a skipped
   tracker's findings live in its own per-tracker log, and its lines in the
   previous run's worker log are duplicates of that, never the only copy.

**Because:** preserved output is load-bearing in exactly one place. An
`--incremental` run skips unchanged trackers, and their cleaned parquets are
the only copy of their data the tables are built from -- wipe those and the
published tables silently contain only the queued trackers. Everywhere else a
preserved output is last run's leftover that this run's tables sum in.

**Rejected:**

- *A stable worker log name instead of timestamp+pid* (the ticket's own
  question 3, "would fix this with no logic at all"). **Measured false**:
  loguru's file sink opens in append mode -- two `logger.add()` calls on one
  path produced two lines, not one. A fixed name would grow across runs
  instead of multiplying, and the rebuild would still double-count because its
  dedup key includes the record timestamp. This is already happening to
  `main_pipeline_patient.log` and `main_pipeline_product.log`, which have been
  accumulating unnoticed.
- *Tagging every log line with a run id and filtering both readers to it*
  (question 1's third candidate). Correct in general, but it needs a run-id
  concept the pipeline does not have, threaded through workers and both
  consumers -- real machinery for a problem production does not have.
- *Making a reader refuse a directory holding more than one run* (question 2).
  It converts a plausible wrong number into a stop sign, but `a4d create
  tables` against a preserved-output directory is legitimate, and after this
  change the situation cannot arise.
- *Excluding `main_*.log` from the findings rebuild*, floated mid-session as
  belt-and-braces. Killed by measurement: the log-only rebuild is **exact**
  (105,464, matching the run), so the main logs carry findings that are not
  duplicated elsewhere -- excluding them would have lost the 14
  `released_units_to_unknown_patient` rows.

**What this gives up:** a second run in the same directory no longer leaves the
first run's raw/cleaned parquets or logs to inspect. `--incremental` preserves
them; `--force` is now the flag that wipes *despite* `--incremental`, rather
than the flag that wipes at all.

### A second defect, found while verifying, and fixed here

With one run's logs on disk, `a4d create tables` still returned **108,466**
findings for a run of **105,464**. The rebuild reads the logs *and* takes
`extra_findings` for the product table stage -- but that stage emits through
`report_finding`, which also writes to the active loguru sink, so its findings
are in `main_pipeline_product.log` too. That log holds 3,016 finding lines;
3,002 of them (2,972 `patient_id_unrepairable`, 30 `patient_id_recovered`)
were counted twice. The other 14 are `released_units_to_unknown_patient`,
which `create tables` never recomputes, so they arrived once.

`rebuild_findings_from_logs` now drops an extra finding the logs already hold,
keyed on `(file_name, error_code, column, message)` -- deliberately without the
timestamp the log scan keys on, because the two copies are emitted by different
processes and their timestamps never match. An extra finding absent from the
logs is still kept; both directions are pinned by
[tests/test_tables/test_rebuild_findings.py](../../../tests/test_tables/test_rebuild_findings.py).

**Evidence (executed, on the 255-tracker local corpus):**

| | before | after |
|---|---|---|
| `a4d run` findings | 105,464 | 105,464 |
| second `a4d run`, same directory | 105,464 (in memory; rebuild 213,921) | 105,464 |
| `a4d create tables` after two runs | 213,921 | **105,464** |
| aggregate log files on disk after run 2 | 20 | 10 |

Two full runs plus `create tables` were executed against
`a4dphase2_upload`; `patient_data_monthly` (86,360) and `product_data`
(75,169) are unchanged, so no data path moved. Full suite 1,270 passed,
coverage 89%, ruff and ty clean. The loguru append behaviour was executed, not
read.

**Tense:** every number above is current behaviour on this branch, measured
after the change unless the column says "before".

**Understood, not a defect:** the logs table reads 217,045 from `create
tables` against the run's 217,022. `create_table_logs` is snapshotted at run
step 3d, and 21 further lines (the product-patient link check, the findings
table, tracker metadata) are logged after it. Confirmed by reading the tail of
`main_pipeline_product.log` in the table itself.
