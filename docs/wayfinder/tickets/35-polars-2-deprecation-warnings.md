---
id: 35
title: Resolve the Polars 2.0 deprecation warnings — decide the behaviour each one is asking about
labels: [wayfinder:task]
status: open
blocked_by: []
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: 33
---

## Premise

Rests on [Fix red CI — ruff format --check fails on Python snippets inside
markdown docs](33-fix-red-ci-ruff-format-markdown.md), closed: CI is green
again on `migration` (run `31644262255`, 2026-08-12), so the test suite runs
end to end on CI for the first time since 2026-08-09 and its output is
readable again.

Also rests on [Audit and update all dependencies and library
versions](13-dependency-audit.md), closed: dependencies were moved to
current latest, which is what surfaced these warnings — they are
forward-looking (Polars **2.0** behaviour), not breakage in the pinned
version.

## Question

`pytest -m "not slow and not integration"` emits **17 warnings**, all
`DeprecationWarning` from Polars, from exactly **three** source sites.
Each is a real behavioural decision, not a silencing job — resolve them per
the map's **triage means deciding, not labelling** bar.

**1. `empty_as_null` on `str.split` — two sites, same call shape:**
- `src/a4d/clean/product.py:215` — `pl.col("product").str.split("; ")` then
  `.explode("product")`, in `_split_multi_product_cells` (R step 2.1)
- `src/a4d/validate/source_vs_output_product.py:38` — the same split, in the
  source-vs-output validator that must mirror the cleaning step

  > In Polars 2.0, the default behavior for `empty_as_null` will change to
  > `False`. To keep the current behavior, explicitly set
  > `empty_as_null=True`.

  The real question: when a product cell is `"Insulin; "` or `"; Lancets"`,
  today's implicit `empty_as_null=True` turns the empty fragment into
  `null`; under 2.0 it becomes an empty string `""` and survives `explode`
  as a phantom product row. **Decide which is correct against real tracker
  data** (do such trailing/leading separators actually occur in the 248-file
  set?), then set the flag explicitly to that answer rather than
  reflexively pinning today's behaviour. Note the two sites must stay in
  lockstep — the validator exists to check the cleaning step, so a silent
  divergence between them would make the validator lie.

**2. String -> Date cast — one site:**
- `src/a4d/clean/converters.py:182` — the `pl.lit(error_value).cast(target_type)`
  branch in `safe_convert_column`, where `error_value` is the
  `"9999-09-09"` date sentinel string and `target_type` is `pl.Date`

  > Casting from String to Date is deprecated and will be removed in Polars
  > 2.0. Use `str.to_date()` instead.

  Mechanical in principle (`pl.lit(error_value).str.to_date()`), but check
  the failure semantics match: `cast(strict=False)` yields null on an
  unparseable string where `str.to_date()` raises by default. The sentinel
  is a known-good constant so it should be equivalent, but confirm rather
  than assume — this is the sentinel-assignment path for *every* failed date
  conversion in the patient pipeline.

**Verify by re-running the suite and confirming a 0-warning run**, and (for
site 1, if the decision changes behaviour) by a real-data pipeline re-run
plus `just compare-outputs` showing no unintended movement — the cleaned
product output is currently at 23,043 cell divergences and any change here
would show up there.

Consider also whether the suite should run with `-W error` (or
`filterwarnings = ["error"]` in `pyproject.toml`) once clean, so the next
deprecation is caught at introduction rather than accumulating unnoticed —
that is the same class of drift [ticket
34](34-local-ci-parity-guard.md) is about.

## Standing bar (applies to this ticket)

Per the map's **triage means deciding, not labelling** preference: pinning
current behaviour to silence a warning is only a valid resolution if
current behaviour is confirmed correct. Say what was checked.
