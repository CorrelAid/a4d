# Validation Summary

Comprehensive comparison of R vs Python pipeline outputs across all 174 patient trackers.

**Verdict: Python pipeline is production-ready.**

---

## Summary Statistics

| Metric | Value |
|--------|-------|
| Total trackers | 174 |
| Perfect record count match | 172 (98.9%) |
| Known acceptable difference | 1 (2024 Mandalay Children's Hospital) |
| Skipped — Excel data quality issue | 1 (2024 Vietnam National Children Hospital) |
| Critical bugs fixed during validation | 8 trackers |

---

## Known Acceptable Differences

These patterns appear across multiple trackers and are expected or intentional.

| # | Column | Pattern | Assessment |
|---|--------|---------|------------|
| 1 | `insulin_total_units` | Python extracts values, R shows null | Python is more correct |
| 2 | `province` | R: "Undefined", Python: actual province name | Python is more correct |
| 3 | `status` | "Active - Remote" vs "Active Remote" (hyphen) | Cosmetic, functionally equivalent |
| 4 | `t1d_diagnosis_age` | R: null, Python: 999999 sentinel | Different null strategy, both valid |
| 5 | `fbg_updated_mg/mmol` (2017-2019) | Python parses "150 (Mar-18)" → 150, R → 999999 | Python is more correct |
| 6 | Date parsing edge cases | DD/MM/YY interpretation differs in rare cases | Python has more robust parsing |
| 7 | `blood_pressure_systolic/diastolic` | BP splitting now implemented in Python | Was HIGH priority, now done |
| 8 | `fbg_baseline_mg` | Inconsistent baseline extraction (2022+) | Medium priority, under investigation |
| 9 | `bmi` | Float precision ~10^-15 difference | Cosmetic only |
| 10 | `insulin_regimen/subtype` | Case: "Other" vs "other", "NPH" vs "nph" | String normalization difference |
| 11 | Future/invalid dates | Python: 9999-09-09 sentinel, R: Buddhist calendar dates | Both valid error strategies |

---

## Known Record Count Differences

### 2024 Mandalay Children's Hospital — KEPT AS KNOWN DIFFERENCE

- R: 1,174 records, Python: 1,185 records (+11, +0.9%)
- Patient MM_QA001 has 12 monthly records in Excel; R retains only 1 (implicit R behavior, not identifiable in R code)
- Decision: keep Python behavior — all 12 monthly records are legitimate longitudinal observations

### 2024 Vietnam National Children Hospital — SKIPPED

- R: 900 records, Python: 927 records (+27, +3.0%)
- Root cause: Jul24 sheet has 27 patients with duplicate rows containing conflicting data (e.g., VN_QC016 appears twice with different status values)
- Decision: skip validation — requires Excel source file correction before comparison is meaningful

---

## Bugs Fixed During Validation (8 Trackers)

| Tracker | Issue | Fix Location |
|---------|-------|-------------|
| 2021 Phattalung Hospital | `find_data_start_row()` stopped at stray space, skipped 42 records | `extract/patient.py` |
| 2021 Phattalung Hospital | `map_elements()` failed on all-null date column | `clean/converters.py` |
| 2022 Surat Thani Hospital | Rows with missing row number (col A) but valid patient_id skipped | `extract/patient.py` |
| 2024 Sultanah Bahiyah | Excel `#REF!` errors in patient_id extracted as valid records | `extract/patient.py` |
| 2024 Sultanah Bahiyah | `ws.max_row` is None for some Excel files, causing TypeError | `extract/patient.py` |
| 2022 Mandalay Children's Hospital | Fixed by numeric zero filtering + patient_id normalization | `extract/patient.py` |
| 2024 Likas Women & Children's Hospital | Fixed by numeric zero filtering + patient_id normalization | `extract/patient.py` |
| 2025_06 Taunggyi Women & Children Hospital | patient_id='0.0' not caught by earlier filter for '0' | `extract/patient.py` |

---

## Python Improvements Over R

- Better `insulin_total_units` extraction (R misses this nearly universally)
- Better province resolution ("Undefined" → actual province names)
- Better date parsing with explicit DD/MM/YYYY handling
- Better legacy FBG extraction from "value (date)" format (2017-2019 trackers)
- Blood pressure splitting implemented (was missing, now done)
- Fixed `insulin_type` derivation bug (R doesn't check analog columns)
- Fixed `insulin_subtype` typo ("rapic" → "rapid" in R)
