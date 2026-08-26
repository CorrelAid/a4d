---
id: 72
title: A sheet whose name the matcher does not recognise is skipped in total silence
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 70
---

## Premise

Rests on [What can go wrong in a tracker that the pipeline never reports at
all?](70-audit-the-finding-taxonomy-for-blind-spots.md), closed 2026-08-26,
which measured this: 517 sheets across the 255-tracker set are never opened by
any code path, and one of them -- `Annual_2026` in `2026_Vietnam National
Children Hospital A4D Tracker_June_26` -- is a real Annual sheet carrying 76
patient rows. Nothing anywhere says so.

Rests on [Unify the two separate channels that report data-quality
findings](66-unify-finding-channels.md), closed 2026-08-25, which made
`report_finding` the single emit point, so there is one place a new finding
would go.

Overturned if the sheet-selection rules change shape -- this ticket assumes
`find_month_sheets` (prefix match against capitalised month abbreviations) and
the exact-string `"Patient List"` / `"Annual"` tests are still how sheets are
chosen.

## Why this is not hypothetical

`sheet_skipped` has **ten call sites and fired zero times** on the 255-tracker
run. Every one of them reports a sheet the pipeline *found and could not use*.
A sheet it never considered emits nothing, because selection happens before any
finding could be raised:

- `find_month_sheets` (`extract/common.py:130`) keeps a sheet only if its name
  **starts with a capitalised month abbreviation**. `JAN24`, `january24`, or a
  leading space all fail. Both the patient and the product extractor use it, so
  a sheet the matcher misses is invisible to both arms.
- `read_all_patient_sheets` matches the static sheets by **exact string**:
  `if "Patient List" in all_sheets`, `if "Annual" in all_sheets`. The
  `sheet_skipped` findings beside them fire when the sheet is *present and
  broken*, never when it is absent or spelled differently.

Measured on the real set:

- **517 sheets never opened, 16 distinct names**, 448 holding more than a
  header row. Almost all are legitimately not tracker data: `Lookup List`
  (151), `Inventory` (133), `INV` (112), `Look Up List` (103).
- **Zero month-name near-misses today.** The case-sensitivity hazard is real in
  the code and has no current instance -- worth stating, not worth fixing on
  its own evidence.
- **One live instance**: `Annual_2026` and `Annual_2025` in the 2026 VNCH
  tracker. `Annual_2026` carries the two-row Annual header and **76 rows with
  `VN_VC###` patient IDs and a filled Patient Status column**. The pipeline
  never opens it, joins no annual data for that tracker, and reports nothing.
  Today's loss is bounded -- that sheet's complication-screening columns are
  empty -- but nobody could learn that from any report, and the loss grows the
  moment a clinic fills them.
- **A hypothesis raised and killed**: the four `empty_product_data` trackers
  were checked for a dedicated stock sheet the product arm would miss. They
  have none (`Lookup List` only), so that code's "no product section found in
  any sheet" is accurate.

## Question

Decide what the pipeline should say about a sheet it does not open, then
implement it.

1. **Is the right unit a per-sheet finding or a per-workbook one?** A finding
   per unopened sheet puts 517 rows of `Lookup List` into the report, which
   buries the one that matters. A finding only for sheets that *look like* ones
   the pipeline wanted (a month name in any casing, an `Annual`/`Patient List`
   variant) is quieter but needs a recogniser, and a recogniser has its own
   blind spot.
2. **Should the name matching be loosened instead of -- or as well as --
   reported?** Case-insensitive month matching and a normalised static-sheet
   match would have opened `Annual_2026` outright. Loosening changes what is
   extracted, so it needs measuring across all 255 trackers before it lands:
   say what new sheets it would pull in and what they contain.
3. **Which code, and what does it mean?** `sheet_skipped`'s glossary says "a
   sheet, or one section of it, could not be read and was skipped" -- which
   does not describe a sheet nobody looked at. Either widen it and rewrite the
   glossary, or add a code that says *this sheet was never examined*.
4. **Does a workbook-level inventory belong in the report?** The Trackers sheet
   already joins per-arm processing state; "sheets seen / sheets skipped" would
   sit naturally beside it and would make this class of defect visible without
   a finding per sheet.

Reproduce with `uv run python scripts/finding_blind_spots.py --probe sheets`.
