---
id: 62
title: Finish the pre-bar classifier audit — the two causes and the one bulk population it did not reach
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
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
