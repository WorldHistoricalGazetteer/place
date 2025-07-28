import logging
import sys
import pyarrow as pa
import pyarrow.parquet as pq
import os
import asyncio

from tqdm import tqdm
from streamer import StreamFetcher
from config import REMOTE_DATASET_CONFIGS

logger = logging.getLogger(__name__)

BATCH_SIZE = 10_000
BASE_DATA_DIR = "/ix1/whcdh/data"


def get_dataset_config(name):
    return next(cfg for cfg in REMOTE_DATASET_CONFIGS if cfg["dataset_name"] == name)


async def fetch_and_split(dataset_name, output_dir, batch_size=BATCH_SIZE):
    cfg = get_dataset_config(dataset_name)
    os.makedirs(output_dir, exist_ok=True)

    for file_cfg in cfg["files"]:
        label = os.path.splitext(os.path.basename(file_cfg["file_name"]))[0]
        file_out_dir = os.path.join(output_dir, label)
        os.makedirs(file_out_dir, exist_ok=True)

        sf = StreamFetcher(file_cfg)
        sf.ingestion_path = file_out_dir
        items_iter = sf.get_items()
        batch, batch_idx = [], 0

        pbar = tqdm(desc=f"Processing {label}", unit="items", ncols=80)

        async for item in items_iter:
            batch.append(item)
            pbar.update(1)
            if len(batch) >= batch_size:
                path = os.path.join(file_out_dir, f"batch_{batch_idx:06}.parquet")
                pq.write_table(pa.Table.from_pylist(batch), path)
                batch.clear()
                batch_idx += 1

        # flush remaining
        if batch:
            path = os.path.join(file_out_dir, f"batch_{batch_idx:06}.parquet")
            pq.write_table(pa.Table.from_pylist(batch), path)
            batch_idx += 1
            batch.clear()

        pbar.close()
        logger.info(f"Wrote {batch_idx} shard files to {file_out_dir}")


if __name__ == "__main__":
    ds = sys.argv[1] if len(sys.argv) > 1 else "GeoNames"
    out = sys.argv[2] if len(sys.argv) > 2 else f"{BASE_DATA_DIR}/{ds.lower()}/batches"
    asyncio.run(fetch_and_split(ds, out))
