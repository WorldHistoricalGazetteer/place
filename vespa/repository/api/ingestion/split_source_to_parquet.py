import logging
import sys

import pyarrow as pa
import pyarrow.parquet as pq
import os
import asyncio
from .streamer import StreamFetcher
from .config import REMOTE_DATASET_CONFIGS

logger = logging.getLogger(__name__)

BATCH_SIZE = 10_000
BASE_DATA_DIR = "/ix1/whcdh/data"


def get_dataset_config(name):
    return next(cfg for cfg in REMOTE_DATASET_CONFIGS if cfg["dataset_name"] == name)


async def fetch_and_split(dataset_name, output_dir, batch_size=BATCH_SIZE):
    cfg = get_dataset_config(dataset_name)
    os.makedirs(output_dir, exist_ok=True)
    batch, batch_idx = [], 0

    for file_cfg in cfg["files"]:
        sf = StreamFetcher(file_cfg)
        items_iter = sf.get_items()
        async for item in items_iter:
            batch.append(item)
            if len(batch) >= batch_size:
                path = os.path.join(output_dir, f"batch_{batch_idx:06}.parquet")
                pq.write_table(pa.Table.from_pylist(batch), path)
                batch.clear()
                batch_idx += 1

        # flush remaining
        if batch:
            path = os.path.join(output_dir, f"batch_{batch_idx:06}.parquet")
            pq.write_table(pa.Table.from_pylist(batch), path)
            batch_idx += 1
            batch.clear()
    print(f"Wrote {batch_idx} shard files to {output_dir}")


if __name__ == "__main__":
    ds = sys.argv[1] if len(sys.argv) > 1 else "GeoNames"
    out = sys.argv[2] if len(sys.argv) > 2 else f"{BASE_DATA_DIR}/{ds.lower()}/batches"
    asyncio.run(fetch_and_split(ds, out))
