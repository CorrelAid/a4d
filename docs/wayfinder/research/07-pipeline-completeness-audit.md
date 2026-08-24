---
ticket: 07-pipeline-completeness-audit
title: Pipeline completeness audit — patient vs product, R-logic coverage, test parity, doc accuracy
date: 2026-08-08
method: read-only (git show / git diff / rg / file reads); no pipeline execution, no output comparison
branches_compared: migration (checked out, HEAD) vs origin/product-pipeline (not merged)
---

# Pipeline completeness audit

Read-only inventory. All claims below are independently reproducible with the
`git`/`rg`/`fd` commands shown inline. No pipeline was executed and no output
parquet was compared — per ticket scope, that's out of scope here.

## 1. R-logic coverage, module for module

### Patient (R: `r-archive/R/script1_helper_read_patient_data.R` +
`script2_helper_patient_data_fix.R`, Python: `migration` branch)

R function inventory (`rg -n "^[a-zA-Z_.]+\s*<-\s*function" r-archive/R/script2_helper_patient_data_fix.R`):
`convert_to`, `cut_numeric_value`, `correct_decimal_sign`, `parse_dates`,
`check_allowed_values`, `parse_character_cleaning_pipeline`, `parse_step`,
`parse_allowed_value_check`, `parse_character_cleaning_config`, `fix_age`,
`fix_bmi`, `fix_sex`, `extract_year_from_age`, `transform_fbg_in_mmol`,
`fix_fbg`, `fix_testing_frequency`, `replace_range_with_mean`,
`split_bp_in_sys_and_dias`, `transform_cm_to_m`, `fix_id`,
`extract_first_raw_regimen`, `extract_regimen` — plus
`extract_patient_data` in `script1_helper_read_patient_data.R`.

Python side (`src/a4d/clean/patient.py`, `clean/converters.py`,
`clean/validators.py`, `clean/transformers.py`, `clean/date_parser.py`,
`extract/patient.py`) has a 1:1-looking function for every one of these:
`convert_to`→`safe_convert_column`, `cut_numeric_value`→same name in
`converters.py`, `correct_decimal_sign`→same name, `parse_dates`→
`parse_date_flexible`/`parse_date_column`, `check_allowed_values`→
`validate_allowed_values`/`validate_column_from_rules`, `fix_age`→
`_fix_age_from_dob`, `fix_bmi`→`_calculate_bmi`/`fix_bmi` in
`transformers.py`, `fix_sex`→`fix_sex`, `fix_testing_frequency`→same name,
`replace_range_with_mean`→same name, `split_bp_in_sys_and_dias`→same name,
`fix_id`→`fix_patient_id` in `validators.py`, `extract_regimen`→same name in
`transformers.py`. No R patient function was found without a plausible
Python counterpart. This matches the prior finding that the patient side is
the mature/reference implementation.

### Product (R: `r-archive/R/helper_product_data.R` +
`script1_process_product_data.R` + `script2_process_product_data.R` +
`script3_create_table_product_data.R` + `script3_link_product_patient.R` +
`read_product_data.R`, Python: `origin/product-pipeline` only)

`helper_product_data.R` (601 lines) function inventory: `extract_product_data`,
`harmonize_input_data_columns`, `read_column_synonyms_product`,
`sanitize_column_name`, `format_date_excelnum`, `format_date_exceldate`,
`format_date`, `extract_month`, `recode_unitcolumnstozero`,
`clean_unitsreceived`, `update_receivedfrom`, `clean_receivedfrom`,
`compute_balance_cleanrows`, `compute_balance_status`, `compute_balance`,
`adjust_column_classes`, `extract_product_multiple`. `read_product_data.R`
adds `count_na_rows`, `check_entry_dates`, `check_negative_balance`,
`report_unknown_products`, `load_product_reference_data`,
`add_product_categories`, `extract_unit_capacity`.

Python (fetched via `git show origin/product-pipeline:<path>`):
- `src/a4d/extract/product.py` (431 lines) — `find_product_section` (=
  `extract_product_data`'s row-finding half), `extract_product_data`,
  `remove_header_rows`, `replace_extra_totals`, `_harmonize` (=
  `harmonize_input_data_columns`), `read_all_product_sheets`.
- `src/a4d/clean/product.py` (1073 lines) — `_split_multi_product_cells`
  (= `extract_product_multiple`), `_switch_misplaced_columns`,
  `_format_dates` (= `format_date`/`format_date_excelnum`/
  `format_date_exceldate`), `_check_entry_dates_match_sheet` /
  `_validate_entry_dates` (= `check_entry_dates`), `_extract_balance_from_received`
  (= `update_receivedfrom`), `_recode_na_units_to_zero` (=
  `recode_unitcolumnstozero`), `_clean_received_from` (= `clean_receivedfrom`),
  `_clean_units_received` (= `clean_unitsreceived`), `_remove_empty_data_rows`
  (= `compute_balance_cleanrows`), `_compute_balance_status` (=
  `compute_balance_status`), `_compute_running_balance` (= `compute_balance`),
  `_validate_negative_balances` (= `check_negative_balance`),
  `_report_unknown_products` (= `report_unknown_products`),
  `_add_product_categories` (= `add_product_categories`),
  `_extract_unit_capacity` (= `extract_unit_capacity`).
- `src/a4d/clean/schema_product.py` — 20-column meta schema, docstring says
  it "matches the R pipeline's `preparing_product_fields()`" in
  `script3_create_table_product_data.R`; field list/order does match.
- `src/a4d/reference/products.py` — `load_known_products` /
  `load_product_categories`, replaces `load_product_reference_data`; its
  docstrings explicitly say "Covers R step 2.19" / "2.20".
  `sanitize_column_name` → covered by `extract/common.py` (shared with
  patient's column-name sanitizer).
- `src/a4d/tables/product.py` — `create_table_product_data` (=
  R's `create_table_product_data`/`preparing_product_fields`, applies
  `fix_patient_id` to `product_released_to` exactly as R applies `fix_id`)
  and `link_product_patient` (= R's `script3_link_product_patient.R`, with
  one **documented** deviation — see below).

**Verdict**: every R product function has a traceable Python counterpart; no
function-level gap found. This is a stronger result than ticket 07's premise
implied ("neither status has actually been audited") — the coverage itself
looks complete at the function-inventory level. What's unverified is
*behavioral* equivalence (that's explicitly out of scope for this ticket —
belongs to output-vs-source validation).

One genuine coverage gap: `calculate_most_frequent` and
`report_empty_intersections` in `script3_create_table_product_data.R` (used
for cross-tab diagnostic logging, not core cleaning logic) have no obvious
Python counterpart — `rg -n "most_frequent|empty_intersection" src/a4d
--glob '!*.pyc'` against `origin/product-pipeline` returns nothing. These are
logging/diagnostic helpers, not data-shape-affecting logic, so low severity,
but they are a real, unmapped gap.

### Divergence documentation: found vs. only-in-diff

Where Python and R intentionally diverge, documentation quality is high on
the product side and mixed on the patient side:

- `src/a4d/tables/product.py:link_product_patient` docstring: "Mirrors R's
  `script3_link_product_patient.R` with one deviation: rows where
  `product_released_to` is null or equals the ... sentinel ... are filtered
  out before joining." — **documented in the docstring itself**, not just
  discoverable via diff.
- `src/a4d/clean/product.py` module-level constants (`BUDDHIST_ERA_THRESHOLD`,
  `YEAR_FLOOR_DELTA`, `PRODUCT_DATE_NA_MARKERS`, `MIN_PLAUSIBLE_EXCEL_SERIAL`,
  lines 42-75) carry multi-line comments explaining exactly which R quirk
  each guard works around and why. **Documented in code.**
- `docs/archive/PYTHON_IMPROVEMENTS.md` on `origin/product-pipeline` (not
  on `migration` — see §3) has a full section (§5, "Product Pipeline: Date
  Parsing Robustness") with per-issue R-vs-Python behavior tables, row
  counts, and affected tracker names for the "Sept" abbreviation bug, the
  `D/M/YYYY` bug, and the malformed-date sentinel guard. **Documented**, but
  the cited primary evidence (`Ali_internship/residual_dig.ipynb`) does not
  exist in the tracked tree on either branch — confirmed via
  `git ls-tree -r --name-only HEAD | grep -i ali_internship` and the same
  against `origin/product-pipeline`, both empty, and `find . -iname
  '*residual_dig*'` empty. This reconfirms the prior session's finding: the
  row-level counts in that section (e.g. "46 rows across 28 groups") are
  asserted prose with no reproducible artifact backing them.
- `src/a4d/validate/source_vs_output_product.py` module docstring: "Group-
  granularity checks only in v1 ... which we deliberately avoid (see the
  plan at `C:/Users/furin/.claude/plans/output-vs-source-validation-swirling-
  nygaard.md`)." **Documented, but the cited plan file is a contributor's
  local Windows path, not in this repo** — same non-reproducibility problem
  as the notebook citation above.
- Patient-side divergences (R bugs Python correctly avoids) are documented
  only in `tests/test_integration/test_r_validation.py`'s
  `ACCEPTABLE_DIFFERENCES` / `FILE_COLUMN_EXCEPTIONS` /
  `PATIENT_LEVEL_EXCEPTIONS` dicts (42 tracker-level entries, 15 with
  `"reason"` strings) — i.e. only inside a slow/USB-drive-gated test file,
  not in `docs/archive/PYTHON_IMPROVEMENTS.md`'s "Summary" table on
  `migration`, which lists only 3 items (insulin_subtype typo,
  insulin_total_units extraction, BMI precision). The patient
  divergence-documentation is real but scattered and incomplete relative to
  what's actually known (visible in the test file's exception dicts).

## 2. Test coverage shape: patient vs product

`git diff migration origin/product-pipeline --stat -- tests/` confirms 15 new
test files on `product-pipeline`; `migration` has 26, `product-pipeline` has
41 (`git ls-tree -r --name-only <branch> -- tests/ | wc -l`).

### Side-by-side inventory

| Category | Patient (migration) | Product (product-pipeline, new vs. migration) |
|---|---|---|
| Extract unit tests | `test_extract/test_patient.py` (648 lines), `test_extract/test_patient_helpers.py` (476 lines) | `test_extract/test_product.py` (385 lines), `test_extract/test_common.py` (90 lines, shared helpers) |
| Clean unit tests | `test_clean/test_patient.py` (418 lines) | `test_clean/test_product.py` (887 lines) |
| Shared clean-module tests | `test_clean/test_converters.py`, `test_clean/test_transformers.py`, `test_clean/test_validators.py` | unchanged (shared, not product-specific) |
| Tables unit tests | `test_tables/test_patient.py` (361 lines) | `test_tables/test_metadata.py` (150 lines, new), `test_tables/test_link_product_patient.py` (151 lines, new) — but **no `test_tables/test_product.py`** for `create_table_product_data` itself |
| Integration (cross-stage) | `test_integration/test_extract_integration.py` (134 lines), `test_integration/test_clean_integration.py` (133 lines) | **none** — `git diff migration origin/product-pipeline -- tests/test_integration/` is empty for every file in that directory |
| End-to-end | `test_integration/test_e2e.py` (147 lines, 4 real-tracker fixtures, `@pytest.mark.e2e`) | **none** — same empty-diff result; zero product references (`grep -ic product tests/test_integration/test_e2e.py` → 0) |
| R-comparison regression | `test_integration/test_r_validation.py` (patient-only, byte-identical across branches per prior finding — confirmed again here, `git diff` → 0 lines) | **none** |
| Source-vs-output validation (new category, not present on migration at all) | `test_validate/test_patient_source_vs_output.py` (311 lines, new) | `test_validate/test_product_source_vs_output.py` (248 lines, new) |
| State/incremental-processing tests (new module, patient- and product-agnostic) | n/a on migration (`state/` module unwired) | `test_state/{test_filter,test_integration,test_manifest,test_source}.py` (349 lines combined) |
| CLI tests | `test_cli/test_cli.py` | `test_cli/test_cli.py` (extended), `test_cli/test_force_incremental.py` (162 lines, new) |
| GCP tests | `test_gcp/{test_bigquery,test_drive,test_storage}.py` | + `test_gcp/test_select_tracker_metadata.py` (77 lines, new) |
| Pipeline orchestration unit tests | none for `pipeline/patient.py` either (shared gap, not a divergence) | none for `pipeline/product.py` (217 new lines) — only indirectly touched via mocked calls in `test_cli/test_cli.py` (`@patch("a4d.cli.run_product_pipeline")`) |

### Concrete structural gaps found

1. **No product integration or e2e test exists at all.** `tests/test_integration/`
   is byte-identical between the two branches (verified: `git diff migration
   origin/product-pipeline -- tests/test_integration/test_e2e.py
   tests/test_integration/test_clean_integration.py
   tests/test_integration/test_extract_integration.py
   tests/test_integration/conftest.py` all return empty). Patient has a
   4-fixture parametrized e2e test asserting exact row counts against real
   tracker files (`tests/test_integration/test_e2e.py:20-27`, e.g.
   `("tracker_2024_penang", 174, 2024, ...)` — this "174" is a per-tracker row
   count, unrelated to the "174 trackers" claim in §3). Product has nothing
   structurally equivalent verifying extract→clean→table works end to end.
2. **`src/a4d/extract/wide_format.py` (145 new lines, handles the Mandalay
   wide-format quirk) has zero test references anywhere in the 41-file
   product-pipeline test suite.** Verified by grepping every test file's
   content on that branch for `wide_format` / `handle_wide_format` — no
   matches in any of the 41 files.
3. **No `test_tables/test_product.py`.** `create_table_product_data` (the
   product analogue of `create_table_patient_data_static/monthly/annual`,
   which do have `test_tables/test_patient.py` coverage) is only exercised
   indirectly through `test_tables/test_link_product_patient.py`, which
   tests `link_product_patient` — a different function in the same module.
4. **`pipeline/product.py` (217 lines, the orchestrator) has no dedicated
   unit test**, mirroring the same gap that already exists for
   `pipeline/patient.py` on `migration` — this one is a shared gap, not a
   product-specific regression.
5. **R-comparison regression test is patient-only** (prior finding,
   reconfirmed): product's only automated cross-check against ground truth
   is `test_validate/test_product_source_vs_output.py`, which per its own
   module docstring (`src/a4d/validate/source_vs_output_product.py:1-7`) is
   "group-granularity only in v1" and deliberately does not reproduce
   cleaning steps 2.0-2.5, so it cannot catch row-level or cell-level
   regressions the way `test_r_validation.py` does for patient.
6. CI (`.github/workflows/python-ci.yml:47`) runs
   `pytest -m "not slow and not integration"` — so even patient's
   `test_r_validation.py` and `test_e2e.py` never execute in CI on either
   branch; they're local-only, gated on the external USB-mounted R output
   directory (`R_OUTPUT_DIR = Path("/Volumes/USB SanDisk 3.2Gen1
   Media/a4d/output_r/patient_data_cleaned")`, `test_r_validation.py:26`).

## 3. Documentation currency: patient vs product

### `docs/CLAUDE.md` (migration branch)

- Module table lists only patient modules — accurate for `migration`'s
  actual tree (`find src/a4d -iname '*product*'` on `migration` → nothing),
  not stale, just necessarily incomplete since product isn't merged.
- **"Patient pipeline: complete, validated against 174 trackers, deployed to
  production"** (line 70) — investigated in depth:
  - The "174" figure is not a static assertion anywhere; it is the dynamic
    count of files under an external, non-repo path
    (`R_OUTPUT_DIR.glob("*_patient_cleaned.parquet")` in
    `test_r_validation.py:339-350`). The docstring at the top of that file
    says "for all 174 trackers" (line 4) as a comment, not an assertion the
    test suite checks against a literal `174`.
  - The test file itself is real and substantial: 42 tracker-level
    exception entries, `PATIENT_LEVEL_EXCEPTIONS` for 3 more trackers,
    `REQUIRED_COLUMN_EXCEPTIONS` for 20 trackers, each with a specific,
    plausible, source-data-referencing reason string. This is not vaporware
    — it's a genuine, detailed regression-test design.
  - However: it is marked `pytestmark = [pytest.mark.slow,
    pytest.mark.integration]`, CI explicitly excludes `slow`/`integration`
    (`.github/workflows/python-ci.yml:47`), and it depends on a path under
    `/Volumes/USB SanDisk 3.2Gen1 Media/...` that is not part of the repo
    and not available to anyone without that physical drive. **There is no
    committed artifact anywhere in the repo (log, CSV, markdown report, CI
    run) recording the *result* of an actual 174-tracker run** — no
    `VALIDATION_TRACKING.md` exists currently (`find . -iname
    '*VALIDATION_TRACKING*'` finds nothing outside `.git` history and a
    stray `a4d-python/` vendor copy from an unrelated deploy commit
    `b57b483`, not the working tree). So: the *test infrastructure* for the
    174-tracker claim is real and checkable; the *pass result* itself is
    not verifiable from the repo and rests entirely on prose.
  - "Deployed to production": `Dockerfile` and `.github` CI exist; commit
    `b57b483` ("Deploy Python pipeline as Cloud Run Job") shows Cloud Run
    deployment tooling was added. No repo artifact (deploy log, GCP export)
    confirms an actual successful production deployment beyond that
    tooling's existence — consistent with wayfinder ticket 05
    ("production-verification-run", still `blocked`) treating this as
    unverified.

### `docs/archive/MIGRATION_GUIDE.md` and `PYTHON_IMPROVEMENTS.md`

- `migration` branch: `MIGRATION_GUIDE.md:5` says "Phases 0–7 complete...
  Product pipeline not yet started" — accurate for that branch's actual
  tree (no `src/a4d/*product*` files exist there).
- `origin/product-pipeline` branch (`git show
  origin/product-pipeline:docs/archive/MIGRATION_GUIDE.md`): line 5 says
  "Phases 0–9 complete... Product pipeline merged into `src/a4d/` on
  2026-04-23." This is accurate *self-referentially* (that branch's tree
  really does contain the product modules, confirmed by the `git diff
  --stat` file list in §1) but the phrase "merged into `src/a4d/`" could
  mislead a reader into thinking it's merged into `migration`/`dev` — it
  is not (`git branch -a` shows `product-pipeline` only as a remote branch,
  ticket 03 "Merge product-pipeline (PR #6) into migration" is still open).
- `PYTHON_IMPROVEMENTS.md` diff (`git diff migration origin/product-pipeline
  -- docs/archive/PYTHON_IMPROVEMENTS.md`, 87 lines added) adds §5/§6 for
  product date-parsing and running-balance precision, plus updates the
  "Migration Validation Status" summary to declare "production-ready" and
  "All value differences are Python improvements over R bugs or negligible
  precision drift." This blanket claim is not fully supported: the
  underlying evidence for the date-parsing row counts is the
  non-existent `Ali_internship/residual_dig.ipynb` (see §1), and the file
  itself provides no link to a reproducible script that regenerates those
  numbers — i.e. the qualitative direction of each divergence (Python
  correct, R buggy) is plausible and mostly consistent with what the code
  comments describe, but the specific row/group counts asserted in the
  document are not currently checkable against anything in the repo.

### Module docstrings

Product module docstrings (`clean/product.py`, `extract/product.py`,
`reference/products.py`, `tables/product.py`, `validate/
source_vs_output_product.py`) consistently cite specific R script names and
step numbers ("Covers R Script 2 steps 2.1-2.22", "Covers R steps 3.1-3.3",
"Covers R step 2.19"). These are checkable claims — cross-referencing them
against `r-archive/R/` (§1) shows they're accurate. This is a stronger
documentation practice than exists on the patient side, where
`clean/patient.py` does not carry an equivalent "covers R steps X-Y" header
comment mapping its private helpers to R script line ranges.

## 4. Concrete gap list

### Product — before "complete"

1. Add `tests/test_integration/` coverage: an extract→clean cross-stage
   test and an e2e test for product, parallel to patient's
   `test_extract_integration.py` / `test_clean_integration.py` /
   `test_e2e.py`. Currently zero.
2. Add tests for `src/a4d/extract/wide_format.py` — currently zero
   references across all 41 test files.
3. Add `tests/test_tables/test_product.py` covering
   `create_table_product_data` directly (currently only reachable via the
   `link_product_patient` test file).
4. Either replace or supplement the "group-granularity only" product
   source-vs-output validator with a cell-level regression check (its own
   docstring already flags this as a known, deliberate v1 limitation), or
   document why group-granularity is considered sufficient long-term.
5. Fix the two dangling evidence citations: `Ali_internship/
   residual_dig.ipynb` (cited in `PYTHON_IMPROVEMENTS.md` §5) and the
   Windows-local plan path (cited in `source_vs_output_product.py`'s module
   docstring) — neither exists in the repo; either commit the artifacts or
   replace the citations with reproducible-in-repo evidence.
6. `calculate_most_frequent` / `report_empty_intersections` (R diagnostic
   helpers) have no Python equivalent — confirm this is an intentional drop
   (they appear to be diagnostic-only, not data-shape-affecting) and note
   it explicitly rather than leaving it silent.
7. Merge is still blocked on wayfinder tickets 03/04/05/06 (CI red at
   `migration` HEAD, no real GCP verification run) — this audit doesn't
   resolve those, just confirms the code/test/doc state feeding into them.

### Patient — before "complete" (despite being the more mature side)

1. The "174 trackers validated" claim in `docs/CLAUDE.md` has real,
   detailed test infrastructure behind it (`test_r_validation.py`) but no
   committed record of an actual passing run — it is `slow`/`integration`,
   excluded from CI, and gated on an external USB drive. Either commit a
   dated validation report (a script-generated one, per the wayfinder map's
   "no notebooks, ever" / automated-report preference) each time this is
   run, or soften the docs claim to reflect that it's manually-verified,
   not continuously verified.
2. `docs/archive/PYTHON_IMPROVEMENTS.md`'s "Summary" table on `migration`
   lists only 3 known R/Python divergences, while `test_r_validation.py`'s
   exception dictionaries document ~15+ distinct, reasoned divergences
   (province validation, Unicode ≥/≤ handling, duplicate patient IDs,
   systematic R extraction failures on several 2025 trackers, etc.) that
   never made it into the human-readable doc — someone reading
   `PYTHON_IMPROVEMENTS.md` alone would materially undercount the known
   differences.
3. No dedicated unit test exists for `pipeline/patient.py` (the
   orchestrator) — same category of gap product also has for
   `pipeline/product.py`; worth deciding once, not twice, for both.
4. "Deployed to production" is asserted in `docs/CLAUDE.md` without a
   corresponding checkable artifact in the repo (matches wayfinder ticket
   05's own framing of this as still open/unverified).

## Commands used (for reproducibility)

```
git branch -a
git log origin/product-pipeline -5 --oneline
git diff migration origin/product-pipeline --stat
git diff migration origin/product-pipeline --stat -- tests/
git ls-tree -r --name-only HEAD -- tests/ | sort
git ls-tree -r --name-only origin/product-pipeline -- tests/ | sort
git diff migration origin/product-pipeline -- tests/test_integration/test_e2e.py ...
git show origin/product-pipeline:<path>         # read files on that branch
git diff migration origin/product-pipeline -- docs/archive/PYTHON_IMPROVEMENTS.md
git diff migration origin/product-pipeline -- docs/archive/MIGRATION_GUIDE.md   # via saved copy + diff
rg -n "^[a-zA-Z_.]+\s*<-\s*function" r-archive/R/helper_product_data.R (and other R files)
rg -n "^def |^class " <python module>
find . -iname "*residual_dig*" ; git ls-tree -r --name-only HEAD | grep -i ali_internship
find . -iname "*VALIDATION_TRACKING*" -not -path "./.git/*"
grep -n "slow\|pytest" .github/workflows/python-ci.yml
```
