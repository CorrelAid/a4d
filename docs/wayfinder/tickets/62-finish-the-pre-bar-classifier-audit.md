---
id: 62
title: Finish the pre-bar classifier audit — the two causes and the one bulk population it did not reach
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-24c
claimed_at: 2026-08-24T16:00:00+02:00
resolution: decided
evidence: executed
closed_by: null
spawned_by: 60
---

## Premise

Rests on [the classifier re-audit](32-audit-classifiers-against-decision-bar.md),
closed, which scoped the audit to the **12** causes predating the map's *triage
means deciding, not labelling* bar and explicitly ruled the other 38 out.

Rests on [the eight pre-bar causes](60-audit-remaining-pre-bar-classifiers.md),
closed, which audited six of the eight and left this remainder. It also
established the method that keeps finding things: scan the whole population,
then ask which rows the stated mechanism does *not* account for. Applied to
`r_extraction_gap` it found three undocumented mechanisms; applied to
`r_validator_rejects_multivalue` it found a second R defect; applied to
`buddhist_era_typo` it found the cause was naming twelve cells that are not
Buddhist-era at all.

**Void rather than in need of rewriting** if ticket 32's scoping is overturned
-- if the post-bar 38 must be audited too, this is the wrong unit of work and
the whole audit should be re-cut by registry.

## Question

Three populations, all judged by the same two bars — what the mechanism
actually is, and the explicit verdict on whether Python is correct.

1. **`r_category_lookup_miss`** (866 rows, `product_category`, product cleaned).
   Ticket 32 read it as "likely fine", traced to `read_product_data.R`'s
   case- and whitespace-sensitive `add_product_categories()` join where
   `src/a4d/reference/products.py` normalizes both sides. Never re-measured
   against the current 254-tracker set. The population test applies directly:
   is every one of the 866 explained by a normalization difference, or does
   some other shape ride along?

2. **`openpyxl_date_typed_stray_cell`** (100 rows). Its docstring names only the
   raw product columns `product_units_received` and `product_received_from`,
   but ticket 60 found it also fires on **20 patient rows** it does not mention
   — `t1d_diagnosis_age` (16), `blood_pressure_mmhg` (3), `testing_frequency`
   (1). The values look like the same mechanism (R holds the raw Excel serial,
   e.g. `20668.0`; Python holds the date the cell's own format declares, e.g.
   `1956-08-01`), but the *source cells were not re-opened* for the patient
   rows, so that is inference from shape, not verification. Note the patient
   values are nonsense as ages — the source cell is a date-formatted cell in an
   age column, which likely also belongs in
   [ticket 40](40-source-defect-findings-report.md).

3. **`r_extraction_gap`'s bulk** — `recruitment_date` (28,009) and
   `edu_occ_updated` (2,770), together ~98% of the cause and the two
   populations ticket 60 did **not** re-measure. Both have a documented,
   source-verified mechanism; what is unmeasured is whether the mechanism
   accounts for the whole population, which is exactly the question that
   turned up three new mechanisms in the other 11% of the same cause.

## Why this still needs `r-archive/`

All three questions are about what R's own code does, so the R source has to
stay until they are answered — the reason
[ticket 12](12-retire-r-workspace.md) is blocked on this ticket rather than on
its predecessor.

## Resolution

**Decision.** All three populations are audited to the two-bar standard and
**Python is the correct side in every one**. No pipeline change was needed or
made — this is the first ticket in the audit chain to find no defect. What it
found instead is that all three *explanations* were wrong or incomplete, so the
three docstrings in `src/a4d/migration/compare.py` are rewritten against
measured mechanisms. The audit that ticket 32 scoped to twelve pre-bar causes is
now complete.

**Because.** Ticket 60's method — scan the whole population, then ask which rows
the stated mechanism does not account for — found something in all three, again.

**1. `r_category_lookup_miss` (866 rows) is two mechanisms, and the larger one
is not about R's join at all.** The docstring blamed a "case or whitespace"
difference against a join R does unnormalized. Bucketing all 866 by the exact
byte difference between R's string, Python's string and the reference entry:

- **652 rows / 26 names: CRLF vs LF.** The reference workbook stores embedded
  line breaks as a bare `\n` — its Stock_Summary sheet XML holds 29 LF bytes and
  **zero** CR bytes — while the trackers store `\r\n` (2021 Surat Thani's
  `sharedStrings.xml`: 80 CRLF pairs). readxl returns each faithfully, so R
  compares `'Accu-Chek Performa Test Strips \r\n(50s/ bottle)'` against a
  reference entry spelled with `\n` and misses. openpyxl normalises CRLF to LF
  on read, so Python's two sides match byte-for-byte. The reference sheet
  already *contains* all 26 names verbatim — R should have joined them, and the
  reason it does not has nothing to do with case or with whitespace-sensitivity.
  This is the same reader difference ticket 22 added
  `normalize_whitespace_column` for, resurfacing as a lookup failure.
- **214 rows / 3 names: genuine case.** `'(singles)'` against the reference's
  `'(Singles)'` on NovoFine (98) and NIPRO (25), and `'ACCU-CHEK Performa
  Glucometer Set'` against `'Accu-Chek Performa Glucometer Set'` (91). Verified
  in R's source that the join is case-sensitive on values:
  `add_product_categories` (read_product_data.R:481) is a bare
  `dplyr::left_join`, and `load_product_reference_data` (:438) lowercases only
  `colnames`. This is the half the docstring had right.

Python correct in both; R loses a category its own reference data can supply.
The names R and Python fail on *together* (`Contour Plus Elite Meter`,
`Aphatyl Vitamin`, …) are genuinely absent from the reference and produce no
divergence — which is why they are not in the 866.

**2. `openpyxl_date_typed_stray_cell` (100 rows) states one verdict for three
shapes, and for two-thirds of the population that verdict is backwards.** The
detection is sound — every cell behind the cause was opened and genuinely
carries a date/time number format — but "Python's value is the faithful one,
R's is a column-wide coercion artifact" holds for only 14 rows:

- **A real date in a quantity column, 14 rows.** Serial in the 43,566-45,652
  range. Ticket 24's verdict stands; `_is_stray_date_zeroed` covers the cleaned
  face, where R carries 43,708 into the stock ledger and Python zeroes it.
- **A quantity or a zero in a date-formatted cell, 66 rows** (48 holding 0, read
  back as `00:00:00`; 18 holding a genuine count of 5-200, read back as a 1900
  date). Here **R's serial is the number the clinician typed and Python's date
  is the misleading rendering**. Source-verified at 2023 Yangon General
  `Apr23!G25` and siblings: column G carries a `d-mmm-yy` format over cells
  holding 150, 200, 30, 5 and 0, alongside `Entry Date`, `Balance` and
  `Units Received` headers at row 27. It costs nothing, because the divergence
  does not survive cleaning — both sides publish identical cleaned values for
  every affected `(product, sheet)` group (executed: 2023 YGH `Apr23`
  Insunova/NovoRapid/Insupen/Easydrip all 5/150/30/200 on both sides). A
  raw-stage representation artifact, so the pipeline is deliberately unchanged,
  on ticket 32's `parse_date_flexible` precedent.
- **The patient arm, 20 rows / 5 source cells / 5 trackers**, which the
  docstring never mentioned. Each is a value Excel silently auto-converted on
  entry, all five re-opened in the workbook and confirmed date-formatted:
  `10/60` → Oct-1960 in a "Blood Pressure (mm HG)" column (2020 Mahosot
  `Nov20!R152`/`Dec20!R153`, 2022 Mahosot `Jun22!Z323`, all `mmm-yy`); `1-2` →
  1-Feb in "Testing Frequency (per day)" (2021 Khon Kaen `Mar21!P60`, `d-mmm` —
  and that column holds `' 1 - 2'` four rows above, which is what the clinician
  meant); and a diagnosis *date* in "Age at Diagnosis" (2023 Chiang Mai
  `Patient List!H14`, 2023 Yangon General `Patient List!H76`). **Python is
  unambiguously correct and visibly so**: it nulls them, while R publishes
  diagnosis ages of **20,668 years** (TH_CP005, 12 sheets) and **42,859 years**
  (MM_YC043, 4 sheets). All five already reach the errors table as
  `type_conversion` with the original value intact, so
  [ticket 40](40-source-defect-findings-report.md) needs nothing added.

**3. `r_extraction_gap`'s bulk: the stated mechanism is false for the larger
half, and the true one is much sharper.** The docstring said R's extraction
"fails to populate `recruitment_date` for the large majority of patients". R in
fact populates **53,331 of its 82,771 raw rows (64%)**, and the divergence is
**perfectly file-level and all-or-nothing**: over the 239 comparable files, 91
where R reads *zero* recruitment dates, 148 with no divergence, and **zero**
files where R reads some and misses others.

The cause is a header cell whose text ends in a space, which forces Excel to
write `xml:space="preserve"`. Executed: 2023 CDA's `Patient List!L8` is literally
`<c r="L8" s="35" t="inlineStr"><is><t xml:space="preserve">Date of Recruitment
</t></is></c>`. R reads its headers with `openxlsx::read.xlsx`
(script1_helper_read_patient_data.R:15), whose inline-string parsing folds that
attribute into the header text, so `make.names` emits the column
**`xmlspacepreservedateofrecruitmentmmmyy`** and no synonym matches it. The
correlation is exact: **all 91 affected files carry that column in R's own raw
parquet, and none of the other 148 do.** openpyxl parses the attribute correctly
and reads `'Date of Recruitment '`. The same defect eats at least one further
column R never maps (`xmlspacepreserveinsurancestatusnanssfeqeqpending`).

`edu_occ_updated` (2,770 rows, 16 files) is also whole-file (13 files at zero),
but unlike `recruitment_date` it is **not one mechanism**: R's raw output carries
three distinct junk names for it — `xlevelofeducationoroccupationdate` (the
documented leading-space fixup), `levelofeducationoroccupationอาชพหรอชนเรยน` and
`...dateupdatedddmmmyyyy` (ticket 60's Thai-header mechanism). Fifteen files
carry a junk name *and* still resolve the column, so unlike recruitment_date the
junk name alone does not predict the loss.

**One of this ticket's own premises was false, and cost nothing to check.** It
said the patient rows' "source cells were not re-opened, so that is inference
from shape". They were — ticket 50 opened them and recorded the exact cells in
the `blood_pressure_mmhg`/`testing_frequency` note in
`scripts/compare_outputs.py`. The genuine gap was that the *classifier's own
docstring* never mentioned the patient arm. This session re-opened all five
independently and found the same cells, plus 2022 Mahosot `Jun22!Z323`.

**Rejected.**
- *Renaming `openpyxl_date_typed_stray_cell`.* "Stray" over-reads for 66 of its
  100 rows — the cell is not stray, only its number format is. But `openpyxl`
  and `date_typed` hold for all 100, ticket 60's precedent is to fix the
  docstring where the name is accurate, and the name is referenced across eight
  closed tickets and two pipeline source comments that a rename would orphan.
  Recorded in the docstring instead.
- *Splitting `r_extraction_gap` per mechanism.* Same reason ticket 60 rejected
  it: the name is true of all thirteen columns and splitting churns counts
  without changing a verdict.
- *Making Python's raw stage read the shape-B cells as numbers.* It would move
  production raw output to fix a divergence that cleaning already erases — the
  cleaned parquets are identical on both sides today.
- *Normalising line endings in Python's category join.* Correct in principle and
  deliberately not done here: it changes a production join for a case nothing in
  the current data triggers, and it needs its own measurement. Recorded as fog
  on the map instead.
- *Auditing the 38 post-bar causes.* Unchanged from tickets 32 and 60.

**Evidence: executed.** Full 254-tracker pipeline run at `a5b2a09` plus a full
`just compare-outputs` against the frozen `output_r/` established the session
baseline, and it reproduced ticket 60's reported deltas exactly
(`buddhist_era_typo` 12 → 0 across both patient stages, `python_absurd_excel_serial`
0 → 6 raw, `python_rejects_beyond_tracker_year` 36 → 42 cleaned) — confirming the
measurement environment before anything was concluded from it. All population
counts come from that run's Excel reports and JSON snapshots; all mechanisms
from opening the source workbooks (and, for the line endings, the raw sheet XML)
and from reading R's own source. A second full comparison after the change
confirms **all four stages report "no change from the previous run" and zero
per-cause movement** — which is the proof that a docstring-only session moved
nothing. Full suite 938 passed / 1 skipped, ruff and `ty check src/` clean.

**Tense.** Every count describes current behaviour, measured this session. The
docstring claims quoted as wrong ("large majority of patients", "case or
whitespace", "Python's value is the faithful one") describe what the registry
*said* before this session, not what the pipeline does.

**What this does to [ticket 12](12-retire-r-workspace.md): it does not unblock
it.** Re-deriving the list of open tickets that still need the R *source*, per
the map's Notes, leaves exactly one: [Monthly rows with a misspelled ID silently
lose their Patient List demographics](58-patient-list-join-uses-unfixed-id.md),
whose question 3 is literally "Check R — R's own join ordering may or may not
have the same gap". Tickets 6, 9, 16, 34, 35, 40 and 41 were each checked and
need no R. So `blocked_by` moves from `[62]` to `[58]`, and the count of tickets
standing between this map and retiring R stays at one.
