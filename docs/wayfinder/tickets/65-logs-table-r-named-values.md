---
id: 65
title: Two values published into the logs table still name R scripts
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: null
claimed_at: null
resolution: superseded
evidence: read
closed_by: 66
spawned_by: 64
---

## Premise

[Rewrite every docstring and doc that explains the code by what R
did](64-documentation-overhaul-drop-r-framing.md) is closed: every comment and
docstring outside `src/a4d/migration/` now explains the pipeline in its own
terms, and a CI guard stops new ones appearing.

That ticket deliberately stopped at the boundary between *documentation* and
*published data*, and this is what it found on the far side. These are not
comments -- they are field values written into the BigQuery `logs` table on
every run, so changing them changes output a consumer may depend on. Ticket 64
recorded them rather than fixing them silently.

Rests also on [retiring R](12-retire-r-workspace.md): `r-archive/` is deleted,
so `script1` and `read_product_data_step1` name files that are no longer in the
repo.

Void, rather than merely rewritten, if the `logs` table is dropped or
restructured for another reason first.

## Question

Two populations, and they may deserve different answers.

1. **`function_name="read_product_data_step1"`**
   (`src/a4d/extract/product.py`, emitted by `_count_orphan_released_units`).
   Every one of the other twenty `function_name` values in the codebase is the
   Python function that emitted the record -- `cut_numeric_value`,
   `_validate_dates`, `read_all_patient_sheets`. This one names an R script
   instead, so the field means something different in this one row type. Note
   `check_entry_dates` in `clean/product.py` is a milder version of the same
   thing: descriptive, but not the emitting function's name either.

2. **`script="script1"` / `script="script3"`** (three sites in
   `extract/product.py`, one in `tables/product.py`). The `script` field
   defaults to `"clean"` -- a stage name -- so the numbered values are a second
   vocabulary inside one column, and the numbers refer to R scripts.

What has to be decided:

- **Is anything actually consuming these?** Measure before deciding: query the
  `logs` table for the distinct `script` and `function_name` values and their
  row counts, and establish whether any dashboard, saved query or downstream
  job filters on them. The answer probably decides the rest.
- **If nothing consumes them**, the cheap fix is to make both fields honest:
  `function_name` becomes the emitting Python function, `script` becomes the
  stage (`extract` / `clean` / `tables`) consistently. That is a one-line
  change per site plus a test assertion.
- **If something does consume them**, decide whether the rename is worth a
  coordinated change, or whether these values are simply frozen vocabulary that
  should be documented as such where the field is defined (`errors.py`).
- **Whether this should land before [promoting `migration` into
  `dev`](06-promote-migration-to-dev.md)** or after. It is deliberately not
  wired as a blocker: it changes published data rather than correctness, and
  the promotion gate was argued on documentation being wrong, which this no
  longer is.

## Resolution (session-2026-08-24i)

**Superseded, not answered.** Folded into
[unify the finding channels](66-unify-finding-channels.md) at the user's
direction.

**Because.** This ticket asked whether two published values naming R scripts
should be renamed, and warned that doing so changes BigQuery output. Ticket 66
changes those same published tables far more substantially -- a new
`table_findings`, `table_errors` superseded, `file_name` normalised on every log
row. Renaming these two values inside that change costs nothing; doing it
separately means two breaking changes to the same consumers.

**What was skipped rather than settled:** the measurement this ticket asked for
-- whether anything actually consumes `script` or `function_name` -- was never
run. It is now question 7 of ticket 66 and still has to be answered there; being
superseded does not make it moot.

**Evidence.** Read. No query was run against the `logs` table; GCP auth had
expired during the session and the finding rests on reading the emit sites in
`src/a4d/extract/product.py` and `src/a4d/tables/product.py`.
