---
id: 67
title: Findings do not say which sheet, year or month they came from, though the emitters know
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-27
claimed_at: 2026-08-27
resolution: decided
evidence: executed
closed_by: null
spawned_by: 16
---


> **Numbers below are superseded (2026-08-26).** [The finding taxonomy
> rework](69-miscategorised-and-duplicated-findings.md) re-measured the run:
> findings total **122,590 -> 105,441**, so the "122,373 carry no `sheet_name`"
> figure must be re-derived. The gap itself is unchanged -- nothing in that
> ticket populated `sheet_name` -- and the codes it names by aggregate
> (`invalid_value`, `missing_column`) have been split into specific ones,
> which makes the per-code half of this question easier rather than harder.

> **The scope question this ticket raises has a measured instance now
> (2026-08-26), from [the taxonomy blind-spot audit](70-audit-the-finding-taxonomy-for-blind-spots.md).**
> This ticket asks whether an error code should declare a **scope** (`tracker`
> / `sheet` / `cell`). The audit found the same gap one level down: the table
> mixes **units** with no field that says which, so two findings side by side
> can mean "one cell" and "one distinct value across thousands of cells".
>
> `validate_allowed_values` iterates `col_values.unique()`, so it emits **one
> finding per distinct bad value per tracker**: 1,502 findings, of which 1,170
> name the `province` column across 124 trackers -- while **26,124 cleaned rows
> across those same 124 trackers carry `province = 'Undefined'`**. A 22x gap,
> and not a defect in the emitter: deduplicating is the right call for a column
> where one misspelling repeats down a sheet. `type_conversion` is the
> contrast, and it was checked rather than assumed: 3,579 findings against
> 3,692 `hba1c_baseline` sentinels and 8,122 against 8,486 `fbg_baseline_mg`
> ones -- per row, within a few percent.
>
> So the unit is per-emitter and invisible. The Summary sheet ranks trackers by
> finding count, which silently weights a per-row emitter above a per-value one.
> Whatever this ticket decides about scope should decide the unit in the same
> move -- they are the same field.

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

## Resolution (session 2026-08-27)

**Decision. Every finding names where it came from, and a finding that names
no sheet says so with a declared `scope` rather than with a blank.** `scope`
is derived from the error code exactly as `category` is -- one map, exhaustive
by test, materialised into the published table -- and it answers both halves
of this ticket at once: what one row counts, and whether a blank `sheet_name`
is a statement or a loss.

The user chose the scope field over the two cheaper routes. Materialising it
into the parquet rather than deriving it at read time was **my call, not
theirs**: `category` is already materialised (ticket 66), and a field that
only exists at read time cannot be filtered or joined in BigQuery, which is
where the drill-down's "what is wrong with this workbook as a whole" question
gets asked.

### The taxonomy

Eight values, each earned by a real code. The prefix says what extent owns the
deduplication; the suffix says what is deduplicated.

| scope | means | example | n |
|---|---|---|---|
| `tracker` | the workbook | `empty_product_data`, `month_sheet_missing` | 9 |
| `sheet` | one sheet | `product_section_not_found`, `released_units_without_recipient` | 2,674 |
| `sheet_column` | one column of one sheet | `unrecognised_column`, `blank_header_with_data` | 21,558 |
| `tracker_column` | one column across the workbook | `tracker_layout_changed`, `glucose_unit_swapped` | 316 |
| `tracker_value` | one distinct bad value per workbook | `value_not_in_allowed_list` | 1,503 |
| `sheet_value` | one distinct bad value per sheet | `product_not_in_catalogue` | 96 |
| `patient` | one patient across the workbook | `diagnosis_age_negative_from_dob` | 8 |
| `row` | one source row | `type_conversion`, `source_formula_error` | 77,439 |

`SCOPES_INSIDE_A_SHEET = {sheet, sheet_column, sheet_value, row}` makes
blankness checkable, and on the real run the invariant holds exactly: **every
in-sheet scope has zero blank sheets, every workbook-spanning scope is blank
on every row.**

### Measured on the real 255-tracker run, before and after

| | before | after |
|---|---|---|
| findings | 105,470 | **103,603** |
| no `sheet_name` | 102,967 | **1,836** (all workbook-scoped) |
| no `tracker_year` | 105,470 | **0** |
| no `tracker_month` | 105,470 | **1,838** |
| no `scope` | n/a | **0** |
| codes firing | 40 | 40 |

`patient_data_monthly` (86,360), `product_data` (75,169),
`patient_data_static` (1,828), `patient_data_annual` (4,520) and
`tracker_metadata` (255) are **unchanged**, so no published data moved.

The 1,838 monthless findings are the 1,836 workbook-scoped ones plus two on
the `Annual` sheet, which covers a whole year and correctly names no month.

### The five questions

1. **One helper, `sheet_context(row)`, splatted at the emit site.** The two
   arms name the same three things differently (`sheet_name` vs
   `product_sheet_name`), and the ticket's own worry was a per-site copy-paste
   of three `row.get` calls across ~34 sites. Renaming the frames was rejected:
   those are published column names. `PLACE_COLUMNS` / `present_place_columns`
   exist for the emitters that narrow a frame with `.select()` first -- the
   typo-rescue path dropped the sheet exactly that way.
2. **The year rides on the tracker context, and the row overrides it.**
   `tracker_year_or_none` reads it off the file name at `tracker_context` time
   (all 255 trackers are named `YYYY_...`, checked). That alone left **3,016**
   findings yearless -- the product *table* stage runs across every tracker
   under `findings_collected`, where no one tracker's context exists -- so
   `sheet_context` also yields the year when the row carries one. That closed
   the last of them.
3. **The month is derived from the sheet name, in `report_finding`.** A sheet
   called `Jan24` states its own month; deriving it once beats threading it
   through every extract emitter, and `Patient List` / `Annual` correctly keep
   `None`. Precedence is explicit arg > sheet name > context, pinned by test.
4. **Answered by the scope field** -- see above.
5. **`patient_id` is 35,018 unknown and deliberately so.** Every scope coarser
   than `row` has no one patient by construction, and the row-scoped ones that
   say `unknown` are about a column or a sheet rather than a person. Not
   pursued further: the ticket's premise was that these were reachable, and
   the scope field shows most of them are not.

### The messages stopped repeating the field

Roughly 24,000 messages said `"Sheet Apr'22: ..."` beside an empty
`sheet_name`. The sheet is now stripped from the message wherever the field
carries the same value -- ticket 66's rule, applied to itself. Kept where the
message names a *different* sheet, as `static_sheet_missing` does when it
points at `Annual_2025`.

### Two duplicate emitters, found by the scope field and removed

A code cannot have two units, so declaring the scope forced both out.

- **`unrecognised_column` was reported twice in the product arm**: once per
  column per sheet by `_harmonize` (20,064), and once per sheet as a batch by
  `ColumnMapper.rename_columns` listing every unmapped column in one row
  (2,490). Reporting moved out of the mapper -- a reference-data utility that
  knows no sheet -- into `report_unrecognised_columns`, called by whoever does.
  **23,180 -> 21,341.** The patient arm *gained* granularity: its 626 batch
  rows became 1,277 per-column findings across 147 (file, column) pairs.
  Checked that no coverage was lost: the old batch rule
  (`get_standard_name(c) == c and c not in synonyms`) and the new one
  (`not is_known_column(c) and c not in synonyms`) return **identical sets over
  every column name in the real corpus** (patient 70/70, product 1/1) and over
  every canonical name in both reference files (0 disagreements).
- **`missing_required_field` emitted a workbook total and then its own rows**
  under the same code. The aggregate is gone; the count stays on the
  operational log. **163 -> 135**, the 28 being one aggregate per affected
  tracker.

**-1,839 and -28 is exactly the -1,867 the run moved. Nothing else changed.**

### Guarded three ways, because one was not enough

- **`Finding` refuses a mismatch at construction**, the way `file_name`
  already refuses a blank. This is the strongest guard and it is what caught
  the ~130 emit sites and test fixtures that were silently dropping the sheet.
- **A static AST guard** over every `report_finding` call site, because the
  runtime check only fires on branches something actually executes. It
  immediately found **four `sheet_skipped` sites in `extract/patient.py` that
  nothing in the suite or the corpus reaches** -- the Patient List and Annual
  `except` arms -- all four now naming their sheet.
- **`FINDING_SCOPE` is exhaustive over `ErrorCode` in both directions**, and
  the published table's scope column is asserted by test.

### A bug this shipped and the test that now stops it

`scope` went out as an **all-null column on its first real run**: the
collector's `to_dataframe` materialised the derived fields and
`create_table_findings` built its own record dicts, so the table BigQuery
actually reads had nothing in it. Both now call one `findings_dataframe`, and
`TestThePublishedTableCarriesTheDerivedFields` covers both writers. This is
the map's "never hand-maintain what can be derived" rule biting on a
derivation that existed twice.

### Also changed

- The report's **Glossary** gains a `Counted` column in plain English ("once
  per row", "once per distinct value, whole workbook"), beside the count it
  qualifies -- this is the answer to ticket 70's finding that the Summary
  sheet ranks trackers by a count weighting a per-row emitter 22x above a
  per-value one. `scope` is deliberately **not** on the Findings sheet: it is
  a property of the code, and 103,603 copies of one of eight strings is noise.
- The report's **Sheet**, **Tracker year** and **Sheet month** columns already
  existed and were always empty. They are now populated.
- `fix_sex` deduplicates by distinct value, matching the code it shares
  (`value_not_in_allowed_list`, scope `tracker_value`). Count unchanged at
  1,503 -- there is one such value in the corpus -- but the finding no longer
  names a patient, which is how the other 1,502 already behaved.
- `scripts/finding_inventory.py` prints each code's scope.

**Rejected.**

- *Leaving the blanks blank and letting the report render them as
  tracker-level.* Cheapest, publishes nothing new -- but it re-creates the
  exact ambiguity that hid 102,967 findings for two months, and the next
  emitter added reintroduces the gap in silence.
- *Splitting the aggregates into per-sheet findings so `sheet_name` is never
  empty.* Makes the field total, but inflates counts (the
  `missing_required_field` aggregate would have become 12 rows, not 1) and is
  simply false for `empty_product_data`, whose entire content is "no sheet had
  this".
- *Two fields, `scope` and `unit`.* More expressive, and the first draft of
  this taxonomy had five scope values and needed it. Killed by splitting the
  values along the extent that owns the deduplication instead -- `tracker_value`
  vs `sheet_value`, `tracker_column` vs `sheet_column` -- which lets one field
  answer both questions without either being approximate.
- *Renaming the product frame's `product_sheet_name` / `product_table_month`
  to match the patient arm's.* Would delete the helper, but those are
  published column names on `product_data`, and every consumer joins on them.
- *A test-only guard instead of the model validator.* It was tempting: the
  validator meant touching ~74 test fixtures. But a test only catches the emit
  sites a test exercises, and the four `sheet_skipped` arms above prove that
  is not enough. The fixtures were also wrong on their own terms -- they
  modelled cleaned frames that production never produces.

**Evidence: executed.** Three full pipeline runs over the real 255-tracker
corpus on the local drive, plus `duckdb` over `table_findings.parquet` each
time, plus a regenerated `findings.xlsx` inspected with openpyxl. Suite
**1,323 passed, 1 skipped, 89% coverage**; `ruff check`, `ruff format --check`
and `ty check src/` all clean.

**Tense.** Every figure describes current behaviour, measured after the change,
except the "before" column, measured on the 2026-08-27 run that preceded it.
