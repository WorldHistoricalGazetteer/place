# merge_duckdbs.py
import duckdb
import sys
from pathlib import Path

from process_parquet_batch import create_duck_tables


def merge_duckdbs(input_dir: Path, output_path: Path):
    db_files = sorted(p for p in input_dir.rglob("*.duckdb") if p != output_path)
    if not db_files:
        print("No DuckDB files found.")
        return

    print(f"Found {len(db_files)} batch DBs. Merging into: {output_path}")
    con = duckdb.connect(str(output_path))
    con.execute("PRAGMA threads=4;")

    create_duck_tables(con)

    for i, db_path in enumerate(db_files):
        alias = f"db_{i}"
        con.execute(f"ATTACH DATABASE '{db_path}' AS {alias};")

        # Insert while avoiding duplicates
        con.execute(f"""
            INSERT INTO place
            SELECT * FROM {alias}.place
            EXCEPT SELECT * FROM place;
        """)
        con.execute(f"""
            INSERT INTO toponym
            SELECT * FROM {alias}.toponym
            EXCEPT SELECT * FROM toponym;
        """)
        con.execute(f"""
            INSERT INTO link
            SELECT * FROM {alias}.link
            EXCEPT SELECT * FROM link;
        """)

        con.execute(f"DETACH DATABASE {alias};")

    con.close()
    print("Merge complete.")

if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python merge_duckdbs.py <input_dir> <output_db>")
        sys.exit(1)

    merge_duckdbs(Path(sys.argv[1]), Path(sys.argv[2]))
