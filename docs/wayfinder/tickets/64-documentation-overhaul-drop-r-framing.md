---
id: 64
title: Rewrite every docstring and doc that explains the code by what R did
labels: [wayfinder:task]
status: closed
blocked_by: []
assignee: session-2026-08-24g
claimed_at: 2026-08-24
resolution: decided
evidence: executed
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
[MR_DESCRIPTION.md](../../archive/MR_DESCRIPTION.md); this ticket moves it to
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

3. **How far this reaches beyond docstrings.** `docs/archive/` holds
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

## Resolution (session-2026-08-24g)

**Decision.** Every module outside `src/a4d/migration/` now explains itself in
its own terms. **353 R references in `src/` and 88 in `tests/` are down to the
179 + 42 inside the comparison package**, which is exempt by decision (below).
Outside it: `src/` 174 -> **0**, `tests/` 46 -> **0**, user-facing markdown 65
-> **0**.

The replacement shape, confirmed against the hardest sites before being applied
broadly: *what the rule does, the source evidence that forced it (tracker,
sheet, cell, count), and what breaks without it.* Examples --
`transform_cm_to_m`'s threshold stopped being "matching R" and became "120
cells reading 2.43/6.9/13.0 were published as 0.069 metres"; the whitespace
strip stopped citing `readxl`'s `trim_ws` and now names Kantha Bopha 2019
KH_KB023's `'F '` cell and the 72 rows of `sex` it cost; the optional closing
parenthesis stopped citing R's regex and now says 25 of 30 source cells are
written `180(May-2017`.

**`src/a4d/migration/` is exempt, and marked historical rather than merely
excused** (option 2 of three, user's choice). Its module docstring now opens by
saying the package is a snapshot of finished work, that no new R output will
ever be produced so the tool will not run again, that it is kept because its
cause registry is the written evidence behind the migration's conclusions, and
that the R source is reachable at `git show r-archive-removed^:...`. The script
itself is unchanged.

**`docs/migration/` moved to `docs/archive/`** (user's instruction, mid-session)
and gained a `README.md` index: what each document is, what superseded it, and
where to look instead for current guidance. Every document carries a banner and
was brought to the true current state first rather than being frozen while
wrong -- `MIGRATION_GUIDE.md`'s "Phases 0-9" status became the real final state,
`MR_DESCRIPTION.md`'s "240 commits / 664 tests" became 285 commits / 981 tests,
and `PYTHON_IMPROVEMENTS.md` now says in its own header that ticket 7 found it
undercounting, and points at the two derived inventories that replaced it.

**`docs/VALIDATION_SUMMARY.md` was deleted**, not banner-ed: it is an
R-vs-Python verdict over **174** trackers, superseded by the 254-tracker
comparison, so it was both R-framed and factually stale. Nothing referenced it.

**A regression guard was added** (question 4), as
`tests/test_docs_have_no_r_framing.py` rather than a new lint hook -- it runs in
CI already and needs no coordination with [ticket
34](34-local-ci-parity-guard.md). It derives its file list from the tree rather
than hardcoding one, exempts the migration package and itself, and assembles
its own patterns from parts so it does not match its own source. Verified by
deliberately introducing a violation and watching it fail with the file and
line, then restoring.

**Because.** A citation of a deleted directory is not a weaker explanation than
one of measured behaviour -- it is not an explanation at all, and the map's own
standing triage bar already required the mechanism to be traced to source. The
evidence existed in 56 closed tickets; this moves it to where a reader of the
code will find it.

**Rejected.**
- *Retire `compare.py` with R.* Would delete the audit trail behind every cause
  the map decided, and the frozen `output_r/` baseline still exists.
- *Exempt `compare.py` silently, repointing only its path citations.* Leaves a
  reader unable to tell whether the module is current guidance -- the exact
  defect being fixed everywhere else.
- *Rewrite the `docs/archive/` documents rather than freezing them.* They are
  records **of** the migration and R-framed by construction; rewriting them
  would destroy the thing they are.
- *Find-and-replace.* Ruled out by [round
  4](51-triage-patient-cleaned-residual-4.md)'s precedent: `_validate_dates`
  claimed its future-date guard "matches R pipeline behavior" when R had no
  such guard, so a stale citation can be wrong about R and each site needed
  reading.

**Deliberately not changed: two published log values that name R.**
`src/a4d/extract/product.py` emits `function_name="read_product_data_step1"`,
the only one of twenty `function_name` values that is not the emitting Python
function, and three sites emit `script="script1"`/`"script3"`. These are **data
in the BigQuery `logs` table**, not comments, so changing them changes published
output and could break a consumer. They are a real inconsistency and they are
the residue of this ticket -- recorded rather than silently fixed, for the user
to decide.

**Evidence.** Executed. Population measured by grep before any edit (353/88/65,
by file), re-measured after. Full suite **1,080 passed, 1 skipped, 86%
coverage** -- 980 before, plus the guard's 100 parametrised cases; no existing
test changed behaviour. `ruff check`, `ruff format --check` and `ty check src/`
all clean. The guard was proven non-vacuous by introducing a violation.

**Tense.** All of the above is current state, committed.
