# FBG header spellings across the 254-tracker set

Generated while closing [ticket 30](../tickets/30-triage-patient-raw-column-divergence.md);
the evidence base for [ticket 42](../tickets/42-fbg-unit-headers-and-implausible-values.md).

`scale_suggests` is inferred from the median (>35 reads as mg/dL); `values_over_35` counts
readings that are implausible as mmol/L. No patient-level data here -- header text and
aggregates only.

| header_in_tracker | unit_claimed_by_header | resolves_to | files | values | median | min | max | scale_suggests | values_over_35 | pct_over_35 | disagrees |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Baseline FBG (mg%) | mg | fbg_baseline_mg | 4 | 1314 | 291 | 91 | 500 | mg/dL | 1314 | 100 |  |
| Baseline FBG (mg/dL) | mg | fbg_baseline_mg | 44 | 9517 | 190.8 | 0 | 760 | mg/dL | 8103 | 85.1 |  |
| Baseline FBG or CBG (mg/dL) | mg | fbg_baseline_mg | 9 | 2679 | 151 | 3.1 | 565.2 | mg/dL | 1573 | 58.7 |  |
| Baseline FBG* mg/dL | mg | fbg_baseline_mg | 23 | 8132 | 174.6 | 0 | 1287 | mg/dL | 6324 | 77.8 |  |
| Updated FBG (mg/dL) | mg | fbg_updated_mg | 6 | 40 | 135 | 94 | 324 | mg/dL | 40 | 100 |  |
| Updated FBG FBG (mg/dL) | mg | fbg_updated_mg | 2 | 572 | 160 | 0 | 384 | mg/dL | 518 | 90.6 |  |
| Updated FBG mg/dL | mg | fbg_updated_mg | 199 | 46814 | 122.4 | 0 | 2013 | mg/dL | 42331 | 90.4 |  |
| Updated FBG or CBG mg/dL | mg | fbg_updated_mg | 9 | 2594 | 106.2 | 0 | 1800 | mg/dL | 1469 | 56.6 |  |
| Updated Mean FBG (mg/%) | mg | fbg_updated_mg | 3 | 14 | 133.2 | 67 | 217.8 | mg/dL | 14 | 100 |  |
| Updated Mean FBG (mg/dL) | mg | fbg_updated_mg | 6 | 1 | 231 | 231 | 231 | mg/dL | 1 | 100 |  |
| Baseline FBG (mmol/L or mg/dL) | mmol | (UNMAPPED - column dropped) | 1 | 155 | 7.7 | 3.6 | 29.7 | mmol/L | 0 | 0 |  |
| Baseline FBG (mmol/dL) | mmol | (UNMAPPED - column dropped) | 1 | 45 | 233 | 67 | 500 | mg/dL | 45 | 100 | HEADER SAYS MMOL, VALUES LOOK MG |
| Updated FBG (mmol/L or mg/dL) | mmol | (UNMAPPED - column dropped) | 1 | 0 |  |  |  |  | 0 |  |  |
| Baseline FBG (mmol/L) | mmol | fbg_baseline_mmol | 17 | 2787 | 21.8 | 3.1 | 71.5 | mmol/L | 386 | 13.9 |  |
| Baseline FBG mmol/L | mmol | fbg_baseline_mmol | 3 | 449 | 11.1 | 3.1 | 53.8 | mmol/L | 40 | 8.9 |  |
| Baseline FBG* mmol/L | mmol | fbg_baseline_mmol | 4 | 1293 | 16.6 | 0 | 81.9 | mmol/L | 129 | 10 |  |
| Updated FBG (mmol/L) | mmol | fbg_updated_mmol | 1 | 0 |  |  |  |  | 0 |  |  |
| Updated FBG FBG mmol/L | mmol | fbg_updated_mmol | 1 | 0 |  |  |  |  | 0 |  |  |
| Updated FBG mmol/L | mmol | fbg_updated_mmol | 48 | 11108 | 8 | 1.4 | 516.8 | mmol/L | 66 | 0.6 |  |
| Updated FBG mmol/dL | mmol | fbg_updated_mmol | 2 | 178 | 9.4 | 3 | 600 | mmol/L | 49 | 27.5 |  |
| Updated FBG or CBG mmol/dL | mmol | fbg_updated_mmol | 1 | 52 | 8.4 | 3.5 | 23.6 | mmol/L | 0 | 0 |  |
| Updated Mean FBG (mmol/L) | mmol | fbg_updated_mmol | 2 | 119 | 8.5 | 2.2 | 30 | mmol/L | 0 | 0 |  |
| Baseline FBG (m/dL) | none | fbg_baseline_mg | 1 | 20 | 122.5 | 5 | 306 | mg/dL | 18 | 90 |  |
