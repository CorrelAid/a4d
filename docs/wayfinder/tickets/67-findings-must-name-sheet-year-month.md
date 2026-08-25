---
id: 67
title: Findings do not say which sheet, year or month they came from, though the emitters know
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

Rests on [Unify the two separate channels that report data-quality
findings](66-unify-finding-channels.md), closed 2026-08-25, which declared the
record: `file_name`, `arm`, `sheet_name`, `patient_id`, `column`,
`original_value`, `message`, `error_code`, `category`, `stage`,
`function_name`, `tracker_year`, `tracker_month`, `timestamp`. That ticket's
whole argument was that a finding must not exist in one place and not another,
and that data belongs in fields rather than stuffed into message text -- it
found six findings emitted twice because "that channel had no fields for
them -- the file and patient were stuffed into the message text".

Rests on [the findings report](16-log-analyzer-drill-down.md), closed
2026-08-25, which built `a4d report findings` and measured this gap while
verifying it. **If ticket 66 were overturned this ticket would be void**, since
there would be no single record to fill; if ticket 16 were overturned this
ticket would merely lose its consumer, not its point.

Rests on [the source-defect report's](40-source-defect-findings-report.md)
standing bar, set by the user via [ticket
30](30-triage-patient-raw-column-divergence.md): a finding must be precise
enough that someone can open the named workbook, find the named cell, and see
the problem. A workbook has twelve month sheets; without the sheet name they
cannot.

### Measured on the real 255-tracker run (2026-08-25), not inferred

Of **122,590** findings, **122,373 carry no `sheet_name`** -- every code except
`blank_header_with_data` (217). `tracker_year` and `tracker_month` are
populated on **zero** rows. `patient_id` is `unknown`/empty on 54,027.

The data is in hand at the emit site in nearly every case:

- **Clean stage, ~95,000 findings.** The frame being validated carries
  `sheet_name`, `tracker_month` and `tracker_year` as columns (patient) and
  `product_sheet_name`, `product_table_month`, `product_table_year` (product).
  Emitters iterate it row-wise and already read `row.get(file_name_col)` --
  e.g. `safe_convert_column` in `clean/converters.py`. The three fields are one
  lookup each on a row already in hand.
- **Extract stage, ~26,000 findings.** Several emitters **already print the
  sheet into the message text** while leaving the field empty:
  `harmonize_input_data_columns` (20,064) writes `"Sheet Apr'22: unknown column
  '11'"`; `excel_error_patient_id` writes `"Row in sheet 'Jan22' has an Excel
  formula error (#REF!)..."`; `missing_required_field` writes `"Row in sheet
  'Apr'22' has missing patient_id"`; `find_product_section` writes `"Sheet
  Apr19: ..."`. This is exactly the pattern ticket 66 was written to end, in a
  channel that now has the field.
- **Genuinely tracker-level, and small.** `empty_product_data` (4, "no product
  section found in any sheet of ..."), and one `read_all_patient_sheets`
  aggregate under `invalid_value` (539, "Found N rows with missing patient_id
  in <file>"). `rename_columns` (3,504) has not been checked and may be either.

Both `tracker_context` call sites (`pipeline/tracker.py:60` and `:135`) omit
`tracker_year` and `tracker_month`, which is why those two are dead
everywhere -- the context defaults them to `None` and nothing overrides.

## Question

Make every finding name where it came from, and decide what "where" means for
the ones that genuinely have no sheet.

1. **How the fields get filled.** The clean-stage emitters read the row
   already; the patient and product frames name the same three things
   differently (`sheet_name` vs `product_sheet_name` etc.), so decide whether
   that is normalised at the emit site, by a small helper, or by renaming in
   the frames. Roughly 34 call sites go through `report_finding`; a per-site
   copy-paste of three `row.get(...)` calls is the thing to avoid.
2. **`tracker_year` at the context.** It is constant for a whole tracker and
   both `tracker_context` call sites can pass it -- the name is `YYYY_...` and
   `get_tracker_year` (`extract/common.py`) already exists, though it wants the
   month-sheet list. Decide whether the context carries the year (cheap, covers
   every finding at once) while the month stays per-row.
3. **The extract-stage sheet, currently in the message.** Move it into the
   field. Decide whether the message keeps saying it too -- duplicating it is
   how the field silently rots, but stripping it changes 20,000 message
   strings.
4. **The tracker-level residue -- and whether a finding should declare its
   scope.** Some findings are genuinely about the workbook's overall structure
   rather than one sheet: `empty_product_data` ("no product section found in
   any sheet of ...") and the `read_all_patient_sheets` aggregate ("Found N
   rows with missing patient_id in <file>") have no one sheet to name, and
   `rename_columns` (3,504) has not been checked and may be either.

   The blunt options are to leave `sheet_name` empty for those and let the
   report render them as tracker-level, or to split the aggregates into
   per-sheet findings so the field is never empty. **But an empty field cannot
   say which of the two it means** -- "this finding is about the whole
   workbook" and "this finding is about a sheet and we lost which one" are the
   same blank today, and that ambiguity is what made this gap invisible until
   now.

   So the option worth weighing against those is a declared **scope** on each
   error code -- `tracker` / `sheet` / `cell` -- derived from the code the way
   `category` already is, exhaustive by test. Then blankness is checkable: a
   `sheet`-scoped finding with no `sheet_name` is a bug the test catches, and a
   `tracker`-scoped one is correctly blank and the report can group it
   separately from the row-level detail. It also gives the report a real
   answer for "what is wrong with this workbook as a whole" versus "which
   cells need retyping", which is the drill-down's own split.
5. **`patient_id` on 54,027 findings.** Some of these genuinely concern a
   column or a sheet rather than a patient (`missing_column`,
   `tracker_layout_changed`). Decide which codes are expected to name a patient
   and whether the ones that should but do not are reachable the same way.

**Guard it, don't just fix it.** Ticket 66's category and glossary maps are
kept honest by tests that fail when a new code ships uncovered. The equivalent
here is a test asserting that findings from codes declared per-sheet carry a
sheet -- otherwise the next emitter added reintroduces the gap and nothing
says so.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: verify
against the real run, not against this ticket's numbers. Every figure above was
measured on 2026-08-25 against 255 trackers and should be re-measured before
being relied on, because the fix itself moves them.
