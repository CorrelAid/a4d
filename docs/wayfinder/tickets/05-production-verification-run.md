---
id: 5
title: Define and execute the real GCP production verification run
labels: [wayfinder:task]
status: closed
blocked_by: [3, 4]
assignee: session-2026-08-09b
claimed_at: 2026-08-09
resolution: decided
evidence: executed
closed_by: null
spawned_by: null
---

## Premise

Depends on [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md)
(need the combined code to run) and [Diagnose and fix why CI is red at migration
HEAD](04-fix-migration-ci.md) (a red CI is not a base to run a production job
from).

This is the destination's core gate: the user wants the merge validated by an
actual GCP run — container deployed, job executed against the production
bucket, output landed in BigQuery — not by tests passing in isolation. Individual
components (product pipeline, state management) have reportedly been tested
against GCP separately already, but never as one combined run.

## Question

Define what "real production run" verification means concretely: which bucket,
what safety/cost bounds, who executes it, and how output is compared against
the R baseline / dashboard numbers (cell-by-cell, per the user's stated
standard). Then execute it and record the result.

## Resolution

**Decision:** Defined and executed the real production run against the
existing GCP infra:

- Buckets/dataset: `a4dphase2_upload` (source trackers) -> `a4dphase2_output`
  (processed output) -> `a4dphase2.tracker` (BigQuery), the live
  `src/a4d/config.py` defaults — no separate sandbox bucket exists or is
  needed; this is the real Cloud Run Job (`a4d-pipeline`, region
  `asia-southeast2`) already provisioned per `SETUP.md`.
- Safety bound: `just backup-bq` run immediately before the job, snapshotting
  `patient_data_static/monthly/annual` and `product_data` (the four tables the
  run `WRITE_TRUNCATE`s) with 7-day expiry as a rollback point.
- Who executes: the user triggered `just deploy && just run-job` directly
  (guardrail — production trigger is a human action). Agent did prep
  (`just docker-build && just docker-smoke` against `migration` HEAD,
  confirming the image builds and starts before deploy) and read-only
  monitoring (polled `gcloud run jobs executions describe` until completion,
  execution `a4d-pipeline-8mxls`, started 01:00:57 UTC, completed 01:07:59 UTC
  2026-08-09, `succeededCount: 1`, `failedCount: 0`).
- Comparison: **not** against R/dashboard numbers — the user decided mid-ticket
  that R plays no role in this run's own check; R-vs-source-Excel comparison
  is ticket 2's remit, deferred and out of this ticket's scope. Instead, built
  `src/a4d/gcp/verify.py` + `scripts/verify_production_run.py` (unit-tested,
  TDD) comparing each live table against its `just backup-bq` snapshot: row
  count, distinct `clinic_id` count (skipped for `patient_data_annual`, which
  has no `clinic_id` column — patient/year granularity only), and schema.
  Run against backup suffix `20260809`: all four tables grew in both row count
  and clinic coverage (51 -> 53 clinics across patient_data_static,
  patient_data_monthly, product_data), no schema changes, no anomalies
  flagged.

**Because:** the destination's gate is "run for real against the GCP
production bucket, with output landed in BigQuery" — a full R-parity
comparison is a separate, heavier concern (ticket 2) the user explicitly
decoupled from this run's own pass/fail. A coarse growth/shape check against a
known-good pre-run snapshot is sufficient to catch a gross regression (empty
table, dropped clinics, broken schema) without waiting on unbuilt tooling.

**Rejected:**
- *Blocking this run on ticket 2's cell-by-cell comparison script being built
  first* — rejected: ticket 2 is explicitly lower-priority/deferred, and the
  user confirmed R has no role in this ticket's own verification standard.
- *SETUP.md's "Level 3" local Docker+ADC dry run against real GCS/BigQuery
  first* — judged unnecessary once the actual Cloud Run Job path was
  confirmed working (image built and smoke-tested locally first instead, a
  cheaper substitute for the same "does the current code even start"
  question).
- *Requiring Cloud Scheduler to be wired up before calling this "production
  verified"* — out of scope for this ticket; confirmed via `gcloud scheduler
  jobs list` that the Cloud Scheduler API isn't even enabled on the project,
  which independently confirms the Migration Guide's "Production Scheduling"
  item is genuinely still open (not just stale docs) — left as its own fog
  entry, not folded into this ticket.

**Evidence:** executed throughout — real `gcloud run jobs execute` triggered
by the user, execution status polled live via `gcloud run jobs executions
describe`, BigQuery row/clinic counts queried live via the verify script
against the real backup snapshot tables (`bq ls` confirmed the snapshot
tables existed first). Nothing here rests on a doc claim or recollection.

**Tense:** current, verified behavior — the combined patient + product
pipeline has now actually run once, end-to-end, against real production GCS
and BigQuery, for the first time as one execution. Prior to this, per the
user, only the product arm alone had been tested in this Cloud Run Job (by an
intern, before `product_data` was in production use) — the BigQuery
`last_modified_time` split seen while orienting (patient tables stale since
2026-04-09, `product_data`/`clinic_data_static`/`tracker_metadata` from
2026-05-29) matches that account rather than contradicting it.

**Where applied:** ran against `migration` HEAD (post PR #6 merge, commit
`7713fea`) via the existing `a4d-pipeline` Cloud Run Job; no infra changes
needed since it was already fully provisioned.
