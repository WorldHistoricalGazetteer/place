# WHG Place Ingestion and Indexing Pipeline (Revised Proposal)

## Overview

This document outlines a revised ingestion and preprocessing pipeline for WHG PLACE, designed to run on the University of Pittsburgh’s Slurm-based infrastructure. The focus is on scalable extraction, transformation, phonetic and temporal normalisation, and preparation of large-scale place datasets (e.g., GeoNames, Wikidata) for Vespa indexing and matching.

---

## Goals

- **Preprocess millions of place records efficiently.**
- **Perform "Phonetic-Phirst" indexing**: prioritise phonetic similarity for variant reconciliation.
- **Enable time- and space-aware search and matching.**
- **Support asynchronous, restartable pipelines with persistent intermediate outputs.**

---

## High-Level Architecture

```text
              +-------------------+
              |  Source Datasets  |
              | (GeoNames, etc.)  |
              +-------------------+
                        |
                        v
          +---------------------------+
          |   Data Extraction &       |
          | Normalisation to Parquet  |
          +---------------------------+
                        |
                        v
        +-----------------------------+
        | IPA transcription + phonetic|
        | alias expansion (opt. FST)  |
        +-----------------------------+
                        |
                        v
         +------------------------------+
         | Spatial & temporal parsing   |
         | + disambiguation heuristics  |
         +------------------------------+
                        |
                        v
        +-----------------------------+
        | Batching into Vespa-ready   |
        | binary format (e.g., MsgPack)|
        +-----------------------------+
                        |
                        v
        +-----------------------------+
        |   Vespa document ingestion  |
        +-----------------------------+
```

---

## Key Technologies

| Component              | Tooling/Format             |
|------------------------|----------------------------|
| Workflow engine        | Slurm                      |
| Parallel processing    | Python + Slurm array jobs  |
| Preprocessed format    | Parquet                    |
| Document serialisation | **MessagePack** (vs JSON)  |
| Containers             | Singularity (via Docker)   |
| Persistent storage     | NFS (shared via Slurm)     |
| Vespa deployment       | K8s or external cluster    |

---

## Pipeline Stages

### 1. **Source Extraction and Normalisation**

- Python scripts extract and normalise raw data.
- Output: `.parquet` files with standardised schema:
  - `id`, `names`, `location`, `timespan`, `source`, etc.

> ✅ **Stored in NFS-mounted directory, readable by all jobs.**

---

### 2. **Phonetic & IPA Normalisation**

- Convert all name variants to **IPA transcription** (e.g., via `epitran`, `segments`).
- Post-process IPA to **blur minor phonetic distinctions**.
- Generate **phonetic aliases** using rule-based mappings (e.g., `GH = G`, `PH = F`, `KH ≈ H`, etc.).

> ✅ Stored as `phonetic_names` field in `.parquet`.

---

### 3. **Temporal Parsing**

- Extract temporal coverage from:
  - Textual fields: `“fl. 12th c.”`, `“-500 to 300 BCE”`, etc.
  - Date spans where available.
- Standardise to `from_year` / `to_year`.

> Optional: fuzzy logic for inferred dates (e.g., reign of ruler).

---

### 4. **Geo-Referencing & Disambiguation**

- Where multiple candidate coordinates exist:
  - Prefer explicit precision
  - Use proximity to known regions (gazetteers)
- Round lat/lon to reasonable precision (e.g., 5 decimals)

---

### 5. **Batching and Serialisation for Vespa**

- Instead of JSON, use **MessagePack** (`msgpack`) for faster parsing and smaller size.
- Each `.parquet` file is converted to a set of **`.msgpack` files**, each representing:
  ```json
  {
    "id": "...",
    "phonetic_names": ["..."],
    "lat": ...,
    "lon": ...,
    "from_year": ...,
    "to_year": ...,
    ...
  }
  ```

> MessagePack yields lower I/O latency and memory overhead during ingestion.

---

### 6. **Vespa Document Indexing**

- Use either:
  - **Single Vespa cluster with multiple document types**, or
  - **Separate Vespa clusters per source/indexing strategy**, if differing ranking/feature sets needed

> Use bulk feed API via HTTP or Vespa CLI.

---

## Deployment Notes

- **No root privileges required.** All jobs run as the cluster user.
- Singularity containers built from Docker images (`docker://ghcr.io/whg/...`) include:
  - `python`, `pyarrow`, `msgpack`, `epitran`, `cltk`, `segments`, etc.
- Shared scratch directory for intermediate outputs

---

## Advantages of MessagePack over JSON

| Feature         | JSON     | MessagePack     |
|-----------------|----------|-----------------|
| Read speed      | Medium   | **Faster**      |
| Size on disk    | Large    | **Compact**     |
| Vespa-ready     | Yes      | **Yes**         |
| Python support  | Good     | **Excellent**   |
| Binary-safe     | No       | **Yes**         |

---

## Next Steps

1. Finalise and test data extraction scripts
2. Build Docker image + Singularity container
3. Create test Slurm job scripts
4. Run pipeline on subset of sources
5. Prepare Vespa ingestion with MsgPack batches

---

## Appendix: Slurm Job Example

```bash
#!/bin/bash
#SBATCH --job-name=whg_ingest
#SBATCH --array=0-99
#SBATCH --cpus-per-task=2
#SBATCH --mem=4G
#SBATCH --time=01:00:00
#SBATCH --output=logs/ingest_%A_%a.out

module load singularity

singularity exec --bind /nfs:/nfs whg_ingest.sif \
  python process_batch.py --input "/nfs/batches/batch_${SLURM_ARRAY_TASK_ID}.parquet"
```

