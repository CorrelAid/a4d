---
id: 74
title: A second local run doubles the rebuilt findings table, because last run's worker logs are still there
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
