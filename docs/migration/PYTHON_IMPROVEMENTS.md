# Python Pipeline Improvements Over R

This document tracks cases where the Python pipeline implementation is **more correct** than the R pipeline, resulting in intentional differences between R and Python outputs.

## 1. insulin_type Derivation Bug Fix

**Status**: ✅ Fixed in Python

**Issue in R**: R's insulin_type derivation logic only checks the human insulin columns to decide between "human insulin" and "analog insulin". When all human insulin columns are None/NA, the condition evaluates to NA, and `ifelse()` returns NA - **even if the analog insulin columns have "Y" values**.

**R Code (Buggy)**:
```r
insulin_type = ifelse(
    human_insulin_pre_mixed == "Y" |
        human_insulin_short_acting == "Y" |
        human_insulin_intermediate_acting == "Y",
    "human insulin",
    "analog insulin"
)
```

**Problem**: For patients with ONLY analog insulin (human columns = None, analog columns = 'Y'):
- `None == "Y"` evaluates to NA in R
- `NA | NA | NA` → NA
- `ifelse(NA, "human insulin", "analog insulin")` → NA

**Python Fix**: Check if ANY insulin column has data first, then derive the type:
```python
pl.when(
    # Only derive if at least one insulin column is not null
    pl.col("human_insulin_pre_mixed").is_not_null()
    | pl.col("human_insulin_short_acting").is_not_null()
    | pl.col("human_insulin_intermediate_acting").is_not_null()
    | pl.col("analog_insulin_rapid_acting").is_not_null()
    | pl.col("analog_insulin_long_acting").is_not_null()
)
.then(
    pl.when(
        (pl.col("human_insulin_pre_mixed") == "Y")
        | (pl.col("human_insulin_short_acting") == "Y")
        | (pl.col("human_insulin_intermediate_acting") == "Y")
    )
    .then(pl.lit("human insulin"))
    .otherwise(pl.lit("analog insulin"))
)
.otherwise(None)
```

**Impact**: For 2024 Sibu Hospital tracker, 5 patients correctly get `insulin_type = 'Analog Insulin'` in Python vs `None` in R.

**File**: `src/a4d/clean/patient.py:_derive_insulin_fields()`

## 2. insulin_subtype Typo Fix

**Status**: ✅ Fixed in Python

**Issue in R**: R has a typo - uses "rapic-acting" instead of "rapid-acting" when deriving insulin_subtype.

**R Code (Typo)**:
```r
paste(ifelse(analog_insulin_rapid_acting == "Y", "rapic-acting", ""), sep = ",")
```

**Python Fix**: Uses correct spelling "rapid-acting"

**Impact**: Derived insulin_subtype values use correct medical terminology. However, since comma-separated values get replaced with "Undefined" by validation, the final output for insulin_subtype is still "Undefined" in both R and Python.

**File**: `src/a4d/clean/patient.py:_derive_insulin_fields()`

## 3. insulin_total_units Extraction Bug Fix

**Status**: ✅ Fixed in Python

**Issue in R**: R's header merge logic has a condition that fails for 2024+ trackers, causing it to skip the two-row header merge and lose columns.

**R Code (Buggy)** - `script1_helper_read_patient_data.R:92`:
```r
if (header_cols[2] == header_cols_2[2]) {
    # Only merge if column 2 matches in both rows
    diff_colnames <- which((header_cols != header_cols_2))
    header_cols[diff_colnames] <- paste(header_cols_2[diff_colnames], header_cols[diff_colnames])
}
```

**Problem for 2024 Sibu Hospital tracker**:
- Row 75 (header_cols_2), Col 2: `"Patient \nID*"`
- Row 76 (header_cols), Col 2: `None` (part of merged cell above)
- Condition `header_cols[2] == header_cols_2[2]` evaluates to `FALSE`
- **Headers NOT merged**, only row 76 used

**Result**:
- Col 27 in R: Only gets "per day" (row 76 alone)
- "per day" doesn't match synonym "TOTAL Insulin Units per day"
- **Column lost during synonym mapping**

**Python Fix**: Python always merges both header rows without conditions:
```python
for h1, h2 in zip(header_1, header_2, strict=True):
    if h1 and h2:
        headers.append(f"{h2} {h1}".strip())
```

**Result**:
- Col 27 in Python: "TOTAL Insulin Units per day" (row 75 + row 76)
- Matches synonym perfectly ✅

**Impact**: For 2024 Sibu Hospital tracker, Python correctly extracts insulin_total_units for 50/53 patients. R loses this column entirely due to header merge failure.

**File**: `src/a4d/extract/patient.py:merge_headers()`

## 4. BMI Float Precision

**Status**: ℹ️ Negligible difference

**Observation**: Minor floating point precision differences at the ~10^-15 level.

**Example**:
- R: `19.735976492259113`
- Python: `19.73597649225911`

**Cause**: Different floating point arithmetic between R and Python/Polars.

**Impact**: Negligible - differences are below any meaningful precision threshold for BMI measurements.

## 5. Product Pipeline: Date Parsing Robustness

**Status**: ✅ Improved in Python

Three distinct date-parsing patterns surfaced during product-pipeline diff investigation against R goldens. In each case Python yields a more correct result than R; no R-parity fix is warranted. Investigation: the underlying notebook (`Ali_internship/residual_dig.ipynb`) was never committed to the repo and no longer exists; the surviving record of this analysis is [`Product pipeline parity presentation.pdf`](Product%20pipeline%20parity%20presentation.pdf), kept until the automated comparison script (see [ticket 2](../wayfinder/tickets/02-documentation-strategy.md)) reproduces and supersedes its numbers.

### 5.1 "Sept" → "Sep" month abbreviation

**Issue in R**: `lubridate` does not recognize the 4-letter abbreviation "Sept" as September. Source strings like `"05-Sept-2025"` or `"25-Sept-2025"` are rejected → `null`.

**Python Fix**: `parse_date_flexible` strips the trailing letter from any 4-letter month abbreviation before matching:

```python
re.sub(r"([a-zA-Z]{3})[a-zA-Z]", r"\1", date_str)
```

This converts `"Sept"` → `"Sep"`, after which the standard `%d-%b-%Y` parse succeeds.

**Impact**: 46 rows across 28 product `(file, sheet, product)` groups where R has `null` and Python has a valid date — the `py_set_r_null` class in the joined-view diff. Affected trackers include `2024_Putrajaya Hospital A4D Tracker` (Sep24) and `2025_NPH A4D Tracker` (Sep25).

**File**: [src/a4d/clean/date_parser.py:67-69](../../src/a4d/clean/date_parser.py#L67-L69)

### 5.2 D/M/YYYY single-digit-month dates

**Issue in R**: `lubridate::dmy()` with default formats does not parse `"20/5/2025"` (single-digit month, slash separator) — rejects → `null`.

**Python Fix**: `parse_date_flexible` includes a slash-format match path that accepts both `D/M/YYYY` and `DD/MM/YYYY`.

**Impact**: 5 rows in `2025_Putrajaya Hospital A4D Tracker` / May25 / WIZ Test Strips with cell values like `"20/5/2025"`, `"22/5/2025"`, `"28/5/2025"`. R rejects all; Python parses them correctly.

**File**: [src/a4d/clean/date_parser.py](../../src/a4d/clean/date_parser.py)

### 5.3 Future-year sentinel guard for malformed date strings

**Issue in R**: `lubridate` is permissive — strings with structural typos like `"10-Oct-2-24"` (extra `-2-` injected) get force-parsed into plausible-but-incorrect dates (e.g. `2024-02-10`). The wrong date sorts at a different position in the cumulative-balance sequence, so intermediate `product_balance` values diverge from what the source spreadsheet shows. R has no future-year guard.

**Python Fix**: `parse_date_flexible` returns successfully or returns the sentinel `9999-09-09` for unparseable input. `_validate_entry_dates` then re-sentinels any successfully-parsed date whose year is between the tracker year and the Buddhist-era threshold (2400) — this catches fat-fingered Gregorian years (e.g. `"2099-..."` typed in a 2024 tracker) while exempting genuine Buddhist-era dates (BE 25xx → CE 20xx). Sentinelled rows sort to the end of the cumulative-balance sequence so they don't corrupt intermediate values.

```python
BUDDHIST_ERA_THRESHOLD = 2400
invalid_mask = (
    pl.col("product_entry_date").is_not_null()
    & (pl.col("product_entry_date") > max_valid)
    & (pl.col("product_entry_date").dt.year() < BUDDHIST_ERA_THRESHOLD)
)
```

**Impact**: 31 rows across 6 product groups (the post-Buddhist-fix `real_divergence` class in `product_balance`) — R force-parses or silently rejects malformed strings while Python correctly sentinels them. Confirmed by raw-Excel inspection of:

- `"10-Oct-2-24"` (×2) — Putrajaya 2024 / Oct24 / WIZ Alcohol Swabs. R parses as `2024-02-10`; Python sentinels.
- `"15-Seep-225"`, `"08-Sep02025"` — NPH 2025 / Sep25. Both R and Python sentinel/null these; balance still diverges via the date-sort interaction with the legitimate Sept rows from §5.1.
- `"01-Ju-2025"` — Sarawak 2025 / Jul25. Both pipelines reject ("Ju" is too short to disambiguate Jun/Jul); balance diverges because R returns `null` (sorts in nulls-first/last position differing from sentinel) while Python returns `9999-09-09` (sorts to end deterministically).

**File**: [src/a4d/clean/product.py:_validate_entry_dates](../../src/a4d/clean/product.py)

## 6. Product Pipeline: Running Balance FP Precision

**Status**: ℹ️ Negligible difference

**Observation**: Python's vectorized `cum_sum().over([sheet, product])` and R's iterative `for (i in 1:nrow)` loop produce running balances that drift by ~5.7 × 10⁻¹⁴ at the deepest accumulation step.

**Cause**: IEEE-754 floating-point accumulation order differs between Polars' vectorized cumsum and R's row-by-row addition.

**Impact**: 411 rows across 80 product groups in the joined-view diff are flagged as different but classify as `fp_precision_only`. Both pipelines produce identical final-row balances per group; only sub-display-precision intermediates differ.

**File**: [src/a4d/clean/product.py:_compute_running_balance](../../src/a4d/clean/product.py)

## Summary

| Issue | R Behavior | Python Behavior | Classification |
|-------|-----------|-----------------|----------------|
| insulin_type derivation | Bug - returns None for analog-only patients (doesn't check analog columns) | Correct derivation (checks all insulin columns) | **Python Fix** |
| insulin_subtype typo | "rapic-acting" (typo) | "rapid-acting" (correct spelling) | **Python Fix** |
| insulin_total_units extraction | Not extracted (header merge fails for 2024+ trackers) | Correctly extracted (unconditional header merge) | **Python Fix** |
| BMI precision | 16 decimal places | 14-15 decimal places | **Negligible** |
| product entry date "Sept" | Rejects 4-letter month abbreviation → null | Truncates to "Sep", parses correctly | **Python Fix** |
| product entry date `D/M/YYYY` | Rejects single-digit-month slash format → null | Parses correctly | **Python Fix** |
| product entry date — malformed strings | Force-parses to plausible-but-incorrect dates (e.g. `"10-Oct-2-24"` → 2024-02-10), distorting cumulative balance | Sentinels to `9999-09-09`, sorts to end, preserves correct intermediate balances | **Python Fix** |
| product running balance | Iterative cumsum, slightly different IEEE-754 accumulation order | Vectorized cumsum, identical final-row balances | **Negligible** |

## Migration Validation Status

✅ **Schema**: 100% match (83 patient columns + 20 product columns)
✅ **Extraction**: Improved (unconditional header merge fixes insulin_total_units)
✅ **Cleaning**: Improved (insulin_type, insulin_subtype, product date parsing)
ℹ️ **Precision**: Acceptable float differences (~10⁻¹⁵ BMI, ~10⁻¹⁴ product running balance)

**All value differences are Python improvements over R bugs or negligible precision drift.**

The Python pipeline is production-ready with significant improvements over the R pipeline:

1. **More robust header parsing** - No conditional merge that fails on 2024+ trackers
2. **Better null handling** - Correctly checks all insulin columns before derivation
3. **Correct terminology** - Uses proper medical terms ("rapid-acting" not "rapic-acting")
4. **More robust date parsing** - Accepts "Sept" and `D/M/YYYY`; sentinels malformed strings instead of force-parsing them into plausible-but-wrong dates that distort cumulative balances
