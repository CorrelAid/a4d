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

2. **2018_CDA A4D Tracker** 🔄 PARTIAL
   - Date: 2025-11-04
   - Status: In Progress
   - Known Issues:
     - hba1c_updated (71.0% mismatches) - investigated, found need for HbA1c symbol handling
     - fbg_updated_mg/mmol (55.1% mismatches) - FIXED with FBG text conversion
   - Notes: Older tracker format, used for testing edge cases

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
   uv run python scripts/compare_r_vs_python.py \
     -r "/Volumes/.../output_r/patient_data_cleaned/FILE.parquet" \
     -p "/Volumes/.../output_python/patient_data_cleaned/FILE.parquet"
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

These differences are expected and acceptable:

1. **insulin_total_units**: Python extracts from Excel, R doesn't (Python is correct)
2. **status**: Formatting difference with hyphen ("Active Remote" vs "Active - Remote")

## Next Files to Validate

Priority order:

1. **2018_CDA A4D Tracker** - Finish validation, oldest format
2. **2019 trackers** - Old format validation
3. **2020-2023 trackers** - Mid-period formats
4. **2024-2025 trackers** - Recent formats with new columns

## Summary Statistics

- **Total:** 174 files
- **Validated:** 1 (0.6%)
- **In Progress:** 1 (0.6%)
- **Pending:** 172 (98.9%)

Last Updated: 2025-11-04
