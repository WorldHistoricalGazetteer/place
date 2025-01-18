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
from ..utils import task_tracker, get_uuid

logger = logging.getLogger(__name__)

executor = ThreadPoolExecutor(max_workers=10)


def feed_link(sync_app, link):
    try:
        response = sync_app.feed_data_point(
            namespace="link",
            schema="link",
            data_id=get_uuid(),
            fields=link
        )

        if response.status_code == 200:
            return {"success": True, "link": link}
        else:
            logger.error(
                f"Failed to feed link: {link}, Status code: {response.status_code}, Response: {response.json() if response.headers.get('content-type') == 'application/json' else response.text}")
            return {
                "success": False,
                "link": link,
                "status_code": response.status_code,
                "message": response.json() if response.headers.get(
                    'content-type') == 'application/json' else response.text
            }
    except Exception as e:
        logger.error(f"Error feeding link: {link}, Error: {str(e)}", exc_info=True)
        return {
            "success": False,
            "link": link,
            "error": str(e)
        }


def feed_document(sync_app, namespace, schema, transformed_document):
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
        toponym_exists = False
        if schema == 'toponym':
            # Check if toponym already exists
            with VespaClient.sync_context("feed") as sync_app:
                bcp47_fields = ["language", "script", "region", "variant"]
                yql = f"select documentid, places from toponym where name matches '^{transformed_document['fields']['name']}$' "
                for field in bcp47_fields:
                    if transformed_document.get("fields", {}).get(f"bcp47_{field}"):
                        yql += f"and bcp47_{field} matches '^{transformed_document['fields'][f'bcp47_{field}']}$' "
                yql += "limit 1"
                logger.info(f"Checking if toponym exists: {yql}")
                existing_response = sync_app.query({'yql': yql}).json
                logger.info(f"Existing toponym response: {existing_response}")
                toponym_exists = existing_response.get("root", {}).get("fields", {}).get("totalCount", 0) > 0

        if toponym_exists:
            # Extend `places` list
            existing_toponym_fields = existing_response.get("root", {}).get("children", [{}])[0].get("fields", {})
            existing_toponym_id = existing_toponym_fields.get("documentid").split("::")[-1]
            existing_places = existing_toponym_fields.get("places", [])

            logger.info(
                f'Extending places with {document_id} for toponym {existing_toponym_id}')

            response = sync_app.update_data(
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
                logger.info(f"Feeding document {namespace}:{schema}::{document_id}: {transformed_document}")
            response = sync_app.feed_data_point(
                namespace=namespace,
                schema=schema,
                data_id=document_id,
                fields=transformed_document['fields']
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
    transformed_document, toponyms, links = DocTransformer.transform(document, dataset_config['dataset_name'],
                                                                     transformer_index)
    task_tracker.update_task(task_id, {
        "transformed": 1,
    })
    # logger.info(f"Feeding document: {document}: {transformed_document}")

    try:
        response = await asyncio.get_event_loop().run_in_executor(
            executor, feed_document, sync_app, dataset_config['namespace'], dataset_config['vespa_schema'],
            transformed_document
        )
        success = response.get("success", False)

        if success and toponyms:
            toponym_responses = await asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(
                    executor, feed_document, sync_app, 'toponym', 'toponym', toponym
                )
                for toponym in toponyms
            ])

            # Check if any toponym feed failed
            if any(not r.get("success") for r in toponym_responses):
                success = False

        if success and links:
            link_responses = await asyncio.gather(*[
                asyncio.get_event_loop().run_in_executor(
                    executor, feed_link, sync_app, link
                )
                for link in links
            ])

            # Check if any link feed failed
            if any(not r.get("success") for r in link_responses):
                success

        task_tracker.update_task(task_id, {
            "processed": 1,
            "success": 1 if success else 0,
            "failure": 1 if not success else 0
        })
        return response
    except Exception as e:
        task_tracker.update_task(task_id, {"processed": 1, "failure": 1})
        return {"success": False,
                "document": f"{dataset_config['namespace']}:{dataset_config['vespa_schema']}:{document}",
                "error": str(e)}


async def process_documents(stream, dataset_config, transformer_index, sync_app, limit, task_id):
    semaphore = asyncio.Semaphore(5)  # Limit concurrent tasks
    batch_size = 100  # Number of documents to process at a time
    results = []  # Collect results from processed documents

    async def process_limited(document):
        async with semaphore:
            return await process_document(document, dataset_config, transformer_index, sync_app, task_id)

    async def process_batch(batch):
        tasks = [process_limited(document) for document in batch]
        return await asyncio.gather(*tasks)

    current_batch = []
    count = 0

    async for document in stream:
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
                stream = stream_fetcher.get_items()
                responses = await process_documents(stream, dataset_config, transformer_index, sync_app, limit,
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
        toponym_response = sync_app.get_data(
            data_id=toponym_id,
            namespace="toponym",
            schema="toponym",
            raise_on_not_found=True
        ).json
        logger.info(f"Toponym response: {toponym_response}")
        places = toponym_response.get("fields", {}).get("places", [])
        if len(places) == 1:
            # Delete toponym if only one place is associated
            logger.info(f"Deleting toponym: {toponym_id}")
            response = sync_app.delete_data(
                namespace="toponym",
                schema="toponym",
                data_id=toponym_id
            )
            logger.info(f"Delete response: {response.json}")
        else:
            logger.info(f"Updating toponym: {toponym_id}")
            response = sync_app.update_data(
                namespace="toponym",
                schema="toponym",
                data_id=toponym_id,
                fields={
                    "places": [place for place in places if place != place_id]
                }
            )
            logger.info(f"Update response: {response.json}")
    except Exception as e:
        logger.error(f"Error deleting or updating toponyms: {str(e)}", exc_info=True)


def delete_related_links(sync_app, place_id):
    """Delete links related to place IDs."""
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
        for slice in sync_app.visit(
                content_cluster_name="content",
                namespace=namespace,
                schema=schema,
                wantedDocumentCount=100,
                fieldSet="place:names"
        ):
            for response in slice:
                for document in response.documents:
                    logger.info(f"Document: {document}")
                    document_id = document["id"].split(":")[-1]

                    # Delete related toponyms
                    for name in document.get("fields", {}).get("names", []):
                        delete_related_toponyms(sync_app, name["toponym_id"], document_id)

                    # Delete related links
                    delete_related_links(sync_app, document_id)

    # Delete documents belonging to the given schema and namespace
    sync_app.delete_all_docs(
        namespace=namespace,
        schema=schema,
        content_cluster_name="content"
    )
