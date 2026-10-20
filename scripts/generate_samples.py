"""Generate three 1000-row sample parquet files, each with one row of an invalid source.

All rows use the same (valid) source, except a single row at the beginning, middle or end
of the file, which uses an invalid one. Useful to test how a bulk upload handles a bad row.

Example:
    uv run python scripts/generate_samples.py --source 12345 -o samples
"""

import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

ROWS = 1000
START = datetime(2026, 1, 1, tzinfo=timezone.utc)  # static, so the files are reproducible


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--source", required=True, help="valid device ID used for all regular rows")
    p.add_argument("--invalid-source", default="999999999999", help="source of the bad row (default: 999999999999)")
    p.add_argument("-o", "--output-dir", default="samples", help="output directory (default: samples)")
    args = p.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    positions = {"begin": 0, "middle": ROWS // 2, "end": ROWS - 1}
    for name, bad in positions.items():
        table = pa.table(
            {
                "timestamp": pa.array([START + timedelta(seconds=i) for i in range(ROWS)], type=pa.timestamp("us", tz="UTC")),
                "source": [args.invalid_source if i == bad else args.source for i in range(ROWS)],
                "series": ["sample.value"] * ROWS,
                "value": [float(i) for i in range(ROWS)],
            }
        )
        path = out / f"invalid_{name}.parquet"
        pq.write_table(table, path)
        print(f"Wrote {path} (invalid source at row {bad})")


if __name__ == "__main__":
    main()
