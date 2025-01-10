# /ingestion/processor.py
import asyncio
import logging
from typing import Dict, Any

import httpx
from vespa.application import Vespa, VespaSync

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..config import host_mapping, namespace
from ..feed.processor import feed_progress
from ..utils import log_message, get_uuid

logger = logging.getLogger(__name__)


def delete_all_docs(sync_app, schema):
    sync_app.delete_all_docs(
        schema=schema,
        namespace=namespace,
        content_cluster_name="content"
    )


def feed_document(sync_app, dataset_config, document_id, transformed_document):
    try:
        response = sync_app.feed_data_point(
            schema=f"{dataset_config['vespa_schema']}",
            data_id=document_id,
            fields=transformed_document,
            namespace=namespace
        )
        if response.status_code == 200:
            return {"success": True, "document_id": document_id}
        else:
            return {
                "success": False,
                "document_id": document_id,
                "status_code": response.status_code,
                "message": response.json() if response.headers.get(
                    'content-type') == 'application/json' else response.text
            }
    except Exception as e:
        return {
            "success": False,
            "document_id": document_id,
            "error": str(e)
        }


async def process_document(document, dataset_config, transformer_index, sync_app):

    # Transform the document using the appropriate transformer
    transformed_document, toponyms = DocTransformer.transform(document, dataset_config['dataset_name'],
                                                              transformer_index)
    document_id = transformed_document.get(dataset_config['files'][transformer_index]['id_field']) or get_uuid()

    try:
        response = await asyncio.to_thread(
            feed_document, sync_app, dataset_config, document_id, transformed_document
        )
        if response.get("success"):
            return response
        else:
            return {"success": False, "document_id": document_id, "error": response.get('error') or response.get('message')}
    except Exception as e:
        return {"success": False, "document_id": document_id, "error": str(e)}


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

    app = Vespa(url=f"{host_mapping['feed']}")

    try:
        with VespaSync(app) as sync_app:

            try:
                await asyncio.to_thread(
                    delete_all_docs, sync_app, dataset_config['vespa_schema']
                )
            except httpx.HTTPStatusError as e:
                return log_message(
                    logger.exception, feed_progress, task_id, "error",
                    f"HTTP error while deleting documents: {e.response.status_code} - {e.response.text}"
                )
            except Exception as e:
                return log_message(
                    logger.exception, feed_progress, task_id, "error",
                    f"Error deleting existing documents: {e}"
                )

            tasks = []  # To keep track of async tasks for feeding documents

            # Process each file in the dataset configuration
            for i, file_config in enumerate(dataset_config['files']):

                # Use StreamFetcher to get the stream of data from the file URL
                stream_fetcher = StreamFetcher(file_config)
                documents = stream_fetcher.get_items()

                for count, document in enumerate(documents):
                    if limit is not None and count >= limit:
                        break

                    # Process each document asynchronously
                    tasks.append(process_document(document, dataset_config, i, sync_app))

            # Run all tasks concurrently
            log_message(
                logger.info, feed_progress, task_id, "processing",
                f"Feeding documents for dataset: {dataset_name}"
            )
            responses = await asyncio.gather(*tasks)

            # Handle responses
            success_count = 0
            failure_count = 0
            errors = []

            for response in responses:
                if response["success"]:
                    log_message(
                        logger.info, feed_progress, task_id, "feeding",
                        f"Successfully ingested document: {response['document_id']}"
                    )
                    success_count += 1
                else:
                    failure_count += 1
                    error_message = (
                        f"Error ingesting document: {response['document_id']} - "
                        f"{response.get('error') or response.get('message', 'Unknown error')} "
                    )
                    errors.append(error_message)
                    log_message(
                        logger.error, feed_progress, task_id, "error",
                        error_message
                    )

            # Aggregate final status
            if failure_count > 0:
                return log_message(
                    logger.error, feed_progress, task_id, "error",
                    f"Processed dataset: {dataset_name} with {failure_count} failures out of {success_count + failure_count} documents. Errors: {errors}"
                )

            return log_message(
                logger.info, feed_progress, task_id, "success",
                f"Successfully processed dataset: {dataset_name}. Ingested {success_count} documents."
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
