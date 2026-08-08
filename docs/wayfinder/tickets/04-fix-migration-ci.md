---
id: 4
title: Diagnose and fix why CI is red at migration HEAD
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

Depends on [Merge product-pipeline (PR #6) into migration](03-merge-product-pipeline.md)
being done first — the user wants migration-readiness work sequenced after the
merge, since the merge itself will change what's running through CI.

Facts on record: `gh run list --branch migration` shows the last 3 runs of the
"Python CI" workflow all failed, including the current tip `faa3c28`
(2026-04-01 and later). PR #2 (`migration` -> `dev`) is `mergeable: MERGEABLE`
but shows the same failing "test" check.

## Question

Find out why CI fails at `migration` HEAD (post-merge) and fix it — is this a
transient environment issue, a real test failure, a lint/type-check break, or
something the merge itself needs to resolve?
