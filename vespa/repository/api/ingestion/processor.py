# /ingestion/processor.py
import asyncio
import logging
from asyncio import Task

from vespa.application import Vespa, VespaSync

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..config import host_mapping, namespace
from ..main import background_tasks
from ..utils import get_uuid

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
            return {"success": False, "document_id": document_id,
                    "error": response.get('error') or response.get('message')}
    except Exception as e:
        return {"success": False, "document_id": document_id, "error": str(e)}


async def background_ingestion(dataset_name: str, task_id: str, limit: int = None) -> None:
    """
    The main logic of dataset ingestion that will run in the background.
    """
    dataset_config = next((config for config in REMOTE_DATASET_CONFIGS if config['dataset_name'] == dataset_name), None)

    if dataset_config is None:
        logger.error(f"Dataset configuration not found for dataset: {dataset_name}")
        return

    logger.info(f"Processing dataset: {dataset_name}")

    app = Vespa(url=f"{host_mapping['feed']}")

    try:
        with VespaSync(app) as sync_app:

            # Run `delete_all_docs` asynchronously to avoid blocking the event loop
            await asyncio.to_thread(delete_all_docs, sync_app, dataset_config['vespa_schema'])

            tasks = []  # To keep track of async tasks for feeding documents

            for i, file_config in enumerate(dataset_config['files']):
                stream_fetcher = StreamFetcher(file_config)
                documents = stream_fetcher.get_items()

                for count, document in enumerate(documents):
                    if limit is not None and count >= limit:
                        break

                    # Process each document asynchronously
                    tasks.append(process_document(document, dataset_config, i, task_id, sync_app))

            # Run all tasks concurrently
            responses = await asyncio.gather(*tasks)

            # Handle responses and logging
            success_count, failure_count, errors = 0, 0, []
            for response in responses:
                if response["success"]:
                    success_count += 1
                else:
                    failure_count += 1
                    error_message = f"Error ingesting document: {response['document_id']} - {response.get('error')}"
                    errors.append(error_message)

            if failure_count > 0:
                logger.error(f"Ingestion failed: {failure_count}/{success_count + failure_count} documents")
                for error in errors:
                    logger.error(error)

            logger.info(f"Success count: {success_count}, Failure count: {failure_count}")

    except Exception as e:
        logger.exception(f"Error processing dataset: {e}")


async def start_ingestion_in_background(dataset_name: str, task_id: str, limit: int = None) -> Task:
    """
    Starts the ingestion in a background task.

    :param dataset_name: The name of the dataset
    :param task_id: The task ID for tracking
    :param limit: Maximum number of items to ingest
    """
    task = asyncio.create_task(background_ingestion(dataset_name, task_id, limit))
    background_tasks[task_id] = task
    return task
