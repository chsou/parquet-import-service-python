"""Replace the source of selected rows in a parquet file with an invalid one.

Positions are row indexes (negative counts from the end) or the keywords begin, middle, end.
The input file is left untouched unless --output points at it.

Example:
    uv run python scripts/invalidate_parquet.py data.parquet --at begin middle 42 -o bad.parquet
"""

import argparse
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq


def resolve(position: str, rows: int) -> int:
    index = {"begin": 0, "middle": rows // 2, "end": rows - 1}.get(position)
    if index is None:
        index = int(position)
        if index < 0:
            index += rows
    if not 0 <= index < rows:
        raise SystemExit(f"Position '{position}' is outside the file ({rows} rows).")
    return index


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("file", help="input parquet file")
    p.add_argument("--at", nargs="+", required=True, help="rows to invalidate: indexes or begin/middle/end")
    p.add_argument("--invalid-source", default="999999999999", help="replacement source (default: 999999999999)")
    p.add_argument("-o", "--output", help="output file (default: <input>.invalid.parquet)")
    args = p.parse_args()

    table = pq.read_table(args.file)
    indexes = {resolve(position, table.num_rows) for position in args.at}

    sources = table.column("source").to_pylist()
    for i in indexes:
        sources[i] = args.invalid_source
    table = table.set_column(table.schema.get_field_index("source"), "source", pa.array(sources, type=pa.string()))

    output = args.output or str(Path(args.file).with_suffix(".invalid.parquet"))
    pq.write_table(table, output)
    print(f"Wrote {output} (invalid source '{args.invalid_source}' at rows {sorted(indexes)})")


if __name__ == "__main__":
    main()
