#!/usr/bin/env python3
"""Compare R vs Python cleaned parquet outputs for migration validation.

This script performs detailed comparison of cleaned patient data from
R and Python pipelines to verify the migration produces equivalent results.

Usage:
    uv run python scripts/compare_r_vs_python.py \\
        --r-parquet <path_to_r_output> \\
        --python-parquet <path_to_python_output>
"""

import polars as pl
import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console()
app = typer.Typer()


def display_basic_stats(r_df: pl.DataFrame, py_df: pl.DataFrame, file_name: str):
    """Display basic statistics about both datasets."""
    console.print(Panel(f"[bold]Comparing: {file_name}[/bold]", expand=False))

    stats_table = Table(title="Basic Statistics", box=box.ROUNDED)
    stats_table.add_column("Metric", style="cyan")
    stats_table.add_column("R Output", style="white", justify="right")
    stats_table.add_column("Python Output", style="white", justify="right")
    stats_table.add_column("Difference", justify="right")

    # Record counts
    r_count = len(r_df)
    py_count = len(py_df)
    diff_count = py_count - r_count
    diff_pct = (diff_count / r_count * 100) if r_count > 0 else 0
    diff_style = "green" if diff_count == 0 else "yellow" if abs(diff_pct) < 5 else "red"

    stats_table.add_row(
        "Records",
        f"{r_count:,}",
        f"{py_count:,}",
        f"[{diff_style}]{diff_count:+,} ({diff_pct:+.1f}%)[/{diff_style}]"
    )

    # Column counts
    r_cols = len(r_df.columns)
    py_cols = len(py_df.columns)
    col_diff = py_cols - r_cols
    col_style = "green" if col_diff == 0 else "yellow"

    stats_table.add_row(
        "Columns",
        f"{r_cols:,}",
        f"{py_cols:,}",
        f"[{col_style}]{col_diff:+,}[/{col_style}]"
    )

    console.print(stats_table)
    console.print()


def compare_schemas(r_df: pl.DataFrame, py_df: pl.DataFrame):
    """Compare column schemas between R and Python outputs."""
    console.print(Panel("[bold]Schema Comparison[/bold]", expand=False))

    r_cols = set(r_df.columns)
    py_cols = set(py_df.columns)
    common_cols = sorted(r_cols & py_cols)
    only_r = sorted(r_cols - py_cols)
    only_py = sorted(py_cols - r_cols)

    # Summary
    summary_table = Table(title="Column Summary", box=box.ROUNDED)
    summary_table.add_column("Category", style="cyan")
    summary_table.add_column("Count", justify="right", style="magenta")

    summary_table.add_row("Common columns", f"{len(common_cols):,}")
    summary_table.add_row("Only in R", f"{len(only_r):,}")
    summary_table.add_row("Only in Python", f"{len(only_py):,}")

    console.print(summary_table)
    console.print()

    # Columns only in R
    if only_r:
        console.print("[red]Columns missing in Python output:[/red]")
        for col in only_r[:20]:  # Limit to first 20
            r_type = str(r_df[col].dtype)
            null_count = r_df[col].is_null().sum()
            null_pct = (null_count / len(r_df)) * 100
            console.print(f"  • {col:40s} ({r_type:15s}, {null_pct:.1f}% null)")
        if len(only_r) > 20:
            console.print(f"  [dim]... and {len(only_r) - 20} more columns[/dim]")
        console.print()

    # Columns only in Python
    if only_py:
        console.print("[yellow]Extra columns in Python output:[/yellow]")
        for col in only_py[:20]:
            py_type = str(py_df[col].dtype)
            null_count = py_df[col].is_null().sum()
            null_pct = (null_count / len(py_df)) * 100
            console.print(f"  • {col:40s} ({py_type:15s}, {null_pct:.1f}% null)")
        if len(only_py) > 20:
            console.print(f"  [dim]... and {len(only_py) - 20} more columns[/dim]")
        console.print()

    # Type mismatches for common columns
    type_mismatches = []
    for col in common_cols:
        r_type = str(r_df[col].dtype)
        py_type = str(py_df[col].dtype)
        if r_type != py_type:
            type_mismatches.append((col, r_type, py_type))

    if type_mismatches:
        console.print("[yellow]Data type mismatches:[/yellow]")
        type_table = Table(box=box.SIMPLE)
        type_table.add_column("Column", style="cyan")
        type_table.add_column("R Type", style="white")
        type_table.add_column("Python Type", style="white")

        for col, r_type, py_type in type_mismatches[:20]:
            type_table.add_row(col, r_type, py_type)

        console.print(type_table)
        if len(type_mismatches) > 20:
            console.print(f"  [dim]... and {len(type_mismatches) - 20} more mismatches[/dim]")
        console.print()
    else:
        console.print("[green]✓ All data types match for common columns[/green]\n")


def compare_metadata_fields(r_df: pl.DataFrame, py_df: pl.DataFrame):
    """Compare critical metadata fields."""
    console.print(Panel("[bold]Metadata Fields Comparison[/bold]", expand=False))

    # Key metadata fields that must be identical
    metadata_fields = [
        "tracker_year", "tracker_month", "file_name",
        "national_id", "start_date", "end_date"
    ]

    existing_fields = [f for f in metadata_fields if f in r_df.columns and f in py_df.columns]

    if not existing_fields:
        console.print("[yellow]No common metadata fields found to compare[/yellow]\n")
        return

    for field in existing_fields:
        console.print(f"[bold cyan]{field}:[/bold cyan]")

        r_unique = r_df[field].unique().sort()
        py_unique = py_df[field].unique().sort()

        if r_unique.equals(py_unique):
            console.print(f"  [green]✓ Match ({len(r_unique):,} unique values)[/green]")
            # Show sample
            sample = r_unique.head(3).to_list()
            console.print(f"    Sample: {sample}")
        else:
            console.print(f"  [red]✗ Mismatch![/red]")
            console.print(f"    R has {len(r_unique):,} unique values")
            console.print(f"    Python has {len(py_unique):,} unique values")

            r_set = set(r_unique.to_list())
            py_set = set(py_unique.to_list())

            only_r = r_set - py_set
            only_py = py_set - r_set

            if only_r:
                console.print(f"    [yellow]Only in R:[/yellow] {list(only_r)[:5]}")
            if only_py:
                console.print(f"    [yellow]Only in Python:[/yellow] {list(only_py)[:5]}")

        console.print()


def compare_patient_records(r_df: pl.DataFrame, py_df: pl.DataFrame, n_samples: int = 5):
    """Compare sample patient records in detail."""
    console.print(Panel(f"[bold]Sample Patient Records (first {n_samples})[/bold]", expand=False))

    if "national_id" not in r_df.columns or "national_id" not in py_df.columns:
        console.print("[yellow]Cannot compare records: national_id column missing[/yellow]\n")
        return

    # Get first n national_ids from R
    sample_ids = r_df["national_id"].head(n_samples).to_list()

    for idx, national_id in enumerate(sample_ids, 1):
        console.print(f"\n[bold]Patient {idx}:[/bold] {national_id}")

        py_records = py_df.filter(pl.col("national_id") == national_id)

        if len(py_records) == 0:
            console.print("[red]  ✗ Not found in Python output![/red]")
            continue
        elif len(py_records) > 1:
            console.print(f"[yellow]  ⚠ Multiple records in Python ({len(py_records)})[/yellow]")

        # Compare key fields
        r_record = r_df.filter(pl.col("national_id") == national_id).head(1).to_dicts()[0]
        py_record = py_records.head(1).to_dicts()[0]

        comparison_fields = [
            "tracker_year", "tracker_month", "start_date", "end_date",
            "sex", "age_group", "diagnosis_malaria"
        ]

        comp_table = Table(box=box.SIMPLE, show_header=False)
        comp_table.add_column("Field", style="cyan", width=20)
        comp_table.add_column("R", style="white", width=25)
        comp_table.add_column("Python", style="white", width=25)
        comp_table.add_column("", justify="center", width=3)

        for field in comparison_fields:
            if field in r_record and field in py_record:
                r_val = r_record[field]
                py_val = py_record[field]
                match = "✓" if r_val == py_val else "✗"
                match_style = "green" if match == "✓" else "red"

                comp_table.add_row(
                    field,
                    str(r_val)[:25],
                    str(py_val)[:25],
                    f"[{match_style}]{match}[/{match_style}]"
                )

        console.print(comp_table)

    console.print()


def find_value_mismatches(r_df: pl.DataFrame, py_df: pl.DataFrame):
    """Find all value differences for common records."""
    console.print(Panel("[bold]Value Mismatches Analysis[/bold]", expand=False))

    if "national_id" not in r_df.columns or "national_id" not in py_df.columns:
        console.print("[yellow]Cannot analyze values: national_id column missing[/yellow]\n")
        return

    # Join on national_id
    try:
        joined = r_df.join(py_df, on="national_id", how="inner", suffix="_py")
        console.print(f"[cyan]Analyzing {len(joined):,} common records (matched on national_id)[/cyan]\n")
    except Exception as e:
        console.print(f"[red]Error joining datasets: {e}[/red]\n")
        return

    # Find columns in both datasets
    common_cols = set(r_df.columns) & set(py_df.columns) - {"national_id"}

    mismatches = {}

    for col in sorted(common_cols):
        col_py = f"{col}_py"
        if col in joined.columns and col_py in joined.columns:
            try:
                # Count mismatches
                mismatched_rows = joined.filter(pl.col(col) != pl.col(col_py))
                mismatch_count = len(mismatched_rows)

                if mismatch_count > 0:
                    mismatch_pct = (mismatch_count / len(joined)) * 100
                    mismatches[col] = {
                        "count": mismatch_count,
                        "percentage": mismatch_pct,
                        "examples": mismatched_rows.select([col, col_py]).head(3)
                    }
            except Exception:
                # Some columns might not support comparison
                pass

    if mismatches:
        mismatch_table = Table(title="Value Mismatches for Common Records", box=box.ROUNDED)
        mismatch_table.add_column("Column", style="cyan")
        mismatch_table.add_column("Mismatches", justify="right", style="red")
        mismatch_table.add_column("%", justify="right")
        mismatch_table.add_column("Priority", justify="center")

        for col, stats in sorted(mismatches.items(), key=lambda x: x[1]["percentage"], reverse=True):
            # Determine priority
            if col in ["national_id", "tracker_year", "tracker_month", "start_date", "end_date"]:
                priority = "[red]HIGH[/red]"
            elif stats["percentage"] > 10:
                priority = "[yellow]MEDIUM[/yellow]"
            else:
                priority = "[dim]LOW[/dim]"

            mismatch_table.add_row(
                col,
                f"{stats['count']:,}",
                f"{stats['percentage']:.1f}%",
                priority
            )

        console.print(mismatch_table)

        # Show some examples
        console.print("\n[dim]Examples of mismatches (first 3 columns with highest mismatch %):[/dim]")
        for col, stats in list(sorted(mismatches.items(), key=lambda x: x[1]["percentage"], reverse=True))[:3]:
            console.print(f"\n[bold]{col}:[/bold]")
            console.print(stats["examples"])

    else:
        console.print("[green]✓ All values match for common records![/green]")

    console.print()


def display_summary(r_df: pl.DataFrame, py_df: pl.DataFrame):
    """Display final summary with actionable insights."""
    console.print(Panel("[bold]Summary & Recommendations[/bold]", expand=False))

    r_count = len(r_df)
    py_count = len(py_df)
    record_match = r_count == py_count

    r_cols = set(r_df.columns)
    py_cols = set(py_df.columns)
    schema_match = r_cols == py_cols

    summary_table = Table(box=box.ROUNDED)
    summary_table.add_column("Check", style="cyan")
    summary_table.add_column("Status", justify="center")
    summary_table.add_column("Details")

    # Record counts
    record_icon = "[green]✓[/green]" if record_match else "[red]✗[/red]"
    record_detail = f"Both have {r_count:,} records" if record_match else f"R: {r_count:,}, Python: {py_count:,}"
    summary_table.add_row("Record counts", record_icon, record_detail)

    # Schema
    schema_icon = "[green]✓[/green]" if schema_match else "[yellow]⚠[/yellow]"
    schema_detail = f"Both have {len(r_cols)} columns" if schema_match else f"R: {len(r_cols)}, Python: {len(py_cols)}"
    summary_table.add_row("Schema match", schema_icon, schema_detail)

    console.print(summary_table)
    console.print()

    # Recommendations
    if not record_match or not schema_match:
        console.print("[bold]Recommendations:[/bold]")
        if not record_match:
            console.print("  1. [yellow]Investigate record count differences[/yellow]")
            console.print("     - Check data filtering logic")
            console.print("     - Review cleaning validation rules")
        if not schema_match:
            console.print("  2. [yellow]Review schema differences[/yellow]")
            console.print("     - Ensure all R columns are mapped in Python")
            console.print("     - Validate extra Python columns are intentional")
    else:
        console.print("[green]✓ Basic validation passed! Record counts and schemas match.[/green]")
        console.print("[dim]Review value mismatches above to ensure data quality.[/dim]")

    console.print()


@app.command()
def compare(
    r_parquet: Path = typer.Option(..., "--r-parquet", "-r", help="R pipeline output (cleaned parquet)"),
    python_parquet: Path = typer.Option(..., "--python-parquet", "-p", help="Python pipeline output (cleaned parquet)"),
):
    """Compare R vs Python cleaned patient data outputs."""

    console.print("\n[bold blue]A4D Migration Validation: R vs Python Comparison[/bold blue]\n")

    # Read data
    console.print("[bold]Loading data...[/bold]")

    try:
        r_df = pl.read_parquet(r_parquet)
        console.print(f"  ✓ R output: {len(r_df):,} records, {len(r_df.columns)} columns")
    except Exception as e:
        console.print(f"[red]  ✗ Failed to read R parquet: {e}[/red]")
        raise typer.Exit(1)

    try:
        py_df = pl.read_parquet(python_parquet)
        console.print(f"  ✓ Python output: {len(py_df):,} records, {len(py_df.columns)} columns")
    except Exception as e:
        console.print(f"[red]  ✗ Failed to read Python parquet: {e}[/red]")
        raise typer.Exit(1)

    console.print()

    # Run comparisons
    file_name = r_parquet.name
    display_basic_stats(r_df, py_df, file_name)
    compare_schemas(r_df, py_df)
    compare_metadata_fields(r_df, py_df)
    compare_patient_records(r_df, py_df, n_samples=3)
    find_value_mismatches(r_df, py_df)
    display_summary(r_df, py_df)

    console.print(Panel("[bold green]Comparison Complete[/bold green]", expand=False))
    console.print()


if __name__ == "__main__":
    app()
