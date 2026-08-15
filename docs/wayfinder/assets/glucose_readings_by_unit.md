# Glucose readings grouped by when measured and stated unit

Measured across all 254 trackers while closing [ticket
30](../tickets/30-triage-patient-raw-column-divergence.md); the evidence sent to
A4D's medical advisor for [ticket
42](../tickets/42-fbg-unit-headers-and-implausible-values.md).

Every glucose column in every month sheet, grouped by whether it records the
reading at diagnosis (baseline) or during treatment (updated), and by the unit
its header states. Per-spelling detail is in
[fbg_header_inventory.md](fbg_header_inventory.md).

| When measured | Unit stated | Files | Readings | Median | p90 | p99 | Lowest | Highest | Median as mmol/L | Exactly 0 | mg/dL under 30 | mg/dL 30-54 | Over 100 mmol/L |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| At diagnosis | Ambiguous (header offers both) | 1 | 155 | 7.7 | 17.5 | 29.7 | 3.6 | 29.7 | 7.7 | 0 | | | 0 |
| At diagnosis | Not stated | 1 | 20 | 122.5 | 306.0 | 306.0 | 5.0 | 306.0 | 122.5 | 0 | | | 12 |
| At diagnosis | mg/dL | 71 | 21,642 | 190.0 | 393.0 | 581.9 | 0.0 | 1287.0 | 10.5 | 134 | 3,714 | 1,040 | 0 |
| At diagnosis | mmol/L | 25 | 4,574 | 19.3 | 38.0 | 80.0 | 0.0 | 500.0 | 19.3 | 244 | | | 30 |
| During treatment | mg/dL | 214 | 50,035 | 122.0 | 265.0 | 445.0 | 0.0 | 2013.0 | 6.8 | 60 | 5,550 | 647 | 3 |
| During treatment | mmol/L | 52 | 11,457 | 8.0 | 15.5 | 36.9 | 1.4 | 600.0 | 8.0 | 0 | | | 92 |

## What this shows

**Unit confusion runs in both directions, and is far larger in one of them.**
9,264 readings sit in columns labelled mg/dL but below 30 mg/dL -- a value that
cannot be an ambulatory reading and lands exactly where a mmol/L number would.
122 readings sit in columns labelled mmol/L but above 100, where a mg/dL number
would. Whether these really are mixed units is the advisor's call, not the
pipeline's.

**Zeros are placeholders, not hypoglycaemia.** All 244 baseline mmol/L readings
under 3 mmol/L are exactly 0.

**The baseline distribution is broad but continuous**, with no values above 100
at all -- so it does not have the bimodal shape a bulk mg/dL contamination
would produce. A median of 19.3 mmol/L may simply be presentation
hyperglycaemia; that is question 3 to the advisor.

**The two cut-offs used here are physiological, not chosen for convenience**:
above 100 mmol/L and below 30 mg/dL are both impossible readings. An earlier
version of this analysis bucketed on 35 mmol/L, which was an invented threshold
and was dropped.
