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
  (2026-08-24): there should never be a finding without one.
- **Volume shape** (254-tracker run): `table_logs` 216,871 rows -- DEBUG
  146,527 / WARNING 39,568 / INFO 30,704 / ERROR 72 -- and `table_errors`
  63,553. Note the ticket 16 premise claimed "1M+ rows"; that is wrong.
  Per file: logs median 646 / p90 1,849 / max 4,340; errors median 90 / p90
  833 / max 2,507.
- **Unverified, do not assume either way:** in that run every WARNING/ERROR log
  row is `_patient`-suffixed, with **zero** product rows. Current code does
  write `_product` logs (`pipeline/tracker.py:140`), and the run predates
  ticket 32's fix, so this may already be resolved. Needs a current run.

**Supersedes [ticket 65](65-logs-table-r-named-values.md)** (two published log
values naming R scripts). Folded in here at the user's direction, since both
change published BigQuery tables and one breaking change beats two.

Void, rather than merely rewritten, if the decision to keep an in-memory
collector at all is reversed.

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

1. **Verify the Cloud Run precondition first -- it can invalidate the design.**
   Per-tracker JSON logs are written to `output_root/logs/`, which on Cloud Run
   is ephemeral container storage. If they are not uploaded before the container
   exits, production runs have **no** per-tracker detail, and the unified
   channel must be BigQuery-first rather than file-first. Check before
   designing, not after.

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
   names consistent with the `"clean"` default.

8. **Fix the arm-ownership smell**: `create_table_errors` should not be called
   from inside the patient arm.
