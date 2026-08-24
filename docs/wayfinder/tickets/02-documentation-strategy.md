---
id: 2
title: Retire the PDF/notebook analysis docs for an automated, script-based report
labels: [wayfinder:grilling]
status: closed
blocked_by: [3]
assignee: session-2026-08-09f
claimed_at: 2026-08-09
resolution: decided
evidence: judgement
closed_by: null
spawned_by: null
---

## Premise

Rests on [Does product-pipeline's test suite meet the same cell-by-cell rigor
as patient's?](01-product-pipeline-test-rigor.md), closed as superseded: that
session decided R-vs-Python output comparison is an analysis activity, not a
pytest concern, and that this ticket is where it belongs.

**Now blocked on** [Merge product-pipeline (PR #6) into
migration](03-merge-product-pipeline.md) — the user corrected the original
sequencing here: this ticket's comparison script only makes sense to build
once patient and product live on one branch, not before, and isn't part of
what makes the merge itself trustworthy (tests green + implementation review
is judged sufficient for that). This ticket used to block the merge; now the
merge blocks this ticket instead. It also decided the
comparison's goal is not R-parity — Python may correctly diverge from R (R can
be wrong) — so the automated report must judge divergence against the
**original source Excel trackers** (available under `a4dphase2_upload` on the
test-data drive) as ground truth, not treat R's output as automatically
correct. A report that only flags "Python != R" without being able to say
which one is right against source doesn't meet this bar.

Facts on record: `docs/archive/PYTHON_IMPROVEMENTS.md` on `product-pipeline`
cites `Ali_internship/residual_dig.ipynb` for the date-parsing analysis (section 5)
— that file does not exist anywhere in the repo's tracked tree, and never has
(`git log --all -- "*residual_dig*"` returns nothing). Two PDF reports also
ship on that branch; both have now been read in full (via
`git show origin/product-pipeline:<path>` + `pdftotext`):

- `docs/archive/dashboarding_evaluation_report_verbose_.pdf` is **unrelated
  to this map** — it's a BI-tool comparison (Looker Studio vs. Evidence/
  Metabase/Superset/Redash) for A4D's research dashboarding, a separate
  internship deliverable with nothing to do with pipeline parity. Out of this
  ticket's (and this map's) scope; not this ticket's concern.
- `docs/archive/Product pipeline parity presentation.pdf` **is** the missing
  `residual_dig.ipynb`'s output — the only surviving record of a real R-vs-
  Python divergence analysis across 189 trackers / 61,077 rows / 20 columns:
  per-column mismatch counts (`Product_entry_date`: 559, `Product_balance`:
  480, `Product_category`: 214, `Product_sheet_name`: 201,
  `Product_received_from`: 154, `Product_units_received`: 9), with the
  entry-date mismatches further broken down by cause (typo-rescue: 408,
  CE-typo: 71, sentinel-null handling: 66, off-by-one-day: 7). Since the
  notebook itself is unrecoverable, this PDF is the ground truth this
  ticket's script needs to be checked against, not just background reading.

## Question

Decide the replacement for the current PDF/notebook-cited documentation:
what should the automated report look like (what does it check — all trackers
locally, error gathering, and where it needs to fall back to the original
source Excel trackers to judge a Python/R divergence rather than trusting R's
output — and how does it regenerate), and what happens to the existing PDFs
and the dead notebook reference (delete, replace, or keep as historical
record with a pointer to the new script)? Also decide what happens to
patient's existing `test_r_validation.py` (the current hand-written
exception-dict pattern) given it's now understood to be this ticket's kind of
artifact, not a pytest one — fold into the new report, or keep separate.

**Validation requirement, per the user:** once the comparison script this
ticket designs is built, run it and check whether it reproduces the same
per-column and per-cause mismatch numbers as the parity-presentation PDF
above (189 trackers, 61,077 rows, 20 columns, the counts listed in the
Premise) — that reproduction is the check that the new script is a faithful,
trustworthy replacement before the PDF is retired. Not required to design
that validation step in detail *now* (design happens when this ticket is
worked); recorded here so it isn't lost.

User has flagged this as lower priority than the merge/CI work, so the
resolution can scope it as a follow-up ticket rather than something to build
in this session.

## Resolution

**Decision.** The R baseline for comparison is the already-frozen
`/Volumes/USB SanDisk 3.2Gen1 Media/a4d/output_r/` (dated 2025-11-14),
generated from the same still-unchanged trackers on `a4dphase2_upload` —
covering both `patient_data_{raw,cleaned}/` and `product_data_{raw,cleaned}/`
plus final tables, in the same per-tracker parquet layout the Python pipeline
produces. **No R re-run is needed**, ever, going forward.

The comparison script (`scripts/compare_outputs.py` + a `just compare-outputs`
recipe — **not** an `a4d.cli` subcommand, since it's migration-only tooling
that becomes meaningless the moment R is retired, ticket 12) is **decoupled
from pipeline execution**: it takes two existing output directories (a Python
one, an R one) and diffs them; producing a fresh Python output is a separate,
manual step the user triggers when wanted.

The diff runs as four increasingly granular layers, mirroring the structure
already used across patient's existing test suite and the now-removed
`test_r_validation.py`: (1) shape/row-count match, (2) aggregate totals
match, (3) column names and dtypes match, (4) cell-by-cell value diff. Cause
classification for flagged cell-level mismatches is a small extensible
registry (`{cause_name: classifier_fn}`), seeded only with the four causes
already known from the parity-presentation PDF for `Product_entry_date`
(typo-rescue, CE-typo, sentinel-null, off-by-one-day); anything else is
reported as an unclassified mismatch. The script's output is an **HTML
report** (chosen over PDF — no extra rendering dependency, easy to skim,
directly embeds the per-column/per-cause summary tables), the direct
successor to the old PDF format but regenerated from real data each run
rather than hand-assembled once.

Docs cleanup (done in this session, both small and fully decided):
- `docs/archive/dashboarding_evaluation_report_verbose_.pdf` deleted —
  confirmed unrelated to this map (a separate BI-tool-comparison internship
  deliverable).
- `docs/archive/Product pipeline parity presentation.pdf` **kept** — it
  holds the only surviving real numbers (per-column/per-cause mismatch
  counts) needed to validate the new script; the user was explicit it stays
  "to compare" and gets removed only once superseded, since it isn't part of
  the pipeline itself.
- `docs/archive/PYTHON_IMPROVEMENTS.md`'s dead citation to
  `Ali_internship/residual_dig.ipynb` (confirmed never committed —
  `git log --all -- "*residual_dig*"` returns nothing) fixed to point at the
  parity-presentation PDF instead, with a note that the new script supersedes
  it once built.
- `test_r_validation.py` is already fully gone from pytest (removed in the
  ticket 3/8 merge work, commit `6b9a095`) — confirmed via `git log --all`.
  Its content isn't ported wholesale: only the causes it's known to have
  captured (folded into the seeded classifier registry above) survive: the
  rest of its old exception-dict logic is superseded by the same
  investigate-and-label process the follow-up ticket below carries out.

Building the script, running it, and triaging the flagged differences
one-by-one to identify and label causes (the bulk of the real work — causes
for most columns aren't known ahead of time and can only be found by
inspecting actual flagged rows against the source trackers) is **not** done
in this session — the user confirmed this stays a follow-up ticket, per the
original scoping note above. Spawned as [ticket
15](15-build-and-run-comparison-script.md).

**Because.** R hasn't been re-run in a long time and re-running it risks
version drift from the trackers' current state; the frozen `output_r/`
sidesteps that entirely since the trackers it was generated from are
confirmed unchanged. R output can only ever be a screening filter — the
user's own point mid-session was that any real disagreement still has to be
settled against the source tracker, R or no R — so building a from-scratch
independent Excel ground-truth extractor up front is unnecessary work; the
layered-check design reuses a pattern already proven in the existing test
suite rather than inventing a new one.

**Rejected.**
- Live R execution as part of the comparison script — rejected: R is being
  retired (ticket 12), version drift risk, and the frozen baseline already
  exists and covers the same trackers.
- A from-scratch independent Excel-native extractor as the ground-truth
  comparator — rejected: real divergences require manual source-tracker
  adjudication regardless of what the bulk diff is checked against, so
  building automated Excel extraction up front duplicates work without
  removing the manual step.
- Wiring the comparison into `a4d.cli` as a subcommand — rejected: it's
  migration-only tooling with a defined end-of-life (R's retirement), not
  part of the pipeline's permanent operational surface.
- Designing the full cause taxonomy now — rejected: most causes are only
  discoverable by actually inspecting flagged differences; that
  investigation is the follow-up ticket's job, not this one's.
- PDF output for the report — rejected in favor of HTML: no extra rendering
  dependency needed, easier to generate and skim.

**Evidence.** *Executed*: confirmed `output_r/` exists on the USB drive with
patient+product data dated 2025-11-14 (`ls`); confirmed
`Ali_internship/residual_dig.ipynb` was never committed (`git log --all`);
confirmed `test_r_validation.py` was already removed in commit `6b9a095`
(`git log --all`); deleted the unrelated PDF and fixed the dead citation.
*Judgement*: the script's design (decoupling, layered-check structure,
extensible cause registry, HTML output, `scripts/` placement) is the user's
live decision this session, not derived from a prior artifact.

**Tense.** All claims above describe either current repository/drive state
(executed) or a design decision for work not yet built (the follow-up
ticket owns building and running it).
