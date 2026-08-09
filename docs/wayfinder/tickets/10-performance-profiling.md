---
id: 10
title: Profile the combined pipeline's performance against the R baseline before promoting to dev
labels: [wayfinder:task]
status: open
blocked_by: [3]
assignee: null
claimed_at: null
resolution: null
evidence: null
closed_by: null
spawned_by: null
---

## Premise

Rests on [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md),
closed: `migration` now carries the combined patient + product pipeline, plus
everything else landed in that merge (the two logging-parity fixes, the
product-only coverage gate). The user's standing understanding is that the
Python pipeline is much faster than the archived R pipeline, but that
comparison predates this merge's additions and the product arm's own cost —
nobody has re-profiled since. This is a fresh concern raised mid-[ticket
5](05-production-verification-run.md) session, not derived from any ticket's
resolution.

Not blocked on [ticket 5](05-production-verification-run.md) itself — profiling
can run against local or production-scale data independent of that ticket's
verification outcome — but both are gating promotion (ticket 6), and ticket 5's
production run may end up a convenient source of real timing data if it's
still fresh when this ticket is worked.

## Question

Define what "profile before going live" means concretely: which pipeline
stages to measure (extract/clean/tables per arm, or end-to-end), what data
volume to profile against (local fixtures vs. a full production-scale run),
what the R baseline comparison point is (the archived R pipeline's own past
timings, if any were recorded, or a fresh run of `r-archive/` for comparison),
and what regression or absolute-time threshold would block promotion to `dev`.
Then execute the profiling and record the result.
