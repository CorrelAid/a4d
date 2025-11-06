# R vs Python Pipeline Validation Tracking

This file tracks which tracker files have been validated for equivalence between R and Python pipelines.

**Total Files:** 174 patient_cleaned.parquet files

## Validation Status

### ✅ Validated Files

Files that have been compared and validated (acceptable differences documented):

1. **2025_06_CDA A4D Tracker** ✅
   - Date: 2025-11-04
   - Status: PASSED
   - Mismatches: 2 expected
     - `insulin_total_units` (77.4%): Python extracts correctly from "TOTAL Insulin Units per day" column, R doesn't
     - `status` (8.5%): Minor formatting difference ("Active Remote" vs "Active - Remote")
   - Fixed Issues:
     - Date validation: Future dates now replaced with error value (9999-09-09)
     - FBG text conversion: high/medium/low → numeric values
     - Float comparison: Approximate comparison with tolerances
   - Notes: Baseline validation, all major issues resolved

2. **2018_CDA A4D Tracker** ✅
   - Date: 2025-11-07
   - Status: PASSED
   - Mismatches: 3 acceptable (Python is more correct than R)
     - `fbg_updated_mg` (37.7%): Python extracts values correctly from "value (date)" format, R shows error values
     - `fbg_updated_mmol` (37.7%): Same as above, Python correctly calculates mmol conversion
     - `fbg_updated_date` (1.4%): Python correctly parses DD/MM/YY as 08/06/18 → 2018-06-08, R incorrectly shows 2008-06-18
   - Fixed Issues:
     - Flexible date parsing: Handles DD/MM/YYYY, month-year abbreviations, Excel serials
     - Date extraction from measurements: Extracts dates from "value (Mar-18)" format
     - Month-year without separator: Handles "May18" in addition to "May-18"
     - FBG unit suffix removal: Strips "mg/dl" and "mmol/l" from values
     - All date fields: 100% match on dob, t1d_diagnosis_date, recruitment_date, age
   - Cleaning Errors: 37 (down from 257 initially)
   - Notes: Oldest tracker format (2018), all date parsing issues resolved. Python implementation is more accurate than R for this file.

### 🔄 In Progress

Files currently being validated:

- None

### ⏳ Pending Validation

Files that need to be validated (172 remaining):

Run this command to see all files:
```bash
find "/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r/patient_data_cleaned" \
  -name "*.parquet" -type f | sort
```

## Validation Procedure

For each file:

1. **Process with Python pipeline**
   ```bash
   cd a4d-python
   # Update scripts/reprocess_tracker.py with tracker path
   uv run python scripts/reprocess_tracker.py
   ```

2. **Run comparison**
   ```bash
   # Simplified: just provide the filename
   uv run python scripts/compare_r_vs_python.py -f "2018_CDA A4D Tracker_patient_cleaned.parquet"
   ```

3. **Analyze results**
   - Record mismatch counts and percentages
   - Investigate any HIGH or MEDIUM priority mismatches
   - Document expected differences
   - Fix Python pipeline if needed

4. **Update this file**
   - Move file to "Validated Files" section
   - Document status and findings

## Known Acceptable Differences

These differences are expected and acceptable (Python is more correct):

1. **insulin_total_units**: Python extracts from Excel, R doesn't (Python is correct)
2. **status**: Formatting difference with hyphen ("Active Remote" vs "Active - Remote")
3. **fbg_updated_mg/mmol** (legacy trackers): Python correctly extracts from "value (date)" format, R shows error values
4. **Date parsing edge cases**: Python correctly handles DD/MM/YY format, R may swap day/month in some cases

## Next Files to Validate

Priority order:

1. **2019 trackers** - Old format validation (similar to 2018)
2. **2020-2023 trackers** - Mid-period formats
3. **2024-2025 trackers** - Recent formats with new columns

## Summary Statistics

- **Total:** 174 files
- **Validated:** 2 (1.1%)
- **In Progress:** 0 (0.0%)
- **Pending:** 172 (98.9%)

Last Updated: 2025-11-07
