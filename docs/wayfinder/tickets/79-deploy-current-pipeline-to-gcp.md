---
id: 79
title: Deploy and run today's pipeline on GCP — production is 137 commits behind
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
