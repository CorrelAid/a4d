---
id: 39
title: Decide whether a date buried inside a clinical note should be recovered or discarded
labels: [wayfinder:grilling]
status: closed
blocked_by: []
assignee: session-2026-08-21
claimed_at: 2026-08-21
resolution: decided
evidence: executed
closed_by: null
spawned_by: 38
---

## Premise

Rests on [Triage the patient cleaned-stage date-column family (round
3)](38-triage-patient-cleaned-date-family.md), closed, which established three
things this ticket depends on:

- **A date cell that records an absence is now nulled, not sentinelled.**
  `MISSING_VALUE_MARKERS` / `DATE_ABSENCE_MARKERS` /
  `DATE_PLACEHOLDER_FRAGMENTS` (`src/a4d/clean/date_parser.py`). That removed
  4,377 of the 6,186 sentinel-stamped date cells, so what remains is no longer
  contaminated by blanks -- this ticket's 1,809 rows really are cells where
  *something* was written.
- **R is not a usable oracle here.** R's `parse_dates` recovers a date from
  some of these strings and is demonstrably wrong on others: `"admitted to
  Pokaku Hosp due to DKA 7-15 Apr"` -> R gives `2015-07-01`; `"DKA: admitted
  6-12 Nov 2020"` -> R gives `2020-12-06` (the range's two numbers read as
  day and month); `"9-Dce-20"` -> R gives `2020-09-01`, discarding the
  transposed "Dce". So "match R" is not available as an answer, and any
  divergence this ticket creates from R needs its own justification.
- **Ticket 37 already added a longest-parseable-prefix fallback**, which
  handles a date at the *start* of the string (`"16-Nov-2019 due to DKA"`).
  This ticket is about the other direction -- the note comes first and the
  date is inside or at the end.

Overturned only if the destination stops requiring that Python's own output be
defensible on its own terms; it survives R's retirement (ticket 12) intact,
because it is a question about Python's behaviour, not about parity.

## Question

**1,809 cleaned date cells across 296 distinct source texts currently become
the error sentinel because a real, legible date is embedded in a clinical
note.** Measured on the real 254-tracker set after ticket 38's fix, largest
first: `t1d_diagnosis_date` 559, `hospitalisation_date` 540, `bmi_date` 126,
`fbg_updated_date` 124, `hba1c_updated_date` 86, then the four
complication-screening date columns and a tail.

Representative texts, all of which a human reads without hesitation:

```
DKA 23 Oct 2020
Passed away 28/10/2019 due to DKA
DKA 30-Nov-2020 (Meikhtila hospital)
7/04/2021: DKA
22nd Feb.2019(DKA)
May'21: Rx at Emergency room Hyperglycemia with Ketosis
```

And the ones that make this a decision rather than a task:

```
DKA: admitted 6-12 Nov 2020          (a range -- which endpoint?)
DKA 2020: June, Aug, Nov             (three events in one cell)
admitted ... due to DKA 7-15 Apr     (a range, and no year at all)
DKA 2019                             (a year, no month -- invent Jan 1?)
10-มค-2025                            (Thai month abbreviation)
```

Decide, with a recommendation rather than a survey:

1. **Do we recover these at all**, or is the sentinel plus the error log the
   right home for "a date is in here somewhere"? Note what is lost either way:
   discarding loses a real hospitalisation date the clinic recorded; recovering
   risks asserting a precise date the source did not state.
2. **If we recover: how strict?** An anchored, unambiguous pattern (day +
   month-name + 4-digit year, and nothing that looks like a range) recovers
   the clean majority and refuses the ambiguous tail. dateutil's `fuzzy=True`
   recovers more and invents more -- it is how R gets `2015-07-01` out of
   `"7-15 Apr"`.
3. **Where does an ambiguous cell go?** Sentinel, null, or first-endpoint-with-
   an-error-log-entry are all defensible; they are not the same claim.
4. **Does `hospitalisation_date` want a different answer from the rest?** It is
   the only column where clinicians routinely write prose -- the template's own
   sub-header says "(Insert Date or NA)" and they write a case note anyway.
   `t1d_diagnosis_date`'s 559 rows may have a different shape entirely and are
   not yet characterized.

Whatever is decided, the corresponding cause needs naming in
`src/a4d/migration/compare.py` so the R-vs-Python report stops carrying these
as `unclassified` -- 487 of them currently sit there.

## Standing bar

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Where
Python turns out to be wrong or to be losing information the source file
carried, fix the pipeline rather than labelling the symptom. A cause genuinely
undecidable on available evidence is recorded as an open question, not closed
with a label; where the evidence shows the source file itself is corrupt,
"the source is wrong, this tracker needs human inspection" is a legitimate
final conclusion.

## Addendum (2026-08-19c, from [round 6](53-triage-patient-cleaned-residual-6.md))

Round 6 measured `hospitalisation_date`'s whole cleaned-stage residual -- 546
cells at the time, 489 after that round's parser fix -- by joining every
flagged cell back to Python's raw stage and grouping by the source value.
**Every distinct source is a clinical note; the "mangled date token and nothing
else" kind that earlier rounds expected alongside them does not appear in this
column at all.** So this ticket owns the entire column, not a share of it.

The population runs in three directions, and the third is new to this ticket:

- **Python sentinels, R has a date (302).** `DKA - Feb-2020`, `DKA; Jul 2018`,
  `Passed away 28/10/2019 due to DKA`, `DKA 2020: June, Aug, Nov`. The
  direction this ticket was written about.
- **R sentinels, Python has a date (179).** `April 19 (due to very high
  Hba1c)` -> Python 2019-04-01, `19th-29th Aug 2019` -> 2019-08-19,
  `7/2020 DKA Admit Ratchaburi Hospital 5 Days` -> 2020-07-01. **Python already
  recovers dates from free text here**, via ticket 37's longest-parseable-prefix
  fallback, and R does not. So the question is not "should Python start doing
  this" -- it partly does, inconsistently, depending on where in the string the
  date sits.
- **Both find a date and they differ (65).** `May 2019, Dec 2019 DKA, August
  2020 DKA`, `Dec 2019, Mar 2020 DKA Jan 2021 DKA`. The cell records *several*
  admissions and the two pipelines pick different ones.

That last group adds a sub-question this ticket should decide alongside the
first: **when a note records more than one date, which one does a single date
column mean** -- the first, the latest, or is a single column simply the wrong
shape for the data? Answering "recover" without answering this leaves the
recovery non-deterministic in exactly the cells clinicians cared enough to
write out.

Round 6 deliberately left all 489 cells `unclassified` rather than naming a
cause for them: a label would read as "understood and settled" while this
decision is open, and would hide the largest single column on the cleaned-stage
report from the next round's re-measurement.

## Resolution (2026-08-21)

### Decision

**A date buried inside a clinical note is recovered, by an explicit pattern
recogniser that refuses anything it does not recognise.** Seven parts, all
settled with the user in session:

1. **Recover, rather than discard.** The choice was never "start recovering or
   not" -- it was which way to make an inconsistency consistent. Python already
   recovered a date at the *front* of a note (ticket 37's prefix walk) and
   discarded the identical date in the middle, so `"16-Nov-2019 due to DKA"`
   was published and `"DKA 16-Nov-2019"` was sentinelled.
2. **Recognition is an explicit, anchored pattern set** (`_DATE_IN_TEXT`,
   `recover_date_from_text`, `clean/date_parser.py`), not `dateutil(fuzzy=True)`
   and not a windowed generalisation of the prefix walk.
3. **A note naming several dates publishes the first**, and the discard is
   logged and reported.
4. **Missing components**: no day -> the 1st; no year -> the row's tracker year.
5. **Everything else keeps the `9999-09-09` sentinel.** Per ticket 38's line:
   null means nothing was recorded, the sentinel means something was recorded
   that cannot be read as a date. Every refused cell is the second.
6. **The recogniser lives in `parse_date_flexible`**, so all 18 date columns
   get it, even though prose occurs in only one.
7. **Three new warning-level error codes** -- `date_recovered_from_text`,
   `date_multiple_in_cell`, `date_year_inferred` (`errors.py`, emitted by
   `_log_text_recoveries` in `clean/converters.py`). Refused cells keep
   `type_conversion`/`invalid_value` unchanged.

### Because

The pattern set was built **after** measuring the column rather than from the
six example strings this ticket was written with -- the user's call, and it
changed three of the answers. The scan (`output/analysis/ticket39_hospitalisation_date_sources.xlsx`,
745 distinct strings over 7,847 non-null cells in 240 trackers) found:

| shape | cells |
|---|---|
| already parsed | 4,734 |
| `NA` / `-` / blank -> nulled | 1,736 |
| words, no digits (mostly `Nil` + template placeholder) | 763 |
| **digits, unparsed** | **614** |

and within that 614: one full date inside prose 302, two or more date tokens
158, month+year only 45, day+month with no year 31, range sharing a month 30,
and **48 cells with digits and no date at all** (`3 month come back meet
Doctor`, `check 2 or 3 time per/day`, `on stamlor 5mg`). That last row is what
disqualifies fuzzy parsing on evidence rather than on taste: `dateutil` does not
decline on any of them, it returns a date built from `datetime.now()` -- the
same failure this parser has already been bitten by in tickets 50, 53 and 56.

The header itself was read from the source workbook rather than assumed:
`2021_Preah Kossamak`, sheet `Feb21`, row 65 -- *"Hospitalisation due to
diabetes emergency or glucose control (Include Date)"*. It is a free-text
clinical field whose only instruction is to include a date, which is why this
column and no other carries prose.

The cells are also **patient-level history, not month events**: `DKA - Feb-2020`
appears in all 12 month sheets of 2021 PKH for `KH_PK010`, `22/7/2020-26/7/2020`
in all 12 of 2021 Chiang Mai for `TH_CP019`. The clinic writes the note once and
copies it down.

### Rejected

- **Discard everything, remove the prefix walk too** -- consistency bought by
  deleting 158 correct dates from production.
- **`dateutil(fuzzy=True)`** -- see the 48 no-date cells; it is also how R gets
  `2015-07-01` out of `"7-15 Apr"`.
- **Windowed prefix search** -- sounds like the smaller change and is the
  dangerous one: `_parse_date_str` ends at `dateutil`, so a window like
  `"5 Days"` parses, and the invented-component problem returns by the side door.
- **Latest date rather than first**, for a multi-date note -- defensible where a
  tracker's header says "Last hospitalisation" (`synonyms_patient.yaml:202`), but
  that wording is a minority and choosing on it would make one string mean
  different things in different files.
- **Refusing multi-date cells outright** -- removes currently-published values
  and is not more honest, since the first date *is* recorded in the cell.
- **Nulling the unreadable cells** (option B/C on the sentinel question) -- the
  user's reasoning: the sentinel is a flag that something was written, was not
  empty, and could not be parsed, which is precisely what wants investigating.
- **Column-scoping the recogniser to `hospitalisation_date`** -- a second code
  path behaving differently for reasons invisible at the call site. The
  user's reasoning: the patterns are general date patterns, correct anywhere.
- **Recognising a bare year inside prose.** `"DKA 2019"` names no month and a
  month cannot be recovered from anything. The whole-cell bare-year convention
  (ticket 52) rests on a clinic writing *only* a year, which this is not; and
  refusing it is what lets `"DKA 2020: June, Aug, Nov"` avoid becoming 1 January.

What the chosen route gives up: each new spelling of a date needs a pattern, and
Python now recovers less than R does on a handful of cells R happens to guess
right.

### What it moved

On the real 254-tracker set, `hospitalisation_date`:

- **673 sentinels -> 156** in cleaned output (5,406 non-null cells).
- **940 cells** logged `date_recovered_from_text`, **240** `date_multiple_in_cell`,
  **40** `date_year_inferred`. Only 7 of the 1,223 entries land outside
  `hospitalisation_date` (5 `bmi_date`, 2 `last_clinic_visit_date`).
- R/Python cell mismatches for the column: **478 -> 0 unclassified**, split
  across three new causes -- `python_reads_date_in_clinical_note` (332),
  `note_dates_read_differently` (134), `r_invents_january_from_bare_year` (24).
- Whole patient cleaned stage: 114,371 -> 114,240 mismatches; unclassified
  3,432 -> 2,955, of which 2,935 is ticket 44's FBG population.

Old parser vs new over **all 18,186 distinct (date string, tracker year) pairs**
in the raw output: 117 strings changed, 553 cells. All but five are
sentinel-to-real-date. The five reading *changes* are all corrections:
`19th-29th Aug 2019` 2019-08-29 -> 2019-08-19 and `19th-28th Oct 2018 (DKA)`
2019-10-28 -> 2018-10-19 (the admission day, not the discharge day, and the
second also had the wrong *year*), `3-9 Sep 2020` 2003-09-09 -> 2020-09-03 (x2
files), `4-13 Oct 2024` 2004-10-13 -> 2024-10-04.

### Three defects found while building it

- **A bare range with no prose was misread, not refused** -- and this was
  pre-existing, not introduced here. `dateutil` takes the range's first number
  for a year, so `"6-12 Nov 2020"` was published as **2006-11-12** and
  `"3-9 Sep 2020"` as **2003-09-09**. Fixed by consulting the range patterns
  first when the cell *opens* with one.
- **The prefix walk beat the recogniser to the range cells**, because it runs
  earlier and ends at `dateutil`. The recogniser now runs before it: it is the
  explicit reading, and the walk is the guess.
- **`_is_range` was checking `match.lastgroup`**, which names the last *inner*
  group to match (`rn_year`), never the outer alternative -- so ranges were
  never flagged `date_multiple_in_cell`. Caught by reading the real error table,
  not by a test.

### Evidence

**Executed.** The 745-string scan, the 18,186-pair old-vs-new parser sweep, two
full patient-arm runs against the real 254-tracker set on the USB drive, three
comparison runs against the frozen `output_r/`, and a direct read of the source
workbook's own header cell. 888 tests pass; ruff and `ty check src/` clean.
Tense: every number above is measured current behaviour, not a projection.

The one claim resting on **judgement** is the year-inference rule -- see
*Assumptions in force* on the map.

### Left open, deliberately

- **One `bmi_date` cell is newly unclassified.** Source `0ct/19` (a zero for the
  letter O); typo rescue makes it `OCT/19`, which Python now reads as
  2019-10-01 and R sentinels. Python is right -- R's parse order list cannot
  express a slash-separated month/year. Not classified because the honest home
  for it is a widened `r_parse_order_cannot_read_cell`, whose own docstring says
  the day>12 signature is what keeps it from over-claiming. One cell.
- **`25Jul-2Aug2022`** (1 cell): a range written with no separators at all.
  Neither pipeline reads it correctly -- R gives 2022-02-25, Python the
  discharge day 2022-08-02. The source is what needs correcting; it goes to
  ticket 40.
- **7 recovered cells land past their tracker year** (`39 Aug 2022`,
  `DKA Jul'29`). Both are source typos; the beyond-tracker-year guard sentinels
  them, so nothing wrong reaches output. Also ticket 40's.

### Findings routed elsewhere

- **The template's own placeholder text is stored as a cell value in ~170 cells**
  (`Insert Date` 65, `Insert Date or NA` 60, `NA or Hospitalisation Date` 44).
  Harmless today -- ticket 38 already nulls them -- but a source defect, so it
  goes to [ticket 40](40-source-defect-findings-report.md).
- **Buddhist-Era years appear in this column** (`18-19/11/2567`,
  `19-22/5/2568`). Refused, since converting them is a separate decision about
  the workbook. Also ticket 40's.
- **The ticket's own claim that `t1d_diagnosis_date` (559 cells) belongs to this
  population is false**, and was checked rather than inherited: every one of its
  sentinels traces to a clean, unambiguous source date rejected by the
  future-date guard -- the corrupt 2022 VNCH column round 4 already decided --
  plus one BE `2560-01-01`. No free text is involved. The same check found the
  other date columns' unparsed values are typos (`9-Dce-20`, `00/00/2020`), not
  prose, so this ticket's population really is one column.
