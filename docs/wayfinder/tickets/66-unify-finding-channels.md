---
id: 66
title: Unify the two separate channels that report data-quality findings
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 16
---

## Premise

Spawned out of [the drill-down log analyzer](16-log-analyzer-drill-down.md)
after that ticket's grilling session established the tool it asks for cannot be
built well until this is fixed. Everything below was **measured this session**,
against a real 254-tracker run on the data drive and against current `src/`, so
it does not need re-deriving.

Rests on [ticket 11](11-cli-ux-observability.md), which built the per-run CLI
summary. That summary is the reason `ErrorCollector` exists at all -- the user's
account (2026-08-24): it was added to collect errors during a run so the CLI
could report a summary at the end. It was never meant to be a second reporting
system, which is what it became.

Rests on [ticket 32](32-audit-classifiers-against-decision-bar.md), which fixed
`a4d run` publishing an errors table holding the patient arm only. The same
structural smell is still present -- `create_table_errors` is called from inside
`pipeline/patient.py:320`, so the *patient* arm owns building a table that
covers both arms.

### The finding: there are two independent channels, and they never meet

| | Channel A | Channel B |
|---|---|---|
| entry point | `ErrorCollector.add_error(...)` | `logger.bind(error_code=...)` |
| call sites | **34** | **35** |
| path | in-memory list -> `table_errors.parquet` -> BQ `errors` | per-tracker JSON `.log` -> `tables/logs.py` -> `table_logs.parquet` -> BQ `logs` |
| granularity | cell-level: `patient_id`, `column`, `original_value` | message-level, plus `exception_type`/`exception_value`, `tracker_year`/`month` |
| `file_name` | bare stem | **`_patient`/`_product`-suffixed** |

`src/a4d/errors.py` **imports no logger**. `add_error` appends to a list and
returns, so no cell-level finding ever reaches the JSON log files.

Consequences, all measured:

- **The error codes are disjoint.** Only in `table_errors`:
  `type_conversion`, `source_formula_error`, `glucose_unit_suspect`,
  `buddhist_era_converted`, `missing_required_field`. Only in `table_logs`:
  `blank_header_with_data`, `tracker_layout_changed`,
  `duplicate_source_columns`, `missing_column`, `invalid_tracker`,
  `glucose_unit_swapped`. **The workbook-structural defects -- the ones A4D
  staff must act on -- exist only in the logs.**
- **The two tables cannot be joined.** 252 distinct `file_name` in errors, 233
  in logs, **overlap zero**. Stripping the `_patient`/`_product` suffix takes
  the overlap to **231 of 251**. This is live in current code:
  `pipeline/tracker.py:61,140` passes the suffixed name to `file_logger`, and
  `logging.py:156` binds it as the `file_name` context on every line.
- **25 rows in `table_errors` carry a blank `file_name`.** The user's rule
  (2026-08-24): there should never be a finding without one. In the *published*
  production table the figure is **33 blank, 0 null**, over 243 distinct files
  and 49,927 rows (measured 2026-08-25 against BigQuery); the 25 was the local
  254-tracker parquet run.
- **Volume shape** (254-tracker run): `table_logs` 216,871 rows -- DEBUG
  146,527 / WARNING 39,568 / INFO 30,704 / ERROR 72 -- and `table_errors`
  63,553. Note the ticket 16 premise claimed "1M+ rows"; that is wrong.
  Per file: logs median 646 / p90 1,849 / max 4,340; errors median 90 / p90
  833 / max 2,507.
- ~~**Unverified, do not assume either way:** in that run every WARNING/ERROR
  log row is `_patient`-suffixed, with **zero** product rows.~~ **Measured
  2026-08-25 and fixed — see "What the 2026-08-25 session settled" below.** It
  was not an artifact of the parquet run: the published BigQuery `logs` table
  had zero product rows too, and the cause was an ordering bug, not ticket 32.

**Supersedes [ticket 65](65-logs-table-r-named-values.md)** (two published log
values naming R scripts). Folded in here at the user's direction, since both
change published BigQuery tables and one breaking change beats two.

Void, rather than merely rewritten, if the decision to keep an in-memory
collector at all is reversed.

### What the 2026-08-25 session settled

All of this was **executed** — against live BigQuery, live GCS, and a test run —
not read.

**1. The Cloud Run precondition is clear: per-tracker logs are not lost.**
`run_all_cmd` uploads `logs/` alongside `tables/` under a per-run timestamped
prefix (`cli.py`, step 4). GCS confirms it: every run since 2026-03 has both,
and the latest production run holds **514** log files at
`gs://a4dphase2_output/2026/08/09/010107/logs/`. The unified channel may be
file-first; it does not have to be BigQuery-first. **Question 1 is answered.**

**2. The reason product findings were missing is an ordering bug, now fixed.**
`create_table_logs` snapshots whatever `.log` files exist under `logs/` at the
moment it is called. It was called from inside `run_patient_pipeline`
(`pipeline/patient.py:313`), which `run_all_cmd` runs *before* the product arm.
On a fresh container that is patient files only, and there was no second call
anywhere in `run_all_cmd`. Measured on the 2026-08-09 production run:

| arm | DEBUG | INFO | WARNING | ERROR | files |
|---|---|---|---|---|---|
| patient | 145,472 | 34,750 | 47,444 | 52 | 248 |
| **product** | **0** | **0** | **0** | **0** | **0** |
| (null `file_name`) | 249 | 277 | — | — | 0 |

The same run wrote **249 `_product.log` files** to GCS holding **33,698 lines**,
of which **10,237 carry an `error_code`**: 4,714 `invalid_tracker`, 2,995
`invalid_value`, 2,452 `missing_column`, 72 `typo_rescued`, 4
`empty_product_data`, 4 ERROR-level `critical_abort`. Uploaded to GCS, absent
from BigQuery.

Fixed by moving the call out of the patient arm into `run_all_cmd` after both
arms, mirroring what [ticket 32](32-audit-classifiers-against-decision-bar.md)
did for `create_table_errors`. Regression test:
`tests/test_cli/test_run_all_logs_table.py`. Before: `{null: 24, patient: 62,
product: 0}`. After: `{patient: 102, product: 34, null: 48}`.

**This closes the logs half of question 8.** `create_table_errors` is still
called from `pipeline/patient.py`, but `run_all_cmd` already rebuilds it from
both arms afterwards, so that one is a redundant write rather than a missing
arm. Still worth removing when the emit point lands.

**3. The null-`file_name` rows are not the blank-`file_name` defect.** The 526
null rows in `logs` come from `main_pipeline_patient.log` /
`main_pipeline_product.log` — run-level operational lines with no per-tracker
binding. Under this ticket's own split they are *operational logs*, so having no
`file_name` is correct for them. The "never blank" rule in question 4 applies to
findings, and must not be written so as to force a `file_name` onto these.

**4. Question 7's premise needs correcting, in two ways.** `script` and
`function_name` are columns on the **`errors`** table, not `logs` — the `logs`
schema has no `script` column at all. And the R-shaped values are **not yet
published**: `script="script1"`/`"script3"` and
`function_name="read_product_data_step1"` are set only in
`extract/product.py:311` and `tables/product.py:89`, i.e. the product arm, which
never reached the published errors table in the 2026-08-09 run. Production
currently shows `clean`/`extract` with real Python function names. Ticket 32's
fix means the **next** production run publishes the R-shaped values for the
first time — so this is a pending consequence, not current behaviour, and
fixing it before that run avoids ever publishing them.

**5. One more input for question 4's record design:** `logs.timestamp` is a
BigQuery `FLOAT` (unix epoch) while `errors.timestamp` is a proper `TIMESTAMP`.
The unified record should take the latter.

**Still entirely undone:** questions 2, 3, 4, 5, 6, 7 — the single emit point,
the 6 hard call sites, the record shape, the category derivation, the
`table_findings`/`table_logs` split and its BigQuery migration.

## Question

The direction is decided (user, 2026-08-24): **unify the channels.**
`ErrorCollector` stays the in-run accumulator that feeds the CLI summary, and
becomes the single source for findings output as well -- one place to add a
finding, three consumers (CLI summary, log stream, published table).

The seam is **not** "merge the two tables". It is separating two things
currently tangled across both:

- **Operational logs** -- what the pipeline did, exceptions, timings. For a
  developer debugging a run.
- **Data-quality findings** -- what is wrong with a *workbook*. For the operator
  and for A4D staff. Every one has a `file_name`, an `error_code`, a category.

What has to be decided and built:

1. ~~**Verify the Cloud Run precondition first.**~~ **Answered 2026-08-25: the
   logs are uploaded to GCS per run, so nothing is lost and the design stands.
   File-first is viable.** Detail above.

2. **One emit point.** `add_error` (or a renamed `report_finding`) both appends
   to the collector *and* emits a bound loguru line, so a finding cannot exist
   in one place and not the other. Plain `logger.info/debug` stays as-is for
   operational logging.

3. **The 6 hard call sites.** Of the 35 `logger.bind(error_code=...)` sites,
   **6 sit in modules with no `ErrorCollector` in scope at all** --
   `reference/synonyms.py` (3), `clean/transformers.py` (2),
   `clean/date_parser.py` (1). Either thread a collector in or make the emit
   function module-level against a context-bound collector. Decide which; this
   is the part that will take the time.

4. **One record.** `file_name` (bare stem, **never blank**), `arm`,
   `sheet_name`, `patient_id`, `column`, `original_value`, `error_code`,
   `category`, `message`, `stage`, `function_name`, `timestamp`.

5. **`category`** is the three-way actionability split agreed with the user
   (2026-08-24), derived from the code rather than stored per row:
   - *The workbook is wrong, a human must fix it* -- `blank_header_with_data`,
     `tracker_layout_changed`, `duplicate_source_columns`, `missing_column`,
     `invalid_tracker`, `excel_error_patient_id`, `missing_required_field`,
     `source_formula_error`, `glucose_unit_swapped`/`_suspect`.
   - *The pipeline recovered it, informational* -- `date_recovered_from_text`,
     `date_multiple_in_cell`, `date_year_inferred`, `typo_rescued`,
     `buddhist_era_converted`.
   - *A cell was unusable, data lost* -- `type_conversion`, `invalid_value`,
     `missing_value`.

6. **Two artifacts with clear jobs.** `table_findings` (every data-quality
   finding, one schema, joinable on `file_name`) and `table_logs` (operational
   only, keeping exception/traceback detail). `table_errors` is superseded.
   Decide the BigQuery migration: new table alongside, or replace.

7. **Fold in ticket 65**: `function_name="read_product_data_step1"` becomes the
   emitting Python function, and `script="script1"`/`"script3"` become stage
   names consistent with the `"clean"` default. These are **`errors`** columns,
   not `logs` ones, and are not published yet — see correction 4 above. The
   measurement ticket 65 never ran (does anything consume them?) is still open.

8. **Fix the arm-ownership smell.** **Logs half done 2026-08-25** — the logs
   table is now built in `run_all_cmd` after both arms. `create_table_errors` is
   still called from inside the patient arm; harmless today because
   `run_all_cmd` rebuilds it from both arms afterwards, but it should go when
   the emit point lands.
