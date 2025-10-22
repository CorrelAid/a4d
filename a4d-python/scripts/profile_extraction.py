"""Profile patient data extraction to identify performance bottlenecks."""

import cProfile
import pstats
from pathlib import Path
from pstats import SortKey

from a4d.extract.patient import extract_patient_data

# Test with both 2019 and 2024 trackers
TRACKER_2024 = Path(
    "/Volumes/USB SanDisk 3.2Gen1 Media/A4D/data/a4dphase2_upload/"
    "Malaysia/SBU/2024_Sibu Hospital A4D Tracker.xlsx"
)
TRACKER_2019 = Path(
    "/Volumes/USB SanDisk 3.2Gen1 Media/A4D/data/a4dphase2_upload/"
    "Malaysia/PNG/2019_Penang General Hospital A4D Tracker_DC.xlsx"
)


def profile_extraction():
    """Run extraction with profiling."""
    print("=" * 80)
    print("Profiling 2024 tracker (Jan24)")
    print("=" * 80)

    profiler_2024 = cProfile.Profile()
    profiler_2024.enable()

    df_2024 = extract_patient_data(TRACKER_2024, "Jan24", 2024)

    profiler_2024.disable()

    print(f"\nExtracted: {len(df_2024)} rows × {len(df_2024.columns)} columns")
    print("\nTop 20 functions by cumulative time:")
    print("-" * 80)

    stats_2024 = pstats.Stats(profiler_2024)
    stats_2024.strip_dirs()
    stats_2024.sort_stats(SortKey.CUMULATIVE)
    stats_2024.print_stats(20)

    print("\n" + "=" * 80)
    print("Profiling 2019 tracker (Feb19 - largest sheet)")
    print("=" * 80)

    profiler_2019 = cProfile.Profile()
    profiler_2019.enable()

    df_2019 = extract_patient_data(TRACKER_2019, "Feb19", 2019)

    profiler_2019.disable()

    print(f"\nExtracted: {len(df_2019)} rows × {len(df_2019.columns)} columns")
    print("\nTop 20 functions by cumulative time:")
    print("-" * 80)

    stats_2019 = pstats.Stats(profiler_2019)
    stats_2019.strip_dirs()
    stats_2019.sort_stats(SortKey.CUMULATIVE)
    stats_2019.print_stats(20)

    # Save detailed stats to file
    output_dir = Path(__file__).parent.parent / "profiling"
    output_dir.mkdir(exist_ok=True)

    stats_2024.dump_stats(output_dir / "extraction_2024.prof")
    stats_2019.dump_stats(output_dir / "extraction_2019.prof")

    print("\n" + "=" * 80)
    print(f"Detailed profiling data saved to {output_dir}/")
    print("View with: python -m pstats profiling/extraction_2024.prof")
    print("=" * 80)


if __name__ == "__main__":
    profile_extraction()
