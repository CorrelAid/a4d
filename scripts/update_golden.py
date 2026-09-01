"""Regenerate the committed golden-master files from the synthetic tracker.

Run via `just golden-update` after a deliberate change to what the pipeline
publishes, then read the resulting diff before committing it.
"""

import sys
import tempfile
from pathlib import Path

import polars as pl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.test_golden.test_golden_master import (  # noqa: E402
    GOLDEN_DIR,
    build_golden_output,
)


def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        frames = build_golden_output(Path(tmp))

    for name, df in frames.items():
        as_text = df.select([pl.col(c).cast(pl.Utf8).alias(c) for c in df.columns])
        as_text.write_csv(GOLDEN_DIR / f"{name}.csv")
        print(f"wrote {name}.csv ({df.height} rows x {df.width} columns)")

    for arm in ("patient", "product"):
        schema = frames[f"{arm}_cleaned"].schema
        dtypes = pl.DataFrame(
            {"column": list(schema.keys()), "dtype": [str(t) for t in schema.values()]}
        )
        dtypes.write_csv(GOLDEN_DIR / f"{arm}_dtypes.csv")
        print(f"wrote {arm}_dtypes.csv ({dtypes.height} columns)")


if __name__ == "__main__":
    main()
