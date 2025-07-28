import sys
import duckdb
import msgpack
import gzip

import logging
from pathlib import Path

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

DEFAULT_BATCH_SIZE = 10_000


def write_batch_to_msgpack(rows, output_path: Path):
    with gzip.open(output_path, "wb") as f:
        for row in rows:
            packed = msgpack.packb(row, use_bin_type=True)
            f.write(packed)
            f.write(b"\n")  # NDMessagePack requires newline-delimited records

    logger.info(f"Wrote {len(rows):,} records to {output_path}")


def export_to_msgpack(duckdb_path: str, output_dir: str, batch_size: int = DEFAULT_BATCH_SIZE):
    duckdb_path = Path(duckdb_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not duckdb_path.exists():
        raise FileNotFoundError(f"DuckDB file not found: {duckdb_path}")

    logger.info(f"Opening DuckDB file: {duckdb_path}")
    con = duckdb.connect(str(duckdb_path))

    logger.info("Exporting all rows from 'main' table...")  # TODO: Fix this with actual schema
    table = con.execute("SELECT * FROM main").arrow()
    total_rows = table.num_rows
    logger.info(f"Total rows: {total_rows:,}")

    rows = table.to_pylist()
    num_batches = (total_rows + batch_size - 1) // batch_size

    for i in range(num_batches):
        start = i * batch_size
        end = min(start + batch_size, total_rows)
        batch_rows = rows[start:end]
        batch_file = output_dir / f"batch_{i:04}.ndmsgpack.gz"
        write_batch_to_msgpack(batch_rows, batch_file)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Usage: python export_to_msgpack.py <input.duckdb> <output_dir> [batch_size]")
        sys.exit(1)

    input_db = sys.argv[1]
    output_dir = sys.argv[2]
    batch_size = int(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_BATCH_SIZE

    export_to_msgpack(input_db, output_dir, batch_size)
