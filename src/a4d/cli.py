"""Command-line interface for A4D pipeline."""

import warnings
from datetime import datetime
from pathlib import Path
from typing import Annotated

import polars as pl
import typer
from rich.console import Console
from rich.table import Table

from a4d.pipeline.patient import (
    discover_tracker_files,
    process_patient_tables,
    run_patient_pipeline,
)
from a4d.tables.errors import create_table_errors
from a4d.tables.logs import create_table_logs

# google-crc32c has no pre-built C wheel for Python 3.14 yet; the pure-Python
# fallback is correct, just slightly slower. Suppress the noisy runtime warning
# before any google SDK calls are made (those happen lazily inside commands).
warnings.filterwarnings(
    "ignore", message="As the c extension couldn't be imported", category=RuntimeWarning
)

app = typer.Typer(
    name="a4d", help="A4D medical tracker data processing pipeline", no_args_is_help=True
)

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

    for name in ["static", "monthly", "annual", "logs", "errors"]:
        if name in tables:
            path = tables[name]
            try:
                record_count = f"{pl.read_parquet(path).__len__():,}"
            except Exception:
                record_count = "?"
            tables_table.add_row(name, str(path.name), record_count)

    console.print(tables_table)
    console.print()


@app.command("process-patient")
def process_patient_cmd(
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
    force: Annotated[
        bool, typer.Option("--force", help="Force reprocessing (ignore existing outputs)")
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
):
    """Process patient data pipeline.

    \b
    Output is always cleaned before each run so tables reflect only the
    current run's files.

    Examples:
        # Process all trackers in data_root (from config)
        uv run a4d process-patient

        # Process all trackers in a specific directory
        uv run a4d process-patient --data-root /path/to/trackers

        # Process specific file
        uv run a4d process-patient --file /path/to/tracker.xlsx

        # Parallel processing with 8 workers
        uv run a4d process-patient --workers 8

        # Just extract + clean, skip tables
        uv run a4d process-patient --skip-tables
    """
    from a4d.config import settings as _settings

    console.print("\n[bold blue]A4D Patient Pipeline[/bold blue]\n")

    if file:
        tracker_files = [file]
        data_root_display = f"{file} (single file)"
    elif data_root:
        tracker_files = discover_tracker_files(data_root)
        if not tracker_files:
            console.print(f"[bold red]Error: No tracker files found in {data_root}[/bold red]\n")
            raise typer.Exit(1)
        data_root_display = str(data_root)
    else:
        tracker_files = None  # pipeline uses settings.data_root
        data_root_display = str(_settings.data_root)

    _output_root = output_root or _settings.output_root
    _workers = workers if workers is not None else _settings.max_workers

    console.print(f"Data root:   {data_root_display}")
    console.print(f"Output root: {_output_root}")
    console.print(f"Workers:     {_workers}")
    if skip_tables:
        console.print("Tables:      skipped")
    if force:
        console.print("Force:       yes")
    console.print()

    # Step 1: Extract + clean (table creation handled below for visible progress)
    console.print("[bold]Step 1/4:[/bold] Extracting and cleaning tracker files...")
    try:
        result = run_patient_pipeline(
            tracker_files=tracker_files,
            max_workers=_workers,
            output_root=output_root,
            skip_tables=True,  # tables created below with console feedback
            force=force,
            clean_output=True,
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

    summary_table = Table(title="Summary")
    summary_table.add_column("Metric", style="cyan")
    summary_table.add_column("Value", style="green")

    summary_table.add_row("Total Trackers", str(result.total_trackers))
    summary_table.add_row("Successful", str(result.successful_trackers))
    summary_table.add_row("Failed", str(result.failed_trackers))
    summary_table.add_row("Tables Created", str(len(tables)))
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


@app.command("create-tables")
def create_tables_cmd(
    input_dir: Annotated[
        Path, typer.Option("--input", "-i", help="Directory containing cleaned parquet files")
    ],
    output_dir: Annotated[
        Path | None,
        typer.Option(
            "--output", "-o", help="Output directory for tables (default: input_dir/tables)"
        ),
    ] = None,
):
    """Create final tables from existing cleaned parquet files.

    This command creates the patient tables (static, monthly, annual) and logs table
    from existing cleaned parquet files, without running the full pipeline.

    Useful for:
    - Re-creating tables after fixing table creation logic
    - Creating tables from manually cleaned data
    - Testing table creation independently

    \\b
    Examples:
        # Create tables from existing output
        uv run a4d create-tables --input output/patient_data_cleaned

        # Specify custom output directory
        uv run a4d create-tables --input output/patient_data_cleaned --output custom_tables
    """
    console.print("\n[bold blue]A4D Table Creation[/bold blue]\n")

    # Determine output directory
    if output_dir is None:
        output_dir = input_dir.parent / "tables"

    console.print(f"Input directory: {input_dir}")
    console.print(f"Output directory: {output_dir}\n")

    # Find cleaned parquet files
    cleaned_files = list(input_dir.glob("*_patient_cleaned.parquet"))
    if not cleaned_files:
        console.print(
            f"[bold red]Error: No cleaned parquet files found in {input_dir}[/bold red]\n"
        )
        raise typer.Exit(1)

    console.print(f"Found {len(cleaned_files)} cleaned parquet files\n")

    try:
        from a4d.tables.clinic import create_table_clinic_static

        console.print("[bold]Creating tables...[/bold]")

        # Create patient tables
        tables = process_patient_tables(input_dir, output_dir)

        # Create logs table separately (operational data)
        logs_dir = input_dir.parent / "logs"
        if logs_dir.exists():
            console.print("  • Creating logs table...")
            logs_table_path = create_table_logs(logs_dir, output_dir)
            tables["logs"] = logs_table_path
        else:
            console.print(f"  [yellow]Warning: Logs directory not found at {logs_dir}[/yellow]")

        # Create clinic static table (reads reference_data/clinic_data.xlsx)
        console.print("  • Creating clinic static table...")
        clinic_table_path = create_table_clinic_static(output_dir)
        tables["clinic_data_static"] = clinic_table_path

        # Display results
        console.print("\n[bold green]✓ Tables created successfully![/bold green]")
        _display_tables_summary(tables)

    except Exception as e:
        console.print(f"\n[bold red]Error creating tables: {e}[/bold red]\n")
        raise typer.Exit(1) from e


@app.command("upload-tables")
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
):
    """Upload pipeline output tables to BigQuery.

    Loads parquet files from the tables directory into the configured
    BigQuery dataset. By default, existing tables are replaced (matching
    the R pipeline behavior).

    \b
    Examples:
        # Upload tables from default output directory
        uv run a4d upload-tables --tables-dir output/tables

        # Upload to a specific dataset
        uv run a4d upload-tables --tables-dir output/tables --dataset tracker_dev

        # Append instead of replace
        uv run a4d upload-tables --tables-dir output/tables --append
    """
    from a4d.gcp.bigquery import load_pipeline_tables

    console.print("\n[bold blue]A4D BigQuery Upload[/bold blue]\n")
    console.print(f"Tables directory: {tables_dir}")

    if not tables_dir.exists():
        console.print(f"[bold red]Error: Directory not found: {tables_dir}[/bold red]\n")
        raise typer.Exit(1)

    try:
        results = load_pipeline_tables(
            tables_dir=tables_dir,
            dataset=dataset,
            project_id=project_id,
            replace=not append,
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


@app.command("download-trackers")
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
        uv run a4d download-trackers --destination /data/trackers

        # Download from specific bucket
        uv run a4d download-trackers --destination /data/trackers --bucket my-bucket
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


@app.command("upload-output")
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
        uv run a4d upload-output --source output/

        # Upload with prefix
        uv run a4d upload-output --source output/ --prefix 2024-01
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


@app.command("download-reference-data")
def download_reference_data_cmd() -> None:
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


@app.command("run-pipeline")
def run_pipeline_cmd(
    workers: Annotated[
        int | None,
        typer.Option(
            "--workers", "-w", help="Number of parallel workers (default: A4D_MAX_WORKERS)"
        ),
    ] = None,
    force: Annotated[
        bool, typer.Option("--force", help="Force reprocessing (ignore existing outputs)")
    ] = False,
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
):
    """Run the full end-to-end A4D pipeline.

    Executes all pipeline stages in sequence:
      0. Download reference data (clinic_data.xlsx) from Google Drive
      1. Download tracker files from Google Cloud Storage
      2. Extract and clean all tracker files
      3. Create final tables (static, monthly, annual, clinic)
      4. Upload output files to Google Cloud Storage
      5. Ingest tables into BigQuery

    All configuration is read from environment variables (A4D_*) or a .env file.

    \b
    Examples:
        # Full pipeline (download + process + upload)
        uv run a4d run-pipeline

        # Download latest files, process locally, skip upload
        uv run a4d run-pipeline --skip-upload

        # Process local files only, no download or upload
        uv run a4d run-pipeline --skip-download --skip-upload

        # Skip Drive download if clinic_data.xlsx is already current
        uv run a4d run-pipeline --skip-drive-download
    """
    from a4d.config import settings
    from a4d.gcp.bigquery import load_pipeline_tables
    from a4d.gcp.drive import download_clinic_data
    from a4d.gcp.storage import download_tracker_files, upload_output
    from a4d.reference.loaders import find_reference_data_dir
    from a4d.tables.clinic import create_table_clinic_static

    _workers = workers if workers is not None else settings.max_workers
    run_ts = datetime.now().strftime("%Y/%m/%d/%H%M%S")

    console.print("\n[bold blue]A4D Full Pipeline[/bold blue]\n")
    console.print(f"Data root:   {settings.data_root}")
    console.print(f"Output root: {settings.output_root}")
    console.print(f"Workers:     {_workers}")
    console.print(f"Project:     {settings.project_id}")
    console.print(f"Dataset:     {settings.dataset}")
    console.print(
        f"Drive:       {'yes' if not skip_drive_download else 'skipped (--skip-drive-download)'}"
    )
    console.print(f"Download:    {'yes' if not skip_download else 'skipped (--skip-download)'}")
    console.print(f"Upload:      {'yes' if not skip_upload else 'skipped (--skip-upload)'}")
    console.print()

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

    # Step 2+3 – Extract, clean and build tables
    console.print("[bold]Steps 2–3/5:[/bold] Processing tracker files...\n")
    try:
        result = run_patient_pipeline(
            max_workers=_workers,
            force=force,
            show_progress=True,
            console_log_level="WARNING",
        )

        console.print(
            f"  ✓ Processed {result.total_trackers} trackers "
            f"({result.successful_trackers} ok, {result.failed_trackers} failed)\n"
        )

        if result.failed_trackers > 0:
            console.print("[bold yellow]Failed trackers:[/bold yellow]")
            for tr in result.tracker_results:
                if not tr.success:
                    console.print(f"  • {tr.tracker_file.name}: {tr.error}")
            console.print()

        if not result.success:
            console.print("[bold red]✗ Pipeline failed – aborting upload steps[/bold red]\n")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"\n[bold red]Error during processing: {e}[/bold red]\n")
        raise typer.Exit(1) from e

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
