# Patient Data Extraction - Performance Profiling Summary

**Date**: 2025-10-23
**Files Tested**: 2024 Sibu Hospital (Jan24), 2019 Penang General Hospital (Feb19)

## Executive Summary

**OPTIMIZED - Single-pass extraction:**
- **2024 tracker**: 0.877s per sheet (66% faster than two-pass)
- **2019 tracker**: 0.080s per sheet (96% faster than two-pass)

**Primary bottleneck**: openpyxl workbook loading (95-99% of time)
**Optimization**: Eliminated second workbook load by implementing forward-fill for horizontally merged cells

## Detailed Breakdown

### Time Distribution by Phase (OPTIMIZED - Single-pass)

| Phase | 2024 Tracker | 2019 Tracker | Average | % of Total |
|-------|--------------|--------------|---------|------------|
| 1. Load workbook (read-only) | 0.625s | 0.051s | **0.338s** | **79-85%** |
| 7. Build Polars DataFrame | 0.086s | 0.000s | 0.043s | 0-12% |
| 3. Read headers | 0.010s | 0.006s | 0.008s | 1-9% |
| 2. Find data start row | 0.005s | 0.004s | 0.004s | 1-6% |
| 5. Read data rows | 0.006s | 0.003s | 0.004s | 1-5% |
| 4. Merge headers | <0.001s | <0.001s | <0.001s | <1% |
| 6. Close workbook | <0.001s | <0.001s | <0.001s | <1% |
| **TOTAL** | **0.732s** | **0.064s** | **0.398s** | **100%** |

**Previous two-pass approach**: 2.583s (2024), 1.973s (2019) - avg 2.278s
**Current single-pass approach**: 0.732s (2024), 0.064s (2019) - avg 0.398s
**Improvement**: 72% faster on average (66-96% depending on file)

### Top Library Bottlenecks (from cProfile) - OPTIMIZED

**Current single-pass approach** (read-only mode only):

1. **openpyxl.reader.excel.load_workbook**: 0.6-0.8s (79-85% of time)
   - `read_worksheets()`: Most of the time
   - `parse_dimensions()`: XML parsing
   - No style/formatting overhead (read_only=True)

2. **XML parsing**: 0.4-0.6s
   - ElementTree parsing Excel's XML format
   - Required by openpyxl, cannot be optimized further

3. **Polars DataFrame construction**: 0.04-0.09s (0-12%)
   - String conversion for all cells
   - Acceptable overhead

## Optimization Assessment

### ✅ Successfully Optimized

1. **Single-pass read-only extraction**
   - Eliminated second workbook load (structure mode)
   - Only uses `read_only=True, data_only=True, keep_vba=False, keep_links=False`
   - **Result**: 66-96% faster than two-pass approach

2. **Forward-fill logic for horizontally merged cells**
   - Tracks `prev_h2` to propagate header across merged columns
   - Example: "Updated HbA1c" fills forward to "(dd-mmm-yyyy)" column
   - **Result**: Correct headers without needing `merged_cells` attribute

3. **Early termination**
   - Stops at first empty row
   - Skips rows with None in column A

4. **Efficient iteration**
   - Uses `iter_rows()` instead of cell-by-cell access
   - Pre-reads fixed width (100 cols) and trims to actual data

### Key Insight

**Initial assumption was WRONG:**
- Thought: "Need structure mode for merged cells, can't read vertically merged cells in read-only mode"
- Reality: **Read-only mode CAN read vertically merged cells** - each cell has the value
- Real problem: **Horizontally merged cells** need forward-fill logic
- Solution: Track previous h2 value and fill forward when h2=None but h1 exists

**Why single-pass works:**
- Vertically merged cells (e.g., "Patient ID" spanning 2 rows): Read-only mode reads both cells directly
- Horizontally merged cells (e.g., "Updated HbA1c" spanning 2 cols): Fill forward from previous column
- No need for `merged_cells` attribute at all!

## Recommendations

### For Current Implementation

**Current approach is OPTIMIZED** - single-pass read-only extraction with forward-fill logic.

Remaining bottleneck (79-85% of time) is unavoidable:
- XML parsing of Excel file structure (required by .xlsx format)
- File I/O overhead
- No further optimization possible without changing file format

### For Future Consideration

1. **Caching**: If processing same file multiple times
   - Cache extracted DataFrames as Parquet
   - Only re-extract when source file changes

2. **Parallel sheet processing**: When processing all months
   - Extract each month sheet in parallel
   - 12 months could process in ~2-3s instead of 24-60s

3. **Progress reporting**: For user experience
   - Show which sheet is being processed
   - Estimated time remaining

4. **Streaming**: For very large trackers
   - Not needed for current data sizes (10-20 patients per sheet)
   - Consider if patient counts exceed 100+ per sheet

## Performance Comparison: R vs Python

**R Pipeline** (openxlsx + readxl):
- Unknown exact timing (not profiled)
- Uses two libraries (complexity)

**Python Pipeline** (openpyxl):
- 2-5 seconds per sheet
- Single library, cleaner code
- Most time spent in unavoidable I/O

**Conclusion**: Both are I/O bound. Python's performance is acceptable and likely comparable to R.

## Test Environment

- **Python**: 3.13.2
- **openpyxl**: Latest version (from uv)
- **Polars**: Latest version
- **OS**: macOS (Darwin 24.6.0)
- **Hardware**: Not specified (user's machine)

## Profiling Commands

```bash
# Full profiling
uv run python scripts/profile_extraction.py

# Detailed phase breakdown
uv run python scripts/profile_extraction_detailed.py

# View saved profile
python -m pstats profiling/extraction_2024.prof
```

## Code Improvements

### Improved Header Detection (2025-10-23)

**Previous approach**: Check if `header_1[1] == header_2[1]` (single column)

**Current approach**: Two-heuristic validation
```python
# 1. Year-based: Multi-line headers introduced starting 2019
is_multiline_year = year >= 2019

# 2. Content-based: Check if ANY pair has both h1 and h2 non-None
#    (Single-row headers have title/section text in row above, not data)
has_multiline_content = any(h1 is not None and h2 is not None
                            for h1, h2 in zip(header_1, header_2))

if is_multiline_year and has_multiline_content:
    # Multi-line header logic (merge h1 and h2)
else:
    # Single-line header logic (use only h1)
```

**Benefits**:
- More explicit and maintainable
- Validates entire header row, not just one column
- Correctly handles edge cases (e.g., 2018 "Summary of Patient Recruitment" in row above)
- Year-based guard prevents false positives

**Performance**: No change (both checks are negligible vs. I/O time)

## Code Coverage

- **patient.py**: 94% coverage
- **All extraction tests**: 10/10 passing
- **Parameterized tests**: Validate 2018 (Dec), 2019 (Jan/Feb/Mar/Oct), and 2024 (Jan)
- **Year coverage**: Tests single-line (2018) and multi-line (2019+) header formats

## Successful Optimization - Single-Pass Extraction (2025-10-23)

### Problem
Original implementation used two-pass approach:
1. Load workbook in structure mode to detect merged cells (1.95s)
2. Load workbook in read-only mode for fast data reading (0.29s)

**Total time**: ~2.3s average per sheet

### Solution
Implemented **single-pass read-only** extraction with **forward-fill logic** for horizontally merged cells:

```python
# Track previous h2 for horizontal merges
prev_h2 = None
for h1, h2 in zip(header_1, header_2, strict=True):
    if h1 and h2:
        headers.append(f"{h2} {h1}".strip())
        prev_h2 = h2
    elif h2:
        headers.append(str(h2).strip())
        prev_h2 = h2
    elif h1:
        if prev_h2:
            # Horizontally merged cell: fill forward
            headers.append(f"{prev_h2} {h1}".strip())
        else:
            headers.append(str(h1).strip())
    else:
        headers.append(None)
        prev_h2 = None
```

### Key Insight
- Vertically merged cells (spanning rows): Read-only mode can read these directly - no special handling needed
- Horizontally merged cells (spanning columns): Excel sets cell value only in first column, subsequent columns are None
- **Solution**: Fill forward from previous column when h2=None but h1 exists

### Example
```
Col 12: h2="Updated HbA1c", h1="%" → "Updated HbA1c %"
Col 13: h2=None (merged),   h1="(dd-mmm-yyyy)" → "Updated HbA1c (dd-mmm-yyyy)"
```

### Performance Results
| Tracker | Before (two-pass) | After (single-pass) | Improvement |
|---------|-------------------|---------------------|-------------|
| 2024    | 2.609s            | 0.877s              | **66% faster** |
| 2019    | 2.122s            | 0.080s              | **96% faster** |

### Data Correctness Validation
- ✅ All 10 tests pass
- ✅ Correct column counts: 31 (2024), 25/28/27/27 (2019), 19 (2018)
- ✅ Proper header names including horizontally merged cells
- ✅ Patient IDs validated: MY_QI001-004

### Lessons Learned
1. **Always verify assumptions**: Initial assumption that merged cells can't be read in read-only mode was incorrect
2. **Question complexity**: The two-pass approach was solving a problem (vertical merges) that didn't exist
3. **Root cause analysis**: The real challenge was horizontal merges, which required forward-fill logic
4. **Data-first approach**: Never change test expectations to match wrong output - fix the code instead
