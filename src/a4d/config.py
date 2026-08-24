"""Application configuration using Pydantic Settings."""

from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env into os.environ so non-prefixed vars like GOOGLE_APPLICATION_CREDENTIALS
# are visible to third-party SDKs (Google Auth, etc.) without requiring a manual export.
load_dotenv(override=False)


class Settings(BaseSettings):
    """
    Application configuration with environment variable support.

    All settings can be overridden with environment variables prefixed with A4D_.
    Example: A4D_DATA_ROOT=/path/to/data
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="A4D_",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "production"] = "development"

    # GCP Configuration
    project_id: str = "a4dphase2"
    dataset: str = "tracker"
    download_bucket: str = "a4dphase2_upload"
    upload_bucket: str = "a4dphase2_output"

    # Paths
    data_root: Path = Path("/Volumes/USB SanDisk 3.2Gen1 Media/a4d/a4dphase2_upload")
    output_dir: Path = Path("output")

    # Processing settings
    max_workers: int = 4

    # Sentinels for 'recorded but unusable'. Distinct from null, which means
    # nothing was recorded at all -- consumers need to tell the two apart.
    error_val_numeric: float = 999999.0
    error_val_character: str = "Undefined"
    error_val_date: str = "9999-09-09"

    # Accepted tracker year range (raise on out-of-range sheet-name or filename)
    min_tracker_year: int = 2017
    max_tracker_year: int = 2030

    @property
    def output_root(self) -> Path:
        """Computed output root path."""
        return self.data_root / self.output_dir

    @property
    def tracker_root(self) -> Path:
        """Tracker files root directory."""
        return self.data_root


# Global settings instance
settings = Settings()
