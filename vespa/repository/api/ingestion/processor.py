# /ingestion/processor.py
import logging
import tempfile
from typing import Dict, Any

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import NPRTransformer
from ..feed.processor import process_documents

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
        msg = f"Dataset configuration not found for dataset: {dataset_name}"
        logger.error(msg)
        ingestion_progress[task_id] = {"status": "error", "message": msg}
        return {"status": "error", "message": msg}

    # TODO: Either remove existing data from Vespa or update

    try:
        # Process each file in the dataset configuration
        for file_config in dataset_config['files']:

            # Use StreamFetcher to get the stream of data from the file URL
            stream_fetcher = StreamFetcher(file_config)
            documents = stream_fetcher.get_items()
            with tempfile.NamedTemporaryFile(delete=False) as document_file:
                for document in documents:
                    transformed_document, toponyms = NPRTransformer.transform(document, dataset_name)
                    document_file.write(f"{transformed_document}\n".encode('utf-8'))  # Write each transformed document to the file
                    document_file.flush()  # Ensure the data is written to disk
                document_file.close()  # Close the file to ensure it's not in use when passed
                # Send documents to the Vespa feed processor
                process_documents('npr', document_file.name, task_id)

            msg = f"Successfully processed dataset: {dataset_name}"
            logger.info(msg)
            ingestion_progress[task_id] = {"status": "success", "message": msg}
            return {"status": "success", "message": msg}

    except ValueError as e:
        msg = f"ValueError while processing dataset: {e}"
        logger.error(msg)
        ingestion_progress[task_id] = {"status": "error", "message": msg}
        return {"status": "error", "message": msg}

    except Exception as e:
        msg = f"Error processing dataset: {e}"
        logger.error(msg)
        ingestion_progress[task_id] = {"status": "error", "message": msg}
        return {"status": "error", "message": msg}
