---
id: 7
title: Is the product pipeline (and patient's own claimed completeness) actually complete and sound, audited against R's product logic and patient's structure?
labels: [wayfinder:research]
status: closed
blocked_by: []
assignee: session-2026-08-08
claimed_at: 2026-08-08
resolution: decided
evidence: executed
closed_by: null
spawned_by: 1
---

## Premise

Rests on [Does product-pipeline's test suite meet the same cell-by-cell rigor
as patient's?](01-product-pipeline-test-rigor.md), closed as superseded: that
session established (a) R-parity isn't the goal — Python may correctly
diverge from R, judged against the original source Excel trackers, not R's
output; (b) comparing R vs. Python output is analysis, not a pytest concern;
(c) neither product's nor patient's "done" status has actually been audited —
patient's completeness has been assumed (`docs/CLAUDE.md`: "Patient pipeline
is complete and deployed to production"), product's completeness is claimed
only in `docs/migration/MIGRATION_GUIDE.md` ("Phases 0-9 complete") and
`docs/migration/PYTHON_IMPROVEMENTS.md` ("production-ready") on the
`product-pipeline` branch, both unverified by this map so far. The user has
not looked at the product pipeline's code themselves and is relying entirely
on secondhand claims ("what the intern said").

If [Retire the PDF/notebook analysis docs for an automated, script-based
report](02-documentation-strategy.md) closes first and changes what counts as
"documented" for this project, re-check this ticket's Question 2 against that
before answering it.

## Question

Read-only code/doc/test inventory — no live pipeline runs, no output
comparison (that's explicitly out of scope here; it belongs to the later
output-validation work and to ticket 2's automated report). For **both**
the patient and product pipelines:

1. Module-for-module, does the Python implementation cover every step of the
   corresponding R logic (`r-archive/`'s `helper_patient_data.R` /
   `helper_product_data.R`), or are there gaps? Where Python deliberately
   does something R doesn't (or vice versa), is that documented anywhere, or
   only discoverable by reading the diff?
2. Does each pipeline have the same shape of test coverage — unit tests per
   cleaning/validation/transform module, integration tests across pipeline
   stages, an end-to-end test, and non-R-comparison regression tests? Produce
   a file-by-file inventory (what exists for patient, what exists for
   product, what's missing for either).
3. Is the documentation (`docs/CLAUDE.md`, `MIGRATION_GUIDE.md`,
   `PYTHON_IMPROVEMENTS.md`, module docstrings) current, or stale/aspirational
   relative to the actual code? Flag every claim that isn't backed by
   something checkable in the repo (code, tests, or a dated analysis
   artifact — not prose alone).
4. Net out: what's the concrete gap list, for product and for patient, before
   either can be called "complete"?

Out of scope for this ticket: running either pipeline, comparing real output,
or judging *why* R and Python differ — those are analysis questions for later
tickets, once this inventory establishes there's a stable pipeline to compare
in the first place.

## Resolution (decided)

Full inventory: [docs/wayfinder/research/07-pipeline-completeness-audit.md](../research/07-pipeline-completeness-audit.md).

**Decision:** Neither pipeline is actually "complete" yet, but for different
reasons, and the premise's "neither status has been audited" turns out to be
only half right:

1. **R-logic coverage is essentially complete on both sides.** Every R
   function in `helper_patient_data.R`/`script2_helper_patient_data_fix.R`
   and every R function in `helper_product_data.R`/`read_product_data.R` has
   a traceable Python counterpart, function for function, verified by
   cross-referencing R's function inventory against the Python modules. The
   one gap found is two diagnostic-only R helpers
   (`calculate_most_frequent`, `report_empty_intersections`, cross-tab
   logging, not data-shape-affecting) with no Python equivalent on
   `origin/product-pipeline`.
2. **Divergence documentation is stronger on product than patient.** Product
   module docstrings cite specific R script/step numbers and the deviation
   is explained inline (e.g. `tables/product.py:link_product_patient`).
   Patient's known divergences live only inside `test_r_validation.py`'s
   exception dicts (42 tracker-level entries, 15+ with reasons) and never
   made it into `PYTHON_IMPROVEMENTS.md`'s 3-item summary table on
   `migration` — someone reading that doc alone undercounts the known
   differences by roughly 5x.
3. **Product has real, structural test gaps**: zero integration/e2e tests
   (`tests/test_integration/` is byte-identical between branches), zero test
   references to `extract/wide_format.py` across all 41 product test files,
   no `test_tables/test_product.py`, and its only regression check against
   ground truth (`source_vs_output_product.py`) is explicitly
   group-granularity only per its own docstring.
4. **Patient's "174 trackers validated" claim has real test infrastructure
   behind it but no committed record of a passing run.** `test_r_validation.py`
   is genuine and detailed, but it's `@pytest.mark.slow`/`integration`,
   excluded from CI (`python-ci.yml` runs `-m "not slow and not
   integration"`), and gated on an external USB-drive path — no
   `VALIDATION_TRACKING.md` or equivalent artifact exists in the repo
   recording that the 174-tracker run actually passed.
5. Two documentation citations point at evidence that doesn't exist in the
   repo: `Ali_internship/residual_dig.ipynb` (cited in
   `PYTHON_IMPROVEMENTS.md` §5) and a contributor's local Windows plan path
   (cited in `source_vs_output_product.py`'s docstring).

**Because:** All of the above verified via `git diff`/`git show`/`git
ls-tree`/`rg` against `migration` and `origin/product-pipeline` — commands
logged in the research file's final section for reproducibility. Full
concrete gap lists (7 items for product, 4 for patient) are in the research
file's §4.

**Rejected:** N/A — this is a research ticket; nothing was decided that had
a rejected alternative. The assumption this ticket was meant to test
(["Assumptions in force": patient's completeness is unverified](../map.md))
is **confirmed as real**, not overturned: patient's R-logic coverage is
solid, but "complete, validated, deployed to production" is still not
backed by a committed pass artifact.

**Evidence:** executed — every claim is backed by a specific `git`/`rg`
command reproduced in the research file, not by reading prose or asserting
from memory.

**Tense:** current — describes the state of `migration` and
`origin/product-pipeline` as of 2026-08-08.

**Spawned:** none yet as fresh tickets — the concrete gap lists in the
research file's §4 are candidate `task`-type tickets for later, once the
pytest-parity ticket (8) decides which of them are in scope for "pytest
parity" specifically vs. left as follow-up work; ticketing them now would
prejudge that decision.
