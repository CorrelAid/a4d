"""Single tracker processing: extract + clean."""

from pathlib import Path

from loguru import logger

from a4d.clean.patient import clean_patient_file
from a4d.errors import ErrorCollector
from a4d.extract.patient import export_patient_raw, read_all_patient_sheets
from a4d.logging import file_logger
from a4d.pipeline.models import TrackerResult
from a4d.reference.synonyms import ColumnMapper


def process_tracker_patient(
    tracker_file: Path, output_root: Path, mapper: ColumnMapper | None = None
) -> TrackerResult:
    """Process single tracker file: extract + clean patient data.

    This function processes one tracker file end-to-end:
    1. Extract patient data from Excel
    2. Export to raw parquet
    3. Clean the raw data
    4. Export to cleaned parquet

    Each step creates a separate log file for debugging.

    Args:
        tracker_file: Path to tracker Excel file
        output_root: Root output directory (will create subdirs for raw/cleaned)
        mapper: ColumnMapper for synonym mapping (loaded if not provided)

    Returns:
        TrackerResult with paths to outputs and success status

    Example:
        >>> tracker_file = Path("/data/2024_Sibu.xlsx")
        >>> output_root = Path("output")
        >>> result = process_tracker_patient(tracker_file, output_root)
        >>> result.success
        True
        >>> result.raw_output
        Path('output/patient_data_raw/2024_Sibu_patient_raw.parquet')
    """
    tracker_name = tracker_file.stem

    try:
        # Setup directories
        raw_dir = output_root / "patient_data_raw"
        cleaned_dir = output_root / "patient_data_cleaned"
        raw_dir.mkdir(parents=True, exist_ok=True)
        cleaned_dir.mkdir(parents=True, exist_ok=True)

        # Expected output paths
        raw_output = raw_dir / f"{tracker_name}_patient_raw.parquet"
        cleaned_output = cleaned_dir / f"{tracker_name}_patient_cleaned.parquet"

        # Log context for this tracker
        with file_logger(f"{tracker_name}_patient", output_root):
            logger.info(f"Processing tracker: {tracker_file.name}")

            # STEP 1: Extract
            logger.info("Step 1: Extracting patient data from Excel")
            error_collector = ErrorCollector()

            df_raw = read_all_patient_sheets(
                tracker_file=tracker_file, mapper=mapper, error_collector=error_collector
            )
            logger.info(f"Extracted {len(df_raw)} rows")

            # Export raw parquet
            raw_output = export_patient_raw(
                df=df_raw, tracker_file=tracker_file, output_dir=raw_dir
            )
            logger.info(f"Raw parquet saved: {raw_output}")

            # STEP 2: Clean
            logger.info("Step 2: Cleaning patient data")

            clean_patient_file(
                raw_parquet_path=raw_output,
                output_parquet_path=cleaned_output,
                error_collector=error_collector,
            )

            error_count = len(error_collector)
            error_breakdown = error_collector.get_error_summary()
            logger.info(f"Cleaned parquet saved: {cleaned_output}")
            logger.info(f"Total data quality errors: {error_count}")
            if error_breakdown:
                logger.info(f"Error breakdown: {error_breakdown}")

        return TrackerResult(
            tracker_file=tracker_file,
            tracker_name=tracker_name,
            raw_output=raw_output,
            cleaned_output=cleaned_output,
            success=True,
            error=None,
            cleaning_errors=error_count,
            error_breakdown=error_breakdown if error_breakdown else None,
            data_errors=error_collector.errors.copy(),
        )

    except Exception as e:
        logger.bind(error_code="critical_abort").exception(
            f"Failed to process tracker: {tracker_file.name}"
        )
        return TrackerResult(
            tracker_file=tracker_file,
            tracker_name=tracker_name,
            raw_output=None,
            cleaned_output=None,
            success=False,
            error=str(e),
        )
