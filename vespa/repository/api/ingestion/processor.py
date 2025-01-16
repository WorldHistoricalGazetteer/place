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


def feed_document(sync_app, namespace, schema, document_id, transformed_document):
    try:
        toponym_exists = False
        if schema == 'toponym':
            # Check if toponym already exists
            with VespaClient.sync_context("feed") as sync_app:
                bcp47_fields = ["language", "script", "region", "variant"]
                yql = f"select * from toponym where name matches '^{transformed_document['name']}$' "
                for field in bcp47_fields:
                    if transformed_document.get(f"bcp47_{field}"):
                        yql += f"and bcp47_{field} matches '^{transformed_document[f'bcp47_{field}']}$' "
                yql += "limit 1"
                logger.info(f"Checking if toponym exists: {yql}")
                existing_response = sync_app.query({'yql': yql}).json
                logger.info(f"Existing toponym response: {existing_response}")
                toponym_exists = existing_response.get("root", {}).get("totalCount", 0) > 0

        if toponym_exists:
            # Extend `places` list
            existing_toponym_id = existing_response.get("root", {}).get("children", [{}])[0].get("id")

            logger.info(
                f'Extending places with {document_id} for toponym {existing_toponym_id}: {existing_response.get("root", {}).get("children", [{}])[0]}')

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
            if schema == 'toponym':
                logger.info(f"Feeding document {namespace}:{schema}::{document_id}: {transformed_document}")
            response = sync_app.feed_data_point(
                namespace=namespace,
                schema=schema,
                data_id=document_id,
                fields=transformed_document,
            )

        if response.status_code == 200:
            return {"success": True, "namespace": namespace, "schema": schema, "document_id": document_id}
        else:
            logger.error(
                f"Failed to feed document: {namespace}:{schema}::{document_id}, Status code: {response.status_code}, Response: {response.json() if response.headers.get('content-type') == 'application/json' else response.text}")
            return {
                "success": False,
                "namespace": namespace,
                "schema": schema,
                "document_id": document_id,
                "status_code": response.status_code,
                "message": response.json() if response.headers.get(
                    'content-type') == 'application/json' else response.text
            }
    except Exception as e:
        logger.error(f"Error feeding document: {document_id}, Error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "namespace": namespace,
            "schema": schema,
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
    # logger.info(f"Feeding document: {document_id}: {transformed_document}")

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            executor, feed_document, sync_app, dataset_config['namespace'], dataset_config['vespa_schema'], document_id,
            transformed_document
        )
        success = response.get("success", False)

        if success and toponyms:
            toponym_responses = await asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(
                    executor, feed_document, sync_app, 'toponym', 'toponym', toponym['record_id'], {
                        key: value for key, value in toponym.items() if key != 'record_id'
                    }  # Remove record_id from toponym document
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
                "document": f"{dataset_config['namespace']}:{dataset_config['vespa_schema']}:{document_id}",
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


def delete_related_toponyms(sync_app, toponym_id, place_id):
    """Delete or update toponyms related to place IDs."""
    try:
        toponym_query = {
            "yql": f"select * from toponym where doc_id matches '::{toponym_id}$' limit 1",
            "namespace": "toponym",
            "schema": "toponym",
            "raise_on_not_found": True
        }
        logger.info(f"Toponym query: {toponym_query}")
        toponym_response = sync_app.get_data(toponym_query).json
        logger.info(f"Toponym response: {toponym_response}")
        toponym_hits = toponym_response.get("root", {}).get("children", [])
        toponym_hit = toponym_hits[0]
        toponym_id = toponym_hit["id"].split(":")[-1]
        if len(toponym_hit.get("fields", {}).get("places")) == 1:
            # Delete toponym if only one place is associated
            logger.info(f"Deleting toponym: {toponym_id}")
            response = sync_app.delete_data(
                namespace="iso3166",
                schema="toponym",
                data_id=toponym_id
            )
            logger.info(f"Delete response: {response.json}")
        else:
            logger.info(f"Updating toponym: {toponym_id}")
            response = sync_app.feed_data_point(
                namespace="toponym",
                schema="toponym",
                data={
                    "update": toponym_id,
                    "fields": {
                        "places": {"remove": [place_id]}
                    }
                }
            )
            logger.info(f"Update response: {response.json}")
    except Exception as e:
        logger.error(f"Error deleting or updating toponyms: {str(e)}", exc_info=True)


def delete_related_links(sync_app, place_ids):
    """Delete links related to place IDs."""
    for place_id in place_ids:
        link_query = f"select * from link where place_id matches '^{place_id}$' or object matches '^{place_id}$' limit {pagination_limit}"
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
                sync_app.delete_data(schema="link", data_id=link["id"].split(":")[-1])

            links_start += pagination_limit  # Move to next page


def delete_all_docs(sync_app, dataset_config):
    """Delete all documents in the given schema and namespace."""
    schema = dataset_config.get("vespa_schema")
    namespace = dataset_config.get("namespace")

    if schema == "place":
        params = {
                "wantedDocumentCount": 100,
                "fieldset": "names",
                "continuation": None
            }
        while True:
            place_response = sync_app.visit(
                namespace=namespace,
                schema=schema,
                params=params,
                content_cluster_name="content"
            )

            # Process the retrieved documents
            for document in place_response.documents:

                # Delete related toponyms
                for name in document.names:
                    delete_related_toponyms(sync_app, name["toponym_id"], document.id.split(":")[-1])

                # Delete related links
                delete_related_links(sync_app, [document.id.split(":")[-1]])

            # Check for continuation
            if "continuation" in place_response.json:
                params["continuation"] = place_response.json["continuation"]
            else:
                break

    # Delete documents belonging to the given schema and namespace
    sync_app.delete_all_docs(
        namespace=namespace,
        schema=schema,
        content_cluster_name="content"
    )
