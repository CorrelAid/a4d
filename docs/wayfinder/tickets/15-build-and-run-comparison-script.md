---
id: 15
title: Build and run the R/Python output comparison script, then triage every flagged difference
labels: [wayfinder:task]
status: open
blocked_by: [2]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 2
---

## Premise

Rests on [Retire the PDF/notebook analysis docs for an automated,
script-based report](02-documentation-strategy.md), closed: the comparison
script's design is decided — decoupled from pipeline execution, diffs two
existing output directories (Python's and the already-frozen
`/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r/`, no R re-run), four
layered checks (shape, totals, columns, cell-by-cell), an extensible
cause-classifier registry seeded with the four causes already known from
`docs/migration/Product pipeline parity presentation.pdf` for
`Product_entry_date`, HTML report output, lives at `scripts/` +
`just compare-outputs` (not `a4d.cli`).

That ticket's session was explicit that only the design was in scope: the
bulk of the real work is investigative — most divergence causes for columns
other than `Product_entry_date` aren't known ahead of time and can only be
identified by inspecting actual flagged rows against the source trackers
(`a4dphase2_upload`) — and it deferred that work here rather than attempting
it inline.

## Question

Build the comparison script per ticket 2's decided design; run it against a
current Python pipeline output (fresh run against `a4dphase2_upload`) and the
frozen `output_r/`; then go through the flagged differences and, for each
column, determine why Python and R disagree — labeling causes into the
classifier registry as they're identified (adding new named classifiers
beyond the four seeded ones as needed), falling back to the original source
Excel trackers as the arbiter of which output is actually correct wherever a
divergence isn't already an understood, expected pattern.

**Validation requirement carried over from ticket 2:** the script's per-column
and per-cause mismatch counts should reproduce (or the session should be able
to explain any deltas from) the parity-presentation PDF's numbers — 189
trackers / 61,077 rows / 20 columns; `Product_entry_date`: 559,
`Product_balance`: 480, `Product_category`: 214, `Product_sheet_name`: 201,
`Product_received_from`: 154, `Product_units_received`: 9; entry-date causes
typo-rescue: 408, CE-typo: 71, sentinel-null: 66, off-by-one-day: 7. That
reproduction is what proves the new script is a faithful, trustworthy
replacement for the retired PDF/notebook documentation, and is a concrete
signal for the map's destination requirement that "every Python/R difference
[is] documented and explicitly decided."

This ticket is large and investigative (189 trackers' worth of triage) — if
it doesn't converge in one session, split the remaining per-column
investigation into further tickets rather than leaving it open-ended.
