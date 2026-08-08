---
id: 0
title: Close out the R-to-Python migration
labels: [wayfinder:map]
status: open
---

## Destination

`product-pipeline` (PR #6) merged into `migration` with conflicts resolved; the
combined pipeline (patient + product + state management) run for real against
the GCP production bucket, with output landed in BigQuery; every Python/R
difference documented and explicitly decided; CI green; and `migration` merged
into `dev` (PR #2). This prevents promoting a merge that looks clean but was
never exercised as a whole, and prevents documenting or promoting based on
claims ("the intern says it works") rather than verified fact — the migration
is large enough, and detail-sensitive enough, that things get missed unless
checked cell-by-cell.

## The tickets

<!-- graph:start -->
```mermaid
flowchart TD
  subgraph FRONTIER["Frontier · 2"]
    direction TB
    T1["<b>1</b> · grilling<br/>Does product-pipeline's<br/>test suite meet the same<br/>cell-by-cell rigor as<br/>patient's?"]
    T2["<b>2</b> · grilling<br/>Retire the PDF/notebook<br/>analysis docs for an<br/>automated, script-based<br/>report"]
  end
  subgraph BLOCKED["Blocked · 4"]
    direction TB
    T3["<b>3</b> · task<br/>Merge product-pipeline (PR<br/>#6) into migration"]
    T4["<b>4</b> · task<br/>Diagnose and fix why CI is<br/>red at migration HEAD"]
    T5["<b>5</b> · task<br/>Define and execute the<br/>real GCP production<br/>verification run"]
    T6["<b>6</b> · task<br/>Promote migration into dev<br/>via PR #2"]
  end

  T1 --> T3
  T1 --> T6
  T2 --> T3
  T2 --> T6
  T3 --> T4
  T3 --> T5
  T3 --> T6
  T4 --> T5
  T4 --> T6
  T5 --> T6

  classDef frontier fill:#1f6feb,stroke:#0b3d91,stroke-width:3px,color:#ffffff
  class T1,T2 frontier
  classDef blocked fill:#6e7781,stroke:#424a53,stroke-width:1px,color:#ffffff
  class T3,T4,T5,T6 blocked
```
<!-- graph:end -->

## Notes

- Domain: A4D medical tracker data pipeline, R-to-Python migration. See
  [CLAUDE.md](../../CLAUDE.md) and [docs/CLAUDE.md](../CLAUDE.md) for the
  codebase map, and [MIGRATION_GUIDE.md](../migration/MIGRATION_GUIDE.md) for
  the migration's own history (note: the copy on `migration` is stale relative
  to `product-pipeline`'s copy, which claims Phases 0-9 complete — that claim
  is unverified, which is exactly what this map exists to check).
- Standing preference: no notebooks for analysis, ever — write scripts.
  Analysis/reports should be automated and stay in sync with the code, not
  hand-written documents (PDFs, notebooks) that go stale.
- Standing preference: verification means cell-by-cell (shape, columns, exact
  values), not spot-checks — this is why the patient pipeline validation took
  as long as it did (174 trackers), and the product pipeline is held to the
  same bar.
- User sequencing preference: make `product-pipeline` ready first, then merge,
  then make `migration` ready, then promote. Tickets are blocked accordingly
  even where the underlying dependency is looser than the sequencing implies.
- Redraw command: `~/.claude/skills/wayfinder/scripts/render-map.sh docs/wayfinder`

## Where this map stands

Nothing is decided yet — this map was just charted. The frontier is tickets
[Does product-pipeline's test suite meet the same cell-by-cell rigor as
patient's?](tickets/01-product-pipeline-test-rigor.md) and [Retire the
PDF/notebook analysis docs for an automated, script-based report](tickets/02-documentation-strategy.md),
both unblocked. Everything else — the merge, the CI fix, the production run,
and the promotion to `dev` — is blocked behind those two per the user's
sequencing preference.

Key facts already gathered while charting (verified via `git`/`gh`, not
assumed): PR #6 (`product-pipeline` -> `migration`) is open but
`mergeable: CONFLICTING`, with no CI runs and an unchecked test plan. PR #2
(`migration` -> `dev`) is open and mergeable, but CI has failed on `migration`
HEAD for its last 3 runs. `product-pipeline` has a real test suite (41 test
files vs. 26 on `migration`) and detailed, already-written diff documentation
in `PYTHON_IMPROVEMENTS.md` — but that documentation cites an analysis
notebook that isn't in the repo, and its two PDF reports haven't been read yet.

## Decisions so far

(none yet)

## Assumptions in force

(none yet)

## Not yet specified

- Whether the R pipeline (`r-archive/`) gets formally retired/archived-further
  once `migration` reaches `dev`/`main`, and what "official migration"
  communication or cutover steps that implies — out of this map's current
  resolution but likely to surface once the promotion ticket is close.
- Cloud Scheduler / production scheduling cutover (mentioned in the Migration
  Guide's state-management open item) — not yet sharp enough to ticket; may
  turn out to be a separate map entirely once `dev` is reached.

## Out of scope

(none yet)

### The route actually walked

Sessions top to bottom, oldest first. `spawned` and `closed` are causal — what a
decision did to the rest of the map — and are where the real structure lives.

<!-- route:start -->
```mermaid
flowchart TB
  subgraph Sopen["Not yet worked"]
    direction LR
    U1["<b>1</b><br/>Does product-pipeline's<br/>test suite meet the same<br/>cell-by-cell rigor as<br/>patient's?"]
    U2["<b>2</b><br/>Retire the PDF/notebook<br/>analysis docs for an<br/>automated, script-based<br/>report"]
    U3["<b>3</b><br/>Merge product-pipeline<br/>(PR #6) into migration"]
    U4["<b>4</b><br/>Diagnose and fix why CI<br/>is red at migration HEAD"]
    U5["<b>5</b><br/>Define and execute the<br/>real GCP production<br/>verification run"]
    U6["<b>6</b><br/>Promote migration into<br/>dev via PR #2"]
  end


  U1 --->|blocked| U3
  U2 --->|blocked| U3
  U3 --->|blocked| U4
  U3 --->|blocked| U5
  U4 --->|blocked| U5
  U1 --->|blocked| U6
  U2 --->|blocked| U6
  U3 --->|blocked| U6
  U4 --->|blocked| U6
  U5 --->|blocked| U6

  classDef tfrontier fill:#1f6feb,stroke:#0b3d91,stroke-width:3px,color:#ffffff
  class U1,U2 tfrontier
  classDef tblocked fill:#6e7781,stroke:#424a53,stroke-width:1px,color:#ffffff
  class U3,U4,U5,U6 tblocked
```
<!-- route:end -->
