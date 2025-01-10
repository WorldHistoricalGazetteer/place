# /ingestion/processor.py
import logging
from typing import Dict, Any

import httpx
from httpx import AsyncClient

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..config import host_mapping, namespace
from ..feed.processor import feed_progress
from ..utils import log_message, get_uuid

logger = logging.getLogger(__name__)


async def delete_existing_documents(dataset_name: str) -> None:
    """
    Delete existing documents for a dataset from the Vespa feed service.
    Args:
        dataset_name:

    Returns:

    """
    delete_url = f"{host_mapping['feed']}/document/v1/{namespace}/{dataset_name}/docid?selection=true"
    async with AsyncClient() as client:
        response = await client.delete(delete_url)
        response.raise_for_status()
        logger.info(f"Existing documents for {dataset_name} deleted successfully.")


async def send_document(feed_url: str, feed_json: Dict[str, Any], logger: logging.Logger, task_id: str) -> None:
    """
    Send a single document to the Vespa feed service.

    :param feed_url: The URL for feeding the document
    :param feed_json: The JSON payload for the document
    :param logger: The logger for logging
    :param task_id: The task ID for progress tracking
    """
    async with AsyncClient() as client:
        try:
            response = await client.put(feed_url, json=feed_json)
            response.raise_for_status()
            log_message(logger.info, feed_progress, task_id, "success",
                        f"Document fed successfully: {feed_json.get('fields', {}).get('id', 'unknown')}")
        except httpx.HTTPStatusError as e:
            log_message(logger.error, feed_progress, task_id, "error",
                        f"HTTP error {e.response.status_code}: {e.response.text}")
        except Exception as e:
            log_message(logger.error, feed_progress, task_id, "error",
                        f"Error sending document: {e}")


async def process_dataset(dataset_name: str, task_id: str, limit: int = None) -> Dict[str, Any]:
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
            logger.info, feed_progress, task_id, "error",
            f"Dataset configuration not found for dataset: {dataset_name}"
        )
    log_message(
        logger.info, feed_progress, task_id, "processing",
        f"Processing dataset: {dataset_name}"
    )

    # Delete existing documents for the dataset
    # await delete_existing_documents(dataset_config['vespa_schema'])

    try:
        # Process each file in the dataset configuration
        for i, file_config in enumerate(dataset_config['files']):

            # Use StreamFetcher to get the stream of data from the file URL
            stream_fetcher = StreamFetcher(file_config)
            documents = stream_fetcher.get_items()

            for count, document in enumerate(documents):
                if limit is not None and count >= limit:
                    break

                transformed_document, toponyms = DocTransformer.transform(document, dataset_name, transformer_index=i)
                document_id = transformed_document.get(dataset_config['id_field']) if dataset_config[
                    'id_field'] else get_uuid()
                feed_url = f"{host_mapping['feed']}/document/v1/{namespace}/{dataset_config['vespa_schema']}/docid/{document_id}"
                feed_json = {"fields": transformed_document}
                await send_document(feed_url, feed_json, logger, task_id)

        return log_message(
            logger.info, feed_progress, task_id, "success",
            f"Successfully processed dataset: {dataset_name}"
        )

    except ValueError as e:
        return log_message(
            logger.exception, feed_progress, task_id, "error",
            f"ValueError while processing dataset: {e}"
        )

    except Exception as e:
        return log_message(
            logger.exception, feed_progress, task_id, "error",
            f"Error processing dataset: {e}"
        )
