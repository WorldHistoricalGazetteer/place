# /ingestion/processor.py
import asyncio
import logging
import queue
import threading
import time
from asyncio import Task
from concurrent.futures import ThreadPoolExecutor

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from .triples import feed_triple, process_variants
from ..bcp_47.bcp_47 import bcp47_fields
from ..config import VespaClient
from ..utils import task_tracker, get_uuid, escape_yql

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=10)

# Create a queue with a maximum size
max_queue_size = 100  # Queue size for document update tasks
update_queue = queue.Queue(maxsize=max_queue_size)


def queue_worker():
    while True:
        task = update_queue.get()
        if task is None:  # Sentinel to terminate the worker thread
            break

        try:
            _, namespace, _, _, _, task_id, count, task_tracker = task

            if namespace == 'tgn':
                response = feed_triple(task)
                if not response.get("success", False):
                    task_tracker.update_task(task_id, {
                        "success": -1,
                        "failure": 1
                    })

            else:
                update_existing_place(task)

            if count % 1000 == 0:
                logger.info(f"{count:,} documents sent for indexing")
            # Pausing helps reduce GC pressure or system resource exhaustion during heavy processing
            if count % 100_000 == 0:
                logger.info(f"Pausing for 3 minutes to reduce system pressure ...")
                time.sleep(3 * 60)

        except Exception as e:
            logger.error(f"Error processing update: {e}")

        finally:
            update_queue.task_done()


def update_existing_place(task):
    sync_app, namespace, schema, document_id, transformed_document, task_id, count, task_tracker = task
    response = sync_app.get_existing(
        namespace=namespace,
        schema=schema,
        data_id=document_id
    )
    # logger.info(f"Response: {response.get('status_code')}: {response}")
    if response.get('status_code') < 500:
        existing_document = response
        existing_names = existing_document.get("fields", {}).get("names", [])
        # logger.info(f'Extending names with {transformed_document["fields"]["names"]} for place {document_id}')
        response = sync_app.update_existing(
            namespace=namespace,
            schema=schema,
            data_id=document_id,
            fields={
                "names": existing_names + transformed_document['fields']['names']
            }
        )
        # logger.info(f"Update response: {response.get('status_code')}: {response}")
    else:
        msg = f"Failed to get existing document: {namespace}:{schema}::{document_id}, Status code: {response.get('status_code')}"
        task_tracker.update_task(task_id, {"error (D)": f"#{count}: {msg}"})
        logger.error(msg)


def feed_link(sync_app, namespace, schema, link, task_id, count):
    try:
        response = sync_app.feed_existing(
            namespace=namespace,  # source identifier
            schema=schema,  # usually 'link'
            data_id=get_uuid(),
            fields=link
        )

        if response.get('status_code') < 500:
            return {"success": True, "link": link}
        else:
            msg = response if response.headers.get('content-type') == 'application/json' else response.text
            task_tracker.update_task(task_id, {"error (C)": f"#{count}: link: >>>{link}<<< {msg}"})
            logger.error(
                f"Failed to feed link: {link}, Status code: {response.get('status_code')}, Response: {msg}")
            return {
                "success": False,
                "link": link,
                "status_code": response.get('status_code'),
                "message": msg
            }
    except Exception as e:
        task_tracker.update_task(task_id, {"error (B)": f"#{count}: link: >>>{link}<<< {str(e)}"})
        logger.error(f"Error feeding link: {link}, Error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "link": link,
            "error": str(e)
        }


def feed_document(sync_app, namespace, schema, transformed_document, task_id, count, update_place=False):
    # logger.info(f"feed_document {count} (update place = {update_place}): {transformed_document.get('document_id')}")

    if namespace == 'tgn':
        # Handle triples differently
        task = (sync_app, namespace, None, None, transformed_document, task_id, count, task_tracker)
        update_queue.put(task)
        return {"success": True} # Pending processing in the worker thread

    document_id = transformed_document.get("document_id")
    if not document_id:
        logger.error(f"Document ID not found: {transformed_document}")
        return {
            "success": False,
            "namespace": namespace,
            "schema": schema,
            "document_id": document_id,
            "error": "Document ID not found in transformed document"
        }
    try:
        preexisting = None
        yql = None
        if schema == 'toponym':
            # Check if toponym already exists
            yql = f'select documentid, places from toponym where name_strict contains "{escape_yql(transformed_document["fields"]["name"])}" '
            for field in bcp47_fields:
                if transformed_document.get("fields", {}).get(f"bcp47_{field}"):
                    yql += f'and bcp47_{field} contains "{transformed_document["fields"][f"bcp47_{field}"]}" '
            yql += 'limit 1'
            preexisting = sync_app.query_existing(
                {'yql': yql},
                # Do not set namespace
                schema=schema,
            )

        if preexisting:  # (and schema == 'toponym')
            # Extend `places` list
            existing_toponym_id = preexisting.get("document_id")
            existing_places = preexisting.get("fields", {}).get("places", [])

            response = sync_app.update_existing(
                # https://docs.vespa.ai/en/reference/document-json-format.html#add-array-elements
                namespace=namespace,
                schema=schema,
                data_id=existing_toponym_id,
                fields={
                    "places": existing_places + [document_id]
                }
            )
        else:
            if schema == 'toponym':
                # Inject creation timestamp
                transformed_document['fields']['created'] = int(time.time() * 1000)
            if update_place:  # (only True when schema == 'place')
                task = (sync_app, namespace, schema, document_id, transformed_document, task_id, count, task_tracker)
                update_queue.put(task)
                response = None
            else:
                response = sync_app.feed_existing(
                    namespace=namespace,
                    schema=schema,
                    data_id=document_id,
                    fields=transformed_document['fields']
                )

        if update_place or response.get('status_code') < 500:
            return {"success": True, "namespace": namespace, "schema": schema, "document_id": document_id}
        else:
            msg = response if response.headers.get('content-type') == 'application/json' else response.text
            task_tracker.update_task(task_id, {"error (A)": f"#{count}: {msg}"})
            logger.error(
                f"Failed to feed document: {namespace}:{schema}::{document_id}, Status code: {response.get('status_code')}, Response: {msg}")
            return {
                "success": False,
                "namespace": namespace,
                "schema": schema,
                "document_id": document_id,
                "status_code": response.get('status_code'),
                "message": msg
            }
    except Exception as e:
        task_tracker.update_task(task_id, {"error (E)": f"#{count}: yql: >>>{yql}<<< {str(e)}"})
        logger.error(f"Error feeding document: {document_id} with {yql}, Error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "namespace": namespace,
            "schema": schema,
            "document_id": document_id,
            "error": str(e)
        }


async def process_document(document, dataset_config, transformer_index, sync_app, task_id, count, update_place=False):
    # logger.info(f"process_document {count} (update place = {update_place})")
    transformed_document, toponyms, links = DocTransformer.transform(document, dataset_config['dataset_name'],
                                                                     transformer_index)
    task_tracker.update_task(task_id, {
        "transformed": 1,
    })

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            executor, feed_document, sync_app, dataset_config['namespace'], dataset_config['vespa_schema'],
            transformed_document, task_id, count, update_place
        ) or {}
        success = response.get("success", False)

        if success and toponyms:
            toponym_responses = await asyncio.gather(*[
                asyncio.to_thread(feed_document, sync_app, dataset_config['namespace'], 'toponym', toponym, task_id,
                                  count, False)
                for toponym in toponyms
            ])

            # Check if any toponym feed failed
            if any(not r.get("success") for r in toponym_responses):
                success = False

        if success and links:
            link_responses = await asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(
                    executor, feed_link, sync_app, dataset_config['namespace'], 'link', link, task_id, count
                )
                for link in links
            ])

            # Check if any link feed failed
            if any(not r.get("success") for r in link_responses):
                success = False

        task_tracker.update_task(task_id, {
            "processed": 1,
            "success": 1 if success else 0,
            "failure": 1 if not success else 0
        })
        return response
    except Exception as e:
        task_tracker.update_task(task_id, {"processed": 1, "failure": 1, "error": f"#{count}: {str(e)}"})
        return {"success": False,
                "document": f"{dataset_config['namespace']}:{dataset_config['vespa_schema']}:{document}",
                "error": str(e)}


async def process_documents(stream, dataset_config, transformer_index, sync_app, limit, task_id, update_place=False):
    # logger.info(f"process_documents: (update place = {update_place})")
    semaphore = asyncio.Semaphore(10)  # Limit concurrent tasks
    batch_size = 25  # Number of documents to process at a time
    results = []  # Collect results from processed documents
    counter = 0

    async def process_limited(document):
        nonlocal counter
        async with semaphore:
            counter += 1
            # Uncomment to reprocess only specific documents (for debugging - disable deletion of other documents too if needed)
            # if not counter in [92697, 206965, 208028]:
            #     # Skip document
            #     return {
            #         "success": True,
            #     }
            # logger.info(f"Processing document {counter}: {document}")

            result = await process_document(document, dataset_config, transformer_index, sync_app, task_id, counter,
                                            update_place=update_place)
            return result

    async def process_batch(batch):
        tasks = [process_limited(document) for document in batch]
        return await asyncio.gather(*tasks)

    current_batch = []
    # skipcount = 0
    count = 0
    filters = dataset_config.get('files')[transformer_index].get('filters')

    async for document in stream:

        # Apply filters (if any)
        if filters and not any(f(document) for f in filters):
            # skipcount += 1
            # logger.info(f"Skipping document {skipcount}: {document['predicate']}")
            continue

        current_batch.append(document)
        count += 1

        # Process the batch when it reaches the batch_size or limit
        if len(current_batch) >= batch_size or (limit is not None and count >= limit):
            batch_results = await process_batch(current_batch)
            results.extend(batch_results)  # Collect results
            current_batch = []

            # Stop processing if the limit is reached
            if limit is not None and count >= limit:
                break

    # Process any remaining documents in the last batch
    if current_batch:
        batch_results = await process_batch(current_batch)
        results.extend(batch_results)  # Collect results

    return results  # Return aggregated results


async def background_ingestion(dataset_name: str, task_id: str, limit: int = None, delete_only: bool = False) -> None:
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
    task_tracker.update_task(task_id, {
        "visit_url": f"/visit?schema={dataset_config['vespa_schema']}&namespace={dataset_config['namespace']}"})

    try:

        # Start the document update worker thread
        worker_thread = threading.Thread(target=queue_worker, daemon=True)
        worker_thread.start()

        with VespaClient.sync_context("feed") as sync_app:

            # Run `delete_all_docs` asynchronously to avoid blocking the event loop
            logger.info(f"Deleting all documents for namespace: {dataset_config['namespace']}")
            await asyncio.to_thread(delete_document_namespace, sync_app, dataset_config['namespace'], None)

            if delete_only:
                task_tracker.update_task(task_id, {
                    "status": "completed",
                    "end_time": time.time()
                })
                return

            for transformer_index, file_config in enumerate(dataset_config['files']):
                logger.info(f"Fetching items from stream: {file_config['url']}")
                update_place = file_config.get("update_place", False)
                stream_fetcher = StreamFetcher(file_config)
                stream = stream_fetcher.get_items()
                logger.info(f"Starting ingestion...")
                responses = await process_documents(stream, dataset_config, transformer_index, sync_app, limit,
                                                    task_id, update_place)
                # Responses could be parsed to check for errors, but avoid accumulating them in memory

                if file_config['file_type'] == 'nt':
                    # Process the temporary `variants` after all triples have been processed
                    process_variants()

            logger.info(f"Completed.")

            # Final update to the task tracker
            task_tracker.update_task(task_id, {
                "status": "completed",
                "end_time": time.time()
            })

    except Exception as e:
        logger.exception(f"Error during ingestion: {e}")
        task_tracker.update_task(task_id, {"status": "failed", "error": str(e)})


async def start_ingestion_in_background(dataset_name: str, task_id: str, limit: int = None, delete_only=False) -> Task:
    """
    Starts the ingestion in a background task.

    :param dataset_name: The name of the dataset
    :param task_id: The task ID for tracking
    :param limit: Maximum number of items to ingest
    """
    task = asyncio.create_task(background_ingestion(dataset_name, task_id, limit, delete_only))

    # Add the task to the task tracker (also triggers cleanup of expired tasks)
    task_tracker.add_task(task_id)

    return task


def delete_document_namespace(sync_app, namespace, schema=None):
    """Delete all documents in the given namespace."""
    # Delete documents belonging to the given namespace

    # logger.info("*********************** Bypassing deletion of variant documents.")
    # return

    if schema is None:
        schema = ['place', 'toponym', 'link', 'variant']
    for schema in schema:
        sync_app.delete_all_docs(
            namespace=namespace,
            schema=schema,
            content_cluster_name="content"
        )
        logger.info(f"Deleted {namespace}:{schema} documents.")

    exit(0)
