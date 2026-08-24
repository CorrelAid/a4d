---
id: 64
title: Rewrite every docstring and doc that explains the code by what R did
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 12
---

## Premise

[Retire R from the workspace once the pipeline is fully verified
Python-only](12-retire-r-workspace.md) is closed: `r-archive/` is deleted, and
the `r-archive-removed` tag is the only way to reach it. That is what makes
this ticket possible and necessary at once -- possible, because R is no longer
a live reference anyone is expected to consult; necessary, because the code
still explains itself by pointing at a directory that no longer exists.

Ticket 12 measured the size of it: **35 citations of R source files across 12
Python modules**, not the 8 in `src/a4d/migration/compare.py` its own inventory
claimed. The spread is what matters -- `compare.py` holds 17, but
`clean/patient.py` holds 10, and `extract/patient.py`, `clean/date_parser.py`,
`clean/schema.py`, `clean/schema_product.py`, `clean/product.py`,
`clean/validators.py` and `tables/product.py` carry the rest. Two test files
cite R as well. So this reaches production cleaning code, not just migration
tooling.

Rests also on the map's **standing triage bar** (Notes, set 2026-08-12g and
refined 2026-08-13): a difference is only understood when its *mechanism* is
traced to source. Fifty-four closed tickets did exactly that work, and the
mechanisms they established -- with real files, real cells, real counts -- are
the material this ticket writes the new documentation from. The evidence for
almost every rule in the pipeline already exists in the closed tickets and in
[MR_DESCRIPTION.md](../../migration/MR_DESCRIPTION.md); this ticket moves it to
where a reader of the code will actually find it.

Would be void, not merely rewritten, if `r-archive/` were restored to the
working tree as a live reference.

## Question

The user's framing (2026-08-24): documentation that justifies a behaviour by
"to match R" was fine as *working* documentation during the migration, and is
now simply **wrong** -- it explains the code by something that no longer
exists, and it says nothing about why the code is the way it is. Comments and
docs should describe the current state and the real reason for a design, with
concrete examples and data.

Decide and execute:

1. **What replaces an R citation.** A docstring reading "R's `fix_fbg` matches
   its category words as substrings, so Python anchors them" has to become a
   statement about Python alone that still carries the reason. The candidate
   shape is: what the rule does, the source evidence that made it necessary
   (the tracker, the sheet, the cell, the count), and what breaks without it.
   Confirm that shape against a handful of the hardest sites before applying it
   to 35.

2. **Which R references are history rather than explanation.** The cause
   registry in `compare.py` documents R/Python *divergences*, and the
   comparison tool's whole purpose was comparing against R. Its classifier
   docstrings may legitimately name R, since R is their subject -- but decide
   that explicitly rather than by default, and decide what happens to the tool
   itself once the migration closes (see the fog entry on formally retiring R).

3. **How far this reaches beyond docstrings.** `docs/migration/` holds
   `MIGRATION_GUIDE.md`, `PYTHON_IMPROVEMENTS.md`,
   `PRODUCT_DATA_PIPELINE_FEATURE.md` and `MR_DESCRIPTION.md` -- all
   R-framed by construction. Some are genuinely historical records of the
   migration and should stay that way; some are read as current guidance and
   should not. Sort them, and decide whether `docs/CLAUDE.md`'s "Migration
   Status" section survives at all once the migration is done.

4. **Guard against regression.** Nothing currently stops a new "matches R
   behaviour" docstring being written. Decide whether a check belongs in the
   lint/CI set that [ticket 34](34-local-ci-parity-guard.md) is aligning, or
   whether the instruction in `CLAUDE.md` is enough.

Note the precedent from [round 4](51-triage-patient-cleaned-residual-4.md):
`_validate_dates` carried a docstring claiming its future-date guard "matches R
pipeline behavior" when R has no such guard at all. A false R citation is not
only stale, it can be **wrong about R** -- so this is a rewrite against measured
behaviour, not a find-and-replace.
