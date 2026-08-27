"""Derive the finding taxonomy's inventory from the source tree.

Every ``report_finding`` call site in ``src/a4d``, with the code it emits, the
category that code carries, the function it sits in, and the condition that
governs it -- joined against how often the code actually fired on a real run.

Written for ticket 70, which audits the taxonomy from the defect rather than
from the code. The list is derived rather than written down because a
hand-kept copy drifts the first time a call site moves; the same reason
``tests/test_finding_taxonomy_guard.py`` walks the AST instead of listing
emitters.

Usage::

    uv run python scripts/finding_inventory.py
    uv run python scripts/finding_inventory.py --findings path/to/table_findings.parquet
    uv run python scripts/finding_inventory.py --format csv
"""

from __future__ import annotations

import argparse
import ast
import csv
import sys
from dataclasses import dataclass, fields
from pathlib import Path

import polars as pl

from a4d.findings import FINDING_CATEGORY, FINDING_GLOSSARY, FINDING_SCOPE

SRC = Path(__file__).resolve().parent.parent / "src" / "a4d"


@dataclass(frozen=True)
class CallSite:
    """One ``report_finding`` call, as the source states it."""

    module: str
    line: int
    function: str
    error_code: str
    category: str
    condition: str
    stage: str


def _enclosing_condition(path: list[ast.AST]) -> str:
    """Source of the nearest ``if``/``for`` guarding this call, or ``always``.

    Approximate on purpose: it says what the reader would look at first when
    asking "when does this fire", not a proof of reachability.
    """
    for node in reversed(path):
        if isinstance(node, ast.If):
            return ast.unparse(node.test)
        if isinstance(node, ast.For):
            return f"for {ast.unparse(node.target)} in {ast.unparse(node.iter)}"
        if isinstance(node, ast.ExceptHandler):
            return f"except {ast.unparse(node.type) if node.type else 'Exception'}"
    return "always"


def _literal(node: ast.AST | None) -> str:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return "" if node is None else f"<{ast.unparse(node)}>"


def _walk_calls(node: ast.AST, module: Path, stack: list[ast.AST], sites: list[CallSite]) -> None:
    """Depth-first walk keeping the path to the current node.

    The path is what turns a bare call into a located one: the enclosing
    function gives the emitter name, and the nearest ``if``/``for`` gives the
    condition the reader wants to see beside the code.
    """
    stack.append(node)
    if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "report_finding":
        kwargs = {kw.arg: kw.value for kw in node.keywords if kw.arg}
        code = _literal(kwargs.get("error_code"))
        function = next(
            (
                f.name
                for f in reversed(stack)
                if isinstance(f, ast.FunctionDef | ast.AsyncFunctionDef)
            ),
            "<module>",
        )
        sites.append(
            CallSite(
                module=str(module.relative_to(SRC.parent.parent)),
                line=node.lineno,
                function=function,
                error_code=code,
                category=FINDING_CATEGORY.get(code, "<unknown>"),  # type: ignore[arg-type]
                condition=_enclosing_condition(stack),
                stage=_literal(kwargs.get("stage")) or "clean (default)",
            )
        )
    for child in ast.iter_child_nodes(node):
        _walk_calls(child, module, stack, sites)
    stack.pop()


def collect_call_sites(root: Path = SRC) -> list[CallSite]:
    sites: list[CallSite] = []
    for py in sorted(root.rglob("*.py")):
        _walk_calls(ast.parse(py.read_text(), filename=str(py)), py, [], sites)
    return sites


@dataclass(frozen=True)
class SilentPath:
    """A place that discards or replaces a value, in a function that reports nothing.

    "Discards" is read structurally: writing an ``error_val_*`` sentinel, an
    ``otherwise(...)`` fallback, or a ``drop``/``filter`` that removes rows or
    columns. Whether the silence is *correct* is a judgement the audit makes
    per site; this only finds the candidates so none is missed by eye.
    """

    module: str
    line: int
    function: str
    kind: str
    lossy: bool
    source: str


_DISCARD_CALLS = frozenset({"drop", "drop_nulls", "filter", "remove", "otherwise", "exclude"})


def _is_lossy(node: ast.Call, kind: str) -> bool:
    """Does this call actually lose a value, or only look like it?

    ``otherwise(pl.col(x))`` leaves the value alone -- it is the branch that
    says "everything else is fine" -- while ``otherwise(pl.lit("Undefined"))``
    replaces it. ``drop_nulls`` on a local Series feeding a calculation loses
    nothing published. Without this split the survey is 86 sites of which most
    are noise, and the real ones do not stand out.
    """
    if kind == "otherwise":
        if not node.args:
            return True
        arg = ast.unparse(node.args[0])
        return not (arg.startswith("pl.col(") and "lit(" not in arg)
    if kind == "drop_nulls":
        return False
    return True


def collect_silent_paths(root: Path = SRC) -> list[SilentPath]:
    paths: list[SilentPath] = []
    for py in sorted(root.rglob("*.py")):
        # compare.py is the retired R-comparison tool, kept as history: it reads
        # sentinels rather than writing them, and reports nothing by design.
        if py.name == "compare.py":
            continue
        tree = ast.parse(py.read_text(), filename=str(py))
        for fn in ast.walk(tree):
            if not isinstance(fn, ast.FunctionDef | ast.AsyncFunctionDef):
                continue
            emits = any(
                isinstance(n, ast.Call) and getattr(n.func, "id", None) == "report_finding"
                for n in ast.walk(fn)
            )
            if emits:
                continue
            for node in ast.walk(fn):
                kind = ""
                lossy = True
                if (
                    isinstance(node, ast.Attribute)
                    and node.attr.startswith("error_val_")
                    and getattr(node.value, "id", None) == "settings"
                ):
                    kind = "sentinel"
                elif (
                    isinstance(node, ast.Call) and getattr(node.func, "attr", "") in _DISCARD_CALLS
                ):
                    kind = getattr(node.func, "attr", "")
                    lossy = _is_lossy(node, kind)
                if not kind:
                    continue
                paths.append(
                    SilentPath(
                        module=str(py.relative_to(SRC.parent.parent)),
                        line=node.lineno,
                        function=fn.name,
                        kind=kind,
                        lossy=lossy,
                        source=ast.unparse(node)[:110],
                    )
                )
    return paths


def run_counts(findings: Path) -> dict[str, tuple[int, int]]:
    """``error_code -> (findings, trackers)`` from a real run's table."""
    if not findings.exists():
        return {}
    frame = (
        pl.scan_parquet(findings)
        .group_by("error_code")
        .agg(pl.len().alias("n"), pl.col("file_name").n_unique().alias("trackers"))
        .collect()
    )
    return {row["error_code"]: (row["n"], row["trackers"]) for row in frame.to_dicts()}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--findings",
        type=Path,
        default=Path("output/tables/table_findings.parquet"),
        help="a run's findings table, to join measured counts onto each code",
    )
    parser.add_argument("--format", choices=("text", "csv"), default="text")
    parser.add_argument(
        "--silent",
        action="store_true",
        help="list discard/sentinel sites in functions that emit no finding",
    )
    args = parser.parse_args()

    if args.silent:
        silent = [p for p in collect_silent_paths() if p.lossy]
        by_fn: dict[tuple[str, str], list[SilentPath]] = {}
        for path in silent:
            by_fn.setdefault((path.module, path.function), []).append(path)
        print(
            f"{len(silent)} discard/sentinel sites in {len(by_fn)} functions that report nothing\n"
        )
        for (module, function), group in sorted(by_fn.items()):
            kinds = ", ".join(sorted({p.kind for p in group}))
            print(f"{module}  {function}()  [{kinds}]")
            for path in group:
                print(f"    :{path.line}  {path.kind}: {path.source}")
            print()
        return 0

    sites = collect_call_sites()
    counts = run_counts(args.findings)
    by_code: dict[str, list[CallSite]] = {}
    for site in sites:
        by_code.setdefault(site.error_code, []).append(site)

    if args.format == "csv":
        writer = csv.writer(sys.stdout)
        writer.writerow([f.name for f in fields(CallSite)] + ["run_findings", "run_trackers"])
        for site in sites:
            n, trackers = counts.get(site.error_code, (0, 0))
            writer.writerow([getattr(site, f.name) for f in fields(CallSite)] + [n, trackers])
        return 0

    print(f"{len(sites)} report_finding call sites -> {len(by_code)} codes")
    print(f"{len(FINDING_CATEGORY)} codes declared in ErrorCode\n")
    for code in sorted(by_code, key=lambda c: -counts.get(c, (0, 0))[0]):
        n, trackers = counts.get(code, (0, 0))
        measured = f"{n:>6,} findings / {trackers:>3} trackers" if counts else "not measured"
        scope = FINDING_SCOPE.get(code, "<unknown>")
        print(f"{code}  [{FINDING_CATEGORY.get(code, '<unknown>')}]  <{scope}>  {measured}")
        print(f"    glossary: {FINDING_GLOSSARY.get(code, '<none>')}")  # type: ignore[arg-type]
        for site in by_code[code]:
            print(f"    {site.module}:{site.line} {site.function}()  stage={site.stage}")
            print(f"        when: {site.condition}")
        print()

    silent = sorted(set(FINDING_CATEGORY) - set(by_code))
    if silent:
        print(f"Codes with no call site ({len(silent)}): {', '.join(silent)}")
    never_fired = sorted(c for c in by_code if counts and c not in counts)
    if never_fired:
        print(f"Codes that never fired on this run ({len(never_fired)}): {', '.join(never_fired)}")
    orphan = sorted(set(counts) - set(FINDING_CATEGORY))
    if orphan:
        print(f"Codes in the run but not in the taxonomy ({len(orphan)}): {', '.join(orphan)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
