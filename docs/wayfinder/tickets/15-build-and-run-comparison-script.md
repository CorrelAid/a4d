---
id: 15
title: Build and run the R/Python output comparison script, then triage every flagged difference
labels: [wayfinder:task]
status: closed
blocked_by: [2]
assignee: session-2026-08-10
claimed_at: 2026-08-10
resolution: decided
evidence: executed
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
`docs/archive/Product pipeline parity presentation.pdf` for
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

## Resolution

**Decision.** Built and ran the comparison script per ticket 2's design;
discovered a real, specific blocker before any cause triage could start, and
split the remaining work into [ticket
17](17-fix-product-row-alignment-and-triage.md) rather than attempting it
here.

Built: `src/a4d/migration/compare.py` (four pure, unit-tested layers —
`compare_shape`, `compare_totals`, `compare_columns`, `compare_cells` — plus
`classify`/`PRODUCT_ENTRY_DATE_CLASSIFIERS` seeded from the PDF's four named
causes, `compare_directory` for per-file orchestration, `render_html_report`
for the HTML output), 23 tests, TDD'd seam-by-seam, ruff/ty clean. Thin CLI
wrapper `scripts/compare_outputs.py` + `just compare-outputs` recipe, per
ticket 2's decision to keep this out of `a4d.cli`.

Ran a fresh Python pipeline pass against `a4dphase2_upload` (both arms,
`--data-root`/`--output` pointed at the USB drive), writing to
`output_python/` next to the frozen `output_r/` (replacing the stale
2025-11-15 copy that predated this map's O(n^2) and product
column-detection fixes) — patient 174/174 succeeded, product 174/174
succeeded. Ran `compare_outputs.py` against the two directories.

**Patient arm's row-alignment key is sound**: `(patient_id, sheet_name)`
has duplicate keys in only 5 of 172 matched files (single-digit duplicate
counts each), confirmed by direct inspection — not a comparison artifact.
172 files matched, 2 only in Python (`2025_06_*` trackers postdating the
frozen R baseline).

**Product arm's row-alignment key is broken**: `(clinic_id, product,
product_sheet_name, product_entry_date)` collapses onto as few as 154
distinct keys for 1,194 rows in one file alone (up to 35 rows sharing one
key), because `product_entry_date` is null on many rows (balance-only or
malformed-date rows) — every duplicate group produces a join fan-out,
inflating cell-mismatch counts by orders of magnitude
(`product_balance`: 62,959 reported vs. 480 in the parity-presentation PDF)
and, worse, silently excludes `product_entry_date` itself from
classification since it's a join key — the PDF's single largest divergence
column (559 mismatches) never gets diffed at all. Confirmed by direct
`group_by` inspection against the real drive data, not inferred. 155 files
matched (0 only in R), 19 only in Python — all from 2017-2022, consistent
with [ticket 14](14-product-column-detection-failures.md)'s finding that
Python now emits schema-conformant 0-row output for pre-product-tracking
years where R produced no file at all.

**Also unreconciled, not yet investigated:** the PDF's 189-tracker /
61,077-row product baseline doesn't match this session's counts (155 R
product files matched, R total product rows not yet summed) — could be a
different snapshot of the drive, a different tracker set, or a stale PDF
number; ticket 17 inherits this as an open question alongside the
row-alignment fix.

**Because.** The row-alignment defect has to be fixed before any per-column
mismatch count or cause classification can be trusted for product — the
current numbers are join-fan-out noise, not real divergence signal. Rather
than design a new key blind, the right next step is inspecting real flagged
rows once alignment is fixed (per the ticket's own scoping: causes aren't
knowable ahead of time), so this session stops at the diagnosis rather than
guessing a fix.

**Rejected.**
- Attempting a product row-alignment fix inline — rejected: the fix likely
  needs the `index` row-order column `clean/product.py` already assigns per
  `(clinic_id, product_sheet_name)` group (step 2.5, not currently in the
  output schema) or some other ordinal scheme, which itself needs
  investigation against real duplicate rows to confirm R and Python assign
  the same order — that's real design work, not a continuation of what this
  ticket built.
- Trusting the reported product numbers and triaging them anyway —
  rejected: the numbers are provably inflated by join fan-out (confirmed via
  direct duplicate-key inspection), so any cause labeled against them would
  be labeling noise.
- Re-scoping this ticket to keep it open rather than closing and spawning —
  rejected: the ticket's own text pre-authorized splitting if triage didn't
  converge in one session; the infrastructure (script, tests, fresh run) is
  a complete, real deliverable independent of the remaining triage.

**Evidence.** *Executed*: built and ran the script against real drive data;
ran the fresh Python pipeline pass (both arms, real trackers); confirmed the
patient/product key-duplication counts via direct `group_by` queries against
the real parquet files, not reasoning. *Judgement*: the diagnosis that
join fan-out (not real divergence) explains the inflated product numbers is
inference from the duplicate-key counts, not a re-run with a corrected key —
ticket 17 should re-verify once a real fix lands.

**Tense.** All claims describe current repository/drive state as of this
session (executed) or a diagnosis of why the current numbers can't be
trusted (not yet fixed).

## Addendum (same session, after closure)

The user kept iterating on the tool directly after this ticket closed and
[ticket 17](17-fix-product-row-alignment-and-triage.md) spawned — same
session, same deliverable, substantial enough to record here rather than
leave implicit in conversation history:

- **Dropped `render_html_report`/HTML output entirely.** The user was
  explicit: triage means loading results as a dataframe, filtering, sorting,
  adding columns — Excel, not a static HTML page. Replaced with
  `build_summary_rows` (same per-column/per-cause aggregate data as plain
  dict rows) merged into the same per-stage Excel workbook the flagged-row
  detail already went into. Each stage now produces exactly one `.xlsx`.
- **Added `compare_id_overlap`/`IdOverlapResult`** (do the same identities —
  `patient_id` for patient, product name for product — appear on both sides
  at all, independent of the row-alignment key) and
  **`compare_categorical_overlap`/`CategoricalOverlap`** (same idea per
  categorical/label column). Both proved immediately useful precisely
  because they don't depend on the broken product row-alignment key: they
  confirmed product *names* match 100% across R and Python even where
  cell-level comparison is meaningless noise.
- **Added `compare_row_key_overlap`/`RowKeyOverlap`** — the piece that was
  actually missing. Counts rows whose *full* row-alignment key (not just a
  single identity column) found no partner on the other side at all, or
  fanned out via a repeated key. This turned out to be essential: raw
  product files were showing 0 cell mismatches, which read as "clean" but
  actually meant the join matched zero rows for that file (e.g. Mahosot:
  354 rows each side, 0 joined; live numbers confirmed near-100% row-key
  divergence — 560/560 unmatched — right where cell divergence read 0).
  Without this check, "0 cell mismatches" was indistinguishable from "the
  key found nothing to compare," which is exactly backwards from what a
  triage tool should say.
- **Compared raw pipeline output (`patient_data_raw`/`product_data_raw`) in
  addition to cleaned**, one report per stage, so a divergence can be
  localized to extraction vs. cleaning. Discovered along the way that raw
  extraction isn't schema-normalized like cleaned output (`apply_schema`
  only runs at the cleaning stage) — column presence varies file by file,
  which required making `compare_totals` and `compare_categorical_overlap`
  skip a column missing from either side instead of crashing.
- **Naming pass**: every count-based check renamed to a consistent "X
  divergence" scheme (ID, Column, Categorical, Row-key, Totals, Cell) after
  the user pointed out "ID overlap" was backwards — overlap should mean
  shared/common, not what's flagged (which is the R-only/Python-only
  divergence). Reordered so Row-key divergence sits immediately before Cell
  divergence, since both depend on the same row-alignment key.
- **Added `--only-mismatches`** (skip files where every measure is clean)
  and grouped the console/Excel output by tracker year, descending.

Net effect for [ticket 17](17-fix-product-row-alignment-and-triage.md): the
tool it inherits is meaningfully more capable than what this ticket
originally closed with. Row-key divergence in particular gives ticket 17 a
direct, per-file measurement of how badly the current key is failing
(matched/r_unmatched/py_unmatched), which should make validating a proposed
fix far more precise than re-eyeballing cell-mismatch counts.

Commits: `296fa86`, `3f5ebde`, `512c6a1`, `ac4090e`, `9fd16bb`, `a96ffc4`.
