#!/usr/bin/env python3
"""Diff a Python pipeline output directory against the frozen R baseline.

Migration-only tooling with a defined end-of-life (R's retirement, ticket 12)
-- deliberately not wired into `a4d.cli`. Decoupled from pipeline execution:
takes two existing output directories and diffs them. Logic lives in
`a4d.migration.compare`; this is a thin CLI + report writer. Per stage
(patient/product x raw/cleaned) writes one Excel workbook -- summary sheets
(aggregate counts) plus the actual flagged rows, one sheet per measure. Excel,
not HTML, because triage means loading this as a dataframe, filtering,
sorting, and adding columns -- not just reading a static page.

Usage:
    uv run python scripts/compare_outputs.py \
        --r-dir "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r" \
        --py-dir "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python" \
        --output-dir output/comparison
"""

import json
import re
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum, auto
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from loguru import logger
from openpyxl import Workbook
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from a4d.clean.schema import (
    get_date_columns,
    get_numeric_columns,
)
from a4d.clean.schema import (
    get_string_columns as get_patient_string_columns,
)
from a4d.clean.validators import load_validation_rules
from a4d.migration.compare import (
    BUDDHIST_ERA_CONVERSION_CLASSIFIERS,
    DERIVED_RUNNING_TOTAL_CLASSIFIERS,
    EXCEL_FORMULA_ERROR_CLASSIFIERS,
    PATIENT_ABSURD_SERIAL_CLASSIFIERS,
    PATIENT_AGE_FROM_BARE_YEAR_CLASSIFIERS,
    PATIENT_BARE_YEAR_CLASSIFIERS,
    PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS,
    PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    PATIENT_CLINICAL_NOTE_CLASSIFIERS,
    PATIENT_DIAGNOSIS_AGE_CLASSIFIERS,
    PATIENT_FBG_TEXT_CLASSIFIERS,
    PATIENT_FUTURE_DATE_CLASSIFIERS,
    PATIENT_GLUCOSE_CASCADE_CLASSIFIERS,
    PATIENT_GLUCOSE_UNIT_CLASSIFIERS,
    PATIENT_HBA1C_RANGE_CLASSIFIERS,
    PATIENT_INSULIN_DRUG_NAME_CLASSIFIERS,
    PATIENT_INSULIN_SUBTYPE_CLASSIFIERS,
    PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS,
    PATIENT_INSULIN_TYPE_CLASSIFIERS,
    PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS,
    PATIENT_MERGED_SUBVALUE_TRIM_CLASSIFIERS,
    PATIENT_MONTH_NAME_TRUNCATED_CLASSIFIERS,
    PATIENT_NA_UNITE_PADDING_CLASSIFIERS,
    PATIENT_NON_LATIN_HEADER_CLASSIFIERS,
    PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    PATIENT_RICHTEXT_SPACE_CLASSIFIERS,
    PATIENT_SCREENING_SELECTION_CLASSIFIERS,
    PATIENT_UNICODE_SANITIZER_CLASSIFIERS,
    PATIENT_UNREADABLE_MONTH_CLASSIFIERS,
    PATIENT_UNRECONSTRUCTABLE_DATE_CLASSIFIERS,
    PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS,
    PATIENT_YMD_FIRST_CLASSIFIERS,
    PRODUCT_CATEGORY_CLASSIFIERS,
    PRODUCT_ENTRY_DATE_CLASSIFIERS,
    PRODUCT_ROW_ORDER_CLASSIFIERS,
    PYTHON_CANONICAL_LABEL_CLASSIFIERS,
    R_DATE_ERROR_SENTINEL_CLASSIFIERS,
    R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS,
    ROW_ORDINAL_COL,
    STRAY_DATE_CLASSIFIERS,
    STRAY_DATE_DROPPED_CLASSIFIERS,
    STRAY_DATE_ZEROED_CLASSIFIERS,
    WIDE_FORMAT_FRAGMENT_CLASSIFIERS,
    Delta,
    DirectoryComparison,
    FileComparison,
    add_row_ordinal,
    align_duplicate_rows,
    build_mismatch_rows,
    build_summary_rows,
    compare_directory,
    compute_deltas,
    load_glucose_unit_swaps,
    normalize_boolean_literal_column,
    normalize_date_column,
    normalize_numeric_column,
    normalize_whitespace_column,
    numeric_normalize_targets,
    snapshot_from_summary,
    string_numeric_normalize_targets,
    summarize_directory,
    whitespace_normalize_targets,
)

# normalize_date_column (via a4d.clean.date_parser.parse_date_flexible) logs
# at DEBUG per parsed value; loguru's default sink has no level filter, so
# without this every date cell would spam the console. This tool never calls
# a4d.logging.setup_logging() (no pipeline run, no output_root to log into).
#
# a4d.clean.* is silenced entirely, not just below WARNING: the date parser
# also warns once per value it cannot parse, which in the *pipeline* is a
# real data-quality signal but here is pure noise -- this tool feeds it raw
# free-text columns precisely to normalize the parseable ones, so
# unparseable cells are expected, not actionable, and at 18 date columns x
# ~245 files they drown the report the tool exists to print.
logger.remove()
logger.add(
    sys.stderr,
    level="WARNING",
    filter=lambda record: not record["name"].startswith("a4d.clean"),
)

console = Console()
app = typer.Typer()


class Sentinel(Enum):
    """Marks a normalization that resolves against each frame's own columns."""

    ALL_RAW_COLUMNS = auto()
    ALL_STRING_COLUMNS = auto()


ALL_RAW_COLUMNS = Sentinel.ALL_RAW_COLUMNS
ALL_STRING_COLUMNS = Sentinel.ALL_STRING_COLUMNS

PATIENT_KEY_COLS = ["patient_id", "sheet_name"]
PATIENT_ID_COL = "patient_id"
# Fields with allowed-value validation in reference_data/data_cleaning.yaml --
# the genuinely categorical patient columns, not free text.
PATIENT_CATEGORICAL_COLS = [
    "analog_insulin_long_acting",
    "analog_insulin_rapid_acting",
    "clinic_visit",
    "complication_screening_eye_exam_value",
    "complication_screening_foot_exam_value",
    "dm_complication_eye",
    "dm_complication_kidney",
    "dm_complication_others",
    "hospitalisation_cause",
    "human_insulin_intermediate_acting",
    "human_insulin_pre_mixed",
    "human_insulin_short_acting",
    "insulin_regimen",
    "insulin_type",
    "insulin_subtype",
    "observations_category",
    "patient_consent",
    "province",
    "remote_followup",
    "status",
    "support_level",
]

# Raw-stage-only, derived from the cleaned schema's own pl.Date columns
# (ticket 23): the same representation gap ticket 20 found and fixed for
# product's raw product_entry_date -- R's raw extraction stores the
# unparsed source text (an Excel serial for date-formatted cells) while
# Python's raw extraction already ISO-formats parsed dates. Cleaned stage
# never needs this since both sides are already parsed dates there.
# meter_received_date (ticket 27) is appended by hand: it's a raw-only
# column absent from the cleaned schema entirely (no cleaned-stage
# equivalent), so get_date_columns() can't see it, but it carries the same
# raw-serial-vs-parsed representation gap -- verified against real drive
# data (1,761 mismatches collapsed to the same shape as the derived columns).
# complication_screening_date (ticket 48) is appended for the same reason: the
# cleaned schema splits screening dates per test (eye/foot/kidney/...), so the
# generic raw column has no cleaned-stage equivalent for get_date_columns() to
# find. It only became visible once ticket 48's merged-header fix started
# extracting the column at all.
PATIENT_RAW_DATE_NORMALIZE_COLS = [
    *get_date_columns(),
    "meter_received_date",
    "complication_screening_date",
]

# Raw-stage-only (ticket 27, extending ticket 22's product_balance
# precedent to patient): R's own float-to-string conversion rounds a raw
# numeric column's trailing digits differently than Python's -- a
# representation difference cleaning's own type-casting already resolves.
#
# Ticket 43 widened this from get_numeric_columns() to every raw column: that
# list
# is derived, but from the wrong schema -- it cannot name the Patient List
# join's ".static" copies (fbg_baseline_mg.static, fbg_baseline_mmol.static)
# and it types a screening measurement as a string because the column can
# also hold "normal" (complication_screening_*_value). All four hold plain
# floats, and all four were reported as mismatches purely because R and
# Python round a float's string form differently. Measured before widening:
# across all 27,980 raw-stage mismatches, exactly 434 have both sides parsing
# to the same float, and all 434 sit in those four columns -- so this widens
# equality without changing anything else. See numeric_normalize_targets.
PATIENT_RAW_NUMERIC_NORMALIZE_COLS = ALL_RAW_COLUMNS

# Ordinal position within (clinic_id, product_sheet_name) -- see
# add_row_ordinal's docstring. Replaces the old equi-join key (clinic_id,
# product, product_sheet_name, product_entry_date), which collapsed onto far
# fewer distinct values than rows exist wherever product_entry_date is null
# (ticket 17).
PRODUCT_ORDINAL_GROUP_COLS = ["clinic_id", "product_sheet_name"]
PRODUCT_ID_COL = "product"
PRODUCT_TRACKER_YEAR_COL = "product_table_year"
PRODUCT_CATEGORICAL_COLS = ["product_category", "product_balance_status"]

# Raw-stage-only (ticket 24, extending ticket 22's product_balance precedent):
# R's own float-to-string conversion rounds a raw numeric column's trailing
# digits differently -- same representation gap product_balance already had,
# just not yet wired for these three quantity columns.
PRODUCT_RAW_NUMERIC_NORMALIZE_COLS = [
    "product_balance",
    "product_units_received",
    "product_units_released",
    "product_received_from",
]

# Raw-stage-only (ticket 22): readxl's trim_ws=TRUE default strips whitespace
# R-side that openpyxl-based Python extraction preserves as-is. Every raw
# string column except product_entry_date (date-normalized instead) and
# product_balance (numeric-normalized instead).
PRODUCT_RAW_WHITESPACE_NORMALIZE_COLS = [
    "product",
    "product_received_from",
    "product_released_to",
    "product_remarks",
    "product_units_received",
    "product_units_released",
    "product_units_returned",
    "product_returned_by",
]

# ticket 21: unlike the other raw-stage-only normalizations, an embedded
# \r\n-vs-\n line break survives cleaning (step 2.16's str.strip_chars only
# trims ends) and still shows up on `product` at the cleaned stage --
# verified directly against the real R/Python cleaned output pair (e.g.
# "FastClix \r\nLancets" vs "FastClix \nLancets"). Scoped to `product` alone:
# it's the only cleaned-stage column found carrying multi-line values: rest
# were already fully explained by PRODUCT_ROW_ORDER_CLASSIFIERS.
# ticket 36 extends this to the two identifier columns. Both pipelines now
# trim every string cell; R trims only product_released_to, so R keeps a
# stray space the source really carries (sheet tab "Dec24 ", file
# "... - final .xlsx"). A settled representation difference, so the report
# should stop counting it as divergence.
PRODUCT_CLEANED_WHITESPACE_NORMALIZE_COLS = ["product", "product_sheet_name", "file_name"]

# ticket 36: patient cleaning now trims too, and sheet_name is half the
# patient row-alignment key -- without this, R's untrimmed "Dec24 " would
# fail to join Python's "Dec24" and drop those rows from the comparison
# entirely rather than showing them as equal.
# Derived from the patient schema rather than hand-listed. R's cleaned patient
# output keeps the trailing whitespace its source cells carry (measured: ~3,750
# cells across edu_occ, observations, name, family_history and others), which
# Python's cleaning now strips -- a settled representation difference, and the
# same treatment ticket 22 gave product's raw stage. sheet_name matters most:
# it is half the patient row-alignment key, so without this R's untrimmed
# "Dec24 " would fail to join Python's "Dec24" and drop those rows from the
# comparison entirely rather than showing them as equal.
PATIENT_WHITESPACE_NORMALIZE_COLS = get_patient_string_columns()

# Ticket 49 widens this to every string column for the *raw* stage only, on
# the same grounds ticket 43 widened the numeric list: get_patient_string_columns()
# reads the cleaned schema, which cannot see a raw-only column
# (dm_complications, no cleaned equivalent) and types as Float64 columns the
# raw stage still holds as text (insulin_injections, hba1c_updated). Those
# three were the entire residual of readxl's trim_ws and \r\n line endings at
# the raw stage -- 40 of the 229 unclassified mismatches. The cleaned stage
# keeps the schema-derived list: there the dtypes are real, and a column
# typed Float64 genuinely holds floats rather than text.
PATIENT_RAW_WHITESPACE_NORMALIZE_COLS = ALL_RAW_COLUMNS

# Ticket 54: cleaning casts its numeric columns, so the cleaned stage needs
# numeric normalization only where the schema keeps a measurement as a string
# (a screening value that can also read "normal"). Resolved per frame against
# the frame's own dtypes -- see string_numeric_normalize_targets.
PATIENT_CLEANED_NUMERIC_NORMALIZE_COLS = ALL_STRING_COLUMNS

CLASSIFIERS_BY_COLUMN = {
    # ticket 28: R's static "Patient List" recruitment-date extraction fails
    # to populate recruitment_date for most patients even where the tracker
    # plainly records one -- verified against the real source Excel.
    "recruitment_date": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    # ticket 37: two verified R gaps on the same column -- the leading-space
    # defeat of R's own "Updated 2022" header fixup on 2022 trackers, and the
    # 2026 template's new "Annual" sheet, which R reads nothing from. Both
    # leave R null where Python has a source-verified value, so both land on
    # r_extraction_gap; the future-date cause covers the reverse direction.
    "edu_occ_updated": PATIENT_FUTURE_DATE_CLASSIFIERS | PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    # ticket 28: R's own allowed-values validator rejects the multi-insulin
    # CSV output R's own derivation logic produces for 2024+ trackers --
    # already documented as a deliberate Python correction in
    # _derive_insulin_fields's docstring (src/a4d/clean/patient.py).
    "insulin_subtype": PATIENT_INSULIN_SUBTYPE_CLASSIFIERS,
    # ticket 42: Python resolves glucose readings recorded under the wrong
    # unit's header (a decision taken on A4D's medical advisor's answer); R has
    # no unit resolution, so every correction shows as a divergence. The
    # baseline-mg join question is a separate, still-open population, which is
    # why the classifier never fires on an R-null cell.
    # ticket 46 adds the rich-text space cause; it is disjoint from the unit
    # correction, which only fires where both sides parse as numbers.
    "fbg_updated_mg": PATIENT_GLUCOSE_UNIT_CLASSIFIERS | PATIENT_RICHTEXT_SPACE_CLASSIFIERS,
    "fbg_updated_mmol": PATIENT_GLUCOSE_UNIT_CLASSIFIERS,
    # ticket 31: the three canonical columns whose source sub-columns both
    # pipelines unite into one value. R's tidyr::unite pads absent
    # sub-columns with the literal string "NA"; Python skips them. Derived,
    # not guessed: these are the only targets that form a duplicate group
    # anywhere in the 254-tracker set.
    # ticket 50 adds the multi-select cause: where the same merged block holds
    # several "(Select)" sub-columns, R's duplicate-name suffixing keeps only
    # the first. Checked after the padding cause, which is the more specific of
    # the two (the shapes are disjoint -- R's value carries no NA token here).
    "complication_screening": (
        PATIENT_NA_UNITE_PADDING_CLASSIFIERS | PATIENT_SCREENING_SELECTION_CLASSIFIERS
    ),
    "latest_complication_screenning": PATIENT_NA_UNITE_PADDING_CLASSIFIERS,
    # ticket 46: two whitespace causes in opposite directions -- readxl
    # dropping a whitespace-only rich-text run (verified in the source XML of
    # 2017 Yangon and 2022 Mahosot) and Python's own trimming of each
    # sub-value before the merge ticket 31 added. Both are direction-scoped,
    # so their order relative to each other does not matter.
    "observations": (
        PATIENT_NA_UNITE_PADDING_CLASSIFIERS
        | PATIENT_RICHTEXT_SPACE_CLASSIFIERS
        | PATIENT_MERGED_SUBVALUE_TRIM_CLASSIFIERS
    ),
    "hba1c_updated": PATIENT_RICHTEXT_SPACE_CLASSIFIERS,
    # ticket 46: R reads no header at all for the 2021 Kantha Bopha column
    # holding the regimen (verified: Mar21!Q, both header rows empty, data
    # "Self-mixed BD"), so it drops the column; Python recovers the name from
    # the sibling sheets that label it (ticket 30). Scoped here rather than
    # left to the generic gap classifier because that one file is the whole
    # of the column's residual.
    "insulin_regimen": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    # ticket 37: the sibling insulin_type column has a different cause --
    # R's ifelse propagates NA from a blank human-insulin column and loses
    # a type the analog columns plainly state.
    "insulin_type": PATIENT_INSULIN_TYPE_CLASSIFIERS,
    # ticket 36: R rejects a source value for its trailing whitespace alone
    # and sentinels it; Python now trims before validating and keeps it.
    "sex": PATIENT_UNTRIMMED_VALIDATION_CLASSIFIERS,
    # ticket 27: bmi and t1d_diagnosis_age are formula-derived in the source
    # trackers -- a source formula error (height 0, an unparseable date)
    # leaves R's raw extraction holding the literal Excel error string,
    # while Python's raw extraction (openpyxl, data_only) has no cached
    # value to carry and returns null. age shares the same shape on a
    # handful of rows. Verified against the real drive data.
    "bmi": EXCEL_FORMULA_ERROR_CLASSIFIERS,
    # ticket 50 adds the stray-date cause: two trackers record a diagnosis
    # *date* in this numeric column. Disjoint from the formula-error cause,
    # which needs an Excel error string on R's side.
    "t1d_diagnosis_age": EXCEL_FORMULA_ERROR_CLASSIFIERS | STRAY_DATE_CLASSIFIERS,
    "age": EXCEL_FORMULA_ERROR_CLASSIFIERS,
    # ticket 27: source-data typos where a clinician entered a Thai
    # Buddhist-Era year into a Gregorian date cell -- see
    # PATIENT_BUDDHIST_ERA_CLASSIFIERS's docstring. Every raw-stage date
    # column found carrying this pattern against the real drive data.
    "bmi_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "hba1c_updated_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    # ticket 37: also the R extraction gap on the 2026 template's new
    # "Annual" sheet -- checked after the Buddhist-era cause, which is the
    # more specific of the two (the shapes are disjoint either way).
    "blood_pressure_updated": (
        PATIENT_BUDDHIST_ERA_CLASSIFIERS | PATIENT_R_EXTRACTION_GAP_CLASSIFIERS
    ),
    # ticket 50: 2019 Preah Kossamak's Jul19/Aug19 sheets lost the header merge
    # that qualifies the FBG "Date" sub-header, so R is left with a bare `date`
    # column it cannot map -- see _is_r_extraction_gap. That one file is the
    # whole of the column's residual.
    "fbg_updated_date": (PATIENT_BUDDHIST_ERA_CLASSIFIERS | PATIENT_R_EXTRACTION_GAP_CLASSIFIERS),
    # ticket 49: 2022 Mukdahan appends Thai translations to both headers, which
    # R's Unicode-aware sanitizer keeps and its exact match then misses -- see
    # _is_r_non_latin_header_miss. Python recovers 44 real dates R drops.
    "last_clinic_visit_date": (
        PATIENT_BUDDHIST_ERA_CLASSIFIERS | PATIENT_NON_LATIN_HEADER_CLASSIFIERS
    ),
    "last_remote_followup_date": PATIENT_NON_LATIN_HEADER_CLASSIFIERS,
    # ticket 49, extending ticket 37's verified 2026 finding to the columns it
    # did not reach: the 2026 template carries these on its new "Annual" sheet,
    # which R reads no values from. Verified per column against the real source
    # Excel (2026 ISDFI, Annual!E32/H32/I32/AD32 for PH_QC022: "college
    # graduate", 80, 50, "for cataract surgery" -- exactly Python's values);
    # every affected row across all five files is a 2026 tracker.
    "blood_pressure_sys_mmhg": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    "blood_pressure_dias_mmhg": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    "edu_occ": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    "other_issues": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    "status": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    # ticket 50: the 2022 Kantha Bopha header opens with thirteen spaces, which
    # defeats R's name sanitizer the way ticket 37's "Updated 2022" leading
    # space did -- both columns of the block, so both carry the gap cause.
    # ticket 39: the clinical-note causes go last, so a cell explained by a
    # specific mechanism above is not swallowed by the broad "R sentinels a
    # note it cannot read" shape.
    "hospitalisation_date": (
        PATIENT_BUDDHIST_ERA_CLASSIFIERS
        | PATIENT_R_EXTRACTION_GAP_CLASSIFIERS
        | PATIENT_CLINICAL_NOTE_CLASSIFIERS
    ),
    "hospitalisation_cause": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    # ticket 50: 2025 LWCH leaves the current-month visit column unheaded in
    # both header rows, so R drops it and Python recovers the name from the
    # sibling month sheets (ticket 30). Disjoint from ticket 49's boolean
    # spelling fold, which never leaves R null.
    "clinic_visit": PATIENT_R_EXTRACTION_GAP_CLASSIFIERS,
    # ticket 50: a date typed into a non-date column. R's readxl coerces the
    # whole column to its majority numeric type and carries the raw Excel
    # serial; Python's openpyxl honours the cell's own date format. Verified
    # source-side per column (2023 Chiang Mai Patient List!H14 and 2023 Yangon
    # General Patient List!H76, both `mmm-yy`/`d-mmm-yyyy` formatted; 2020
    # Mahosot Nov20!R152; 2021 Khon Kaen Mar21!P60) -- the same
    # openpyxl_date_typed_stray_cell ticket 24 root-caused on the product arm,
    # and a source defect reported for ticket 40 rather than a pipeline change.
    "blood_pressure_mmhg": STRAY_DATE_CLASSIFIERS,
    "testing_frequency": STRAY_DATE_CLASSIFIERS,
    "complication_screening_kidney_test_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "complication_screening_lipid_profile_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "complication_screening_thyroid_test_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    "complication_screening_eye_exam_date": PATIENT_BUDDHIST_ERA_CLASSIFIERS,
    # ticket 36: the entry-date-specific causes are checked first (they are
    # source-verified and stage-specific), then the row-order fallback every
    # positionally-aligned product column carries. R's readxl nulls the
    # *text*-formatted cells of a mixed-type Entry Date column (verified: 2022
    # Vietnam National Children's Hospital, Apr22, where "20/04/2022" is
    # stored as text and "2022-04-01" as a datetime), which drops R back to
    # input-order sorting -- so both sides hold a real, different date and
    # `r_value_missing` never fires.
    # ticket 61 leads: a Buddhist-era entry date the cleaned stage converts is
    # otherwise claimed by python_out_of_window_date_preserved, whose test the
    # R side genuinely passes.
    "product_entry_date": (
        BUDDHIST_ERA_CONVERSION_CLASSIFIERS
        | PRODUCT_ENTRY_DATE_CLASSIFIERS
        | PRODUCT_ROW_ORDER_CLASSIFIERS
    ),
    "product_category": PRODUCT_CATEGORY_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 21: cleaned-stage columns whose mismatches are dominated by a
    # within-(clinic, sheet) sort-order divergence, not genuine content
    # differences -- see PRODUCT_ROW_ORDER_CLASSIFIERS's docstring.
    # ticket 36: the endpoint test comes first -- it is the order-independent
    # evidence for a derived running total, where the membership heuristic
    # under-detects by construction (27.9% caught, ticket 21's "future work").
    "product_balance": DERIVED_RUNNING_TOTAL_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 24: also carries the raw-stage stray-date-typed-cell cause --
    # merged since CLASSIFIERS_BY_COLUMN holds one registry per column across
    # every stage. Stray-date checked first: row_order_candidate is a loose
    # "this value appears elsewhere in the group" heuristic that false-fires
    # on common small values like "0", so it must not shadow the more
    # specific, source-verified stray-date match.
    "product_received_from": STRAY_DATE_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_released_to": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_remarks": PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 36: STRAY_DATE_ZEROED_CLASSIFIERS is the cleaned-stage face of the
    # same cause and must, like the raw-stage one, precede the loose row-order
    # heuristic -- "0" appears all over a group, so row_order_candidate
    # false-fires on it.
    "product_units_received": STRAY_DATE_CLASSIFIERS
    | STRAY_DATE_ZEROED_CLASSIFIERS
    | PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product": PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 36: the remaining schema columns, wired so no positionally
    # aligned column is left without the row-order fallback.
    "product_units_notes": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_units_returned": STRAY_DATE_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_returned_by": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_balance_status": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "orig_product_released_to": PRODUCT_ROW_ORDER_CLASSIFIERS,
    "product_unit_capacity": PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 24: raw-stage wide-format comma/hyphen split ambiguity (2017-2019
    # Mandalay files). ticket 25 adds the row-order cause for the cleaned
    # stage, which this column shares with every sibling above -- it was
    # omitted when ticket 21 named six columns and not this one, leaving
    # 2,144 cleaned-stage mismatches reported as unclassified. Wide-format
    # first (it is source-verified and stage-specific); measured against the
    # real drive data, it matches nothing at the cleaned stage, so the order
    # only guards the raw stage's existing classification.
    "product_units_released": WIDE_FORMAT_FRAGMENT_CLASSIFIERS | PRODUCT_ROW_ORDER_CLASSIFIERS,
    # ticket 29: R's insulin-column dedup grep deletes "TOTAL Insulin Units"
    # from every 2024+ tracker before it is read, so R's column is null on all
    # 81,859 rows while Python reads it correctly.
    "insulin_total_units": PATIENT_INSULIN_TOTAL_UNITS_CLASSIFIERS,
    # ticket 29: R's Patient List join suffixes both sides on a name
    # collision, so R's cleaning finds no unsuffixed column and leaves these
    # null for the whole file (21 files / 3 files respectively).
    # ticket 42 is checked first and is disjoint from the join question: it
    # never fires on an R-null cell, which is the whole of the join shape.
    "fbg_baseline_mg": (
        PATIENT_GLUCOSE_UNIT_CLASSIFIERS | PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS
    ),
    "fbg_baseline_mmol": (
        PATIENT_GLUCOSE_UNIT_CLASSIFIERS | PATIENT_JOIN_SUFFIX_COLLISION_CLASSIFIERS
    ),
}

# ticket 29: every column whose validation rules declare canonical-label
# aliases diverges from R by design -- R's config lists the retired spelling
# as an allowed value and its first-match lookup collapses onto it, while
# Python folds retired spellings into one canonical label. Derived from the
# same config that produces the values, so a future alias needs no edit here.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PYTHON_CANONICAL_LABEL_CLASSIFIERS
    for col, spec in load_validation_rules().items()
    if isinstance(spec, dict) and spec.get("aliases")
}

# ticket 29: R's 999999 numeric sentinel is not a property of any one column
# -- R stamps it on any numeric cell whose source text failed to parse -- so
# it is derived from the patient schema's own numeric column list rather than
# hand-listed. Appended after each column's specific causes so a
# source-verified, column-specific classifier still wins the first match.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | R_NUMERIC_ERROR_SENTINEL_CLASSIFIERS
    for col in get_numeric_columns()
}

# ticket 38: the same argument on the date path -- R stamps 9999-09-09 on any
# date cell that recorded an absence its is.na() check does not recognize
# (literal "NA", "-", "Nil"), so like its numeric twin the cause belongs to
# every date column rather than to any one of them. Derived from the schema's
# own date column list, and appended last so a column-specific,
# source-verified cause still wins the first match.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | R_DATE_ERROR_SENTINEL_CLASSIFIERS
    for col in get_date_columns()
}

# ticket 51: R's ymd-before-dmy parse order, which mis-reads any D.M.YY source
# string. Same argument again -- parse_date_string is R's one date entry point,
# so the cause belongs to every date column, not to the five that happen to
# carry it in the current tracker set.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_YMD_FIRST_CLASSIFIERS
    for col in get_date_columns()
}

# ticket 60: a junk Excel serial published as a year-3000-plus date is not
# evidence about R -- it was reaching r_parse_order_cannot_read_cell, which
# asserts R's parse orders failed, when R had simply carried the serial
# through as a string. Prepended rather than appended because the cause it
# must out-rank is itself schema-derived; safe to run first because its own
# Buddhist-era band check declines a genuine BE year.
CLASSIFIERS_BY_COLUMN |= {
    col: PATIENT_ABSURD_SERIAL_CLASSIFIERS | CLASSIFIERS_BY_COLUMN.get(col, {})
    for col in get_date_columns()
}

# ticket 52: a bare year typed into a date cell, which Python now resolves as
# the year and R still reads as a 1905 Excel serial. parse_date_flexible is
# Python's one date entry point, so the cause belongs to every date column
# rather than to the two that carry it in the current tracker set.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_BARE_YEAR_CLASSIFIERS
    for col in get_date_columns()
}

# ticket 52: the two ages derived from those dates. Named explicitly rather
# than derived from a list: these are exactly the columns _fix_age and
# _fix_t1d_diagnosis_age compute from dob and t1d_diagnosis_date.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_AGE_FROM_BARE_YEAR_CLASSIFIERS
    for col in ("age", "t1d_diagnosis_age")
}

# ticket 51: Python's own beyond-tracker-year guard (_validate_dates), which
# runs over get_date_columns() itself -- so the cause has exactly that domain
# by construction, not by observation.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_BEYOND_TRACKER_YEAR_CLASSIFIERS
    for col in get_date_columns()
}

# ticket 54: R never derives a diagnosis age at all (its call site is
# commented out), and a date typed into that column reaches R as a serial.
# Scoped to the one column _fix_t1d_diagnosis_age computes, and appended after
# PATIENT_AGE_FROM_BARE_YEAR_CLASSIFIERS so the bare-year subset -- which is
# the same mechanism already decided under a narrower, row-flagged test --
# keeps its own name rather than being absorbed by the general one.
CLASSIFIERS_BY_COLUMN["t1d_diagnosis_age"] = (
    CLASSIFIERS_BY_COLUMN.get("t1d_diagnosis_age", {}) | PATIENT_DIAGNOSIS_AGE_CLASSIFIERS
)

# ticket 55: the 2024+ insulin tick boxes that one clinic ticks by naming the
# drug. Appended after the existing insulin_subtype causes so the narrower
# multi-value shape keeps its own name.
CLASSIFIERS_BY_COLUMN["insulin_subtype"] = (
    CLASSIFIERS_BY_COLUMN.get("insulin_subtype", {}) | PATIENT_INSULIN_DRUG_NAME_CLASSIFIERS
)

# ticket 55: R's fix_fbg manufactures a reading from text and cannot read a
# reading that carries its unit. Scoped to the two mg/dL columns fix_fbg runs
# over -- the mmol pair is ticket 44's, and its R-null shape is a different
# mechanism.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_FBG_TEXT_CLASSIFIERS
    for col in ("fbg_updated_mg", "fbg_baseline_mg")
}

# ticket 44: the mmol columns are derived from their mg siblings, so an mg
# cell's divergence restates itself next door. Appended last of all the glucose
# causes, because it names a cascade rather than a mechanism -- anything that
# can explain the mmol cell in its own right must claim it first.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_GLUCOSE_CASCADE_CLASSIFIERS
    for col in ("fbg_updated_mmol", "fbg_baseline_mmol")
}

# ticket 56: R's own date entry point again -- the destructive month-name
# truncation in parse_dates and the order list it falls through afterwards. Like
# every other parse_dates cause the domain is the whole date family, not the
# columns that happen to carry it today.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_MONTH_NAME_TRUNCATED_CLASSIFIERS
    for col in get_date_columns()
}

# ticket 56: the unreadable-month half of the same mechanism. hospitalisation_date
# is excluded by name: round 6 measured its residual as 100% clinical notes, so
# an R sentinel there means R could not read a sentence -- ticket 39's open
# question, and a different cause wearing the same shape.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_UNREADABLE_MONTH_CLASSIFIERS
    for col in get_date_columns()
    if col != "hospitalisation_date"
}

# ticket 57: the other face of the same parse_dates mechanism -- R publishing a
# date from a token no reading can be recovered from, where Python declines.
# Same domain argument and the same hospitalisation_date carve-out, and
# appended after every column-specific and every reconstructable cause, because
# its test is direction alone: it must only ever see what nothing narrower
# claimed.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_UNRECONSTRUCTABLE_DATE_CLASSIFIERS
    for col in get_date_columns()
    if col != "hospitalisation_date"
}

# ticket 57: a fasting-glucose reading typed into the HbA1c column, which R has
# no range check to catch. Scoped to the two columns validation_rules.yaml
# declares an HbA1c range for -- the classifier reads that same config, so the
# two cannot drift.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_HBA1C_RANGE_CLASSIFIERS
    for col in ("hba1c_baseline", "hba1c_updated")
}

# ticket 57: the third face of the stray-date cause (ticket 24's raw shape,
# ticket 36's zeroed shape). Where the column's cleaned type is an integer,
# Python's failed cast leaves null rather than 0, which neither existing test
# can see.
CLASSIFIERS_BY_COLUMN["testing_frequency"] = (
    CLASSIFIERS_BY_COLUMN.get("testing_frequency", {}) | STRAY_DATE_DROPPED_CLASSIFIERS
)

# ticket 51: the two sanitizers disagree on accented letters, so the cause
# belongs to every allowed-value column rather than to province alone -- it is
# only province today because province is the one whose canonical values carry
# accents. Appended last so a column-specific cause still wins the first match.
CLASSIFIERS_BY_COLUMN |= {
    col: CLASSIFIERS_BY_COLUMN.get(col, {}) | PATIENT_UNICODE_SANITIZER_CLASSIFIERS
    for col in PATIENT_CATEGORICAL_COLS
}


# ticket 61: the cleaned stage's Buddhist-era conversion, which runs over
# get_date_columns() itself -- so, like ticket 51's future-date guard, the
# cause has exactly that domain by construction. Prepended rather than
# appended: its test is the tightest of any date cause (an exact 543-year
# shift, same month and day), and several broader causes -- R sentinelling,
# a note read differently -- match a converted cell too.
CLASSIFIERS_BY_COLUMN |= {
    col: BUDDHIST_ERA_CONVERSION_CLASSIFIERS | CLASSIFIERS_BY_COLUMN.get(col, {})
    for col in get_date_columns()
}


class RowAlignment(Enum):
    """How an arm's R and Python rows are paired for cell-by-cell comparison."""

    # Product (ticket 17): no usable natural key -- product_entry_date is null
    # on many rows -- so a row is identified purely by its position within its
    # sheet. Nothing checks that the two paired rows describe the same thing.
    POSITIONAL = auto()
    # Patient (ticket 45): patient_id is the real key and sheet_name is the
    # data's monthly granularity, so rows pair only when both agree. The
    # ordinal breaks ties in the handful of sheets that list a patient twice,
    # and the tie is broken by content rather than position, because within
    # one patient-and-sheet group the row order carries no meaning.
    IDENTITY = auto()


@dataclass(frozen=True)
class Stage:
    """One comparable output directory and how its rows are aligned.

    Every field is named rather than positional (ticket 45): how an arm aligns
    its rows decides whether the comparison still checks identity at all, and
    that is too load-bearing to read off tuple position.
    """

    label: str
    subdir: str
    id_col: str
    categorical_cols: list[str]
    alignment: RowAlignment
    # The columns add_row_ordinal groups by before appending a within-group
    # ordinal: a whole sheet for POSITIONAL, the identity key itself for
    # IDENTITY.
    ordinal_group_cols: list[str]
    date_normalize_cols: list[str] | None = None
    numeric_normalize_cols: list[str] | Sentinel | None = None
    whitespace_normalize_cols: list[str] | Sentinel | None = None
    # Raw-stage-only (ticket 49): readxl writes an Excel boolean as FALSE,
    # openpyxl as False. Cleaning already canonicalizes both, so the cleaned
    # stage never sees it.
    normalize_boolean_literals: bool = False
    # Cleaned-stage-only (ticket 44): resolve_glucose_units runs during
    # cleaning, so a swapped column is a fact about cleaned output. The raw
    # stage holds the workbook's own headers, where nothing has moved yet.
    load_glucose_unit_swaps: bool = False
    # The column holding the tracker's own calendar year, if this stage has one
    # (ticket 32). It lets a classifier judge whether Python's own value is
    # plausible for the tracker, not just how the two sides differ.
    tracker_year_col: str | None = None

    @property
    def detect_row_order_divergence(self) -> bool:
        """compare_cells' order_group_cols diagnostic (ticket 21): does a
        mismatched value appear elsewhere in its group -- i.e. are R and Python
        ordering the same rows differently rather than holding different data?
        Only meaningful for a positional key over a whole sheet; under IDENTITY
        a group is one patient on one sheet, where the same test would label
        noise as understood."""
        return self.alignment is RowAlignment.POSITIONAL


# Raw and cleaned are compared separately so a divergence can be localized to
# extraction vs. cleaning; categorical columns listed here that don't exist yet
# at the raw stage are silently skipped by compare_categorical_overlap.
# date_normalize_cols is raw-stage-only (ticket 20): R's raw extraction
# stores unparsed source date text (an Excel serial for date-formatted
# cells) while Python's raw extraction already ISO-formats parsed dates --
# a representation difference, not a real divergence, that the cleaned
# stage never has since both sides are already parsed dates there.
# numeric_normalize_cols is raw-stage-only (ticket 22): R's own
# float-to-string conversion rounds a raw numeric column's trailing digits
# differently, a representation difference cleaning's own type-casting (step
# 2.16) already resolves. whitespace_normalize_cols mostly is too (readxl's
# trim_ws=TRUE trims R-side what Python's raw extraction preserves), but an
# embedded \r\n-vs-\n line break isn't touched by cleaning's end-trim-only
# str.strip_chars and survives into `product` at the cleaned stage (ticket 21).
STAGES = [
    Stage(
        label="Patient (raw)",
        subdir="patient_data_raw",
        id_col=PATIENT_ID_COL,
        categorical_cols=PATIENT_CATEGORICAL_COLS,
        alignment=RowAlignment.IDENTITY,
        ordinal_group_cols=PATIENT_KEY_COLS,
        date_normalize_cols=PATIENT_RAW_DATE_NORMALIZE_COLS,
        numeric_normalize_cols=PATIENT_RAW_NUMERIC_NORMALIZE_COLS,
        whitespace_normalize_cols=PATIENT_RAW_WHITESPACE_NORMALIZE_COLS,
        normalize_boolean_literals=True,
    ),
    Stage(
        label="Patient (cleaned)",
        subdir="patient_data_cleaned",
        id_col=PATIENT_ID_COL,
        categorical_cols=PATIENT_CATEGORICAL_COLS,
        alignment=RowAlignment.IDENTITY,
        ordinal_group_cols=PATIENT_KEY_COLS,
        whitespace_normalize_cols=PATIENT_WHITESPACE_NORMALIZE_COLS,
        numeric_normalize_cols=PATIENT_CLEANED_NUMERIC_NORMALIZE_COLS,
        load_glucose_unit_swaps=True,
    ),
    Stage(
        label="Product (raw)",
        subdir="product_data_raw",
        id_col=PRODUCT_ID_COL,
        categorical_cols=PRODUCT_CATEGORICAL_COLS,
        alignment=RowAlignment.POSITIONAL,
        ordinal_group_cols=PRODUCT_ORDINAL_GROUP_COLS,
        date_normalize_cols=["product_entry_date"],
        tracker_year_col=PRODUCT_TRACKER_YEAR_COL,
        numeric_normalize_cols=PRODUCT_RAW_NUMERIC_NORMALIZE_COLS,
        whitespace_normalize_cols=PRODUCT_RAW_WHITESPACE_NORMALIZE_COLS,
    ),
    Stage(
        label="Product (cleaned)",
        subdir="product_data_cleaned",
        id_col=PRODUCT_ID_COL,
        categorical_cols=PRODUCT_CATEGORICAL_COLS,
        alignment=RowAlignment.POSITIONAL,
        ordinal_group_cols=PRODUCT_ORDINAL_GROUP_COLS,
        tracker_year_col=PRODUCT_TRACKER_YEAR_COL,
        whitespace_normalize_cols=PRODUCT_CLEANED_WHITESPACE_NORMALIZE_COLS,
    ),
]


def _load_parquet_dir(directory: Path) -> dict[str, pl.DataFrame]:
    return {path.name: pl.read_parquet(path) for path in sorted(directory.glob("*.parquet"))}


def _numeric_cols(frames: dict[str, pl.DataFrame]) -> list[str]:
    if not frames:
        return []
    sample = next(iter(frames.values()))
    return [name for name, dtype in sample.schema.items() if dtype.is_numeric()]


ERRORS_TABLE = Path("tables") / "table_errors.parquet"


def _unit_swaps_by_frame(py_root: Path, py_frames: dict[str, pl.DataFrame]) -> dict[str, set[str]]:
    """Re-key the run's glucose-unit swaps from tracker name to parquet name.

    The error table names a tracker; the comparison names a parquet file. The
    bridge is each frame's own ``file_name`` column rather than string surgery
    on the parquet's name, so a change to the output naming convention cannot
    silently drop the context.
    """
    errors_path = py_root / ERRORS_TABLE
    if not errors_path.exists():
        console.print(
            f"[yellow]No {ERRORS_TABLE} under {py_root} -- glucose unit-swap context "
            "unavailable, so swapped columns will not be classified.[/yellow]"
        )
        return {}
    swaps = load_glucose_unit_swaps(pl.read_parquet(errors_path))
    by_frame = {}
    for name, df in py_frames.items():
        if "file_name" not in df.columns or not len(df):
            continue
        columns = swaps.get(df["file_name"][0])
        if columns:
            by_frame[name] = columns
    return by_frame


def _compare_arm(py_root: Path, r_dir: Path, py_dir: Path, stage: Stage) -> DirectoryComparison:
    r_frames = _load_parquet_dir(r_dir)
    py_frames = _load_parquet_dir(py_dir)
    unit_swapped_columns = (
        _unit_swaps_by_frame(py_root, py_frames) if stage.load_glucose_unit_swaps else {}
    )
    for column in stage.date_normalize_cols or []:
        for frames in (r_frames, py_frames):
            for name, df in frames.items():
                frames[name] = normalize_date_column(df, column)
    # Whitespace before numeric (ticket 24): normalize_numeric_column widens a
    # column to `pl.Object` (mixed float/str) the moment any value parses,
    # which breaks normalize_whitespace_column's `.str.*` expressions on the
    # non-numeric residual if applied after -- stripping first keeps the
    # column `pl.String` for numeric normalization to then act on.
    for frames in (r_frames, py_frames):
        for name, df in frames.items():
            if stage.whitespace_normalize_cols is ALL_RAW_COLUMNS:
                # Resolved per frame, not once: raw parquets differ in which
                # columns they carry, and a 2026 tracker holds columns a 2017
                # one never had.
                columns = whitespace_normalize_targets(df, exclude=[])
            else:
                columns = stage.whitespace_normalize_cols or []
            for column in columns:
                frames[name] = normalize_whitespace_column(frames[name], column)
            # Boolean literals share whitespace's scope and must run before
            # numeric normalization for the same reason: once a column widens
            # to pl.Object the `.str.*` expressions no longer apply.
            if stage.normalize_boolean_literals:
                for column in columns:
                    frames[name] = normalize_boolean_literal_column(frames[name], column)
    for frames in (r_frames, py_frames):
        for name, df in frames.items():
            if stage.numeric_normalize_cols is ALL_STRING_COLUMNS:
                columns = string_numeric_normalize_targets(df, exclude=stage.ordinal_group_cols)
            elif stage.numeric_normalize_cols is ALL_RAW_COLUMNS:
                # The ordinal's group columns are excluded because
                # normalize_numeric_column widens a column to pl.Object the
                # moment any value parses, which would stop add_row_ordinal
                # whitespace-normalizing it as a string.
                columns = numeric_normalize_targets(df, exclude=stage.ordinal_group_cols)
            else:
                columns = stage.numeric_normalize_cols or []
            for column in columns:
                frames[name] = normalize_numeric_column(frames[name], column)
    key_cols = None
    if stage.alignment is RowAlignment.IDENTITY:
        # Both sides at once: the tie-break between two rows sharing an
        # identity key is decided by which pairing agrees best, which cannot be
        # computed from one frame alone.
        for name in r_frames.keys() & py_frames.keys():
            r_frames[name], py_frames[name], key_cols = align_duplicate_rows(
                r_frames[name], py_frames[name], stage.ordinal_group_cols
            )
    for frames in (r_frames, py_frames):
        for name, df in frames.items():
            if ROW_ORDINAL_COL in df.columns:
                continue
            frames[name], key_cols = add_row_ordinal(df, stage.ordinal_group_cols)
    assert key_cols is not None
    # Everything add_row_ordinal returned except the trailing ordinal itself --
    # the group a within-group sort-order divergence (ticket 21) is scoped to.
    order_group_cols = key_cols[:-1] if stage.detect_row_order_divergence else None
    # __-prefixed helper columns from add_row_ordinal are join-key-only synthetic
    # data (an ordinal counter, normalized group values) -- summing/diffing them
    # as if they were real output columns would be noise, not signal.
    numeric_cols = [c for c in _numeric_cols(r_frames) if not c.startswith("__")]
    # compare_directory/compare_categorical_overlap skip a column not present on
    # both sides of a given file -- raw output isn't schema-normalized like cleaned
    # output, so which columns exist can vary file by file, not just by directory.
    return compare_directory(
        r_frames,
        py_frames,
        key_cols=key_cols,
        numeric_cols=numeric_cols,
        id_col=stage.id_col,
        categorical_cols=stage.categorical_cols,
        order_group_cols=order_group_cols,
        unit_swapped_columns=unit_swapped_columns,
        tracker_year_col=stage.tracker_year_col,
    )


LEGEND = """\
[bold]Shape match[/bold]        -- do R and Python have the same row count for this file? A \
coarse structural check: matching shape says nothing about whether individual cell values agree.

[bold]ID divergence[/bold]      -- identities (patient_id for patient, product name for \
product) present on only one side, regardless of row count. Independent of the row-alignment \
key used for row-key/cell divergence below -- catches a patient or product dropped entirely, \
even when that key is unreliable.

[bold]Column divergence[/bold]  -- columns present on only one side, plus columns present on \
both sides but with a different dtype. Structural, like shape -- no values are compared.

[bold]Categorical divergence[/bold] -- of the file's categorical/label columns (allowed-value \
fields for patient; product_category/product_balance_status for product), how many have a \
label value on one side that never appears on the other? Also independent of the \
row-alignment key -- a distinct-value-set check per column, not tied to row identity.

[bold]Totals divergence[/bold]  -- of the file's numeric columns, how many have a column-sum \
that differs beyond a float tolerance? The first check that actually compares values, at the \
coarsest (whole-column) granularity.

[bold]Row-key divergence[/bold] -- rows whose full row-alignment key (all of it, not just the \
single identity column above) found no partner on the other side at all, counted per row, not \
per distinct key. A repeated key on one side with no matching repeat on the other also counts \
here -- that's the fan-out failure mode. This is what tells you whether Cell divergence below \
is measuring real disagreement or just has nothing to compare.

[bold]Cell divergence[/bold]    -- rows matched across R and Python (via the arm's \
row-alignment key), diffed value by value. The most granular value comparison -- but it's only \
meaningful once Row-key divergence above confirms the key actually paired the rows; 0 here can \
mean "everything agreed" or "nothing was paired to compare" (ticket 15/17 on the wayfinder map).\
"""


def _print_legend() -> None:
    console.print(Panel(LEGEND, title="What these columns measure", expand=False))


YEAR_PREFIX = re.compile(r"^(\d{4})_")


def _file_year(file_name: str) -> int | None:
    match = YEAR_PREFIX.match(file_name)
    return int(match.group(1)) if match else None


def _has_any_mismatch(file_comparison: FileComparison) -> bool:
    return (
        not file_comparison.shape.match
        or bool(file_comparison.columns.only_in_r)
        or bool(file_comparison.columns.only_in_py)
        or bool(file_comparison.columns.dtype_mismatches)
        or bool(file_comparison.totals)
        or bool(file_comparison.categorical_overlap)
        or bool(file_comparison.cell_mismatches)
        or file_comparison.row_key_overlap.r_unmatched > 0
        or file_comparison.row_key_overlap.py_unmatched > 0
        or (
            file_comparison.id_overlap is not None
            and bool(file_comparison.id_overlap.only_in_r or file_comparison.id_overlap.only_in_py)
        )
    )


def _print_summary(arm: str, comparison: DirectoryComparison, only_mismatches: bool) -> None:
    files = (
        [f for f in comparison.files if _has_any_mismatch(f)]
        if only_mismatches
        else comparison.files
    )
    if only_mismatches and not files:
        console.print(f"[green]{arm}: no mismatches in any file.[/green]")
        return

    by_year: dict[int | None, list] = {}
    for file_comparison in files:
        by_year.setdefault(_file_year(file_comparison.file_name), []).append(file_comparison)

    for year in sorted(by_year, key=lambda y: (y is None, -(y or 0))):
        title = f"{arm} — {year}" if year is not None else f"{arm} — unknown year"
        table = Table(title=title)
        table.add_column("File")
        table.add_column("Shape match")
        table.add_column("ID divergence (R-only / Py-only)")
        table.add_column("Column divergence", justify="right")
        table.add_column("Categorical divergence", justify="right")
        table.add_column("Totals divergence", justify="right")
        table.add_column("Row-key divergence (R-only / Py-only)")
        table.add_column("Cell divergence", justify="right")

        for file_comparison in by_year[year]:
            column_divergence = (
                len(file_comparison.columns.only_in_r)
                + len(file_comparison.columns.only_in_py)
                + len(file_comparison.columns.dtype_mismatches)
            )
            if file_comparison.id_overlap is None:
                id_divergence_str = "n/a"
            else:
                id_divergence_str = (
                    f"{len(file_comparison.id_overlap.only_in_r)} / "
                    f"{len(file_comparison.id_overlap.only_in_py)}"
                )
            row_key_str = (
                f"{file_comparison.row_key_overlap.r_unmatched} / "
                f"{file_comparison.row_key_overlap.py_unmatched}"
            )
            table.add_row(
                file_comparison.file_name,
                "✓" if file_comparison.shape.match else "✗",
                id_divergence_str,
                str(column_divergence),
                str(len(file_comparison.categorical_overlap)),
                str(len(file_comparison.totals)),
                row_key_str,
                str(len(file_comparison.cell_mismatches)),
            )
        console.print(table)

    _render_arm_totals(arm, comparison)

    if comparison.only_in_r:
        console.print(
            f"[yellow]Only in R ({len(comparison.only_in_r)}):[/yellow] "
            f"{', '.join(comparison.only_in_r)}"
        )
    if comparison.only_in_py:
        console.print(
            f"[yellow]Only in Python ({len(comparison.only_in_py)}):[/yellow] "
            f"{', '.join(comparison.only_in_py)}"
        )


def _render_arm_totals(arm: str, comparison: DirectoryComparison) -> None:
    """Whole-arm rollup, printed after the per-year tables.

    The per-year tables say *where* a divergence is; without this you can
    only get *how much* there is by scrolling and adding up every year.
    """
    summary = summarize_directory(comparison)

    table = Table(title=f"{arm} — totals across all {summary.files_compared} files compared")
    table.add_column("Measure")
    table.add_column("Files affected", justify="right")
    table.add_column("Total", justify="right")

    def add(measure: str, value: tuple[int, int]) -> None:
        files_affected, total = value
        style = "" if total == 0 else "yellow"
        table.add_row(measure, str(files_affected), str(total), style=style)

    shape_style = "" if summary.shape_mismatch_files == 0 else "yellow"
    table.add_row("Shape mismatch", str(summary.shape_mismatch_files), "—", style=shape_style)
    add("ID divergence", summary.id_divergence)
    add("Column divergence", summary.column_divergence)
    add("Categorical divergence", summary.categorical_divergence)
    add("Totals divergence", summary.totals_divergence)
    add("Row-key divergence", summary.row_key_divergence)
    add("Cell divergence", summary.cell_divergence)

    console.print(table)

    if summary.only_in_r or summary.only_in_py:
        console.print(
            f"[yellow]Files on only one side:[/yellow] "
            f"{summary.only_in_r} R-only, {summary.only_in_py} Python-only "
            f"(not included in the counts above — nothing to compare them against)"
        )


def _write_excel_report(path: Path, rows_by_sheet: dict[str, list[dict]]) -> None:
    workbook = Workbook()
    workbook.remove(workbook.active)
    for sheet_name, rows in rows_by_sheet.items():
        worksheet = workbook.create_sheet(sheet_name[:31])
        if not rows:
            worksheet.append(["(no mismatches)"])
            continue
        headers = list(rows[0].keys())
        worksheet.append(headers)
        for row in rows:
            worksheet.append([row[h] for h in headers])
    workbook.save(path)


def _previous_run_dirs(output_dir: Path, current_run_dir: Path) -> list[Path]:
    # Run directories are named by ISO-8601 timestamp, so lexicographic sort is
    # chronological -- most recent first, excluding the run just created.
    if not output_dir.exists():
        return []
    run_dirs = [p for p in output_dir.iterdir() if p.is_dir() and p != current_run_dir]
    return sorted(run_dirs, reverse=True)


def _load_latest_snapshot(
    output_dir: Path, current_run_dir: Path, subdir: str
) -> dict[str, dict[str, int]] | None:
    # A stage can be missing from an older run (e.g. it errored, or the stage
    # set changed) -- walk back further rather than only checking the single
    # most recent run directory.
    for run_dir in _previous_run_dirs(output_dir, current_run_dir):
        snapshot_path = run_dir / f"snapshot_{subdir}.json"
        if snapshot_path.exists():
            return json.loads(snapshot_path.read_text())
    return None


def _write_snapshot(run_dir: Path, subdir: str, snapshot: dict[str, dict[str, int]]) -> Path:
    path = run_dir / f"snapshot_{subdir}.json"
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True))
    return path


def _print_deltas(label: str, column_deltas: list[Delta], cause_deltas: list[Delta]) -> None:
    if not column_deltas and not cause_deltas:
        console.print(f"[dim]{label}: no change from the previous run.[/dim]")
        return

    table = Table(title=f"{label} — change since previous run")
    table.add_column("Column")
    table.add_column("Previous", justify="right")
    table.add_column("Current", justify="right")
    table.add_column("Diff", justify="right")
    for delta in column_deltas:
        diff = delta.current - delta.previous
        style = "red" if diff > 0 else "green"
        table.add_row(
            delta.key, str(delta.previous), str(delta.current), f"[{style}]{diff:+d}[/{style}]"
        )
    console.print(table)


def _delta_rows(deltas: list[Delta]) -> list[dict]:
    return [
        {
            "key": delta.key,
            "previous": delta.previous,
            "current": delta.current,
            "diff": delta.current - delta.previous,
        }
        for delta in deltas
    ]


@app.command()
def compare(
    r_dir: Annotated[Path, typer.Option("--r-dir", help="Root of the frozen R output directory")],
    py_dir: Annotated[Path, typer.Option("--py-dir", help="Root of the Python output directory")],
    output_dir: Annotated[
        Path,
        typer.Option(
            "--output-dir", help="Directory each run's own timestamped subfolder is created under"
        ),
    ] = Path("output/comparison"),
    only_mismatches: Annotated[
        bool,
        typer.Option(
            "--only-mismatches", help="Only print files with at least one measure flagged"
        ),
    ] = False,
) -> None:
    _print_legend()
    # Every stage of this run shares one timestamped subfolder, so a run is a
    # single self-contained unit on disk -- its reports and snapshots (for the
    # *next* run's delta) live together, and nothing gets overwritten by a
    # later run.
    run_dir = output_dir / datetime.now(UTC).strftime("%Y-%m-%dT%H%M%SZ")
    run_dir.mkdir(parents=True, exist_ok=True)

    for stage in STAGES:
        label, subdir = stage.label, stage.subdir
        comparison = _compare_arm(py_dir, r_dir / subdir, py_dir / subdir, stage)
        _print_summary(label, comparison, only_mismatches)

        # One workbook per stage -- combining raw and cleaned into one per-column
        # aggregate would sum e.g. product_entry_date mismatches from both stages
        # into a single count, defeating the point of separating them.
        stage_report_out = run_dir / f"compare_report_{subdir}.xlsx"
        summary_sheets = build_summary_rows(comparison, classifiers_by_column=CLASSIFIERS_BY_COLUMN)
        detail_sheets = build_mismatch_rows(comparison, classifiers_by_column=CLASSIFIERS_BY_COLUMN)

        # Run-over-run history (ticket 19): compare this run's per-column/per-cause
        # counts against the most recent prior run's snapshot for this stage, so a
        # triage fix's actual effect (or a regression) is visible directly rather
        # than only ever seeing the current numbers.
        current_snapshot = snapshot_from_summary(summary_sheets)
        previous_snapshot = _load_latest_snapshot(output_dir, run_dir, subdir)
        column_deltas = (
            compute_deltas(previous_snapshot["per_column"], current_snapshot["per_column"])
            if previous_snapshot
            else []
        )
        cause_deltas = (
            compute_deltas(previous_snapshot["per_cause"], current_snapshot["per_cause"])
            if previous_snapshot
            else []
        )
        if previous_snapshot is None:
            console.print(f"[dim]{label}: no previous run to compare against.[/dim]")
        else:
            _print_deltas(label, column_deltas, cause_deltas)
        history_sheets = {
            "history_column_deltas": _delta_rows(column_deltas),
            "history_cause_deltas": _delta_rows(cause_deltas),
        }
        _write_snapshot(run_dir, subdir, current_snapshot)

        _write_excel_report(stage_report_out, {**summary_sheets, **detail_sheets, **history_sheets})

        console.print(f"[bold green]{label} report written to {stage_report_out}[/bold green]")


if __name__ == "__main__":
    app()
