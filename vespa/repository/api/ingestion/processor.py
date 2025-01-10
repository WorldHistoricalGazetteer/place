# /ingestion/processor.py
import logging
from typing import Dict, Any

from vespa.application import Vespa, VespaSync

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..config import host_mapping, namespace
from ..feed.processor import feed_progress
from ..utils import log_message, get_uuid

logger = logging.getLogger(__name__)


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

    app = Vespa(url=f"{host_mapping['feed']}", port=8080)

    # Delete existing documents for the dataset
    # await delete_existing_documents(dataset_config['vespa_schema'])

    try:
        with VespaSync(app) as sync_app:
            # Process each file in the dataset configuration
            for i, file_config in enumerate(dataset_config['files']):

                # Use StreamFetcher to get the stream of data from the file URL
                stream_fetcher = StreamFetcher(file_config)
                documents = stream_fetcher.get_items()

                for count, document in enumerate(documents):
                    if limit is not None and count >= limit:
                        break

                    transformed_document, toponyms = DocTransformer.transform(document, dataset_name,
                                                                              transformer_index=i)
                    document_id = transformed_document.get(file_config['id_field']) if file_config[
                        'id_field'] else get_uuid()
                    try:
                        response = sync_app.feed_data_point(
                            schema=f"{dataset_config['vespa_schema']}",
                            data_id=document_id,
                            fields=transformed_document,
                            namespace=namespace
                        )
                        if response.status_code != 200:
                            log_message(
                                logger.error, feed_progress, task_id, "error",
                                f"Error ingesting document: {response}"
                            )
                            continue  # Proceed to next document
                        else:
                            log_message(
                                logger.info, feed_progress, task_id, "feeding",
                                f"Successfully ingested document: {document_id}"
                            )

                    except Exception as e:
                        log_message(
                            logger.exception, feed_progress, task_id, "error",
                            f"Error processing document {document_id}: {e}"
                        )
                        continue

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
