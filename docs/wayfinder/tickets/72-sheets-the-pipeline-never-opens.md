---
id: 72
title: A sheet whose name the matcher does not recognise is skipped in total silence
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-27
claimed_at: 2026-08-27
resolution: decided
evidence: executed
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


## Resolution (session 2026-08-27)

**Decision.** The pipeline lists every sheet it never opens on the **operational
log**, and raises a **`fix_workbook` finding** for every sheet a tracker of its
year *should* hold and does not. Sheet selection itself is unchanged: no
matcher was loosened, and no extraction moved.

Three new error codes, all `fix_workbook`, all emitted from
`audit_workbook_sheets` (`src/a4d/extract/sheet_audit.py`), called once per
workbook from `read_all_patient_sheets` -- the patient arm only, because the
audit is per workbook and the product arm reads the same file:

- **`month_sheet_missing`** -- a month absent from *inside* the tracker's own
  first-to-last range. Fires **1/255**: 2017 Mahosot has `Feb17` then `Apr17`,
  with no `Mar17` under any spelling.
- **`month_sheets_end_early`** -- a *completed* year whose last month sheet is
  before December. Fires **4/255**: 2020 YCH (Oct), 2022 UTH (Aug), 2023 CHO
  (Oct), 2025 UMC (Aug).
- **`static_sheet_missing`** -- `Patient List` or `Annual` absent although the
  tracker's year is at or past that sheet's introduction year. Fires **1/255**:
  the 2026 VNC tracker.

`unopened_sheets()` / `log_unopened_sheets()` write the full list to the log
instead of the findings table: **510 log lines across all 255 trackers** (2x per
tracker, the logs table's pre-existing loguru dual-sink behaviour -- a
pre-existing `find_month_sheets` info line lands 8x, so this is not new).

**Because.** The user rejected the ticket's implied "widen the matcher" route as
a hidden subset of "report everything": widening requires already knowing every
sheet name in use, and even then says nothing about names future trackers will
invent. So the two halves are deliberately different in kind -- an exhaustive
*list* for the log, which needs no recogniser and therefore has no blind spot,
and an *assertion on what should be present* for the findings table, which
surfaces an unopened sheet named anything at all because the sheet it should
have been is reported missing.

The thresholds were chosen by measuring the population, not by principle. The
ticket's own framing ("all 12 monthly sheets") would fire on **36** trackers, of
which **31** are clinics that joined mid-year (VNC starts Jul 2017, PTJ Jul
2021, QMC Dec 2025) and 48 are 2026 trackers whose year has not finished. The
three narrower checks fire **6 times total**, and every one is actionable.

The static-sheet introduction years are derived from the corpus, not declared:
`Patient List` 0/62 before 2022 and 145/145 from 2022; `Annual` 0/122 before
2024 and 132/133 from 2024 -- the single exception being the case this ticket
exists to report.

**The ticket named the wrong sheet, and the correction is the session's main
finding.** The ticket says the loss is `Annual_2026`'s 76 rows and is "bounded"
because its screening columns are empty. Measured directly against the real
workbooks:

| sheet | workbook | 76 patient rows | screening data |
|---|---|---|---|
| `Annual` | 2025 VNC tracker | yes | **none** -- ID/Name/Status/Education only |
| `Annual_2025` | **2026** VNC tracker | yes | **26 kidney tests, 21 eye exams, 21 BP pairs**, 15 and 8 in two more blocks |
| `Annual_2026` | 2026 VNC tracker | yes | 6 cells -- this year, barely started |

The clinic filled 2025's annual screening in retrospectively, **in the 2026
workbook**. The pipeline opens the 2025 workbook's `Annual` sheet, finds it
empty of screening data, and never opens the populated copy. So `Annual_2025`
holds the only annual screening VNC has for 2025, and the loss is neither
bounded nor hypothetical. This also kills the obvious widening rule: "prefix-
match `Annual`, take the sheet matching the tracker year" selects the *empty*
`Annual_2026` and still loses `Annual_2025`. The `static_sheet_missing` message
names both candidates and says explicitly that a sheet holding another year's
data belongs in that year's tracker.

**Rejected.**

- *Widen the matcher (case-insensitive months, normalised static-sheet match).*
  Measured: case-insensitive month matching pulls in **zero** new sheets today
  -- none of the 16 distinct unopened names starts with a month abbreviation in
  any casing. A normalised `Annual` match pulls in exactly `Annual_2025` and
  `Annual_2026`. Killed on the user's reasoning above, and independently by the
  fact that `join_static_sheet` (`extract/patient.py`) joins Annual data onto
  the tracker's own patient rows carrying no year of its own, so reading
  `Annual_2025` from a 2026 workbook would file 2025 screening under 2026.
- *Read `Annual_2025` and attribute it to the year in its name*, joining it into
  the 2025 tracker's output. Semantically correct and rejected as far larger
  than this ticket: it introduces cross-tracker data flow, which nothing in the
  pipeline does today, and needs a rule for when both copies hold values. The
  finding now puts it on record for A4D to fix at source.
- *A finding per unopened sheet.* 517 rows, 499 of them `Lookup List` /
  `Inventory` / `INV` variants, burying the one that matters.
- *A recogniser for "sheets that look like ones we wanted".* The user's point:
  it can only match names somebody already thought of, which is the exact blind
  spot this ticket exists to close.

**What this gives up.** `Annual_2025`'s screening data stays unread until A4D
moves it. The case-sensitivity hazard in `find_month_sheets` is real and
untouched -- it has zero current instances, and `log_unopened_sheets` would now
surface the first one.

**Evidence: executed.** Every number above was measured against the real
255-tracker corpus on the drive, not a fixture. Full both-arm run
(`a4d run --skip-download --skip-upload --skip-drive-download --force`):
findings **105,464 -> 105,470**, exactly the 1 + 4 + 1 predicted and nothing
else; codes firing **37 -> 40**; `patient_data_monthly` (86,360),
`product_data` (75,169), `patient_data_static` (1,828) and
`patient_data_annual` (4,520) all unchanged, so no production data moved. The
`Annual_2025` / `Annual` cell counts were read directly from both VNC
workbooks. Full suite 1,293 passed / 1 skipped (15 new tests), ruff,
`ruff format --check`, `ty check src/` all pass.

**Tense.** Everything above is current behaviour on `dev` as of this session,
except the two rejected extraction changes, which describe what *would* happen
and were not made.
