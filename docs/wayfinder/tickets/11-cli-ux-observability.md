---
id: 11
title: Decide what CLI/TUI UX and error-log observability improvements admins/developers need before rollout
labels: [wayfinder:grilling]
status: open
blocked_by: [3]
assignee: null
claimed_at: null
resolution: null
evidence: null
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
