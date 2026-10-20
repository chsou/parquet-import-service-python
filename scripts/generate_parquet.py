"""Generate a parquet file with random measurement data.

Columns: timestamp, source, series, value.

Example:
    uv run python scripts/generate_parquet.py \
        --rows 1000000 --sources 123 456 789 --series 20 -o data.parquet
"""

import argparse
from datetime import datetime, timezone

import numpy as np
import pyarrow as pa
import pyarrow.parquet as pq

WORDS = """
able acid agent alarm amber angle apple arrow atlas badge baker basin beach beam berry bike birch blade blue bolt bone
brass bread brick bridge brook cable camel candle canyon cargo cedar chain chalk charm cliff cloud coast comet coral
cotton crane creek crown cycle daisy delta desert diesel dove dream drift eagle earth ember engine fabric falcon feather
fern field flame flint forest fox frost garden gate gear glass globe gold grain granite grove harbor hawk hazel heart
hill honey horizon iron island ivory jade jungle kettle lake lamp lantern leaf lemon light lily lunar maple marble meadow
mirror moon moss mount nectar night north oak ocean olive orbit otter paper pearl pine planet plum polar pond prairie
quartz rain raven reef ridge river robin rocket saddle sage sand shadow silver sky snow solar spark spring star stone
storm stream summer sun swan tiger timber tower trail tulip valley velvet violet water willow wind winter wolf zenith
""".split()


def make_series(count: int, rng: np.random.Generator) -> list[str]:
    """Generate `count` distinct series names of the form a.b from random words."""
    if count > len(WORDS) ** 2:
        raise SystemExit(f"At most {len(WORDS) ** 2} distinct series are possible with the built-in word list.")
    names: set[str] = set()
    while len(names) < count:
        a, b = rng.choice(WORDS, size=2)
        names.add(f"{a}.{b}")
    return sorted(names)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--rows", type=int, required=True, help="total number of rows")
    p.add_argument("--sources", nargs="+", required=True, help="source (managed object) IDs to draw from")
    p.add_argument("--series", type=int, required=True, help="number of distinct series")
    p.add_argument("--start", default=None, help="start time, ISO 8601 (default: now minus rows*step)")
    p.add_argument("--step", type=float, default=1.0, help="seconds between consecutive rows (default: 1)")
    p.add_argument("--seed", type=int, default=None, help="random seed for reproducible output")
    p.add_argument("-o", "--output", default="data.parquet", help="output file (default: data.parquet)")
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)

    step_us = int(args.step * 1_000_000)
    if args.start:
        start = datetime.fromisoformat(args.start)
        if start.tzinfo is None:
            start = start.replace(tzinfo=timezone.utc)
    else:
        start = datetime.now(timezone.utc)
        start = datetime.fromtimestamp(start.timestamp() - args.rows * args.step, timezone.utc)
    start_us = int(start.timestamp() * 1_000_000)

    timestamps = start_us + np.arange(args.rows, dtype=np.int64) * step_us
    series = make_series(args.series, rng)

    table = pa.table(
        {
            "timestamp": pa.array(timestamps, type=pa.timestamp("us", tz="UTC")),
            "source": pa.array(rng.choice(np.array(args.sources), size=args.rows)),
            "series": pa.array(rng.choice(np.array(series), size=args.rows)),
            "value": pa.array(rng.uniform(0, 100, size=args.rows)),
        }
    )
    pq.write_table(table, args.output)
    print(f"Wrote {args.rows} rows ({len(args.sources)} sources, {len(series)} series) to {args.output}")


if __name__ == "__main__":
    main()
