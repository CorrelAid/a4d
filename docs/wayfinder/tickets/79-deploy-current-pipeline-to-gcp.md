---
id: 79
title: Deploy and run today's pipeline on GCP — production is 137 commits behind
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: null
claimed_at: null
resolution: decided
evidence: executed
closed_by: null
spawned_by: 66
---

## Premise

Rests on [Define and execute the real GCP production verification
run](05-production-verification-run.md), closed 2026-08-09: the combined
patient + product pipeline has run once for real, against
`a4dphase2_upload` -> `a4dphase2_output` -> `a4dphase2.tracker`, via the
already-provisioned `a4d-pipeline` Cloud Run Job in `asia-southeast2`,
triggered by the user with a `just backup-bq` snapshot taken first as the
rollback point. That ticket also settled who does what: the agent does the
prep and the read-only monitoring, the user pushes the button.

Rests on [Unify the two separate channels that report data-quality
findings](66-unify-finding-channels.md), closed: the published output shape
changed. The `errors` table is gone and `findings` replaced it; the `logs`
table's contents changed substantially; product rows reach the logs table
for the first time. Several later tickets ([75](75-screening-selections-under-merged-header.md),
[76](76-columns-dropped-by-the-fixed-output-shape.md),
[67](67-findings-must-name-sheet-year-month.md),
[69](69-finding-taxonomy-miscategorises.md)) added or moved published
columns on top of that.

Rests on [Promote migration into dev via PR #2](06-promote-migration-to-dev.md):
`dev` is the trunk, and it is what a deploy should now ship. The last
production image was built from `migration` at commit `7713fea`; `dev` HEAD
is **137 commits** ahead of it.

Void rather than rewritable if ticket 5 is overturned — if the Cloud Run Job,
the buckets or the dataset are not the production path after all, this ticket
is asking about the wrong infrastructure.

## Question

What stands between `dev` HEAD and a production Cloud Run execution, and
clear it, so the user can trigger the run.

Four things are already known to be wrong or unverified, and there may be
more:

1. **The pre-run safety snapshot no longer covers what the run overwrites.**
   `just backup-bq` snapshots a hand-typed list that still names `errors` (a
   table the pipeline stopped producing) and does not name `findings` (the
   table that replaced it). So the one rollback point the production run
   relies on would silently skip the newest published table. The list is
   derivable from `PARQUET_TO_TABLE` in `src/a4d/gcp/bigquery.py` — the map's
   standing rule says derive it rather than retype it.

2. **The post-run check ignores the tables that changed most.**
   `VERIFIED_TABLES` in `src/a4d/gcp/verify.py` covers the four patient and
   product tables only, so a `findings` or `logs` table that lands empty or
   malformed would pass verification silently — and those are exactly the two
   this deploy changes.

3. **Nobody has confirmed the current code still builds and starts as a
   container.** 137 commits, a dependency audit and a Python/Polars bump have
   landed since the last image was built.

4. **Nobody has checked the job still fits its resource envelope.** The
   pipeline now reads and publishes more per workbook than it did (findings,
   screenings, the recovered columns), and the triage rounds each added work
   per tracker. The last run took 7 minutes end to end, but memory, timeout
   and worker count were sized for the old code and nobody has re-measured.

Then: take the snapshot, hand the trigger to the user, monitor read-only,
and verify what landed — including deciding what happens to the orphaned
`errors` table now sitting in BigQuery with no producer.

## Progress — session 2026-08-30

Items 1 and 2 are **done and landed**; items 3 and 4 are **blocked on the
local machine**, not on the code. The trigger itself remains the user's.

**1. Safety snapshot — fixed, derived.** `published_table_names()` added to
`src/a4d/gcp/bigquery.py`, derived from `PARQUET_TO_TABLE` and unit-tested
(TDD; tests written red first). `just backup-bq` now calls it instead of
carrying its own list, so the eight tables it snapshots are exactly the eight
the run overwrites: `clinic_data_static findings logs patient_data_annual
patient_data_monthly patient_data_static product_data tracker_metadata`.
The retired `errors` is gone from it and `findings` is in it.

**2. Post-run check — widened to the same derived list.** `VERIFIED_TABLES`
in `src/a4d/gcp/verify.py` was the four patient/product tables; it is now
`published_table_names()`, so `findings`, `logs`, `clinic_data_static` and
`tracker_metadata` are checked too. `fetch_table_stats` already tolerated a
table with no `clinic_id`, so no change was needed there.

Widening exposed a crash the old list hid: `scripts/verify_production_run.py`
demanded a snapshot for every verified table, and `findings` has none — it did
not exist at the last backup. Added `fetch_table_stats_if_present`, which
returns `None` on `NotFound`. The script now reports a table with no snapshot
as *published for the first time* rather than dying, reports a table that was
expected but is absent after the run as a failure, and exits non-zero for
either that or a real anomaly.

**3. Container build — blocked, not failing.** The Docker daemon is not
running on this machine, so `just docker-build && just docker-smoke` could not
be executed. Reading the Dockerfile found nothing stale: it pins
`python:3.14-slim` against `requires-python = ">=3.14"`, installs from
`uv.lock --frozen`, and its `CMD` is still `uv run a4d run`. That is a read,
not a build — it does not establish that the image builds.

**4. Job resource envelope — blocked.** `just job-settings` fails with
`Reauthentication failed`; the local `gcloud` credentials have expired, so
nothing about the deployed job could be read, including its memory, timeout,
parallelism, or the current BigQuery row counts to compare against.

**The run itself is green on today's code, against the real corpus.**
`a4d run --skip-download --skip-upload --skip-drive-download` on `dev` at
`9f48e33`, 4 workers, ~3 minutes wall clock:

- 255 of 255 trackers succeeded on **both** arms; zero failed on either,
  zero lost entirely.
- All eight published tables were written. `table_logs.parquet` and
  `tracker_metadata.parquet` appear only after the product arm finishes,
  which is [ticket 66](66-unify-finding-channels.md)'s fix behaving as
  designed, not a missing output.
- Rows: `patient_data_static` 1,828 · `patient_data_monthly` 86,360 ·
  `patient_data_annual` 4,520 · `product_data` 75,169 ·
  `clinic_data_static` 59 · `logs` 226,522 · `findings` 104,861 ·
  `tracker_metadata` 255. 59 distinct clinics, 1,828 distinct patients.
- Findings carry a `file_name` for all 255 trackers, split patient 67,755 /
  product 37,106, categorised `fix_workbook` 62,583 · `data_lost` 24,165 ·
  `recovered` 18,113.

Against [ticket 66](66-unify-finding-channels.md)'s own measurement (118,175
findings; `data_lost` 67,190, `fix_workbook` 48,995, `recovered` 1,990), the
taxonomy work since has moved tens of thousands of findings out of "lost" and
into "fixable at the clinic" or "recovered", and cut the total by 13,314. That
is the intended direction, but nobody has verified the drop line by line.

CI's own checks pass at this commit: `ruff format --check`, `ruff check`,
`ty check src/`, and `pytest -m "not slow and not integration"`
(1,310 passed, 1 skipped).

**What is left, in order:**

1. User runs `gcloud auth login` and starts Docker Desktop.
2. `just docker-build && just docker-smoke` — confirm the image builds and
   the CLI starts at `dev` HEAD.
3. `just job-settings` — record memory, timeout, parallelism; judge them
   against the ~3-minute local run at 4 workers.
4. `just backup-bq` — now snapshots `findings` for the first time.
5. User triggers `just deploy && just run-job`; agent monitors read-only.
6. `uv run python scripts/verify_production_run.py --backup-suffix <date>`.
7. Decide what happens to the orphaned `errors` table in BigQuery: it has no
   producer since ticket 66 and nothing snapshots it any more, so it will sit
   frozen at the 2026-08-09 contents until someone drops it.

## Progress — session 2026-08-30, part 2

Items 3 and 4 are now done, and a hazard nobody had listed was found and
cleared. Everything up to the snapshot is ready; the trigger is still the
user's.

**3. Container build and startup — verified, and one defect fixed.** The image
builds at `dev` (`just docker-build`, tagged `39397b6`) and the CLI is
reachable. The smoke test then showed the deployed startup path doing
something it should not: `uv run` re-resolves at container start, downloading
`ruff`, `ty` and `virtualenv` from PyPI on every cold start -- dev tooling the
job never uses -- and then reinstalling 18 packages over the venv the image had
already built with `uv sync --frozen --no-dev`. So the job's startup depended
on PyPI reachability, and what actually ran was not necessarily what the lock
file pinned at build time. `CMD` is now `uv run --no-sync a4d run`, and
`just docker-smoke` was changed to use `--no-sync` too, so the smoke test
exercises the path the Cloud Run Job takes rather than a different one.
Re-verified after the change: no downloads, no reinstall, CLI reachable.

**4. Resource envelope — read, and comfortable.** The `a4d-pipeline` job is
8 CPU / 8Gi memory, `timeoutSeconds: 3600`, `taskCount: 1`, `parallelism`
unset, `A4D_MAX_WORKERS=8`, service account
`a4d-pipeline@a4dphase2.iam.gserviceaccount.com`, image
`.../a4d/pipeline:latest`. The local run did the same 255 trackers in ~3
minutes at *half* those workers, and the last full production run (download +
process + upload) took 7 minutes against a 3600s timeout. Nothing here needs
changing.

**The hazard that was not on the list: the dataset has eight views built on
these tables, and the loader deletes each table before recreating it.**
`patient_data`, `active_patients`, `active_patients_delta`,
`active_patients_per_country_and_year`, `clinic_data_static_per_year`,
`dez2023_june2024_status`, `patient_data_static_with_clinic` and
`product_data_for_looker_v2` -- the last feeding Looker. A column dropped or
renamed by this deploy would break them, and `patient_data` is worse than
that: it is `SELECT *` across a three-way join, so a column *added* to two of
the joined tables at once would also break it on duplicate names.

**Checked, and they survive.** Diffing every live BigQuery schema against the
parquet the local run just produced:

- `patient_data_static`, `clinic_data_static`, `product_data`,
  `tracker_metadata`: no columns added, none removed.
- `patient_data_monthly`: two added, `complication_screening` and
  `complication_screening_results` (from [ticket
  75](75-screening-selections-under-merged-header.md)); none removed.
- `logs`: `error_code` removed -- correct and intended, findings moved out of
  the logs table into `findings` in [ticket
  66](66-unify-finding-channels.md). No view reads `logs`.

The `patient_data` join was checked for name collisions specifically: after
its own `EXCEPT` clauses, monthly/static/clinic share no column name beyond
the join keys, and every column the views name (`country_code`, `clinic_code`,
`tracker_date`, `tracker_year`, `tracker_month`, `status`, `patient_id`,
`country`) is still present. So the views compile after this deploy. The two
new screening columns will simply appear in `patient_data`'s output.

**What is left:**

1. `just backup-bq` -- snapshots all eight tables, `findings` for the first
   time. Additive, 7-day expiry.
2. User triggers `just deploy && just run-job`; agent monitors read-only.
3. `uv run python scripts/verify_production_run.py --backup-suffix <date>`.
4. Decide what happens to the orphaned `errors` table. It still exists in
   BigQuery with the 2026-08-09 contents, has had no producer since ticket 66,
   is no longer snapshotted, and no view reads it. Also unresolved, and
   separate: `product_data_for_looker` is a *table*, not a view, and nothing in
   this pipeline writes it -- so something outside the repo does.

## Progress — session 2026-08-30, part 3

The pipeline now runs on GCP from `dev`. Three production executions, each
finding a defect the one before it could not have shown.

| Execution | Image | Findings table | Console |
|---|---|---|---|
| `pb4j8` 11:11 UTC | `f27ffe16` | failed silently | 3,765 lines |
| `4qk8w` 11:33 UTC | `8e185afe` | **landed** | 3,765 lines |
| `7fl4k` 11:50 UTC | `7e10470c` | landed | 688 lines |

**The findings table had never once loaded, and the run said it had.** The
first execution exited 0 with the table simply absent. Two independent
defects behind that:

- `TABLE_CONFIGS["findings"]` declared **five** clustering fields; BigQuery
  caps them at four and rejects at *load* time, not config time, so every
  load of that table since it was introduced had failed with a 400. Every
  unit test around the loader mocks the BigQuery client, so only a real load
  could surface it. Dropped `column`, the fifth and most granular -- clustering
  prunes on a prefix, so it was doing the least work anyway. A test now holds
  every entry to the limit.
- `load_pipeline_tables` logged each failure and returned the partial result
  set, so the CLI printed its success line and the job exited 0. Failures are
  now collected, every remaining table is still attempted, and the run raises
  at the end naming what failed. The CLI already turned an exception into a
  non-zero exit, so no change was needed there.

Verified after the second execution: `findings` in BigQuery holds 104,861
rows across all 255 trackers and all three categories -- the first time it has
existed in the dataset.

**The console was publishing one line per finding.** 3,765 log lines, 2,987
WARNING, and **2,972 of those were the same sentence** ("Invalid patient ID
format..."), because findings log at WARNING and the bare `a4d run` set its
console to that level -- while `run patient` and `run product`, the two debug
commands, were already quiet at ERROR. The console format binds none of the
finding's fields, so the lines named no file, sheet or patient either. All
2,993 are published as `patient_id_unrepairable` to the findings table, the
per-tracker logs and the workbook, so nothing is lost by silencing them.

That left 256 DEBUG lines, one per tracker downloaded. Cause: `setup_logging`
is called from inside each arm, and Steps 0 and 1 run before either, so
loguru's default DEBUG handler was still installed. Added
`configure_quiet_console()`, called before the first download; no file sink,
since the output directory is not even cleared at that point.

Measured on a real 255-tracker run: **3,765 console lines -> 124**, zero of
them log lines.

**The run summary was counting the pipeline's own successes as errors.** "Top
Files by Error Count" ranked on every finding, recoveries included. That put
the 2025 Kantha Bopha II tracker seventh with 1,424 "errors", **1,022 of them
`age_derived_from_dob`** -- the pipeline correctly computing a missing age from
date of birth -- leaving 402 real problems, ranked above 2022 trackers carrying
1,952 and 1,936 real problems with no recoveries at all. It now reads the
findings table (the only thing carrying a category), counts what needs action,
and is titled accordingly. Falls back to the old per-arm counts under the old
title when there is no findings table, so `--skip-tables` degrades rather than
losing it.

Added **Findings by Tracker Year**, on the user's request, because nothing in
the summary answered "was this year processed, and is the newest template
actually clean?":

| Year | Trackers | Findings | Recovered | Needs action | Per tracker |
|---|---|---|---|---|---|
| 2026 | 48 | 9,959 | 3,567 | 6,392 | **133.2** |
| 2025 | 47 | 16,400 | 5,506 | 10,894 | 231.8 |
| 2024 | 38 | 16,478 | 4,130 | 12,348 | 324.9 |
| 2023 | 33 | 16,995 | 1,266 | 15,729 | 476.6 |
| 2022 | 27 | 15,621 | 178 | 15,443 | **572.0** |
| 2019 | 11 | 6,502 | 356 | 6,146 | 558.7 |
| 2017 | 4 | 2,170 | 186 | 1,984 | 496.0 |

`per_tracker` divides *actionable* findings by trackers, so a workbook full of
successful recoveries does not score as badly as a broken one. Read that way
the trend inverts: the newest template is four times cleaner per tracker than
2022, which the per-file ranking had hidden.

**The eight views survived, as predicted.** The schema diff done before the
deploy held: nothing dropped or renamed, `patient_data_monthly` gained the two
screening columns, `logs` lost `error_code`.

**Still open on this ticket:**

1. Deploy the summary changes -- the image on GCP (`7e10470c`) predates them.
2. The orphaned `errors` table. Still in BigQuery with its 2026-08-09
   contents, no producer since [ticket 66](66-unify-finding-channels.md),
   no longer snapshotted, and read by none of the eight views.

**Found and deliberately not fixed:**

- `console_main_thread_only` in `src/a4d/logging.py` defaults to `False` and
  nothing in the codebase ever sets it `True`, so the filter meant to keep
  worker logs off the console has always been dead. Moot at ERROR level, so
  widening this session's change to cover it was not justified.
- `product_data_for_looker` is a **table**, not a view, and nothing in this
  repo writes it -- so something outside the repo does, and nobody knows what.

## Resolution

**Decision:** The current pipeline runs on GCP from `dev`. Four executions on
2026-08-30 got it there, each exposing a defect the one before could not have
shown; the fifth (`bgv8x`, 12:54 UTC) is the clean one. The retired `errors`
table was dropped by the user, leaving the dataset as exactly the eight tables
`PARQUET_TO_TABLE` publishes plus `product_data_for_looker`, which nothing in
this repo writes.

The work split into three kinds:

*Pre-deploy, from reading the deploy path:* the pre-run BigQuery snapshot and
the post-run verification each carried a hand-typed table list, and both had
drifted -- still naming the retired `errors`, never covering `findings`, so the
newest published table would have been truncated with no rollback point and no
check. Both now read `published_table_names()`, derived from
`PARQUET_TO_TABLE`. The container was re-resolving its dependencies from PyPI
at every cold start, pulling dev tooling over the venv the image had already
built from the lock file; `CMD` now uses `--no-sync`, and `just docker-smoke`
was changed to exercise that same path rather than a different one.

*The hazard that was not on the ticket:* the dataset holds eight views, one
feeding Looker, and the loader deletes each table before recreating it. Diffing
every live schema against the parquet a local run produced showed they survive
-- nothing dropped or renamed, `patient_data_monthly` gaining the two screening
columns, `logs` losing `error_code` as [ticket
66](66-unify-finding-channels.md) intended. Confirmed after the deploy.

*What only a real run could find:* three defects, detailed in part 3 above --
the findings table's five clustering fields against BigQuery's limit of four
(so it had never once loaded), the loader swallowing every load failure so the
job exited 0 with a table missing, and the console publishing one line per
finding (3,765 lines, 2,972 of them identical). Then, on the user's reading of
the output, the run summary counting recoveries as errors, which is what made
the newest trackers look like the worst.

**Because:** the destination's gate is a real run against the production
bucket with output in BigQuery, and the last one predated 137 commits that
changed what the pipeline publishes. Every defect above was invisible to the
test suite -- the loader's tests mock the BigQuery client, and no test could
see a console the CliRunner never captures. The only instrument that finds
them is a real execution, which is the argument for having done this now
rather than at the end.

**Rejected:**
- *Widening `VERIFIED_TABLES` without tolerating a missing snapshot* --
  rejected on contact: `findings` had no snapshot because it had never
  existed, so the verification would have crashed on `NotFound` instead of
  reporting. `fetch_table_stats_if_present` reports it as new.
- *Raising on the first table that fails to load* -- rejected: one unloadable
  table would strand every table after it. Failures are collected, all are
  attempted, and the run raises at the end naming them.
- *Reordering the `findings` clustering fields while fixing the count* --
  rejected: the order was a previous decision and no evidence said it was
  wrong. Only the fifth field was dropped.
- *Excluding recoveries from the findings table itself* -- rejected: a
  recovery is worth publishing, it is just not a triage item. Only the run
  summary's ranking changed.
- *Removing the dead `console_main_thread_only` filter* -- rejected for this
  session: it is moot at ERROR level, and widening the change into the same
  session that depended on the level was not justified. Left as fog.

**Evidence:** executed throughout. Five real Cloud Run executions, their logs
read from Cloud Logging; BigQuery schemas and row counts queried live;
`bq show` confirming `errors` is gone and `findings` holds 104,861 rows across
255 trackers; the image built and smoke-tested locally each time; the pipeline
run end to end against all 255 real trackers on four occasions, before and
after each change, with row counts compared. The console reduction
(3,765 -> 124 lines) and the per-year figures were measured on real runs, not
inferred.

**Tense:** current, verified behaviour. One claim is a *prediction* rather
than an observation and is marked as such above: nothing has yet exercised the
new "a table failed to load, so the job fails" path against a real BigQuery
error, because no table has failed since the clustering fix.
