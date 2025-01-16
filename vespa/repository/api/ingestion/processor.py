# /ingestion/processor.py
import asyncio
import logging
import time
from asyncio import Task
from concurrent.futures import ThreadPoolExecutor

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..config import VespaClient, pagination_limit
from ..utils import get_uuid, task_tracker

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=10)


def feed_document(sync_app, schema, namespace, document_id, transformed_document):
    try:
        toponym_exists = False
        if schema == 'toponym':
            # Check if toponym already exists
            with VespaClient.sync_context("feed") as sync_app:
                bcp47_fields = ["language", "script", "region", "variant"]
                query = f"select * from toponym where name = '{transformed_document['name']}' "
                for field in bcp47_fields:
                    if transformed_document.get(f"bcp47_{field}"):
                        query += f"and bcp47_{field} = '{transformed_document[f'bcp47_{field}']}' "
                query += "limit 1"
                existing_response = sync_app.query(query).json
                toponym_exists = existing_response.get("root", {}).get("totalCount", 0) > 0

        if toponym_exists:
            # Extend `places` list
            existing_toponym_id = existing_response.get("root", {}).get("children", [{}])[0].get("id")

            logger.info(f'Extending places with {document_id} for toponym {existing_toponym_id}: {existing_response.get("root", {}).get("children", [{}])[0]}')

            response = sync_app.feed_data_point(
                # https://docs.vespa.ai/en/reference/document-json-format.html#add-array-elements
                schema=schema,
                data={
                    "update": existing_toponym_id,
                    "fields": {
                        "places": {
                            "add": [document_id]
                        }
                    }
                }
            )
        else:
            logger.info(f"Feeding document {schema}:{namespace}:{document_id}: {transformed_document}")
            response = sync_app.feed_data_point(
                schema=schema,
                namespace=namespace,
                data_id=document_id,
                fields=transformed_document,
            )

        if response.status_code == 200:
            return {"success": True, "document_id": document_id, "schema": schema, "namespace": namespace}
        else:
            logger.error(
                f"Failed to feed document: {schema}:{namespace}:{document_id}, Status code: {response.status_code}, Response: {response.json() if response.headers.get('content-type') == 'application/json' else response.text}")
            return {
                "success": False,
                "document_id": document_id,
                "schema": schema,
                "namespace": namespace,
                "status_code": response.status_code,
                "message": response.json() if response.headers.get(
                    'content-type') == 'application/json' else response.text
            }
    except Exception as e:
        logger.error(f"Error feeding document: {document_id}, Error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "document_id": document_id,
            "schema": schema,
            "namespace": namespace,
            "error": str(e)
        }


async def process_document(document, dataset_config, transformer_index, sync_app, task_id):
    transformed_document, toponyms = DocTransformer.transform(document, dataset_config['dataset_name'],
                                                              transformer_index)
    document_id = transformed_document.get(dataset_config['files'][transformer_index]['id_field']) or get_uuid()
    task_tracker.update_task(task_id, {
        "transformed": 1,
    })
    # logger.info(f"Feeding document: {document_id}: {transformed_document}")

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            executor, feed_document, sync_app, dataset_config['vespa_schema'], dataset_config['namespace'], document_id,
            transformed_document
        )
        success = response.get("success", False)

        if success and toponyms:
            toponym_responses = await asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(
                    executor, feed_document, sync_app, 'toponym', None, toponym['record_id'], toponym
                )
                for toponym in toponyms
            ])

            # Check if any toponym feed failed
            if any(not r.get("success") for r in toponym_responses):
                success = False

        task_tracker.update_task(task_id, {
            "processed": 1,
            "success": 1 if success else 0,
            "failure": 1 if not success else 0
        })
        return response
    except Exception as e:
        task_tracker.update_task(task_id, {"processed": 1, "failure": 1})
        return {"success": False,
                "document": f"{dataset_config['vespa_schema']}:{dataset_config['namespace']}:{document_id}",
                "error": str(e)}


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
        with VespaClient.sync_context("feed") as sync_app:

            # Run `delete_all_docs` asynchronously to avoid blocking the event loop
            logger.info(f"Deleting all documents for schema: {dataset_config['namespace']}")
            await asyncio.to_thread(delete_all_docs, sync_app, dataset_config)

            if delete_only:
                task_tracker.update_task(task_id, {
                    "status": "completed",
                    "end_time": time.time()
                })
                return

            all_responses = []
            for transformer_index, file_config in enumerate(dataset_config['files']):
                logger.info(f"Fetching items from stream: {file_config['url']}")
                stream_fetcher = StreamFetcher(file_config)
                documents = stream_fetcher.get_items()
                responses = await process_documents(documents, dataset_config, transformer_index, sync_app, limit,
                                                    task_id)
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


async def start_ingestion_in_background(dataset_name: str, task_id: str, limit: int = None, delete_only = False) -> Task:
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


def delete_related_toponyms(sync_app, place_ids, schema):
    """Delete or update toponyms related to place IDs."""
    for place_id in place_ids:
        toponym_query = f"select * from toponym where places contains '{place_id}' limit {pagination_limit}"
        toponym_start = 0
        while True:
            toponym_query_paginated = {
                "yql": toponym_query,
                "offset": toponym_start
            }
            logger.info(f"Paginated toponym query: {toponym_query_paginated}")
            toponym_response = sync_app.query(toponym_query_paginated).json
            toponym_hits = toponym_response.get("root", {}).get("children", [])

            if not toponym_hits:
                break

            for toponym_hit in toponym_hits:
                toponym_id = toponym_hit["id"]
                if len(toponym_hit.get("fields", {}).get("places")) == 1:
                    # Delete toponym if only one place is associated
                    sync_app.delete_data(schema="toponym", data_id=toponym_id)
                else:
                    sync_app.feed_data_point(
                        schema=schema,
                        data={
                            "update": toponym_id,
                            "fields": {
                                "places": {"remove": [place_id]}
                            }
                        }
                    )

            toponym_start += pagination_limit  # Move to next page


def delete_related_links(sync_app, place_ids):
    """Delete links related to place IDs."""
    for place_id in place_ids:
        link_query = f"select * from link where place_id contains '{place_id}' or object contains '{place_id}' limit {pagination_limit}"
        links_start = 0
        while True:
            link_query_paginated = {
                "yql": link_query,
                "offset": links_start
            }
            logger.info(f"Paginated link query: {link_query_paginated}")
            links_response = sync_app.query(link_query_paginated).json
            links = links_response.get("root", {}).get("children", [])

            if not links:
                break

            for link in links:
                sync_app.delete_data(schema="link", data_id=link["id"])

            links_start += pagination_limit  # Move to next page


def delete_all_docs(sync_app, dataset_config):
    """Delete all documents in the given schema and namespace."""
    schema = dataset_config.get("vespa_schema")
    namespace = dataset_config.get("namespace")

    if schema == "place":
        # Fetch all place documents with pagination
        place_query = f"select * from place where true limit {pagination_limit}"
        start = 0
        while True:
            place_query_paginated = {
                "yql": place_query,
                "namespace": namespace,
                "offset": start
            }
            logger.info(f"Paginated place query: {place_query_paginated}")
            place_response = sync_app.query(place_query_paginated).json
            places = place_response.get("root", {}).get("children", [])

            if not places:
                break

            place_ids = [place["id"].split(":")[-1] for place in places]

            # Step 1: Delete or update toponyms related to place IDs
            delete_related_toponyms(sync_app, place_ids, schema)

            # Step 2: Delete related links for place IDs
            delete_related_links(sync_app, place_ids)

            if len(places) < pagination_limit:
                break

            start += pagination_limit  # Move to next page

    # Delete documents belonging to the given schema and namespace
    sync_app.delete_all_docs(
        schema=schema,
        namespace=namespace,
        content_cluster_name="content"
    )
