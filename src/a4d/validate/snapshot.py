"""Golden-master snapshot digest over a real pipeline run.

The pipeline's own correctness against source truth is covered by
``source_vs_output_*``. This module answers a different question: did the
output move since last time, and was it the code or the workbook that moved
it?

A run's whole output is reduced to a **digest** -- one row per
(source, stage, column) carrying statistics and a one-way fingerprint, never
a value. Diffing two digests separates the only two things that can have
happened:

* the workbook's own MD5 is unchanged, so a moved column can only be the code
  -- a possible regression, and the reason this check exists;
* the MD5 changed, so the workbook itself was edited and the output was
  *supposed* to move.

The digest is written beside the tracker corpus rather than committed, so no
per-clinic shape is published; see the planning record kept outside this
regression-tests.md`` for that decision.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path

import polars as pl
from loguru import logger

from a4d.tables.metadata import md5_file

#: Output subdirectory -> stage name, in the order a reader wants them.
STAGE_DIRS: dict[str, str] = {
    "patient_data_raw": "patient_raw",
    "patient_data_cleaned": "patient_cleaned",
    "product_data_raw": "product_raw",
    "product_data_cleaned": "product_cleaned",
    "tables": "tables",
}

#: Suffixes the pipeline appends to a tracker stem when writing a stage.
_STAGE_SUFFIXES = (
    "_patient_raw",
    "_patient_cleaned",
    "_product_raw",
    "_product_cleaned",
)

DIGEST_COLUMNS = (
    "source",
    "stage",
    "column",
    "dtype",
    "n_rows",
    "n_null",
    "n_distinct",
    "value_hash",
    "input_md5",
)

_DIGEST_SCHEMA = {
    "source": pl.Utf8,
    "stage": pl.Utf8,
    "column": pl.Utf8,
    "dtype": pl.Utf8,
    "n_rows": pl.Int64,
    "n_null": pl.Int64,
    "n_distinct": pl.Int64,
    "value_hash": pl.Utf8,
    "input_md5": pl.Utf8,
}

#: Statistics compared field-by-field when a key exists on both sides.
_COMPARED_FIELDS = ("dtype", "n_rows", "n_null", "n_distinct", "value_hash")

_NULL_MARKER = "\x00"
_CELL_SEPARATOR = "\x1f"
_FIELD_SEPARATOR = "\x1e"

#: Columns the run stamps rather than reads out of a workbook. Their contents
#: differ on every run by design, so they are digested for shape and type but
#: never fingerprinted -- otherwise every table moves on every run.
VOLATILE_COLUMNS = frozenset({"timestamp"})

#: Stands in for a volatile column's fingerprint, so the exclusion is visible
#: in the digest rather than silent.
RUNTIME_STAMP = "(run-time)"

#: Pseudo-column carrying the row-alignment fingerprint for a whole frame.
ROW_ALIGNMENT = "(row alignment)"

#: Published tables left out of the digest entirely.
#:
#: ``table_logs`` is the record of what the pipeline *did*, for a developer --
#: not data read out of a workbook. Three of its fields are per-run by
#: construction: ``log_file`` embeds the run's wall-clock time and process id,
#: ``process_name`` is whichever worker happened to take a tracker, and some
#: messages count the run's own artifacts ("Found 520 log files to process").
#:
#: These cannot be handled as volatile *columns*, because ``message`` is also a
#: column of ``table_findings``, where it is stable and load-bearing -- excluding
#: the name globally would silently blind the findings check, which is one of the
#: things this digest most needs to watch.
EXCLUDED_TABLES = frozenset({"table_logs"})


def _hash(payload: str) -> str:
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def column_fingerprint(series: pl.Series) -> str:
    """Hash a column's values as a multiset, in a form no value survives.

    Row **order is deliberately not part of the hash**. The published artifacts
    are BigQuery tables, which are unordered sets of rows, and the aggregated
    tables are assembled from parallel workers that finish in a different order
    on every run -- an order-sensitive hash reports a regression on every table
    after every run, which is how this check first failed in real use. What is
    still caught is any change to the values themselves: a different multiset
    hashes differently.

    Nulls hash distinctly from the empty string, which matters throughout this
    pipeline: null means nothing was recorded, while a sentinel or an empty
    cell means something was and could not be used.

    The digest is stored on the tracker drive and never committed, but the
    fingerprint is one-way regardless -- a leaked digest reveals no readings.
    """
    values = series.cast(pl.Utf8, strict=False).fill_null(_NULL_MARKER).sort()
    return _hash(_CELL_SEPARATOR.join(values.to_list()))


def row_alignment_fingerprint(df: pl.DataFrame) -> str:
    """Hash whole rows as a multiset, so columns cannot drift apart unnoticed.

    Per-column hashes are blind to one column shifting against the others --
    a mis-keyed join keeps every column's values and pairs them wrongly, and
    every column hash still matches. Hashing each row's fields together, then
    hashing the sorted row hashes, catches that while staying insensitive to
    the order the rows arrive in.

    Volatile columns are left out, or the row hash would move on every run for
    the same reason their own would.
    """
    columns = [c for c in df.columns if c not in VOLATILE_COLUMNS]
    if not columns or df.height == 0:
        return _hash("")

    joined = df.select(
        pl.concat_str(
            [pl.col(c).cast(pl.Utf8, strict=False).fill_null(_NULL_MARKER) for c in columns],
            separator=_FIELD_SEPARATOR,
        ).alias("row")
    )["row"]
    row_hashes = sorted(_hash(r) for r in joined.to_list())
    return _hash(_CELL_SEPARATOR.join(row_hashes))


def _tracker_index(data_root: Path) -> dict[str, Path]:
    """Map every tracker stem under ``data_root`` to its path.

    Output for a tracker the corpus no longer holds still digests; its
    ``input_md5`` is null, which the diff reads as "cannot tell whether the
    workbook moved".
    """
    index: dict[str, Path] = {}
    for path in sorted(data_root.rglob("*.xlsx")):
        if path.name.startswith("~$"):  # Excel lock file
            continue
        index.setdefault(path.stem, path)
    return index


def _source_stem(parquet_stem: str) -> str:
    """Recover the tracker stem from a stage parquet's filename."""
    for suffix in _STAGE_SUFFIXES:
        if parquet_stem.endswith(suffix):
            return parquet_stem[: -len(suffix)]
    return parquet_stem


def _digest_frame(df: pl.DataFrame, source: str, stage: str, input_md5: str | None) -> list[dict]:
    rows = []
    for name in df.columns:
        series = df[name]
        volatile = name in VOLATILE_COLUMNS
        rows.append(
            {
                "source": source,
                "stage": stage,
                "column": name,
                "dtype": str(series.dtype),
                "n_rows": df.height,
                "n_null": series.null_count(),
                # A volatile column's distinct count is as run-dependent as its
                # values; its shape and type are still worth checking.
                "n_distinct": None if volatile else series.drop_nulls().n_unique(),
                "value_hash": RUNTIME_STAMP if volatile else column_fingerprint(series),
                "input_md5": input_md5,
            }
        )

    rows.append(
        {
            "source": source,
            "stage": stage,
            "column": ROW_ALIGNMENT,
            "dtype": "-",
            "n_rows": df.height,
            "n_null": 0,
            "n_distinct": None,
            "value_hash": row_alignment_fingerprint(df),
            "input_md5": input_md5,
        }
    )
    return rows


def build_digest(output_root: Path, data_root: Path) -> pl.DataFrame:
    """Reduce a completed run's output to its digest.

    Args:
        output_root: The run's output directory (the one holding
            ``patient_data_cleaned/``, ``tables/`` and the rest).
        data_root: Where the trackers live, read only to fingerprint them.

    Returns:
        One row per (source, stage, column), sorted so two digests of the same
        run are byte-identical.
    """
    trackers = _tracker_index(data_root) if data_root.exists() else {}
    rows: list[dict] = []
    skipped: list[str] = []

    for stage_dir, stage in STAGE_DIRS.items():
        directory = output_root / stage_dir
        if not directory.is_dir():
            continue
        for parquet in sorted(directory.glob("*.parquet")):
            source = _source_stem(parquet.stem)
            if stage == "tables" and source in EXCLUDED_TABLES:
                skipped.append(source)
                continue
            tracker = trackers.get(source)
            input_md5 = md5_file(tracker) if tracker is not None else None
            rows.extend(_digest_frame(pl.read_parquet(parquet), source, stage, input_md5))

    if skipped:
        logger.info(f"Snapshot digest excludes {', '.join(sorted(set(skipped)))} (run-time record)")

    if not rows:
        return pl.DataFrame(schema=_DIGEST_SCHEMA).select(DIGEST_COLUMNS)
    return (
        pl.DataFrame(rows, schema=_DIGEST_SCHEMA)
        .select(DIGEST_COLUMNS)
        .sort(["source", "stage", "column"])
    )


@dataclass(frozen=True)
class DigestKey:
    """One digested column, named the way the report names it."""

    source: str
    stage: str
    column: str

    def __str__(self) -> str:
        return f"{self.source} [{self.stage}] {self.column}"


@dataclass(frozen=True)
class ChangedColumn:
    """A column present on both sides whose digest moved."""

    key: DigestKey
    fields: list[str]
    before: dict
    after: dict
    input_changed: bool

    @property
    def source(self) -> str:
        return self.key.source

    @property
    def column(self) -> str:
        return self.key.column


@dataclass
class SnapshotDiff:
    """What moved between two digests, split by what could have moved it."""

    changed: list[ChangedColumn] = field(default_factory=list)
    added: list[DigestKey] = field(default_factory=list)
    removed: list[DigestKey] = field(default_factory=list)
    #: Sources whose workbook MD5 differs between the two digests.
    edited_sources: list[str] = field(default_factory=list)
    #: Sources whose output moved with an unchanged workbook.
    regression_sources: list[str] = field(default_factory=list)

    @property
    def moved(self) -> bool:
        return bool(self.changed or self.added or self.removed or self.edited_sources)


def _keyed(digest: pl.DataFrame) -> dict[DigestKey, dict]:
    return {DigestKey(row["source"], row["stage"], row["column"]): row for row in digest.to_dicts()}


def _md5_by_source(digest: pl.DataFrame) -> dict[str, str | None]:
    if digest.height == 0:
        return {}
    first = digest.group_by("source").first()
    return dict(zip(first["source"], first["input_md5"], strict=True))


def diff_digests(baseline: pl.DataFrame, current: pl.DataFrame) -> SnapshotDiff:
    """Compare two digests and classify every movement by its possible cause."""
    before, after = _keyed(baseline), _keyed(current)
    before_md5, after_md5 = _md5_by_source(baseline), _md5_by_source(current)

    edited = sorted(
        source
        for source in set(before_md5) & set(after_md5)
        if before_md5[source] != after_md5[source]
    )

    changed: list[ChangedColumn] = []
    for key in sorted(set(before) & set(after), key=lambda k: (k.source, k.stage, k.column)):
        fields = [f for f in _COMPARED_FIELDS if before[key][f] != after[key][f]]
        if fields:
            changed.append(
                ChangedColumn(
                    key=key,
                    fields=fields,
                    before=before[key],
                    after=after[key],
                    input_changed=key.source in edited,
                )
            )

    def sort_key(k: DigestKey) -> tuple[str, str, str]:
        return (k.source, k.stage, k.column)

    return SnapshotDiff(
        changed=changed,
        added=sorted(set(after) - set(before), key=sort_key),
        removed=sorted(set(before) - set(after), key=sort_key),
        edited_sources=edited,
        regression_sources=sorted({c.source for c in changed if not c.input_changed}),
    )


def _describe(change: ChangedColumn) -> str:
    parts = []
    for f in change.fields:
        if f == "value_hash":
            parts.append("values changed")
        else:
            parts.append(f"{f} {change.before[f]} -> {change.after[f]}")
    return f"    {change.key}: {', '.join(parts)}"


def format_diff(diff: SnapshotDiff, max_lines_per_section: int = 40) -> str:
    """Render a diff for a human, alarm first.

    Movement under an unchanged workbook leads, because it is the only kind
    that can be a regression. Movement under an edited workbook follows: it is
    expected after a corpus download, and is shown in full because seeing what
    a workbook fix did is the other reason to run this.
    """
    if not diff.moved:
        return "Snapshot: no movement against the baseline."

    lines: list[str] = []

    regressions = [c for c in diff.changed if not c.input_changed]
    if regressions:
        lines.append(
            f"POSSIBLE REGRESSION -- same workbook, different output "
            f"({len(regressions)} columns across {len(diff.regression_sources)} trackers):"
        )
        lines.extend(_describe(c) for c in regressions[:max_lines_per_section])
        if len(regressions) > max_lines_per_section:
            lines.append(f"    ... and {len(regressions) - max_lines_per_section} more")
        lines.append("")

    edits = [c for c in diff.changed if c.input_changed]
    if diff.edited_sources:
        lines.append(
            f"EXPECTED -- workbook edited since the baseline "
            f"({len(diff.edited_sources)} trackers, {len(edits)} columns moved):"
        )
        lines.extend(f"    {source}" for source in diff.edited_sources)
        lines.extend(_describe(c) for c in edits[:max_lines_per_section])
        if len(edits) > max_lines_per_section:
            lines.append(f"    ... and {len(edits) - max_lines_per_section} more")
        lines.append("")

    for label, keys in (("NEW", diff.added), ("GONE", diff.removed)):
        if keys:
            lines.append(f"{label} ({len(keys)}):")
            lines.extend(f"    {k}" for k in keys[:max_lines_per_section])
            if len(keys) > max_lines_per_section:
                lines.append(f"    ... and {len(keys) - max_lines_per_section} more")
            lines.append("")

    return "\n".join(lines).rstrip()
