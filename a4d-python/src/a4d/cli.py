"""Command-line interface for A4D pipeline."""

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from a4d.pipeline.patient import run_patient_pipeline

app = typer.Typer(name="a4d", help="A4D medical tracker data processing pipeline", no_args_is_help=True)

console = Console()


@app.command("process-patient")
def process_patient_cmd(
    file: Path | None = typer.Option(
        None, "--file", "-f", help="Process specific tracker file (if not set, processes all files in data_root)"
    ),
    workers: int = typer.Option(1, "--workers", "-w", help="Number of parallel workers (1 = sequential)"),
    skip_tables: bool = typer.Option(False, "--skip-tables", help="Skip table creation (only extract + clean)"),
    force: bool = typer.Option(False, "--force", help="Force reprocessing (ignore existing outputs)"),
    output_root: Path | None = typer.Option(None, "--output", "-o", help="Output directory (default: from config)"),
):
    """Process patient data pipeline.

    \b
    Examples:
        # Process all trackers in data_root
        uv run a4d process-patient

        # Process specific file
        uv run a4d process-patient --file /path/to/tracker.xlsx

        # Parallel processing with 8 workers
        uv run a4d process-patient --workers 8

        # Just extract + clean, skip tables
        uv run a4d process-patient --skip-tables
    """
    console.print("\n[bold blue]A4D Patient Pipeline[/bold blue]\n")

    # Prepare tracker files list
    tracker_files = [file] if file else None

    # Run pipeline with progress bar and minimal console logging
    try:
        result = run_patient_pipeline(
            tracker_files=tracker_files,
            max_workers=workers,
            output_root=output_root,
            skip_tables=skip_tables,
            force=force,
            show_progress=True,  # Show tqdm progress bar
            console_log_level="ERROR",  # Only show errors in console
        )

        # Display results
        console.print("\n[bold]Pipeline Results[/bold]\n")

        # Calculate error statistics
        total_errors = sum(tr.cleaning_errors for tr in result.tracker_results)
        files_with_errors = sum(1 for tr in result.tracker_results if tr.cleaning_errors > 0)

        summary_table = Table(title="Summary")
        summary_table.add_column("Metric", style="cyan")
        summary_table.add_column("Value", style="green")

        summary_table.add_row("Total Trackers", str(result.total_trackers))
        summary_table.add_row("Successful", str(result.successful_trackers))
        summary_table.add_row("Failed", str(result.failed_trackers))
        summary_table.add_row("Tables Created", str(len(result.tables)))
        summary_table.add_row("", "")  # Spacer
        summary_table.add_row("Data Quality Errors", f"{total_errors:,}")
        summary_table.add_row("Files with Errors", str(files_with_errors))

        console.print(summary_table)

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

        # Show failed trackers if any
        if result.failed_trackers > 0:
            console.print("\n[bold yellow]Failed Trackers:[/bold yellow]")
            failed_table = Table()
            failed_table.add_column("File", style="red")
            failed_table.add_column("Error")

            for tr in result.tracker_results:
                if not tr.success:
                    failed_table.add_row(
                        tr.tracker_file.name,
                        str(tr.error)[:100],  # Truncate long errors
                    )

            console.print(failed_table)

        # Show top files with most data quality errors (if any)
        if total_errors > 0:
            console.print("\n[bold yellow]Top Files by Error Count:[/bold yellow]")
            # Sort by error count (descending) and take top 10
            files_by_errors = sorted(
                [(tr.tracker_file.name, tr.cleaning_errors) for tr in result.tracker_results if tr.cleaning_errors > 0],
                key=lambda x: x[1],
                reverse=True
            )[:10]

            errors_table = Table()
            errors_table.add_column("File", style="yellow")
            errors_table.add_column("Errors", justify="right", style="red")

            for filename, error_count in files_by_errors:
                errors_table.add_row(filename, f"{error_count:,}")

            console.print(errors_table)

        # Show created tables
        if result.tables:
            console.print("\n[bold green]Created Tables:[/bold green]")
            tables_table = Table()
            tables_table.add_column("Table", style="cyan")
            tables_table.add_column("Path", style="green")

            for name, path in result.tables.items():
                tables_table.add_row(name, str(path))

            console.print(tables_table)

        # Exit status
        if result.success:
            console.print("\n[bold green]✓ Pipeline completed successfully![/bold green]\n")
            raise typer.Exit(0)
        else:
            console.print(f"\n[bold red]✗ Pipeline completed with {result.failed_trackers} failures[/bold red]\n")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"\n[bold red]Error: {e}[/bold red]\n")
        raise typer.Exit(1)


@app.command("version")
def version_cmd():
    """Show version information."""
    console.print("[bold cyan]A4D Pipeline v0.1.0[/bold cyan]")
    console.print("Python implementation of the A4D medical tracker processing pipeline")


def main():
    """Entry point for CLI."""
    app()


if __name__ == "__main__":
    main()
