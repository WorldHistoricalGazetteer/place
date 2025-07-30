import logging
import pprint
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import os
import asyncio

from tqdm import tqdm
from streamer import StreamFetcher
from config import REMOTE_DATASET_CONFIGS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

BASE_DATA_DIR = "/ix1/whcdh/data"

BATCH_SIZE = 10_000
BATCH_CPUS_PER_TASK = 2  # 2 CPUs for each batch job
BATCH_MEMORY_PER_TASK = "4G"  # 4GB memory for each batch job
BATCH_TIME_LIMIT = "01:00:00"  # 1 hour for each batch job


def get_dataset_config(name):
    return next(cfg for cfg in REMOTE_DATASET_CONFIGS if cfg["dataset_name"] == name)


def extract_job_id_from_output(output):
    """Extracts the job ID from the SLURM output string."""
    match = re.search(r"Submitted batch job (\d+)", output)
    if not match:
        raise RuntimeError("Failed to extract SLURM job ID")
    return match.group(1)


def submit_slurm_array_job(manifest_path):
    job_script = f"""#!/bin/bash
        #SBATCH --job-name=parquet_transform
        #SBATCH --output=slurm_logs/%x-%A_%a.out
        #SBATCH --error=slurm_logs/%x-%A_%a.err
        #SBATCH --time={BATCH_TIME_LIMIT}
        #SBATCH --cpus-per-task={BATCH_CPUS_PER_TASK}
        #SBATCH --mem={BATCH_MEMORY_PER_TASK}   
        #SBATCH --array=0-{{N}}
    
        source /home/gazetteer/miniconda/etc/profile.d/conda.sh
        conda activate vespa-env
        cd  ~/repository/place/vespa/repository/api/ingestion/slurm
        
        batch_file=$(sed -n "${{SLURM_ARRAY_TASK_ID}}p" {manifest_path})
        db_path="${{batch_file%.parquet}}.duckdb"
        
        python process_parquet_batch.py "$batch_file" "$db_path"
        """

    with open(manifest_path, "r") as f:
        num_tasks = sum(1 for _ in f)

    if num_tasks == 0:
        logger.warning("No batch files to submit.")
        return

    # Write and submit array job
    os.makedirs("slurm_logs", exist_ok=True)
    script_path = "slurm_array_job.sh"
    with open(script_path, "w") as f:
        f.write(job_script.replace("{N}", str(num_tasks - 1)))

    result = subprocess.run(["sbatch", script_path], capture_output=True, text=True)
    logger.info(f"Submitted array job: {result.stdout.strip()}")

    # Extract job ID
    return extract_job_id_from_output(result.stdout)


def submit_slurm_merge_db_job(output_dir, dependency_job_id):
    # Submit a merge job after all batch jobs are done
    merge_script = f"""#!/bin/bash
        #SBATCH --job-name=merge_duckdbs
        #SBATCH --output=slurm_logs/merge-%j.out
        #SBATCH --error=slurm_logs/merge-%j.err
        #SBATCH --time={BATCH_TIME_LIMIT}
        #SBATCH --cpus-per-task={BATCH_CPUS_PER_TASK}
        #SBATCH --mem={BATCH_MEMORY_PER_TASK}
        #SBATCH --dependency==afterok:{dependency_job_id}
        #SBATCH --nice=100
    
        source /home/gazetteer/miniconda/etc/profile.d/conda.sh
        conda activate vespa-env
        cd  ~/repository/place/vespa/repository/api/ingestion/slurm
    
        echo "Merging DuckDB files..."
        python merge_duckdbs.py "{output_dir}" "{output_dir}/merged.duckdb"
        
        echo "Deleting per-batch DuckDBs..."
        find "{output_dir}" -type f -name "*.duckdb" ! -name "merged.duckdb" -delete
        """

    merge_script_path = "slurm_merge_duckdbs.sh"
    with open(merge_script_path, "w") as f:
        f.write(merge_script)

    result = subprocess.run(["sbatch", merge_script_path])
    logger.info(f"Submitted SLURM job to merge all DuckDBs into {output_dir}/merged.duckdb: {result.stdout.strip()}")

    # Extract job ID
    return extract_job_id_from_output(result.stdout)


def submit_slurm_ndmsgpack_job(merged_db_path, output_dir, dependency_job_id):
    ndmsgpack_script = f"""#!/bin/bash
        #SBATCH --job-name=ndmsgpack_export
        #SBATCH --output=slurm_logs/ndmsgpack-%j.out
        #SBATCH --error=slurm_logs/ndmsgpack-%j.err
        #SBATCH --time={BATCH_TIME_LIMIT}
        #SBATCH --cpus-per-task={BATCH_CPUS_PER_TASK}
        #SBATCH --mem={BATCH_MEMORY_PER_TASK}
        #SBATCH --dependency=afterok:{dependency_job_id}
        #SBATCH --nice=100

        source /home/gazetteer/miniconda/etc/profile.d/conda.sh
        conda activate vespa-env
        cd ~/repository/place/vespa/repository/api/ingestion/slurm

        echo "Generating NDMessagePack from {merged_db_path}..."
        python export_to_msgpack.py "{merged_db_path}" "{output_dir}/vespa.ndmsgpack"
    """

    script_path = "slurm_ndmsgpack_export.sh"
    with open(script_path, "w") as f:
        f.write(ndmsgpack_script)

    result = subprocess.run(["sbatch", script_path], capture_output=True, text=True)
    logger.info(f"Submitted SLURM job to export NDMessagePack to {output_dir}/vespa.ndmsgpack: {result.stdout.strip()}")

    return extract_job_id_from_output(result.stdout)



async def fetch_and_split(dataset_name, output_dir, batch_size=BATCH_SIZE):
    cfg = get_dataset_config(dataset_name)

    if os.path.exists(output_dir) and list(Path(output_dir).rglob("*.parquet")):
        logger.info(f"Output directory {output_dir} already contains parquet files. Skipping `fetch_and_split`.")
        return

    os.makedirs(output_dir, exist_ok=True)

    def normalise_batch(batch):  # Normalise Pleiades data
        for item in batch:
            for field in ("reprPoint", "bbox"):
                if field in item:
                    val = item[field]
                    if val is None:
                        item[field] = []
                    elif not isinstance(val, list):
                        item[field] = [val]  # Or log a warning if needed
        return batch

    for file_cfg in cfg["files"]:
        file_name = file_cfg.get("file_name") or os.path.basename(file_cfg["url"])
        label = Path(file_name).with_suffix('').stem
        file_out_dir = os.path.join(output_dir, label)
        os.makedirs(file_out_dir, exist_ok=True)

        sf = StreamFetcher(file_cfg)
        sf.ingestion_path = file_out_dir
        sf.local_name = file_name

        filters = file_cfg.get("filters", [])
        def is_wanted(doc):
            return all(f(doc) for f in filters)

        items_iter = sf.get_items()
        batch, batch_idx = [], 0

        pbar = tqdm(desc=f"Processing {label}", unit="items", ncols=80, total=file_cfg.get("item_count"))

        async for item in items_iter:
            pbar.update(1)
            if not is_wanted(item):
                continue

            batch.append(item)
            if len(batch) >= batch_size:
                if dataset_name == "Pleiades":
                    batch = normalise_batch(batch)

                    # Debugging: Check for inconsistent types in fields
                    field_types = defaultdict(set)
                    for row in batch:
                        for k, v in row.items():
                            field_types[k].add(type(v).__name__)
                    for k, v in field_types.items():
                        if len(v) > 1:
                            print(f"Inconsistent types for '{k}': {v}")

                path = os.path.join(file_out_dir, f"batch_{batch_idx:06}.parquet")
                pq.write_table(pa.Table.from_pylist(batch), path)
                batch.clear()
                batch_idx += 1

        # flush remaining
        if batch:
            if dataset_name == "Pleiades":
                batch = normalise_batch(batch)
            path = os.path.join(file_out_dir, f"batch_{batch_idx:06}.parquet")
            pq.write_table(pa.Table.from_pylist(batch), path)
            batch_idx += 1
            batch.clear()

        pbar.close()
        logger.info(f"Wrote {batch_idx} shard files to {file_out_dir}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python split_source_to_parquet.py <dataset_name> [output_dir]")
        sys.exit(1)

    dataset = sys.argv[1]
    output_dir = sys.argv[2] if len(sys.argv) > 2 else f"{BASE_DATA_DIR}/{dataset.lower()}"

    asyncio.run(fetch_and_split(dataset, output_dir))
    logger.info(f"Dataset {dataset} split into Parquet files at {output_dir}")

    # Discover all batch files recursively and write to manifest
    batch_files = list(Path(output_dir).rglob("*.parquet"))
    manifest_path = Path(output_dir) / "batch_manifest.txt"
    with open(manifest_path, "w") as f:
        for path in batch_files:
            f.write(str(path.resolve()) + "\n")

    if not batch_files:
        logger.warning("No batch files found. Exiting.")
        sys.exit(0)

    exit(101)  #  Pending enablement of slurm

    logger.info(f"Discovered {len(batch_files)} batches. Writing SLURM array job.")
    array_job_id = submit_slurm_array_job(manifest_path)
    merge_job_id = submit_slurm_merge_db_job(output_dir, array_job_id)
    ndmsgpack_job_id = submit_slurm_ndmsgpack_job(f"{output_dir}/merged.duckdb", output_dir, merge_job_id)

    # Discover all NDMessagePack files and write to manifest
    ndmsgpack_files = list(Path(output_dir).rglob("*.ndmsgpack.gz"))
    ndmsgpack_manifest_path = Path(output_dir) / "ndmsgpack_manifest.txt"
    with open(ndmsgpack_manifest_path, "w") as f:
        for path in ndmsgpack_files:
            f.write(str(path.resolve()) + "\n")

    if not ndmsgpack_files:
        logger.warning("No NDMessagePack files found. Exiting.")
        sys.exit(0)

    logger.info(f"Discovered {len(ndmsgpack_files)} NDMessagePack files. Writing SLURM array job.")
    # TODO: Implement SLURM job for submission of NDMessagePack files to Vespa
