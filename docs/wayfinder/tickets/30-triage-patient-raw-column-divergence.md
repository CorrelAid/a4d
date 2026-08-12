---
id: 30
title: Triage the patient pipeline's raw-stage column-existence divergence
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 26
---

## Premise

Rests on [Triage the product pipeline's column-existence and dtype
divergence](26-triage-product-column-divergence.md), closed: that ticket
added a `column_divergence` sheet to every stage's comparison report and
triaged product's (both stages) and patient's cleaned-stage divergences
fully — patient cleaned stage is essentially clean (one single-file dtype
mismatch). Patient's raw stage did not converge and was split off here
rather than forced.

On the current 248-tracker `output_r`/`output_python` pair
(`just compare-outputs` against the USB drive), patient raw stage's
`column_divergence` sheet has 18,783 rows across 245 common files —
two large, distinct patterns, neither yet root-caused:

- Hundreds of uniquely-numbered only-in-R columns (`na`, `na1`, `na2`, ...
  up to `na10064` in one file alone), which look like R's own
  deduplication scheme for blank or duplicate Excel header cells (R
  appends a numeric suffix to disambiguate repeated/empty column names on
  read) rather than anything Python's extraction produces.
- A large only-in-Python set of literal, unmapped source header text
  (`"Phone Number"`, `"Date"`, `"Home Visit"`, `"Home Visit 1"`, `"BGM
  A4D"`, etc.) — apparent raw passthrough of Excel headers that didn't
  match any entry in `reference_data/synonyms/synonyms_patient.yaml`,
  present in Python's raw output but not R's.

Unlike product raw's `product_returned_by`/`product_units_returned`
divergence (ticket 26, confirmed a genuine R extraction gap via direct
source-Excel spot check), neither pattern here has been spot-checked
against a real source file yet, and it isn't yet known whether they're
related to each other (e.g. R's blank-header dedup swallowing a header
Python matches to real text) or independent.

## Question

Root-cause both patterns against real source Excel and R's actual
extraction code (`r-archive/R/read_patient_data.R` or equivalent), the same
way ticket 26 did for product's raw-stage gap: for the `na`/`naN` columns,
confirm what R is actually doing on read (blank-header dedup, a fixed-width
header-row assumption, something else) and whether Python's raw extraction
is silently dropping equivalent columns or correctly has no equivalent to
drop; for the only-in-Python header-text columns, confirm whether these are
genuinely un-synonym-mapped columns Python passes through by design (raw
stage isn't schema-enforced) while R drops anything it can't map, or
whether R is failing to extract real data the same way it did for
product's "returned" columns. Decide, per file/column-family rather than
row-by-row given the volume: genuine content gap (needs a synonym-file
addition or an R-side note), or an expected raw-stage passthrough
difference (needs documenting only, per ticket 26's precedent for the
harmless cases).


## Standing bar (added 2026-08-12g, applies to this ticket)

Per the map's **triage means deciding, not labelling** preference: it is not
enough to explain a difference and name a cause. Each one must also carry an
explicit verdict on **whether Python is doing the right thing**, with the
evidence that establishes it (source Excel, or R's/Python's own code). Noting
"Python has A where R has B" and adding a classifier is not a decision in
favour of A. Where Python turns out to be wrong or to be losing information
the source file carried, fix the pipeline rather than labelling the symptom
— see [ticket 27](27-triage-patient-raw-residual.md), where exactly that
turned a labelling job into a real extraction fix. A cause genuinely
undecidable on available evidence is recorded as an open question, not
closed with a label.
