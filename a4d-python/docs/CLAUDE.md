# CLAUDE.md

Python pipeline for A4D medical tracker data — processes Excel trackers into BigQuery tables.
Patient pipeline is complete. Product pipeline is deferred.

## Key facts

- `clinic_id` = parent folder name of the tracker file
- Year detected from sheet names (`Jan24` → 2024) or filename
- Error sentinel values: numeric `999999`, string `"Undefined"`, date `"9999-09-09"`
- `ErrorCollector` accumulates row-level data quality errors; never raises
- `reference_data/` is shared with the R pipeline — changes affect both
