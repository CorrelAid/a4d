---
id: 71
title: The pipeline reads its own report, and Excel's lock files, as if they were trackers
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: null
claimed_at: null
resolution: decided
evidence: executed
closed_by: 69
spawned_by: 69
---

## Premise

Rests on [the findings report](16-log-analyzer-drill-down.md), closed
2026-08-25, which introduced `a4d report findings` writing `findings.xlsx`
into the run's own output directory. Nothing before it put an `.xlsx` there.

Rests on [the finding taxonomy rework](69-miscategorised-and-duplicated-findings.md),
closed 2026-08-26, only in that its re-measurement run is where this surfaced:
the Trackers sheet ended with two rows named `findings` and `~$findings`, and
the run reported **257 trackers** where the directory holds 255.

Neither decision would be made incoherent by this ticket's answer -- it is an
independent defect that the report merely made visible.

## The defect

Tracker discovery is `data_root.rglob("*.xlsx")`, at
`src/a4d/tables/metadata.py:68` and `src/a4d/pipeline/patient.py:53`. On the
local dataset `data_root` is `a4dphase2_upload/` and the output directory is
`a4dphase2_upload/output/`, i.e. **inside it**, so the walk picks up:

- `output/findings.xlsx` -- the pipeline's own report, from the previous run
- `output/~$findings.xlsx` -- Excel's lock file, present whenever someone has
  the report open

Both were processed, both landed in `tracker_metadata`, and both appear on the
report's own Trackers sheet as trackers that produced no findings -- which is
exactly the state that sheet exists to distinguish from a genuinely clean
tracker.

Measured on the 2026-08-26 run: `select count(distinct file_name) from
tracker_metadata` returns **257**; the two extra names are as above.

## Question

1. **Does this reach production?** In production `data_root` is a GCS download
   directory and output may not sit inside it. Establish whether it does before
   sizing the fix -- the answer changes this from a real data defect to a
   local-run annoyance. Check `settings.output_dir` resolution against the
   deployed configuration, not against the local default.
2. **Exclude the output directory from tracker discovery**, in both call sites.
   Deriving the exclusion from `settings` rather than hardcoding a name, so the
   two do not drift.
3. **Skip Excel lock files (`~$*`) regardless.** These appear next to *any*
   open workbook, including a real tracker a staff member is editing during a
   run, so this half of the defect is not confined to the output directory and
   is the more likely one to bite in production.
4. **Decide whether a non-tracker workbook should be reported rather than
   silently processed.** A file that reaches extraction and yields nothing is
   currently indistinguishable from a tracker that failed. This overlaps
   [ticket 70](70-audit-the-finding-taxonomy-for-blind-spots.md)'s question and
   may belong there instead.


## Resolution

**Decision.** One shared `discover_tracker_files` in a new `src/a4d/discovery.py`,
used by every caller, excluding both the output root and Excel lock files.

**Q1: yes, it reaches production.** `Settings.output_root` is
`data_root / output_dir` (`config.py`) -- a computed property, not a
configurable path -- so the output directory is *always* inside the tree
tracker discovery walks, in every deployment. This was a real data defect, not
a local-run annoyance.

**Q2 and Q3, both done, and the two call sites had drifted exactly as the
"never hand-maintain a derived list" rule predicts**: `pipeline/patient.py`
skipped `~$` files but not the output directory; `tables/metadata.py` skipped
neither, being a bare `sorted(data_root.rglob("*.xlsx"))`. They are now one
function. The exclusion derives from `data_root / settings.output_dir` rather
than a literal name, so renaming `output_dir` moves it; a caller may override
it, which is what lets a deployment put output outside `data_root` without
silently dropping a clinic folder that happens to share the name.

**Q4 deferred to [ticket 70](70-audit-the-finding-taxonomy-for-blind-spots.md)**,
as this ticket's own text anticipated: whether a non-tracker workbook that
reaches extraction and yields nothing should be *reported* rather than silently
processed is an instance of that ticket's question, and answering it here would
have meant designing a finding code outside the taxonomy work that had just
settled.

**Rejected.**
- *Filtering `findings.xlsx` by name* -- would have missed every future output
  artifact and the lock files, which are the half likelier to bite in
  production.
- *Moving the output directory outside `data_root`* -- changes the deployed GCS
  layout and every path consumers already depend on, to fix a walk that should
  have been scoped anyway.
- *Fixing only `tables/metadata.py`* -- leaves two implementations of the same
  question, which is what produced the drift.

**Evidence: executed.** Full pipeline run over the real 255-tracker dataset.
`select count(distinct file_name) from tracker_metadata` returns **255** (was
257) and neither `findings` nor `~$findings` appears. Six new tests in
`tests/test_tracker_discovery.py` cover clinic subfolders, the report, anything
under the output root, lock files, a renamed output dir, and an output root
outside `data_root`. Suite 1,247 passed.

**Tense.** All figures are current behaviour, measured after the fix.
