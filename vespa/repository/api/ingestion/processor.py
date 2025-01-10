# /ingestion/processor.py
import asyncio
import json
import logging
import tempfile
from typing import Dict, Any, List

from httpx import AsyncClient

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..config import host_mapping, batch_feed_size, namespace
from ..feed.processor import process_documents, feed_progress
from ..utils import log_message

logger = logging.getLogger(__name__)


async def send_batch(feed_service_url: str, batch: List[Dict[str, Any]], logger: logging.Logger, task_id: str) -> None:
    """
    Send a batch of documents to the Vespa feed service.

    :param feed_service_url: The URL of the Vespa feed service
    :param batch: A list of documents to send
    :param logger: The logger for logging
    :param task_id: The task ID for progress tracking
    """
    async with AsyncClient() as client:
        try:
            response = await client.post(feed_service_url, json=batch)
            response.raise_for_status()
            log_message(logger.info, feed_progress, task_id, "success",
                        f"Successfully fed a batch of {len(batch)} documents")
        except Exception as e:
            log_message(logger.error, feed_progress, task_id, "error", f"Error sending batch: {e}")


def process_dataset(dataset_name: str, task_id: str, limit: int = None) -> Dict[str, Any]:
    """
    Process a remote dataset for ingestion into the system.

    :param dataset_name: The name of the dataset to ingest
    :param task_id: The task ID for tracking the progress of the ingestion
    :param limit: The maximum number of items to ingest
    """

    feed_service_url = host_mapping['feed']

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

    try:
        # Process each file in the dataset configuration
        for i, file_config in enumerate(dataset_config['files']):

            # Use StreamFetcher to get the stream of data from the file URL
            stream_fetcher = StreamFetcher(file_config)
            documents = stream_fetcher.get_items()

            batch = []
            batch_count = 0

            for count, document in enumerate(documents):
                if limit is not None and count >= limit:
                    break

                transformed_document, toponyms = DocTransformer.transform(document, dataset_name, transformer_index=i)
                batch.append(transformed_document)

                if len(batch) >= batch_feed_size:
                    batch_count += 1
                    log_message(logger.info, feed_progress, task_id, "processing", f"Sending batch {batch_count}")
                    asyncio.run(send_batch(feed_service_url, batch, logger, task_id))
                    batch.clear()

            # Send any remaining documents in the last batch
            if batch:
                batch_count += 1
                log_message(logger.info, feed_progress, task_id, "processing", f"Sending final batch {batch_count}")
                asyncio.run(send_batch(feed_service_url, batch, logger, task_id))

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
