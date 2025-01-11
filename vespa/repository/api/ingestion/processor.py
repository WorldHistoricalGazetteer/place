# /ingestion/processor.py
import asyncio
import logging
import time
from asyncio import Task
from concurrent.futures import ThreadPoolExecutor

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..config import namespace, VespaClient
from ..utils import get_uuid, task_tracker

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=10)


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


async def process_document(document, dataset_config, transformer_index, sync_app, task_id):
    transformed_document, toponyms = DocTransformer.transform(document, dataset_config['dataset_name'],
                                                              transformer_index)
    document_id = transformed_document.get(dataset_config['files'][transformer_index]['id_field']) or get_uuid()
    task_tracker.update_task(task_id, {
        "transformed": 1,
    })

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            executor, feed_document, sync_app, dataset_config, document_id, transformed_document
        )
        success = response.get("success", False)
        task_tracker.update_task(task_id, {
            "processed": 1,
            "success": 1 if success else 0,
            "failure": 1 if not success else 0
        })
        return response
    except Exception as e:
        task_tracker.update_task(task_id, {"processed": 1, "failure": 1})
        return {"success": False, "document_id": document_id, "error": str(e)}


async def process_documents(documents, dataset_config, transformer_index, sync_app, limit, task_id):
    semaphore = asyncio.Semaphore(5)  # Limit concurrent tasks

    async def process_limited(document):
        async with semaphore:
            return await process_document(document, dataset_config, transformer_index, sync_app, task_id)

    tasks = [
        process_limited(document)
        for count, document in enumerate(documents)
        if limit is None or count < limit
    ]
    return await asyncio.gather(*tasks)


async def background_ingestion(dataset_name: str, task_id: str, limit: int = None) -> None:
    """
    The main logic of dataset ingestion that will run in the background.
    """
    dataset_config = next((config for config in REMOTE_DATASET_CONFIGS if config['dataset_name'] == dataset_name), None)

    if dataset_config is None:
        logger.error(
            f"Dataset configuration not found for dataset: {dataset_name}. Valid names are {', '.join([c['dataset_name'] for c in REMOTE_DATASET_CONFIGS])}.")
        task_tracker.update_task(task_id, {"status": "failed",
                                           "error": f"Dataset configuration not found for dataset: {dataset_name}. Valid names are {', '.join([c['dataset_name'] for c in REMOTE_DATASET_CONFIGS])}."})
        return

    logger.info(f"Processing dataset: {dataset_name}")
    task_tracker.update_task(task_id, {"visit_url": f"/visit?schema={dataset_config['vespa_schema']}"})

    try:
        with VespaClient.sync_context("feed") as sync_app:

            # Run `delete_all_docs` asynchronously to avoid blocking the event loop
            logger.info(f"Deleting all documents for schema: {dataset_config['vespa_schema']}")
            await asyncio.to_thread(delete_all_docs, sync_app, dataset_config['vespa_schema'])

            all_responses = []
            for i, file_config in enumerate(dataset_config['files']):
                logger.info(f"Fetching items from stream: {file_config['url']}")
                stream_fetcher = StreamFetcher(file_config)
                documents = stream_fetcher.get_items()
                responses = await process_documents(documents, dataset_config, i, sync_app, limit, task_id)
                all_responses.extend(responses)

            success_count = sum(1 for r in all_responses if r.get("success"))
            failure_count = len(all_responses) - success_count
            logger.info(f"Success: {success_count}, Failures: {failure_count}")

            # Final update to the task tracker
            task_tracker.update_task(task_id, {
                "status": "completed" if failure_count == 0 else "failed",
                "end_time": time.time()
            })

    except Exception as e:
        logger.exception(f"Error during ingestion: {e}")
        task_tracker.update_task(task_id, {"status": "failed", "error": str(e)})


async def start_ingestion_in_background(dataset_name: str, task_id: str, limit: int = None) -> Task:
    """
    Starts the ingestion in a background task.

    :param dataset_name: The name of the dataset
    :param task_id: The task ID for tracking
    :param limit: Maximum number of items to ingest
    """
    task = asyncio.create_task(background_ingestion(dataset_name, task_id, limit))

    # Add the task to the task tracker (also triggers cleanup of expired tasks)
    task_tracker.add_task(task_id)

    return task
