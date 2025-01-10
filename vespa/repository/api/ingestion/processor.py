# /ingestion/processor.py
import asyncio
import logging
import os
import tempfile
from typing import Dict, Any

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..feed.processor import process_documents
from ..utils import log_message

logger = logging.getLogger(__name__)
ingestion_progress = {}


def process_dataset(dataset_name: str, task_id: str, limit: int = None) -> Dict[str, Any]:
    """
    Process a remote dataset for ingestion into the system.

    :param dataset_name: The name of the dataset to ingest
    :param task_id: The task ID for tracking the progress of the ingestion
    :param limit: The maximum number of items to ingest
    """
    # Get the configuration for the dataset
    dataset_config = next((config for config in REMOTE_DATASET_CONFIGS if config['dataset_name'] == dataset_name), None)

    if dataset_config is None:
        return log_message(
            logger.info, ingestion_progress, task_id, "error",
            f"Dataset configuration not found for dataset: {dataset_name}"
        )

    # TODO: Either remove existing data from Vespa or update

    try:
        # Process each file in the dataset configuration
        for i, file_config in enumerate(dataset_config['files']):

            # Use StreamFetcher to get the stream of data from the file URL
            stream_fetcher = StreamFetcher(file_config)
            documents = stream_fetcher.get_items()
            with tempfile.NamedTemporaryFile(delete=False) as document_file:
                temp_file_path = document_file.name
                log_message(
                    logger.info, ingestion_progress, task_id, "processing",
                    f"Processing dataset: {dataset_name} ({i + 1}/{len(dataset_config['files'])})"
                )
                for count, document in enumerate(documents):
                    if limit is not None and count >= limit:
                        break
                    # log_message(
                    #     logger.info, ingestion_progress, task_id, "processing",
                    #     f"Processing document {count + 1}: {str(document)[:3000]}..."
                    # )
                    transformed_document, toponyms = DocTransformer.transform(document, dataset_name, transformer_index=i)
                    document_file.write(f"{transformed_document}\n".encode('utf-8'))  # Write each transformed document to the file
                document_file.close()

            # Process the file
            try:
                log_message(
                    logger.info, ingestion_progress, task_id, "processing",
                    f"Sending documents to Vespa: {dataset_name} ({i + 1}/{len(dataset_config['files'])})"
                )
                asyncio.run(process_documents(dataset_config['vespa_schema'], temp_file_path, task_id))
            finally:
                # Ensure the tempfile is deleted even if processing fails
                os.remove(temp_file_path)

        return log_message(
            logger.info, ingestion_progress, task_id, "success",
            f"Successfully processed dataset: {dataset_name}"
        )

    except ValueError as e:
        return log_message(
            logger.exception, ingestion_progress, task_id, "error",
            f"ValueError while processing dataset: {e}"
        )

    except Exception as e:
        return log_message(
            logger.exception, ingestion_progress, task_id, "error",
            f"Error processing dataset: {e}"
        )
