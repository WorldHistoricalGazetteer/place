import sys
import asyncio

import duckdb

from ..transformers import DocTransformer


def create_duck_tables(con: duckdb.DuckDBPyConnection, drop_existing: bool = False):
    schemas = {
        "place": """
            id TEXT PRIMARY KEY,
            record_id TEXT,
            record_url TEXT,
            names JSON,
            locations JSON[],
            bbox_sw_lat DOUBLE,
            bbox_sw_lng DOUBLE,
            bbox_ne_lat DOUBLE,
            bbox_ne_lng DOUBLE,
            convex_hull JSON,
            representative_point JSON,
            cartesian JSON,
            types TEXT[],
            classes TEXT[],
            ccodes TEXT[],
            year_start INT,
            year_end INT,
            lpf_feature JSON,
            meta JSON
        """,
        "toponym": """
            id TEXT PRIMARY KEY,
            name_strict TEXT,
            name TEXT,
            bcp47_language TEXT,
            places JSON 
        """,
        "link": """
            place_id TEXT,
            predicate TEXT,
            object TEXT,
            PRIMARY KEY (place_id, predicate, object)
        """
    }
    for table_name, columns_sql in schemas.items():
        if drop_existing:
            con.execute(f"DROP TABLE IF EXISTS {table_name};")
        create_sql = f"CREATE TABLE {table_name} ({columns_sql});"
        con.execute(create_sql)


class ParquetBatchTransformer:

    def __init__(self, parquet_path, db_path='places.duckdb', batch_size=1000):
        self.parquet_path = parquet_path
        self.db_path = db_path
        self.batch_size = batch_size

        self.places_buffer = []
        self.toponyms_buffer = []
        self.links_buffer = []

        self.conn = duckdb.connect(database=self.db_path, read_only=False)
        create_duck_tables(self.conn, drop_existing=True)

    async def transform_and_store(self, document):
        place, toponyms, links = DocTransformer.transform(document, self.dataset_name, self.transformer_index)

        if place:
            self.places_buffer.append(place)
        if toponyms:
            self.toponyms_buffer.extend(toponyms)
        if links:
            self.links_buffer.extend(links)

        if len(self.places_buffer) >= self.batch_size:
            await asyncio.to_thread(self._insert_places_batch, self.places_buffer)
            self.places_buffer.clear()

        if len(self.toponyms_buffer) >= self.batch_size:
            await asyncio.to_thread(self._insert_toponyms_batch, self.toponyms_buffer)
            self.toponyms_buffer.clear()

        if len(self.links_buffer) >= self.batch_size:
            await asyncio.to_thread(self._insert_links_batch, self.links_buffer)
            self.links_buffer.clear()

    async def flush_all(self):
        if self.places_buffer:
            await asyncio.to_thread(self._insert_places_batch, self.places_buffer)
            self.places_buffer.clear()

        if self.toponyms_buffer:
            await asyncio.to_thread(self._insert_toponyms_batch, self.toponyms_buffer)
            self.toponyms_buffer.clear()

        if self.links_buffer:
            await asyncio.to_thread(self._insert_links_batch, self.links_buffer)
            self.links_buffer.clear()

    def _insert_places_batch(self, places):
        # DuckDB supports standard SQL MERGE via UPSERT pattern but simpler to do INSERT with ON CONFLICT REPLACE in latest versions
        # We'll do a naive insert with handling duplicates by ignoring them here with "ON CONFLICT DO NOTHING"
        records = [(p['id'], str(p)) for p in places]  # Adapt serialization to your needs
        self.conn.executemany('''
                              INSERT INTO places (id, data)
                              VALUES (?, ?) ON CONFLICT(id) DO NOTHING
                              ''', records)

    def _insert_toponyms_batch(self, toponyms):
        records = [(t['id'], str(t)) for t in toponyms]
        self.conn.executemany('''
                              INSERT INTO toponyms (id, data)
                              VALUES (?, ?) ON CONFLICT(id) DO NOTHING
                              ''', records)

    def _insert_links_batch(self, links):
        records = [(l['id'], l['source'], l['target'], str(l)) for l in links]
        self.conn.executemany('''
                              INSERT INTO links (id, source, target, data)
                              VALUES (?, ?, ?, ?) ON CONFLICT(id) DO NOTHING
                              ''', records)

    async def process_batch(self):
        df = pd.read_parquet(self.parquet_path)
        self.dataset_name = "your_dataset_name"  # adjust or pass via constructor
        self.transformer_index = 0  # adjust or pass via constructor

        for _, document in df.iterrows():
            await self.transform_and_store(document)

        await self.flush_all()

    def close(self):
        self.conn.close()


async def run(parquet_path, db_path):
    transformer = ParquetBatchTransformer(parquet_path, db_path=db_path)
    await transformer.process_batch()
    transformer.close()


if __name__ == "__main__":
    parquet_path = sys.argv[1]
    db_path = sys.argv[2]
    asyncio.run(run(parquet_path, db_path))
