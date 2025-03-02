# /ingestion/processor.py
import asyncio
import json
import logging
import os
import queue
import threading
import time
from concurrent.futures import ThreadPoolExecutor

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..bcp_47.bcp_47 import bcp47_fields
from ..config import VespaClient
from ..utils import task_tracker, get_uuid, distinct_dicts, escape_yql

logger = logging.getLogger(__name__)


class TransformationManager:
    def __init__(self, source_file_path, dataset_name, transformer_index, task_id, skip_transform=False):
        """
        Initializes TransformationManager with output file path based on source file.

        :param source_file_path: Path to the source file.
        :param dataset_name: Name of the dataset.
        :param transformer_index: Index of the transformer.
        :param task_id: Unique identifier for the ingestion task.
        :param skip_transform: If True, skips transformation.
        """
        self.dataset_name = dataset_name
        self.transformer_index = transformer_index
        self.task_id = task_id
        self.output_file = self._get_output_file_path(source_file_path, transformer_index)
        if not skip_transform and os.path.exists(self.output_file):
            os.remove(self.output_file)  # Delete pre-existing file unless skip_transform is True

    def _get_output_file_path(self, source_file_path, transformer_index):
        """
        Constructs the output file path based on the source file path and transformer index.

        :param source_file_path: Path to the source file.
        :param transformer_index: Index of the transformer.
        :return: Path to the output file.
        """
        base_name, _ = os.path.splitext(source_file_path)
        return f"{base_name}_transformed_{transformer_index}.ndjson"

    async def transform_and_store(self, document):
        """
        Transforms the document and stores the result in the output file.

        :param document: The document to be transformed and stored.
        """
        transformed_data = DocTransformer.transform(document, self.dataset_name, self.transformer_index)
        task_tracker.update_task(self.task_id, {"transformed": 1})
        with open(self.output_file, "a") as f:
            json.dump(transformed_data, f)
            f.write("\n")


class IngestionManager:
    def __init__(self, dataset_name, task_id, limit=None, delete_only=False, no_delete=False, skip_transform=False):
        """
        Initializes IngestionManager with dataset configuration and Vespa client.

        :param dataset_name: Name of the dataset to ingest.
        :param task_id: Unique identifier for the ingestion task.
        :param limit: Optional limit for the number of documents to process.
        :param delete_only: If True, only deletes existing data.
        :param no_delete: If True, skips deleting existing data.
        :param skip_transform: If True, skips transformation
        """
        self.dataset_name = dataset_name
        self.task_id = task_id
        self.limit = limit
        self.delete_only = delete_only
        self.no_delete = no_delete
        self.dataset_config = self._get_dataset_config()
        self.executor = ThreadPoolExecutor(max_workers=10)  # Executor for async tasks
        self.max_queue_size = 100  # Queue size for document update tasks
        self.update_queue = queue.Queue(maxsize=self.max_queue_size)
        self.transformer_index = None
        self.update_place = False
        self.transformation_manager = None
        self.skip_transform = skip_transform
        task_tracker.add_task(self.task_id)

    def _get_dataset_config(self):
        """
        Retrieves the configuration for the given dataset.

        :return: Dataset configuration.
        :raises ValueError: If the dataset configuration is not found.
        """
        config = next((config for config in REMOTE_DATASET_CONFIGS if config['dataset_name'] == self.dataset_name),
                      None)
        if config is None:
            raise ValueError(f"Dataset configuration not found for dataset: {self.dataset_name}")
        return config

    async def _delete_existing_data(self, schema=None):
        """
        Deletes existing data in the specified Vespa schema(s).

        :param schema: List of schema names to delete data from. If None, deletes from all schemas.
        """
        logger.info(f"Deleting all documents for namespace: {self.dataset_config['namespace']}")
        if schema is None:
            schema = ['place', 'toponym', 'link', 'variant']

        with VespaClient.sync_context("feed") as sync_app:

            for schema in schema:
                # https://pyvespa.readthedocs.io/en/latest/reference-api.html#vespa.application.Vespa.delete_all_docs
                response = sync_app.delete_all_docs(
                    namespace=self.dataset_config['namespace'],
                    schema=schema,
                    content_cluster_name="content"
                )
                logger.info(f"Deleted {self.dataset_config['namespace']}:{schema} documents.")
                logger.info(f"Response: {response}")

    async def ingest_data(self):
        """
        Orchestrates the ingestion process: deletes existing data (if configured),
        processes the dataset, and updates the task tracker.
        """
        logger.info(f"Processing dataset: {self.dataset_name}")
        task_tracker.update_task(self.task_id, {
            "visit_url": f"/visit?schema={self.dataset_config['vespa_schema']}&namespace={self.dataset_config['namespace']}"
        })

        try:
            # Start the queue worker thread
            worker_thread = threading.Thread(target=self._queue_worker, daemon=True)
            worker_thread.start()

            if not self.no_delete:
                await self._delete_existing_data()

            if not self.delete_only:
                await self._process_dataset()

            task_tracker.update_task(self.task_id, {
                "status": "completed",
                "end_time": time.time()
            })

        except Exception as e:
            logger.exception(f"Error during ingestion: {e}")
            task_tracker.update_task(self.task_id, {"status": "failed", "error": str(e)})

    async def _process_dataset(self):
        """
        Processes each file in the dataset configuration by fetching data from the stream,
        initiating document processing, and handling any post-processing steps.
        """
        for self.transformer_index, file_config in enumerate(self.dataset_config['files']):
            logger.info(f"Fetching items from stream: {file_config['url']}")
            self.update_place = file_config.get("update_place", False)
            stream_fetcher = StreamFetcher(file_config)

            # Get the source file path from StreamFetcher
            source_file_path = stream_fetcher.get_file_path()  # Access the _get_file_path method

            # Initialise TransformationManager with source_file_path
            self.transformation_manager = TransformationManager(
                source_file_path,
                self.dataset_name,
                self.transformer_index,
                self.task_id,
                skip_transform=self.skip_transform
            )

            logger.info(f"Output file: {self.transformation_manager.output_file}")
            logger.info(f"Path exists: {os.path.exists(self.transformation_manager.output_file)}")
            logger.info(f"Skip transform: {self.skip_transform}")

            if self.skip_transform and os.path.exists(self.transformation_manager.output_file):
                logger.info(f"Skipping transformation - using existing transformed file.")
            else:
                stream = stream_fetcher.get_items()
                logger.info(f"Starting transformation...")
                await self._transform_documents(stream)
                stream_fetcher.close_stream()

            # Open a new stream for ingesting from the transformed file
            transformed_file_path = self.transformation_manager.output_file
            transformed_stream_fetcher = StreamFetcher({
                'url': transformed_file_path,
                'file_type': 'ndjson'
            })

            transformed_stream = transformed_stream_fetcher.get_items()
            logger.info(f"Starting ingestion from {transformed_file_path}...")
            # Ingest data from the transformed stream
            await self._process_documents(transformed_stream)
            transformed_stream_fetcher.close_stream()  # Close the transformed stream

        logger.info("Starting post-processing...")
        await self._condense_toponyms()  # Condense toponyms after all are processed

        logger.info(f"Completed processing dataset {self.dataset_name}")

    async def _transform_documents(self, stream):
        """
        Processes documents from the stream, applying filters and handling concurrency.
        """
        results = []
        counter = 0
        filters = self.dataset_config.get('files')[self.transformer_index].get('filters')

        async for document in stream:
            # Apply filters (if any)
            if filters and not any(f(document) for f in filters):
                continue

            # It is necessary to await the task to ensure that the file is written (otherwise the file may not be closed correctly)
            await self.transformation_manager.transform_and_store(document)
            counter += 1

            # Stop processing if the limit is reached
            if self.limit is not None and counter >= self.limit:
                break

        return results

    async def _process_documents(self, stream):
        """
        Processes documents from the stream, handling concurrency.

        :param stream: Asynchronous iterator yielding documents.
        :return: List of results from processed documents.
        """
        results = []  # Collect results from processed documents
        counter = 0

        async for document in stream:
            transformed_document, toponyms, links = document
            await self._process_document(transformed_document, toponyms, links, counter)
            counter += 1

            # Stop processing if the limit is reached
            if self.limit is not None and counter >= self.limit:
                break

        return results  # Return aggregated results

    async def _process_document(self, transformed_document, toponyms, links, count):
        """
        Processes a single document by transforming it, feeding it to Vespa,
        and handling any associated toponyms and links.

        :param document: The document to process.
        :param count: The document counter.
        :return: Dictionary containing the success status and any errors.
        """

        try:
            if not transformed_document and not toponyms:
                # Set dummy response
                response = {"success": True}
                success = True
            else:
                response = await asyncio.get_event_loop().run_in_executor(
                    self.executor, self._feed_document, transformed_document, count, False
                ) or {}
                success = response.get("success", False)

                if success and toponyms:
                    toponym_responses = await asyncio.gather(*[
                        asyncio.get_event_loop().run_in_executor(self.executor, self._feed_document, toponym, count,
                                                                 True)  # Set is_toponym flag
                        for toponym in toponyms
                    ])

                    # Check if any toponym feed failed
                    if any(not r.get("success") for r in toponym_responses):
                        success = False

            if success and links:
                link_responses = await asyncio.gather(*[
                    asyncio.get_event_loop().run_in_executor(
                        self.executor, self._feed_link, 'link', link, count
                    )
                    for link in links
                ])

                # Check if any link feed failed
                if any(not r.get("success") for r in link_responses):
                    success = False

            task_tracker.update_task(self.task_id, {
                "processed": 1,
                "success": 1 if success else 0,
                "failure": 1 if not success else 0
            })
            return response
        except Exception as e:
            task_tracker.update_task(self.task_id, {"processed": 1, "failure": 1, "error": f"#{count}: {str(e)}"})
            return {"success": False,
                    "document": f"{self.dataset_config['namespace']}:{self.dataset_config['vespa_schema']}:{transformed_document}",
                    "error": str(e)}

    def _feed_document(self, transformed_document, count, is_toponym=False):
        """
        Feeds the transformed document to Vespa, handling toponym deduplication and updates.

        :param transformed_document: The transformed document to feed.
        :param count: The document counter.
        :param is_toponym: Flag indicating whether the document is a toponym.
        :return: Dictionary containing the success status and any errors.
        """

        document_id = transformed_document.get("document_id")
        if not document_id:
            logger.error(f"Document ID not found: {transformed_document}")
            return {
                "success": False,
                "namespace": self.dataset_config['namespace'],
                "schema": self.dataset_config['vespa_schema'],
                "document_id": document_id,
                "error": "Document ID not found in transformed document"
            }

        try:
            with VespaClient.sync_context("feed") as sync_app:
                #  Handle toponyms: add creation timestamp and staging flag
                if is_toponym or self.dataset_config['vespa_schema'] == 'toponym':
                    transformed_document['fields']['created'] = int(time.time() * 1000)
                    transformed_document['fields']['is_staging'] = True
                    task_tracker.update_task(self.task_id, {"toponyms_staged": 1})

                #  If updating place, add to queue and return
                if self.update_place and not is_toponym:
                    task = (self.dataset_config['vespa_schema'], document_id, transformed_document, count)
                    self.update_queue.put(task)
                    return {"success": True}  # Indicate success for queueing

                #  Otherwise, feed the document directly to Vespa
                response = sync_app.feed_existing(
                    namespace=self.dataset_config['namespace'],
                    schema='toponym' if is_toponym else self.dataset_config['vespa_schema'],
                    data_id=document_id,
                    fields=transformed_document['fields']
                )

                if response.get('status_code') < 500:
                    return {"success": True, "namespace": self.dataset_config['namespace'],
                            "schema": self.dataset_config['vespa_schema'], "document_id": document_id}
                else:
                    msg = response if response.headers.get('content-type') == 'application/json' else response.text
                    task_tracker.update_task(self.task_id, {"error (A)": f"#{count}: {msg}"})
                    logger.error(
                        f"Failed to feed document: {self.dataset_config['namespace']}:{self.dataset_config['vespa_schema']}::{document_id}, Status code: {response.get('status_code')}, Response: {msg}")
                    return {
                        "success": False,
                        "namespace": self.dataset_config['namespace'],
                        "schema": self.dataset_config['vespa_schema'],
                        "document_id": document_id,
                        "status_code": response.get('status_code'),
                        "message": msg
                    }

        except Exception as e:
            task_tracker.update_task(self.task_id, {"error (E)": f"#{count}: yql: >>>{yql}<<< {str(e)}"})
            logger.error(f"Error feeding document: {document_id} with {yql}, Error: {str(e)}", exc_info=True)
            return {
                "success": False,
                "namespace": self.dataset_config['namespace'],
                "schema": self.dataset_config['vespa_schema'],
                "document_id": document_id,
                "error": str(e)
            }

    def _feed_link(self, schema, link, count):
        """
        Feeds a link to Vespa.

        :param schema: The schema for the link.
        :param link: The link document to feed.
        :param count: The document counter.
        :return: Dictionary containing the success status and any errors.
        """
        # TODO: Check if the link already exists
        # TODO: If the predicate is symmetrical, also check if the reverse link exists
        try:
            with VespaClient.sync_context("feed") as sync_app:
                response = sync_app.feed_existing(
                    namespace=self.dataset_config['namespace'],  # source identifier
                    schema=schema,  # usually 'link'
                    data_id=get_uuid(),
                    fields=link
                )

                if response.get('status_code') < 500:
                    return {"success": True, "link": link}
                else:
                    msg = response if response.headers.get('content-type') == 'application/json' else response.text
                    task_tracker.update_task(self.task_id, {"error (C)": f"#{count}: link: >>>{link}<<< {msg}"})
                    logger.error(
                        f"Failed to feed link: {link}, Status code: {response.get('status_code')}, Response: {msg}")
                    return {
                        "success": False,
                        "link": link,
                        "status_code": response.get('status_code'),
                        "message": msg
                    }
        except Exception as e:
            task_tracker.update_task(self.task_id, {"error (B)": f"#{count}: link: >>>{link}<<< {str(e)}"})
            logger.error(f"Error feeding link: {link}, Error: {str(e)}", exc_info=True)
            return {
                "success": False,
                "link": link,
                "error": str(e)
            }

    def _queue_worker(self):
        """
        Worker function to process tasks from the update queue.
        Uses queue to ensure sequential processing of documents.
        Handles feeding triples and updating existing places.
        """
        while True:
            task = self.update_queue.get()
            if task is None:  # Sentinel to terminate the worker thread
                break

            try:
                _, _, _, count = task

                self._update_existing_place(task)

                if count % 1000 == 0:
                    logger.info(f"{count:,} documents sent for indexing")
                # Pausing helps reduce GC pressure or system resource exhaustion during heavy processing
                if count % 100_000 == 0:
                    logger.info(f"Pausing for 3 minutes to reduce system pressure ...")
                    time.sleep(3 * 60)

            except Exception as e:
                logger.error(f"Error processing update: {e}", exc_info=True)

            finally:
                self.update_queue.task_done()

    def _update_existing_place(self, task):
        """
        Updates an existing place document with new names.

        :param task: Tuple containing schema, document ID, transformed document, and count.
        """
        schema, document_id, transformed_document, count = task
        with VespaClient.sync_context("feed") as sync_app:
            response = sync_app.get_existing(
                namespace=self.dataset_config['namespace'],
                schema=schema,
                data_id=document_id
            )
            # logger.info(f"Response: {response.get('status_code')}: {response}")
            if response.get('status_code') < 500:
                existing_document = response
                existing_names = existing_document.get("fields", {}).get("names", [])
                # logger.info(f'Extending names with {transformed_document["fields"]["names"]} for place {document_id}')
                response = sync_app.update_existing(
                    namespace=self.dataset_config['namespace'],
                    schema=schema,
                    data_id=document_id,
                    fields={
                        "names": distinct_dicts(existing_names, transformed_document['fields']['names'])
                    }
                )
                # logger.info(f"Update response: {response.get('status_code')}: {response}")
            else:
                msg = f"Failed to get existing document: {self.dataset_config['namespace']}:{schema}::{document_id}, Status code: {response.get('status_code')}"
                task_tracker.update_task(self.task_id, {"error (D)": f"#{count}: {msg}"})
                logger.error(msg)

    async def _condense_toponyms(self):
        """
        Condenses staged toponyms in Vespa, iterating until no more are found.
        """
        with VespaClient.sync_context("feed") as sync_app:
            while True:
                yql = 'select * from toponym where is_staging = true limit 1'
                staging_toponym = sync_app.query_existing({'yql': yql}, schema='toponym')

                if not staging_toponym:
                    break  # No more staging toponyms

                logger.info(f"Found staging toponym: {staging_toponym}")

                name = staging_toponym['fields']['name']

                # Find all matching toponyms, ordered by creation timestamp
                yql = f'select documentid, places, is_staging, created from toponym where name_strict contains "{escape_yql(name)}" '
                for field in bcp47_fields:
                    if staging_toponym.get("fields", {}).get(f"bcp47_{field}"):
                        yql += f'and bcp47_{field} contains "{staging_toponym["fields"][f"bcp47_{field}"]}" '
                yql += 'order by created asc'  # Order by creation timestamp
                query_response = sync_app.query({'yql': yql}, schema='toponym')

                if not query_response.is_successful():
                    logger.error(f"Failed to query toponyms: {query_response.get_status_code()}")
                    break

                matching_toponyms = [doc.get('fields', {}) for doc in query_response.get_json().get('root', {}).get('children', [])]
                logger.info(f"Found {len(matching_toponyms)} matching toponyms for {name}")
                logger.info(f"Matching toponyms: {matching_toponyms}")

                # Remove the oldest toponym from the list using pop, and if necessary clear the is_staging flag
                oldest_toponym = matching_toponyms.pop(0)

                logger.info(f"Oldest toponym: {oldest_toponym}")

                oldest_toponym_id = oldest_toponym['documentid'].split('::')[-1]
                deleted_toponyms = []
                if oldest_toponym.get('is_staging'):
                    sync_app.update_existing(
                        namespace=self.dataset_config['namespace'],
                        schema='toponym',
                        data_id=oldest_toponym_id,
                        fields={"is_staging": False}
                    )
                    task_tracker.update_task(self.task_id, {"toponyms_unstaged": 1})

                # If any matching toponyms remain, merge them with the oldest toponym
                if matching_toponyms:
                    unique_places = set(oldest_toponym.get('places', []))

                    # For each, replace the toponym id in the linked place with the oldest toponym id
                    for toponym in matching_toponyms:
                        toponym_id = toponym['documentid'].split('::')[-1]
                        toponym_places = toponym.get('places', [])

                        # Update the place(s) linked to the toponym
                        for place_id in toponym_places:
                            place = sync_app.get_existing(
                                namespace=self.dataset_config['namespace'],
                                schema='place',
                                data_id=place_id
                            )
                            place_names = place['fields'].get('names', [])
                            # Find the matching name and replace the toponym id
                            for name in place_names:
                                if name.get('toponym_id') == toponym_id:
                                    name['toponym_id'] = oldest_toponym_id
                            # Update the place with the replaced toponym id
                            sync_app.update_existing(
                                namespace=self.dataset_config['namespace'],
                                schema='place',
                                data_id=place_id,
                                fields={"names": place_names}
                            )
                            # Add the place to the unique set
                            unique_places.add(place_id)

                        # Delete the merged toponym
                        sync_app.delete_data(
                            namespace=self.dataset_config['namespace'],
                            schema='toponym',
                            data_id=toponym_id
                        )
                        task_tracker.update_task(self.task_id, {"toponyms_unstaged": 1})
                        deleted_toponyms += [toponym_id]

                    # Update the oldest toponym with merged places
                    sync_app.update_existing(
                        namespace=self.dataset_config['namespace'],
                        schema='toponym',
                        data_id=oldest_toponym_id,
                        fields={
                            "places": list(unique_places)
                        }
                    )

                ## Latency has to be mitigated

                # Loop until the oldest_toponym has a False is_staging flag
                while True:
                    oldest_toponym = sync_app.get_existing(
                        namespace=self.dataset_config['namespace'],
                        schema='toponym',
                        data_id=oldest_toponym_id
                    )
                    logger.info(f"Check update Oldest toponym: {oldest_toponym}")
                    if not oldest_toponym.get('fields', {}).get('is_staging'):
                        break
                    time.sleep(0.001)

                # Loop until all deleted toponyms are no longer found
                while True:
                    found = []
                    for toponym_id in deleted_toponyms:
                        toponym = sync_app.get_existing(
                            namespace=self.dataset_config['namespace'],
                            schema='toponym',
                            data_id=toponym_id
                        )
                        if toponym:
                            found.append(toponym_id)
                    if not found:
                        break
                    time.sleep(0.001)