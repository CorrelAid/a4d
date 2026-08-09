"""Command-line interface for A4D pipeline."""

import warnings
from datetime import datetime
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
import typer.core
from rich.console import Console
from rich.table import Table

from a4d.pipeline.patient import (
    discover_tracker_files,
    process_patient_tables,
    run_patient_pipeline,
)
from a4d.pipeline.product import process_product_tables, run_product_pipeline
from a4d.state import filter_unchanged_trackers, load_previous_manifest
from a4d.tables.errors import create_table_errors
from a4d.tables.logs import create_table_logs

# google-crc32c has no pre-built C wheel for Python 3.14 yet; the pure-Python
# fallback is correct, just slightly slower. Suppress the noisy runtime warning
# before any google SDK calls are made (those happen lazily inside commands).
warnings.filterwarnings(
    "ignore", message="As the c extension couldn't be imported", category=RuntimeWarning
)


class _SortedTyperGroup(typer.core.TyperGroup):
    """Lists subcommands alphabetically instead of Typer's default creation order."""

    def list_commands(self, ctx) -> list[str]:
        return sorted(super().list_commands(ctx))


app = typer.Typer(
    name="a4d",
    help="A4D medical tracker data processing pipeline",
    no_args_is_help=True,
    cls=_SortedTyperGroup,
)

# Command groups, named after the process they perform (run / create / upload /
# download), not the object they act on — `a4d run patient`, not `a4d patient run`.
# `run_app` uses invoke_without_command so bare `a4d run` (no subcommand) runs the
# full pipeline, while `a4d run patient` / `a4d run product` run a single arm.
create_app = typer.Typer(help="Rebuild tables from existing cleaned output.", cls=_SortedTyperGroup)
download_app = typer.Typer(
    help="Download pipeline input (trackers, reference data).", cls=_SortedTyperGroup
)
run_app = typer.Typer(
    help="Run the pipeline: full run by default, or a single arm.",
    invoke_without_command=True,
    cls=_SortedTyperGroup,
)
upload_app = typer.Typer(help="Upload pipeline output (tables, files).", cls=_SortedTyperGroup)

app.add_typer(create_app, name="create")
app.add_typer(download_app, name="download")
app.add_typer(run_app, name="run")
app.add_typer(upload_app, name="upload")

console = Console()


def _display_tables_summary(tables: dict[str, Path]) -> None:
    """Display summary table of created tables with record counts.

    Args:
        tables: Dictionary mapping table name to output path
    """
    if not tables:
        return

    console.print("\n[bold green]Created Tables:[/bold green]")
    tables_table = Table(title="Created Tables")
    tables_table.add_column("Table", style="cyan")
    tables_table.add_column("Path", style="green")
    tables_table.add_column("Records", justify="right", style="magenta")

    # Add patient tables first, then product, then logs/errors/clinic/metadata
    for name in [
        "static",
        "monthly",
        "annual",
        "product_data",
        "logs",
        "errors",
        "clinic_data_static",
        "tracker_metadata",
    ]:
        if name in tables:
            path = tables[name]
            try:
                record_count = f"{pl.read_parquet(path).__len__():,}"
            except Exception:
                record_count = "?"
            tables_table.add_row(name, str(path.name), record_count)

    console.print(tables_table)
    console.print()


def _render_pipeline_header(
    data_root: str | Path,
    output_root: str | Path,
    workers: int,
    *,
    skip_tables: bool = False,
    extras: list[tuple[str, str]] | None = None,
) -> None:
    """Render the per-command header banner.

    `extras` carries the bare `run`-only fields (Project / Dataset / Drive /
    Download / Upload / Product) so run patient and run product can
    omit them. All labels are padded to a 13-character column to match the
    pre-refactor output exactly.
    """
    rows: list[tuple[str, str]] = [
        ("Data root", str(data_root)),
        ("Output root", str(output_root)),
        ("Workers", str(workers)),
    ]
    if skip_tables:
        rows.append(("Tables", "skipped"))
    if extras:
        rows.extend(extras)
    for label, value in rows:
        console.print(f"{label + ':':<13}{value}")
    console.print()


def _render_pipeline_results_summary(
    result,
    tables: dict[str, Path],
    total_errors: int,
    files_with_errors: int,
) -> None:
    """Render the 7-row Summary table used by run patient / run product."""
    summary_table = Table(title="Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Total Trackers", str(result.total_trackers))
    summary_table.add_row("Successful", str(result.successful_trackers))
    summary_table.add_row("Failed", str(result.failed_trackers))
    summary_table.add_row("Tables Created", str(len(tables)))
    summary_table.add_row("", "")
    summary_table.add_row("Data Quality Errors", f"{total_errors:,}")
    summary_table.add_row("Files with Errors", str(files_with_errors))

    console.print(summary_table)


def _resolve_tracker_files(
    file: Path | None,
    data_root_arg: Path | None,
    incremental: bool,
    output_root: Path,
) -> tuple[list[Path] | None, str]:
    """Resolve the tracker-file list for a CLI invocation.

    Returns ``(tracker_files, display_str)``. ``tracker_files`` is ``None`` when
    the orchestrator should discover trackers itself (the default
    non-incremental "process everything in data_root" path). An empty list means
    discovery + incremental filtering produced no work; the caller should
    short-circuit.

    --file always wins; --incremental + --file is a no-op (logged warning),
    matching the design that single-file is an explicit user override.
    """
    if file:
        if incremental:
            console.print("[yellow]Warning: --incremental is ignored when --file is set[/yellow]")
        return [file], f"{file} (single file)"

    from a4d.config import settings as _settings

    if data_root_arg is not None:
        files = discover_tracker_files(data_root_arg)
        if not files:
            console.print(
                f"[bold red]Error: No tracker files found in {data_root_arg}[/bold red]\n"
            )
            raise typer.Exit(1)
        display = str(data_root_arg)
    elif incremental:
        files = discover_tracker_files(_settings.data_root)
        display = str(_settings.data_root)
    else:
        # Default: orchestrator discovers everything from settings.data_root.
        return None, str(_settings.data_root)

    if incremental:
        manifest = load_previous_manifest(output_root)
        files, summary = filter_unchanged_trackers(files, manifest)
        console.print(
            f"[cyan]Incremental filter: queued {summary.queued}, "
            f"skipped {summary.skipped} unchanged "
            f"(new={summary.new}, changed={summary.changed}, "
            f"incomplete={summary.previously_incomplete})[/cyan]\n"
        )

    return files, display


def _render_combined_run_summary(patient_result, product_result) -> None:
    """Render a combined patient+product view of a full `run` execution.

    Crosses each tracker file's patient and product outcome (both ok / one
    arm failed / lost entirely) and merges both arms' per-file error counts.
    Only meaningful once both arms have actually run — silently skips
    otherwise (e.g. --skip-patient / --skip-product, or the product arm
    crashing before producing a result).
    """
    if patient_result is None or product_result is None:
        return

    patient_by_name = {tr.tracker_name: tr for tr in patient_result.tracker_results}
    product_by_name = {tr.tracker_name: tr for tr in product_result.tracker_results}
    all_names = sorted(set(patient_by_name) | set(product_by_name))

    both_ok = patient_only_failed = product_only_failed = both_failed = 0
    attention_rows: list[tuple[str, str, str]] = []
    error_counts: dict[str, int] = {}

    for name in all_names:
        p = patient_by_name.get(name)
        q = product_by_name.get(name)
        p_ok = p.success if p is not None else True
        q_ok = q.success if q is not None else True

        if p_ok and q_ok:
            both_ok += 1
        else:
            p_err = p.error if p is not None and not p_ok else None
            q_err = q.error if q is not None and not q_ok else None
            attention_rows.append((name, p_err or "-", q_err or "-"))
            if not p_ok and not q_ok:
                both_failed += 1
            elif not p_ok:
                patient_only_failed += 1
            else:
                product_only_failed += 1

        file_errors = (p.cleaning_errors if p else 0) + (q.cleaning_errors if q else 0)
        if file_errors:
            error_counts[name] = file_errors

    console.print("\n[bold blue]Combined Run Summary[/bold blue]")
    summary_table = Table()
    summary_table.add_column("Outcome", style="cyan")
    summary_table.add_column("Files", justify="right", style="green")
    summary_table.add_row("Both arms OK", str(both_ok))
    summary_table.add_row("Patient failed only", str(patient_only_failed))
    summary_table.add_row("Product failed only", str(product_only_failed))
    summary_table.add_row("Lost entirely (both arms failed)", str(both_failed))
    console.print(summary_table)

    if attention_rows:
        console.print("\n[bold yellow]Files needing attention:[/bold yellow]")
        detail_table = Table()
        detail_table.add_column("File", style="red")
        detail_table.add_column("Patient error")
        detail_table.add_column("Product error")
        for name, p_err, q_err in attention_rows:
            detail_table.add_row(name, p_err, q_err)
        console.print(detail_table)

    if error_counts:
        console.print(
            "\n[bold yellow]Top Files by Error Count (patient + product combined):[/bold yellow]"
        )
        top_table = Table()
        top_table.add_column("File", style="cyan")
        top_table.add_column("Errors", justify="right", style="magenta")
        for name, count in sorted(error_counts.items(), key=lambda kv: -kv[1])[:20]:
            top_table.add_row(name, str(count))
        console.print(top_table)


def _render_failed_trackers(
    result,
    *,
    mode: str,
    truncate: int | None = 100,
    title: str = "Failed Trackers",
    leading_newline: bool = True,
) -> None:
    """Render the failed-trackers section.

    `mode="table"` matches run patient / run product (Rich Table,
    error truncated). `mode="bullets"` matches `run` (bullet list,
    full error). `truncate` is ignored in bullets mode.
    """
    if result.failed_trackers <= 0:
        return
    prefix = "\n" if leading_newline else ""
    console.print(f"{prefix}[bold yellow]{title}:[/bold yellow]")
    if mode == "table":
        failed_table = Table()
        failed_table.add_column("File", style="red")
        failed_table.add_column("Error")
        for tr in result.tracker_results:
            if not tr.success:
                error_text = str(tr.error)
                if truncate is not None:
                    error_text = error_text[:truncate]
                failed_table.add_row(tr.tracker_file.name, error_text)
        console.print(failed_table)
    else:  # bullets
        for tr in result.tracker_results:
            if not tr.success:
                console.print(f"  • {tr.tracker_file.name}: {tr.error}")
        console.print()


@run_app.command("patient")
def run_patient_cmd(
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            help="Process specific tracker file (if not set, processes all files in data_root)",
        ),
    ] = None,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers", "-w", help="Number of parallel workers (default: A4D_MAX_WORKERS)"
        ),
    ] = None,
    skip_tables: Annotated[
        bool, typer.Option("--skip-tables", help="Skip table creation (only extract + clean)")
    ] = False,
    data_root: Annotated[
        Path | None,
        typer.Option(
            "--data-root", "-d", help="Directory containing tracker files (default: from config)"
        ),
    ] = None,
    output_root: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output directory (default: from config)")
    ] = None,
    incremental: Annotated[
        bool,
        typer.Option(
            "--incremental",
            help=(
                "Skip trackers whose MD5 + completion state match the previous "
                "run's manifest. Preserves prior outputs (clean_output disabled)."
            ),
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help=(
                "Wipe prior outputs and reprocess every tracker. Same as the "
                "default behavior; pass explicitly for self-documenting deploy "
                "commands. Overrides --incremental if both are passed."
            ),
        ),
    ] = False,
):
    """Process patient data pipeline.

    \b
    By default, output is cleaned before each run so tables reflect only the
    current run's files. With --incremental, prior outputs are preserved and
    only new/changed/previously-incomplete trackers are re-processed.
    With --force, behaves as the default (wipe + reprocess) and overrides
    --incremental if both are passed.

    Examples:
        # Process all trackers in data_root (from config)
        uv run a4d run patient

        # Process all trackers in a specific directory
        uv run a4d run patient --data-root /path/to/trackers

        # Process specific file
        uv run a4d run patient --file /path/to/tracker.xlsx

        # Parallel processing with 8 workers
        uv run a4d run patient --workers 8

        # Just extract + clean, skip tables
        uv run a4d run patient --skip-tables

        # Skip trackers whose MD5 matches the previous run's manifest
        uv run a4d run patient --incremental

        # Explicitly wipe outputs and reprocess everything
        uv run a4d run patient --force
    """
    from a4d.config import settings as _settings

    console.print("\n[bold blue]A4D Patient Pipeline[/bold blue]\n")

    if force and incremental:
        console.print("[yellow]Warning: --incremental is ignored when --force is set[/yellow]")
        incremental = False

    _output_root = output_root or _settings.output_root
    _workers = workers if workers is not None else _settings.max_workers

    tracker_files, data_root_display = _resolve_tracker_files(
        file, data_root, incremental, _output_root
    )

    if tracker_files is not None and len(tracker_files) == 0:
        console.print("[bold green]✓ No trackers need reprocessing — exiting[/bold green]\n")
        raise typer.Exit(0)

    _render_pipeline_header(data_root_display, _output_root, _workers, skip_tables=skip_tables)

    # Step 1: Extract + clean (table creation handled below for visible progress)
    console.print("[bold]Step 1/4:[/bold] Extracting and cleaning tracker files...")
    try:
        result = run_patient_pipeline(
            tracker_files=tracker_files,
            max_workers=_workers,
            output_root=output_root,
            skip_tables=True,  # tables created below with console feedback
            clean_output=force
            or not incremental,  # incremental keeps prior outputs; --force always wipes
            show_progress=True,
            console_log_level="ERROR",
        )
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]\n")
        raise typer.Exit(1) from e

    # Steps 2-4: Table and log/error creation with console feedback
    tables: dict[str, Path] = {}
    if not skip_tables and result.successful_trackers > 0:
        cleaned_dir = _output_root / "patient_data_cleaned"
        tables_dir = _output_root / "tables"
        logs_dir = _output_root / "logs"

        console.print("[bold]Step 2/4:[/bold] Creating patient tables...")
        try:
            tables = process_patient_tables(cleaned_dir, tables_dir)
        except Exception as e:
            console.print(f"[bold red]Error creating tables: {e}[/bold red]")

        if logs_dir.exists():
            console.print("[bold]Step 3/4:[/bold] Creating logs table...")
            try:
                logs_table_path = create_table_logs(logs_dir, tables_dir)
                tables["logs"] = logs_table_path
            except Exception as e:
                console.print(f"[bold red]Error creating logs table: {e}[/bold red]")

        console.print("[bold]Step 4/4:[/bold] Creating errors table...")
        try:
            all_data_errors = [e for r in result.tracker_results for e in r.data_errors]
            errors_table_path = create_table_errors(all_data_errors, tables_dir)
            tables["errors"] = errors_table_path
        except Exception as e:
            console.print(f"[bold red]Error creating errors table: {e}[/bold red]")
    elif skip_tables:
        console.print("[dim]Steps 2–3: Skipped (--skip-tables)[/dim]")
        console.print("[bold]Step 4/4:[/bold] Creating errors table...")
        try:
            tables_dir = _output_root / "tables"
            all_data_errors = [e for r in result.tracker_results for e in r.data_errors]
            errors_table_path = create_table_errors(all_data_errors, tables_dir)
            tables["errors"] = errors_table_path
        except Exception as e:
            console.print(f"[bold red]Error creating errors table: {e}[/bold red]")

    # Display results
    console.print("\n[bold]Pipeline Results[/bold]\n")

    # Calculate error statistics
    total_errors = sum(tr.cleaning_errors for tr in result.tracker_results)
    files_with_errors = sum(1 for tr in result.tracker_results if tr.cleaning_errors > 0)

    _render_pipeline_results_summary(result, tables, total_errors, files_with_errors)

    # Show error type breakdown if there are errors
    if total_errors > 0:
        console.print("\n[bold yellow]Error Type Breakdown:[/bold yellow]")

        # Aggregate error types across all trackers
        error_type_totals: dict[str, int] = {}
        for tr in result.tracker_results:
            if tr.error_breakdown:
                for error_type, count in tr.error_breakdown.items():
                    error_type_totals[error_type] = error_type_totals.get(error_type, 0) + count

        # Create frequency table
        error_type_table = Table()
        error_type_table.add_column("Error Type", style="yellow")
        error_type_table.add_column("Count", justify="right", style="red")
        error_type_table.add_column("Percentage", justify="right", style="cyan")

        # Sort by count (descending)
        sorted_error_types = sorted(error_type_totals.items(), key=lambda x: x[1], reverse=True)

        for error_type, count in sorted_error_types:
            percentage = (count / total_errors) * 100
            error_type_table.add_row(error_type, f"{count:,}", f"{percentage:.1f}%")

        console.print(error_type_table)

    _render_failed_trackers(result, mode="table")

    # Show top files with most data quality errors (if any)
    if total_errors > 0:
        console.print("\n[bold yellow]Top Files by Error Count:[/bold yellow]")
        # Sort by error count (descending) and take top 10
        files_by_errors = sorted(
            [
                (tr.tracker_file.name, tr.cleaning_errors)
                for tr in result.tracker_results
                if tr.cleaning_errors > 0
            ],
            key=lambda x: x[1],
            reverse=True,
        )[:10]

        errors_table = Table()
        errors_table.add_column("File", style="yellow")
        errors_table.add_column("Errors", justify="right", style="red")

        for filename, error_count in files_by_errors:
            errors_table.add_row(filename, f"{error_count:,}")

        console.print(errors_table)

    # Show created tables
    _display_tables_summary(tables)

    # Exit status
    if result.success:
        console.print("\n[bold green]✓ Pipeline completed successfully![/bold green]\n")
        raise typer.Exit(0)
    else:
        console.print(
            f"\n[bold red]✗ Pipeline completed with {result.failed_trackers} failures[/bold red]\n"
        )
        raise typer.Exit(1)


@create_app.command("tables")
def create_tables_cmd(
    output_root: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o", help="Pipeline output root directory (default: from config)"
        ),
    ] = None,
):
    """Rebuild all tables from existing cleaned output, without re-running extract/clean.

    Reads whichever of `patient_data_cleaned/`, `product_data_cleaned/`, and
    `logs/` exist under the output root and rebuilds the corresponding
    tables (patient static/monthly/annual, product, logs), plus the clinic
    static table and tracker metadata table. At least one of the patient or
    product cleaned directories must exist.

    Useful for:
    - Re-creating tables after fixing table creation logic
    - Creating tables from manually cleaned data
    - Testing table creation independently

    \\b
    Examples:
        # Rebuild tables from the default output root (from config)
        uv run a4d create tables

        # Rebuild from a specific output root
        uv run a4d create tables --output /path/to/output
    """
    from a4d.config import settings as _settings
    from a4d.tables.clinic import create_table_clinic_static
    from a4d.tables.metadata import create_table_tracker_metadata

    console.print("\n[bold blue]A4D Table Creation[/bold blue]\n")

    _output_root = output_root or _settings.output_root
    patient_cleaned_dir = _output_root / "patient_data_cleaned"
    product_cleaned_dir = _output_root / "product_data_cleaned"
    logs_dir = _output_root / "logs"
    tables_dir = _output_root / "tables"

    console.print(f"Output root: {_output_root}")
    console.print(f"Tables directory: {tables_dir}\n")

    if not patient_cleaned_dir.exists() and not product_cleaned_dir.exists():
        console.print(
            f"[bold red]Error: Neither {patient_cleaned_dir} nor {product_cleaned_dir} "
            "exists — nothing to build tables from[/bold red]\n"
        )
        raise typer.Exit(1)

    try:
        tables: dict[str, Path] = {}

        if patient_cleaned_dir.exists():
            console.print("  • Creating patient tables...")
            tables.update(process_patient_tables(patient_cleaned_dir, tables_dir))
        else:
            console.print(
                f"  [yellow]Warning: {patient_cleaned_dir} not found, "
                "skipping patient tables[/yellow]"
            )

        if product_cleaned_dir.exists():
            console.print("  • Creating product table...")
            tables.update(process_product_tables(product_cleaned_dir, tables_dir))
        else:
            console.print(
                f"  [yellow]Warning: {product_cleaned_dir} not found, "
                "skipping product table[/yellow]"
            )

        if logs_dir.exists():
            console.print("  • Creating logs table...")
            tables["logs"] = create_table_logs(logs_dir, tables_dir)
        else:
            console.print(f"  [yellow]Warning: Logs directory not found at {logs_dir}[/yellow]")

        # Create clinic static table (reads reference_data/clinic_data.xlsx)
        console.print("  • Creating clinic static table...")
        tables["clinic_data_static"] = create_table_clinic_static(tables_dir)

        # Create tracker metadata table (MD5 + per-tracker output presence).
        # Skipped if settings.data_root is unreachable — the table needs the
        # raw .xlsx files, which create tables doesn't otherwise require.
        if _settings.data_root.exists():
            console.print("  • Creating tracker metadata table...")
            tables["tracker_metadata"] = create_table_tracker_metadata(
                _settings.data_root, _output_root
            )
        else:
            console.print(
                f"  [yellow]Warning: data_root {_settings.data_root} not found, "
                "skipping tracker metadata[/yellow]"
            )

        # Display results
        console.print("\n[bold green]✓ Tables created successfully![/bold green]")
        _display_tables_summary(tables)

    except Exception as e:
        console.print(f"\n[bold red]Error creating tables: {e}[/bold red]\n")
        raise typer.Exit(1) from e


@create_app.command("logs")
def create_logs_cmd(
    output_root: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o", help="Pipeline output root directory (default: from config)"
        ),
    ] = None,
):
    """Rebuild only the logs table from existing pipeline log files.

    Faster than `create tables` when only the logs table is needed — e.g.
    iterating on a log-analysis tool without rebuilding patient/product
    tables too.

    \\b
    Examples:
        uv run a4d create logs
        uv run a4d create logs --output /path/to/output
    """
    from a4d.config import settings as _settings

    console.print("\n[bold blue]A4D Logs Table Creation[/bold blue]\n")

    _output_root = output_root or _settings.output_root
    logs_dir = _output_root / "logs"
    tables_dir = _output_root / "tables"

    if not logs_dir.exists():
        console.print(f"[bold red]Error: Logs directory not found: {logs_dir}[/bold red]\n")
        raise typer.Exit(1)

    try:
        logs_table_path = create_table_logs(logs_dir, tables_dir)
        console.print(f"[bold green]✓ Logs table created: {logs_table_path}[/bold green]\n")
    except Exception as e:
        console.print(f"\n[bold red]Error creating logs table: {e}[/bold red]\n")
        raise typer.Exit(1) from e


@run_app.command("product")
def run_product_cmd(
    file: Annotated[
        Path | None,
        typer.Option(
            "--file",
            "-f",
            help="Process specific tracker file (if not set, processes all files in data_root)",
        ),
    ] = None,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers", "-w", help="Number of parallel workers (default: A4D_MAX_WORKERS)"
        ),
    ] = None,
    skip_tables: Annotated[
        bool, typer.Option("--skip-tables", help="Skip table creation (only extract + clean)")
    ] = False,
    data_root: Annotated[
        Path | None,
        typer.Option(
            "--data-root", "-d", help="Directory containing tracker files (default: from config)"
        ),
    ] = None,
    output_root: Annotated[
        Path | None, typer.Option("--output", "-o", help="Output directory (default: from config)")
    ] = None,
    incremental: Annotated[
        bool,
        typer.Option(
            "--incremental",
            help=(
                "Skip trackers whose MD5 + completion state match the previous "
                "run's manifest. Preserves prior outputs (clean_output disabled)."
            ),
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help=(
                "Wipe prior outputs and reprocess every tracker. Same as the "
                "default behavior; pass explicitly for self-documenting deploy "
                "commands. Overrides --incremental if both are passed."
            ),
        ),
    ] = False,
):
    """Process product data pipeline.

    \b
    By default, output is cleaned before each run so tables reflect only the
    current run's files. With --incremental, prior outputs are preserved and
    only new/changed/previously-incomplete trackers are re-processed.
    With --force, behaves as the default (wipe + reprocess) and overrides
    --incremental if both are passed.

    Examples:
        # Process all trackers in data_root (from config)
        uv run a4d run product

        # Process specific file
        uv run a4d run product --file /path/to/tracker.xlsx

        # Parallel processing with 8 workers
        uv run a4d run product --workers 8

        # Just extract + clean, skip tables
        uv run a4d run product --skip-tables

        # Skip trackers whose MD5 matches the previous run's manifest
        uv run a4d run product --incremental

        # Explicitly wipe outputs and reprocess everything
        uv run a4d run product --force
    """
    from a4d.config import settings as _settings

    console.print("\n[bold blue]A4D Product Pipeline[/bold blue]\n")

    if force and incremental:
        console.print("[yellow]Warning: --incremental is ignored when --force is set[/yellow]")
        incremental = False

    _output_root = output_root or _settings.output_root
    _workers = workers if workers is not None else _settings.max_workers

    tracker_files, data_root_display = _resolve_tracker_files(
        file, data_root, incremental, _output_root
    )

    if tracker_files is not None and len(tracker_files) == 0:
        console.print("[bold green]✓ No trackers need reprocessing — exiting[/bold green]\n")
        raise typer.Exit(0)

    _render_pipeline_header(data_root_display, _output_root, _workers, skip_tables=skip_tables)

    console.print("[bold]Step 1/4:[/bold] Extracting and cleaning product data...")
    try:
        result = run_product_pipeline(
            tracker_files=tracker_files,
            max_workers=_workers,
            output_root=output_root,
            skip_tables=True,
            clean_output=force
            or not incremental,  # incremental keeps prior outputs; --force always wipes
            show_progress=True,
            console_log_level="ERROR",
        )
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]\n")
        raise typer.Exit(1) from e

    # Steps 2-4 mirror process_patient_cmd: table, then logs, then errors.
    tables: dict[str, Path] = {}
    if not skip_tables and result.successful_trackers > 0:
        cleaned_dir = _output_root / "product_data_cleaned"
        tables_dir = _output_root / "tables"
        logs_dir = _output_root / "logs"

        console.print("[bold]Step 2/4:[/bold] Creating product table...")
        try:
            tables = process_product_tables(cleaned_dir, tables_dir)
        except Exception as e:
            console.print(f"[bold red]Error creating tables: {e}[/bold red]")

        if logs_dir.exists():
            console.print("[bold]Step 3/4:[/bold] Creating logs table...")
            try:
                logs_table_path = create_table_logs(logs_dir, tables_dir)
                tables["logs"] = logs_table_path
            except Exception as e:
                console.print(f"[bold red]Error creating logs table: {e}[/bold red]")

        console.print("[bold]Step 4/4:[/bold] Creating errors table...")
        try:
            all_data_errors = [e for r in result.tracker_results for e in r.data_errors]
            errors_table_path = create_table_errors(all_data_errors, tables_dir)
            tables["errors"] = errors_table_path
        except Exception as e:
            console.print(f"[bold red]Error creating errors table: {e}[/bold red]")
    elif skip_tables:
        console.print("[dim]Steps 2-3: Skipped (--skip-tables)[/dim]")
        console.print("[bold]Step 4/4:[/bold] Creating errors table...")
        try:
            tables_dir = _output_root / "tables"
            all_data_errors = [e for r in result.tracker_results for e in r.data_errors]
            errors_table_path = create_table_errors(all_data_errors, tables_dir)
            tables["errors"] = errors_table_path
        except Exception as e:
            console.print(f"[bold red]Error creating errors table: {e}[/bold red]")

    console.print("\n[bold]Pipeline Results[/bold]\n")

    total_errors = sum(tr.cleaning_errors for tr in result.tracker_results)
    files_with_errors = sum(1 for tr in result.tracker_results if tr.cleaning_errors > 0)

    _render_pipeline_results_summary(result, tables, total_errors, files_with_errors)

    _render_failed_trackers(result, mode="table")

    _display_tables_summary(tables)

    if result.success:
        console.print("\n[bold green]✓ Product pipeline completed successfully![/bold green]\n")
        raise typer.Exit(0)
    else:
        console.print(
            f"\n[bold red]✗ Product pipeline completed with "
            f"{result.failed_trackers} failures[/bold red]\n"
        )
        raise typer.Exit(1)


@upload_app.command("tables")
def upload_tables_cmd(
    tables_dir: Annotated[
        Path,
        typer.Option("--tables-dir", "-t", help="Directory containing parquet table files"),
    ],
    dataset: Annotated[
        str | None,
        typer.Option("--dataset", "-d", help="BigQuery dataset name (default: from config)"),
    ] = None,
    project_id: Annotated[
        str | None,
        typer.Option("--project", "-p", help="GCP project ID (default: from config)"),
    ] = None,
    append: Annotated[
        bool,
        typer.Option("--append", help="Append to existing tables instead of replacing"),
    ] = False,
    only: Annotated[
        list[str] | None,
        typer.Option(
            "--only",
            help="Restrict upload to a table group: patient, product, clinic, logs, "
            "errors, metadata. Repeatable; default uploads all groups.",
        ),
    ] = None,
):
    """Upload pipeline output tables to BigQuery.

    Loads parquet files from the tables directory into the configured
    BigQuery dataset. By default, existing tables are replaced (matching
    the R pipeline behavior).

    \b
    Examples:
        # Upload tables from default output directory
        uv run a4d upload tables --tables-dir output/tables

        # Upload to a specific dataset
        uv run a4d upload tables --tables-dir output/tables --dataset tracker_dev

        # Append instead of replace
        uv run a4d upload tables --tables-dir output/tables --append

        # Only upload the patient tables
        uv run a4d upload tables --tables-dir output/tables --only patient
    """
    from a4d.gcp.bigquery import TABLE_GROUPS, load_pipeline_tables

    console.print("\n[bold blue]A4D BigQuery Upload[/bold blue]\n")
    console.print(f"Tables directory: {tables_dir}")

    if not tables_dir.exists():
        console.print(f"[bold red]Error: Directory not found: {tables_dir}[/bold red]\n")
        raise typer.Exit(1)

    only_tables: set[str] | None = None
    if only:
        invalid = sorted(set(only) - set(TABLE_GROUPS))
        if invalid:
            console.print(
                f"[bold red]Error: unknown --only group(s): {', '.join(invalid)} "
                f"(valid: {', '.join(sorted(TABLE_GROUPS))})[/bold red]\n"
            )
            raise typer.Exit(1)
        only_tables = set().union(*(TABLE_GROUPS[group] for group in only))
        console.print(f"Restricting to: {', '.join(sorted(only))}")

    try:
        results = load_pipeline_tables(
            tables_dir=tables_dir,
            dataset=dataset,
            project_id=project_id,
            replace=not append,
            only_tables=only_tables,
        )

        if results:
            result_table = Table(title="Uploaded Tables")
            result_table.add_column("Table", style="cyan")
            result_table.add_column("Rows", justify="right", style="green")
            result_table.add_column("Status", style="green")

            for table_name, job in results.items():
                result_table.add_row(
                    table_name,
                    f"{job.output_rows:,}" if job.output_rows else "?",
                    "✓",
                )

            console.print(result_table)
            console.print(
                f"\n[bold green]✓ Uploaded {len(results)} tables to BigQuery[/bold green]\n"
            )
        else:
            console.print("[bold yellow]No tables found to upload[/bold yellow]\n")

    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]\n")
        raise typer.Exit(1) from e


@download_app.command("trackers")
def download_trackers_cmd(
    destination: Annotated[
        Path,
        typer.Option("--destination", "-d", help="Local directory to download files to"),
    ],
    bucket: Annotated[
        str | None,
        typer.Option("--bucket", "-b", help="GCS bucket name (default: from config)"),
    ] = None,
):
    """Download tracker files from Google Cloud Storage.

    \b
    Examples:
        # Download to local directory
        uv run a4d download trackers --destination /data/trackers

        # Download from specific bucket
        uv run a4d download trackers --destination /data/trackers --bucket my-bucket
    """
    from a4d.gcp.storage import download_tracker_files

    console.print("\n[bold blue]A4D Tracker Download[/bold blue]\n")
    console.print(f"Destination: {destination}")

    try:
        downloaded = download_tracker_files(destination=destination, bucket_name=bucket)
        console.print(f"\n[bold green]✓ Downloaded {len(downloaded)} files[/bold green]\n")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]\n")
        raise typer.Exit(1) from e


@upload_app.command("output")
def upload_output_cmd(
    source_dir: Annotated[
        Path,
        typer.Option("--source", "-s", help="Output directory to upload"),
    ],
    bucket: Annotated[
        str | None,
        typer.Option("--bucket", "-b", help="GCS bucket name (default: from config)"),
    ] = None,
    prefix: Annotated[
        str,
        typer.Option("--prefix", help="Prefix for uploaded blob names"),
    ] = "",
):
    """Upload pipeline output to Google Cloud Storage.

    \b
    Examples:
        # Upload output directory
        uv run a4d upload output --source output/

        # Upload with prefix
        uv run a4d upload output --source output/ --prefix 2024-01
    """
    from a4d.gcp.storage import upload_output

    console.print("\n[bold blue]A4D Output Upload[/bold blue]\n")
    console.print(f"Source: {source_dir}")

    if not source_dir.exists():
        console.print(f"[bold red]Error: Directory not found: {source_dir}[/bold red]\n")
        raise typer.Exit(1)

    try:
        uploaded = upload_output(source_dir=source_dir, bucket_name=bucket, prefix=prefix)
        console.print(f"\n[bold green]✓ Uploaded {len(uploaded)} files to GCS[/bold green]\n")
    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]\n")
        raise typer.Exit(1) from e


@download_app.command("clinic-data")
def download_clinic_data_cmd() -> None:
    """Download reference data files from Google Drive.

    Downloads clinic_data.xlsx from Google Drive into the reference_data/
    directory. Uses Application Default Credentials with Drive readonly scope.

    The service account must have at least Viewer access to the file.
    """
    from a4d.gcp.drive import download_clinic_data
    from a4d.reference.loaders import find_reference_data_dir

    console.print("\n[bold blue]A4D Reference Data Download[/bold blue]\n")

    reference_dir = find_reference_data_dir()
    console.print(f"Destination: {reference_dir}\n")

    try:
        console.print("Downloading clinic_data.xlsx from Google Drive...")
        path = download_clinic_data(reference_dir)
        size_kb = path.stat().st_size / 1024
        console.print(
            f"  [bold green]✓[/bold green] clinic_data.xlsx ({size_kb:.1f} KB) -> {path}\n"
        )
    except Exception as e:
        console.print(f"  [bold red]✗ Download failed: {e}[/bold red]\n")
        raise typer.Exit(1) from e


@run_app.callback(invoke_without_command=True)
def run_all_cmd(
    ctx: typer.Context,
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers", "-w", help="Number of parallel workers (default: A4D_MAX_WORKERS)"
        ),
    ] = None,
    skip_download: Annotated[
        bool,
        typer.Option("--skip-download", help="Skip GCS download (use files already in data_root)"),
    ] = False,
    skip_upload: Annotated[
        bool,
        typer.Option("--skip-upload", help="Skip GCS and BigQuery upload steps"),
    ] = False,
    skip_drive_download: Annotated[
        bool,
        typer.Option(
            "--skip-drive-download",
            help="Skip Google Drive download of reference data (clinic_data.xlsx)",
        ),
    ] = False,
    skip_product: Annotated[
        bool,
        typer.Option("--skip-product", help="Skip the product pipeline arm."),
    ] = False,
    skip_patient: Annotated[
        bool,
        typer.Option(
            "--skip-patient",
            help=(
                "Skip the patient pipeline arm. Note: leaves "
                "tracker_metadata.complete=False for all trackers, so the "
                "next --incremental run will re-queue everything."
            ),
        ),
    ] = False,
    incremental: Annotated[
        bool,
        typer.Option(
            "--incremental",
            help=(
                "Skip trackers whose MD5 + completion state match the previous "
                "run's manifest. Both arms see the same filtered queue."
            ),
        ),
    ] = False,
    force: Annotated[
        bool,
        typer.Option(
            "--force",
            help=(
                "Wipe prior local outputs (raw, cleaned, tables) before each "
                "pipeline arm runs. Without this flag, `run` reuses any "
                "existing per-tracker parquets on disk. Overrides --incremental "
                "if both are passed."
            ),
        ),
    ] = False,
):
    """Run the full end-to-end A4D pipeline (default), or a single arm.

    Bare `a4d run` executes all pipeline stages in sequence:
      0. Download reference data (clinic_data.xlsx) from Google Drive
      1. Download tracker files from Google Cloud Storage
      2. Extract and clean all tracker files
      3. Create final tables (static, monthly, annual, clinic)
      4. Upload output files to Google Cloud Storage
      5. Ingest tables into BigQuery

    Use `a4d run patient` or `a4d run product` to run a single arm locally
    without any of the GCS/Drive/BigQuery steps.

    All configuration is read from environment variables (A4D_*) or a .env file.

    \b
    Examples:
        # Full pipeline (download + process + upload)
        uv run a4d run

        # Download latest files, process locally, skip upload
        uv run a4d run --skip-upload

        # Process local files only, no download or upload
        uv run a4d run --skip-download --skip-upload

        # Skip Drive download if clinic_data.xlsx is already current
        uv run a4d run --skip-drive-download

        # Wipe prior outputs before each arm runs
        uv run a4d run --force
    """
    if ctx.invoked_subcommand is not None:
        return

    from a4d.config import settings
    from a4d.gcp.bigquery import load_pipeline_tables
    from a4d.gcp.drive import download_clinic_data
    from a4d.gcp.storage import download_tracker_files, upload_output
    from a4d.reference.loaders import find_reference_data_dir
    from a4d.tables.clinic import create_table_clinic_static

    if skip_patient and skip_product:
        console.print(
            "[bold red]Error: --skip-patient and --skip-product are mutually exclusive[/bold red]\n"
        )
        raise typer.Exit(1)

    if force and incremental:
        console.print("[yellow]Warning: --incremental is ignored when --force is set[/yellow]")
        incremental = False

    _workers = workers if workers is not None else settings.max_workers
    run_ts = datetime.now().strftime("%Y/%m/%d/%H%M%S")

    console.print("\n[bold blue]A4D Full Pipeline[/bold blue]\n")
    extras = [
        ("Project", str(settings.project_id)),
        ("Dataset", str(settings.dataset)),
        ("Drive", "yes" if not skip_drive_download else "skipped (--skip-drive-download)"),
        ("Download", "yes" if not skip_download else "skipped (--skip-download)"),
        ("Upload", "yes" if not skip_upload else "skipped (--skip-upload)"),
        ("Product", "yes" if not skip_product else "skipped (--skip-product)"),
        ("Patient", "yes" if not skip_patient else "skipped (--skip-patient)"),
        ("Incremental", "yes" if incremental else "no"),
        ("Force", "yes" if force else "no"),
    ]
    _render_pipeline_header(settings.data_root, settings.output_root, _workers, extras=extras)

    # Step 0 – Download reference data from Google Drive
    if not skip_drive_download:
        console.print("[bold]Step 0/5:[/bold] Downloading reference data from Google Drive...")
        try:
            reference_dir = find_reference_data_dir()
            path = download_clinic_data(reference_dir)
            size_kb = path.stat().st_size / 1024
            console.print(f"  ✓ clinic_data.xlsx ({size_kb:.1f} KB)\n")
        except Exception as e:
            console.print(f"\n[bold red]Error downloading reference data: {e}[/bold red]\n")
            raise typer.Exit(1) from e
    else:
        console.print("[bold]Step 0/5:[/bold] Skipping Drive download (--skip-drive-download)\n")

    # Step 1 – Download tracker files from GCS
    if not skip_download:
        console.print("[bold]Step 1/5:[/bold] Downloading tracker files from GCS...")
        try:
            downloaded = download_tracker_files(destination=settings.data_root)
            console.print(f"  ✓ Downloaded {len(downloaded)} files\n")
        except Exception as e:
            console.print(f"\n[bold red]Error during download: {e}[/bold red]\n")
            raise typer.Exit(1) from e
    else:
        console.print("[bold]Step 1/5:[/bold] Skipping GCS download (--skip-download)\n")

    # Resolve the tracker queue once. Without --incremental, pass None and let
    # each orchestrator discover. With --incremental, discover + filter here so
    # both arms see the same queue (single manifest load, coherent skip).
    shared_tracker_files: list[Path] | None = None
    if incremental:
        all_trackers = discover_tracker_files(settings.data_root)
        manifest = load_previous_manifest(settings.output_root)
        shared_tracker_files, summary = filter_unchanged_trackers(all_trackers, manifest)
        console.print(
            f"[cyan]Incremental filter: queued {summary.queued}, "
            f"skipped {summary.skipped} unchanged "
            f"(new={summary.new}, changed={summary.changed}, "
            f"incomplete={summary.previously_incomplete})[/cyan]\n"
        )
        if not shared_tracker_files:
            console.print(
                "[bold green]✓ No trackers need reprocessing — exiting cleanly[/bold green]\n"
            )
            raise typer.Exit(0)

    # Step 2+3 – Extract, clean and build tables.
    # clean_output wiring is `force` here, not `force or not incremental` like
    # run patient/run product. Reason: the bare `run`'s historical default
    # (on `migration` and on this branch pre-change) was preserve-outputs — it
    # never passed clean_output, inheriting the orchestrator's False default.
    # --force on `migration` was a vestigial no-op (declared, plumbed, never
    # read). With --force now actually wired through, opting in wipes both arms;
    # without it, `run` keeps its prior preserve-outputs contract.
    result = None
    product_result = None
    if not skip_patient:
        console.print("[bold]Steps 2–3/5:[/bold] Processing tracker files...\n")
        try:
            result = run_patient_pipeline(
                tracker_files=shared_tracker_files,
                max_workers=_workers,
                clean_output=force,
                show_progress=True,
                console_log_level="WARNING",
            )

            console.print(
                f"  ✓ Processed {result.total_trackers} trackers "
                f"({result.successful_trackers} ok, {result.failed_trackers} failed)\n"
            )

            _render_failed_trackers(
                result,
                mode="bullets",
                title="Failed trackers",
                leading_newline=False,
            )

            if not result.success:
                # Soft-fail posture, matching the product arm below: some trackers
                # failing doesn't block the rest of the run (product arm, tables,
                # upload) — the combined run summary below is what surfaces this.
                console.print(
                    "[bold yellow]Warning: some patient trackers failed — "
                    "continuing with the rest of the run.[/bold yellow]\n"
                )

        except Exception as e:
            console.print(
                f"\n[bold yellow]Warning: patient pipeline failed: {e}[/bold yellow]\n"
                "[yellow]Continuing with product/upload steps.[/yellow]\n"
            )
    else:
        console.print("[bold]Steps 2–3/5:[/bold] Skipping patient pipeline (--skip-patient)\n")

    tables_dir = settings.output_root / "tables"
    logs_dir = settings.output_root / "logs"

    # Clinic static table — independent of tracker processing, always created
    console.print("[bold]Step 3b/5:[/bold] Creating clinic static table...")
    try:
        create_table_clinic_static(tables_dir)
        console.print("  ✓ Clinic static table created\n")
    except Exception as e:
        console.print(f"  [bold red]Error creating clinic static table: {e}[/bold red]\n")
        raise typer.Exit(1) from e

    # Product pipeline arm — soft failure posture: a crash here warns and
    # continues so patient outputs (already on disk) still get uploaded.
    if not skip_product:
        console.print("[bold]Step 3c/5:[/bold] Running product pipeline...\n")
        # Drop any stale product table from a prior run before re-running.
        # Without --force, `run` preserves outputs (clean_output=False),
        # so a crash mid-product would otherwise leave the previous run's
        # parquet for upload. With --force the orchestrator wipes anyway, so
        # this unlink is redundant in that case but harmless.
        (settings.output_root / "tables" / "product_data.parquet").unlink(missing_ok=True)
        try:
            product_result = run_product_pipeline(
                tracker_files=shared_tracker_files,
                max_workers=_workers,
                clean_output=force,
                show_progress=True,
                console_log_level="WARNING",
            )
            console.print(
                f"  ✓ Processed {product_result.total_trackers} product trackers "
                f"({product_result.successful_trackers} ok, "
                f"{product_result.failed_trackers} failed)\n"
            )
            _render_failed_trackers(
                product_result,
                mode="bullets",
                title="Failed product trackers",
                leading_newline=False,
            )
        except Exception as e:
            console.print(
                f"[bold yellow]Warning: product pipeline failed: {e}[/bold yellow]\n"
                "[yellow]Continuing with patient outputs only.[/yellow]\n"
            )
    else:
        console.print("[bold]Step 3c/5:[/bold] Skipping product pipeline (--skip-product)\n")

    _render_combined_run_summary(result, product_result)

    # Tracker metadata table — MD5 + per-tracker output presence.
    # Not a skip-gated step; it's cheap and summarises the run's final state.
    if settings.data_root.exists():
        console.print("[bold]Step 3d/5:[/bold] Creating tracker metadata table...\n")
        try:
            from a4d.tables.metadata import create_table_tracker_metadata

            create_table_tracker_metadata(settings.data_root, settings.output_root)
            console.print("  ✓ Tracker metadata table created\n")
        except Exception as e:
            console.print(f"  [bold yellow]Warning: tracker metadata failed: {e}[/bold yellow]\n")

    # Step 3e – Product-patient link validation (logging-only, post-tables).
    # Skips silently if either arm's table is missing (e.g. --skip-product), or
    # when --skip-patient leaves a stale patient_data_static.parquet on disk
    # whose contents don't match this run's product output.
    product_table = tables_dir / "product_data.parquet"
    patient_static = tables_dir / "patient_data_static.parquet"
    if not skip_patient and product_table.exists() and patient_static.exists():
        console.print("[bold]Step 3e/5:[/bold] Validating product-patient links...")
        try:
            from a4d.tables.product import link_product_patient

            product_df = pl.read_parquet(product_table)
            mismatched = link_product_patient(product_df, patient_static)
            console.print(f"  ✓ Link validation complete ({mismatched} unmatched product rows)\n")
        except Exception as e:
            console.print(f"  [bold yellow]Warning: link validation failed: {e}[/bold yellow]\n")

    # Step 4 – Upload tables/ and logs/ to GCS under a timestamped prefix
    # Each run gets an isolated path: YYYY/MM/DD/HHMMSS/tables/ and .../logs/
    # This avoids overwriting previous runs and keeps objectCreator permission sufficient.
    if not skip_upload:
        console.print("[bold]Step 4/5:[/bold] Uploading output files to GCS...")
        console.print(f"  Prefix: {run_ts}/\n")
        try:
            uploaded: list[str] = []
            if tables_dir.exists():
                uploaded += upload_output(source_dir=tables_dir, prefix=f"{run_ts}/tables")
            if logs_dir.exists():
                uploaded += upload_output(source_dir=logs_dir, prefix=f"{run_ts}/logs")
            console.print(
                f"  ✓ Uploaded {len(uploaded)} files to gs://{settings.upload_bucket}/{run_ts}/\n"
            )
        except Exception as e:
            console.print(f"\n[bold red]Error during GCS upload: {e}[/bold red]\n")
            raise typer.Exit(1) from e
    else:
        console.print("[bold]Step 4/5:[/bold] Skipping GCS upload (--skip-upload)\n")

    # Step 5 – Ingest tables into BigQuery
    if not skip_upload:
        console.print("[bold]Step 5/5:[/bold] Ingesting tables into BigQuery...")
        try:
            bq_results = load_pipeline_tables(tables_dir=tables_dir)
            console.print(f"  ✓ Loaded {len(bq_results)} tables into BigQuery\n")
        except Exception as e:
            console.print(f"\n[bold red]Error during BigQuery upload: {e}[/bold red]\n")
            raise typer.Exit(1) from e
    else:
        console.print("[bold]Step 5/5:[/bold] Skipping BigQuery upload (--skip-upload)\n")

    console.print("[bold green]✓ Full pipeline completed successfully![/bold green]\n")


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
