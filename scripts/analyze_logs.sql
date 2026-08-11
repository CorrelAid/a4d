-- analyze_logs.sql
.mode box.timer on -- Summary Statistics
SELECT
    'Log Summary' as section;

SELECT
    COUNT(*) as total_logs,
    COUNT(DISTINCT file_name) as unique_trackers,
    MIN(timestamp) as earliest,
    MAX(timestamp) as latest
FROM
    '/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python/tables/table_logs.parquet';

-- Level Distribution
SELECT
    'Level Distribution' as section;

SELECT
    level,
    COUNT(*) as count
FROM
    '/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python/tables/table_logs.parquet'
GROUP BY
    level
ORDER BY
    count DESC;

-- Top Errors
SELECT
    'Top 10 Files with Most Errors' as section;

SELECT
    file_name,
    COUNT(*) as issues
FROM
    '/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python/tables/table_logs.parquet'
WHERE
    level = 'ERROR'
GROUP BY
    file_name
ORDER BY
    issues DESC
LIMIT
    10;

SELECT
    file_name,
    COUNT(*) as issues
FROM
    '/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python/tables/table_logs.parquet'
WHERE
    level = 'WARNING'
GROUP BY
    file_name
ORDER BY
    issues DESC
LIMIT
    10;

-- Exception Summary
SELECT
    'Exception Types' as section;

SELECT
    exception_type,
    COUNT(*) as count
FROM
    '/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_python/tables/table_logs.parquet'
WHERE
    has_exception = true
GROUP BY
    exception_type
ORDER BY
    count DESC;