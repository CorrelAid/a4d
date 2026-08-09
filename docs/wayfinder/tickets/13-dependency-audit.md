---
id: 13
title: Audit and update all dependencies and library versions before rollout
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

Rests on the same destination redraw as [ticket 10](10-performance-profiling.md),
[ticket 11](11-cli-ux-observability.md) and [ticket 12](12-retire-r-workspace.md):
the user confirmed rollout readiness covers more than merge/verify/promote,
and dependency hygiene is part of that bar.

Needs [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md)
closed (it is) so there's one `pyproject.toml`/`uv.lock` to audit, not two
branches' worth.

## Question

Audit every dependency in `pyproject.toml`/`uv.lock` (and the `Dockerfile`'s
base image, `python:3.14-slim`) against current upstream versions: what's
outdated, what has known security advisories, what's safe to bump now versus
what needs a deprecation/breaking-change check first. Update what's safe,
record what's deliberately deferred and why (e.g. a major version needing
migration work of its own).

**Sequencing note**: this should land before [ticket
10](10-performance-profiling.md)'s profiling run, not after — profiling
against a dependency set that's about to change makes the numbers stale
immediately. Ticket 10 has been wired `blocked_by: [3, 13]` to reflect this.
