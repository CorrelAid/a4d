---
id: 11
title: Decide what CLI/TUI UX and error-log observability improvements admins/developers need before rollout
labels: [wayfinder:grilling]
status: closed
blocked_by: [3]
assignee: session-2026-08-09g
claimed_at: 2026-08-09
resolution: decided
evidence: executed
closed_by: null
spawned_by: null
---

## Premise

Rests on [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md),
closed: `migration` now carries the combined patient + product pipeline, its
CLI (`a4d.cli`), and both arms' error/logging paths (including the two
logging-parity fixes from that merge — product now populates
`TrackerResult.data_errors` and a logs/errors table like patient does).

Raised mid-[ticket 5](05-production-verification-run.md) session as a fresh
concern, not derived from any ticket's resolution. Initially parked as fog
("Not yet specified") because "improve whatever helps" wasn't a sharp
decision and it wasn't clear the concern was even in this map's scope; the
user then confirmed explicitly that it belongs to this effort — this map's
destination has been redrawn to include it (see Destination section, "2026-08-09").

## Question

What does "good enough to operate the pipeline day to day" mean concretely
for admins/developers, covering both:

- **CLI/TUI UX**: is `a4d.cli`'s current command surface, output, and
  ergonomics (Typer-based; commands listed in `docs/CLAUDE.md`) sufficient for
  someone running/debugging a pipeline execution, or are there specific gaps
  (progress visibility during a long run, clearer error summaries, easier
  local reproduction of a failed production run, etc.)?
- **Error-log observability**: whether the existing error surfaces (the
  `logs` BigQuery table, `table_errors.parquet`, Cloud Run Job logs via `just
  logs-job`) give enough to observe and debug a run without reading raw JSON
  logs line by line — e.g. is a summary view, a dashboard, or a CLI subcommand
  needed?

Scope to what's needed for confident rollout, not a general UX overhaul —
name concrete gaps against concrete use cases (a run fails partway; an admin
wants to know how many trackers had errors and why) rather than redesigning
the CLI from scratch.

**Prior art (read before deletion, not to be ported as-is):** `tools/LogViewerA4D`
was an R Shiny dashboard, since deleted (see [ticket
12](12-retire-r-workspace.md)), that read local tab-separated `.log` files
(`Timestamp/Thread/Level/Package/Function/Message`) and offered three views: a
main log table plus a per-tracker summary and Sankey diagram, an overview tab
with a regex-filterable plot across tracker files, and a reference-data
validation tab flagging missing/duplicate `clinic_id` entries against
`reference_data/`. Useful as a reference for what admins actually wanted to
see, but its whole design assumes local log files — the current pipeline logs
via loguru into the `logs` BigQuery table (1M+ rows) instead, so any Python
equivalent would need a different shape, not a port.

## Resolution

**Decision:** The CLI/TUI UX question is answered for the "normal a4d output"
half of the scope; the observability half is split off into a separate
deliverable (spawned as [ticket
16](16-log-analyzer-drill-down.md)) rather than answered here.

Concretely, this session:

1. **Discovered a real gap by demonstration, not just reasoning**: built a
   small synthetic dataset (clean tracker, a data-quality-error tracker, an
   outright-unparseable tracker) and ran `process-patient` against it to see
   actual CLI output. That surfaced that `process-patient`/`process-product`
   already render an "Error Type Breakdown" and "Top Files by Error Count"
   table (richer than this ticket's own description assumed) — but
   `run-pipeline`, the actual production entry point behind the Cloud Run
   Job, never calls any of that rendering at all. It only prints a one-line
   `✓ Processed N trackers (X ok, Y failed)` per arm, with no cross-arm view.
2. **User confirmed the shape of the fix**: keep the current per-arm summary
   tables, extend `run-pipeline`'s output with a combined view that answers
   "how many files could not be processed and why — total lost, only
   patient, only product — and how many errors per file", scoped to a
   patient-ok/product-ok level (not a further extract/clean/tables per-stage
   breakdown — noted as a possible future refinement, not built).
3. **Implemented and shipped it** (this map carries execution per its Notes):
   added `_render_combined_run_summary()` to `src/a4d/cli.py`, wired into
   `run_pipeline_cmd` after both arms run. It crosses each tracker file's
   patient/product outcome into four buckets (both ok / patient failed only
   / product failed only / lost entirely), lists the files needing attention
   with each arm's error text, and merges both arms' per-file error counts
   into one "Top Files by Error Count" table. Only renders when both arms
   actually ran (skips cleanly under `--skip-patient`/`--skip-product`).
4. **Found and fixed a real behavior bug this exposed**: `run-pipeline`
   previously aborted the entire run (`raise typer.Exit(1)`) the instant any
   single patient tracker failed — before the product arm ever ran. That
   meant the combined view's "patient-only failed" vs "both failed"
   distinction could never actually be observed in a real run. Confirmed
   with the user this should switch to the same soft-fail-and-continue
   posture the product arm already uses; implemented the switch.
5. **Found and fixed a real test-isolation bug surfaced by that change**:
   two existing `run-pipeline` CLI tests mocked only `run_patient_pipeline`,
   not `run_product_pipeline`. Because `run_product_pipeline` binds
   `settings` at its own module-import time, patching `a4d.config.settings`
   in the test did not stop it discovering trackers from the real local
   `data_root` when actually invoked. Under the old abort-on-patient-failure
   code this was never reached in the failing-patient test; the soft-fail
   change now lets execution reach it, and running the test once (before
   the fix) processed 185 real tracker files from local disk as a side
   effect. Fixed by mocking both arms in every `run-pipeline` test — this
   generalizes beyond this ticket's own new tests.

**Because:** distinguishing "lost entirely" from "one arm degraded" is
exactly the question an admin needs answered after a run, and it was
structurally impossible to answer with the abort-on-any-patient-failure
behavior in place — fixing the summary without fixing the abort would have
shipped a view that could never show its most important row in practice.

**Rejected:** building the log-analyzer drill-down tool (open a specific
file, see every error/log line — replacing `LogViewerA4D`'s job) in this
same session — it's a genuinely separate, larger deliverable (querying
`table_logs`/`table_errors` by file, likely its own subcommand or small
TUI/dashboard), not an extension of the run summary tables. Spawned as
[ticket 16](16-log-analyzer-drill-down.md) instead of sprawling this
ticket.

**Evidence:** executed — real CLI run against synthetic data (not real
patient trackers, per this map's guardrails) showing actual output; the
combined-summary implementation is covered by new unit tests
(`TestCombinedRunSummary` in `tests/test_cli/test_cli.py`); full suite (494
tests), ruff, and `ty check src/` all pass. Pushed as `33694b4`.

**Tense:** all claims above describe current (post-commit) behavior, not a
proposal.
