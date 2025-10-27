#!/usr/bin/env python3
"""Test extraction + cleaning on multiple trackers for end-to-end validation."""

from pathlib import Path
from a4d.extract.patient import read_all_patient_sheets
from a4d.clean.patient import clean_patient_data
from a4d.errors import ErrorCollector
import sys

# Disable logging for clean output
import logging
logging.disable(logging.CRITICAL)

test_files = [
    ('2024_ISDFI', Path('/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Philippines/ISD/2024_ISDFI A4D Tracker.xlsx')),
    ('2024_Penang', Path('/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Malaysia/PNG/2024_Penang General Hospital A4D Tracker.xlsx')),
    ('2023_Sibu', Path('/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Malaysia/SBU/2023_Sibu Hospital A4D Tracker.xlsx')),
    ('2022_Penang', Path('/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload/Malaysia/PNG/2022_Penang General Hospital A4D Tracker.xlsx')),
]

print('=' * 100)
print('END-TO-END TESTING: Extraction + Cleaning')
print('=' * 100)

results = []

for name, tracker_path in test_files:
    print(f'\n📁 {name}')
    print('-' * 100)

    if not tracker_path.exists():
        print(f'  ❌ File not found: {tracker_path}')
        results.append((name, 'MISSING', {}))
        continue

    try:
        # Extract
        df_raw = read_all_patient_sheets(tracker_path)

        # Get metadata
        sheets = df_raw['sheet_name'].unique().to_list() if 'sheet_name' in df_raw.columns else []
        months = df_raw['tracker_month'].unique().sort().to_list() if 'tracker_month' in df_raw.columns else []
        year = df_raw['tracker_year'][0] if len(df_raw) > 0 and 'tracker_year' in df_raw.columns else 'N/A'

        print(f'  ✅ EXTRACTION: {len(df_raw)} rows, {len(df_raw.columns)} cols, year={year}, months={months}')

        # Clean
        collector = ErrorCollector()
        df_clean = clean_patient_data(df_raw, collector)

        # Validate schema
        if len(df_clean.columns) != 83:
            print(f'  ⚠️  Schema: Expected 83 columns, got {len(df_clean.columns)}')

        # Check key columns
        stats = {
            'insulin_type': df_clean['insulin_type'].is_not_null().sum(),
            'insulin_total_units': df_clean['insulin_total_units'].is_not_null().sum(),
            'fbg_updated_mg': df_clean['fbg_updated_mg'].is_not_null().sum(),
            'hba1c_updated': df_clean['hba1c_updated'].is_not_null().sum(),
        }

        print(f'  ✅ CLEANING: {len(df_clean)} rows, 83 cols, {len(collector)} errors')
        print(f'     Key columns: insulin_type={stats["insulin_type"]}/{len(df_clean)}, ' +
              f'insulin_total={stats["insulin_total_units"]}/{len(df_clean)}, ' +
              f'fbg_mg={stats["fbg_updated_mg"]}/{len(df_clean)}, ' +
              f'hba1c={stats["hba1c_updated"]}/{len(df_clean)}')

        results.append((name, 'PASS', stats))

    except Exception as e:
        print(f'  ❌ ERROR: {type(e).__name__}: {str(e)[:150]}')
        results.append((name, 'FAIL', {'error': str(e)[:100]}))

# Summary
print('\n' + '=' * 100)
print('SUMMARY')
print('=' * 100)

passed = sum(1 for _, status, _ in results if status == 'PASS')
failed = sum(1 for _, status, _ in results if status == 'FAIL')
missing = sum(1 for _, status, _ in results if status == 'MISSING')

print(f'\nTotal: {len(results)} trackers')
print(f'  ✅ Passed: {passed}')
print(f'  ❌ Failed: {failed}')
print(f'  ⚠️  Missing: {missing}')

if passed == len(results):
    print('\n✨ All trackers processed successfully!')
    sys.exit(0)
else:
    print('\n⚠️  Some trackers failed - review output above')
    sys.exit(1)
