---
id: 66
title: Unify the two separate channels that report data-quality findings
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-25b
claimed_at: 2026-08-25
resolution: decided
evidence: executed
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

## Resolution (2026-08-25, session-2026-08-25b)

**Decision: the two channels are one.** `report_finding()` in the new
`src/a4d/findings.py` is the only way to record a data-quality finding. It
appends to the collector bound by `tracker_context()` *and* emits the same
finding to that tracker's log stream, so a finding cannot exist in one place
and not the other. `table_errors` is gone; `findings` is the published table;
`logs` narrowed to operational lines only. `src/a4d/errors.py` and
`src/a4d/tables/errors.py` are deleted.

Every number below was **executed** -- against the real 254-tracker set on the
data drive, a full `a4d run` of both arms, and the test suite. Nothing here is
read or inferred.

### What was decided, question by question

**Q2, one emit point.** `report_finding()`, module-level. 34 `add_error` sites
and 25 finding-bearing `logger.bind(error_code=...)` sites now call it.
`critical_abort` (3 sites) stays operational: it is loguru's generic exception
handler, so it fires on a code bug as readily as a workbook defect.

**Q3, the 6 hard sites: (a), context-bound, and no optional collector.** The
user chose a `ContextVar` over threading a collector through, and chose to let
an unbound emit **raise** rather than drop. `tracker_context(tracker_name, arm,
output_root)` supersedes `file_logger` and binds both the collector and the log
context; it takes the stem and the arm *separately*, which is what fixes the
join. Both escape hatches are named contexts, per the user's choice of option
(i): `findings_discarded()` for the deliberate sacrificial re-parse in
`validate/common.py`, `findings_collected(file_name=...)` for the validators
and for tests.

**One of the six was not a finding at all.** `reference/synonyms.py:128` fires
from `_build_lookup`, which runs when `reference_data/synonyms/*.yaml` is
loaded -- not per tracker. Making it a finding would have attributed a
config defect to whichever tracker happened to trigger the load, once per
tracker. It is now a plain `logger.warning`. The real count was 5.

**Q4, the record.** `file_name` (bare stem, validated non-blank), `arm`,
`sheet_name`, `patient_id`, `column`, `original_value`, `message`,
`error_code`, `category`, `stage`, `function_name`, `tracker_year`,
`tracker_month`, `timestamp` -- the last as a real `Datetime`, per correction 5.

**Q5, category derived, not stored per call site.** `FINDING_CATEGORY` maps
every `ErrorCode` to `fix_workbook` / `recovered` / `data_lost`. Two tests keep
it exhaustive in both directions, so a new code cannot ship uncategorised and a
deleted one cannot leave a stale entry.

**Q6, replace rather than publish alongside.** The user's reasoning: an
internal tool and dashboard are the only consumers, so a second channel during
a transition would recreate the condition this ticket exists to end. Measured
first: BigQuery holds only the latest run -- `load_parquet_to_bigquery` defaults
to `replace=True` and deletes the table each upload -- so there is no history
to strand. **The table is named `findings`, not `tracker_findings`**: the
dataset is already `tracker`, so the prefix would have repeated it
(`tracker.findings`).

**Q7, ticket 65 folded in and discharged.** No `script="script1"`/`"script3"`
and no `function_name="read_product_data_step1"` survive outside
`src/a4d/migration/`. A test greps the tree for `"script<n>"` so they cannot
return. The orphan-units site that carried the R name turned out to be one of
the duplicate emissions below, so collapsing it fixed both at once.

**Q8, arm ownership closed.** The errors table is gone, so the patient arm no
longer builds a both-arms table. `run_all_cmd` builds `findings` after both
arms; a patient-only run builds its own from its own findings.

### What the change turned up that the ticket did not ask about

**Six findings were being emitted twice, once per channel.** Each had a
log-channel copy with the file and patient stuffed into the message text --
because that channel had no fields for them -- and a collector copy with the
fields. Now that one call does both, the pairs collapsed:
`clean/glucose.py` (unit swap), `clean/converters.py` (typo rescue, text date
recovery), `extract/product.py` (unknown columns, orphan released units),
`extract/patient.py` (Excel-error patient IDs). Each is now one finding, the
one that names the column.

**A seventh duplicate spanned two modules.** `date_parser.parse_date_detailed`
reported an unparseable date, and its only caller `parse_date_column` reported
the same cell again with the column, patient and file the parser cannot see.
The parser's copy is now a DEBUG line.

**`tables/product.py` held a hand-written re-emit loop that existed only
because these findings had no context** -- `fix_patient_id` and
`safe_convert_column` run at the table-aggregation stage, outside any
`file_logger`, and its own comment said "without this loop the errors
disappear silently". Those findings never reached the errors table either. The
loop is deleted; the findings now flow through the context like every other.

**`fix_patient_id` never named itself.** Found by diffing the rebuilt table
against the run's own (below): its findings carried an empty `function_name`.

**The logs table was carrying every finding twice.** loguru writes each line
to both the per-tracker handler and the worker's own `main_worker_*.log`, so
on the 254-tracker run 236,350 of 451,527 log rows were findings already
published elsewhere. Narrowing `logs` to operational-only removes them.

**`a4d create tables` would have published a stale findings table.** It
re-derives every table from disk, but findings live in memory during a run.
It would have refreshed everything else and left whatever `table_findings`
an earlier run wrote -- the same shape of silent-staleness bug as the
patient-only logs table. `rebuild_findings_from_logs` fixes it, and is exact
because `report_finding` binds every field of the record onto its log line.

### Measured, on the real 254-tracker run

| | before | after |
|---|---|---|
| findings in one queryable table | 63,553 (`errors`, cell-level only) | **118,175** (`findings`, all 21 codes) |
| arms covered | patient only in `logs`; both in `errors` | **patient 81,591 / product 36,584** |
| findings with a blank/null `file_name` | 33 published (BigQuery, 2026-08-09) | **0** |
| files joinable to `tracker_metadata` | 0 (`logs` was suffixed) | **254 of 254** |
| `logs` rows | 451,527, of which 236,350 were findings | **215,177, all operational** |

By category: `data_lost` 67,190, `fix_workbook` 48,995, `recovered` 1,990. The
`fix_workbook` figure is the one A4D staff act on, and before this ticket it
was split across two tables that could not be joined.

The rebuild-from-logs path was verified against that same run: **118,175 both
ways, zero rows differing on any of the eleven compared fields.**

### Rejected

- **Threading a collector through (Q3 option b).** Rejected by the user: it
  puts an `ErrorCollector` parameter on `reference/synonyms.py`'s loader and on
  `date_parser`'s pure parsing functions, and it preserves the
  `error_collector: ErrorCollector | None` pattern, which is what let a finding
  vanish whenever a caller passed nothing.
- **Keeping the sacrificial-collector pattern (Q3 option ii).** Rejected: it
  would mean two ways to emit a finding forever. The discard is a named
  context instead.
- **`findings` alongside `errors` for a transition (Q6 option a).** Rejected:
  writing both channels is the two-systems condition this ticket removes.
- **Keeping the name `errors` with a new schema (Q6 option c).** Rejected: a
  consumer breaks on missing columns rather than a missing table, which is
  quieter and worse, and the name would be wrong -- a recovered Buddhist-era
  date is not an error.
- **`tracker_findings` / `data_quality_issues` / `tracker_defects`.** Rejected
  by the user: the dataset is already `tracker`, so the prefix repeats;
  "issues" is wrong for the informational category; "defects" overclaims on
  recoveries.
- **Making `check_column_null_rate_delta` a finding.** It describes the run,
  not a workbook, and had `file_name=""`. It is a diagnostic log line now --
  the alternative was inventing an attribution to satisfy the non-blank rule.

### What this does not do

- **The BigQuery `errors` table is not dropped.** The next run publishes
  `findings` and stops writing `errors`, leaving the old table in place with
  its last contents. Someone has to delete it, and repoint the internal tool
  and dashboard the user named.
- **The `main_worker_*.log` duplication is unfixed.** It no longer reaches the
  findings table or the logs table, but the log *files* on disk still carry
  each finding twice. Left alone: it is a loguru handler-scoping question,
  not a findings one.
- **Ticket 65's own open measurement** -- does anything consume `script` /
  `function_name`? -- is answered only as far as the user's statement that the
  consumers are one internal tool and dashboard.
