# /ingestion/processor.py
import asyncio
import json
import logging
import os
import time

import httpx

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..bcp_47.bcp_47 import bcp47_fields
from ..config import VespaClient
from ..utils import task_tracker, distinct_dicts, escape_yql

logger = logging.getLogger(__name__)
logging.getLogger("httpx").setLevel(logging.WARNING)


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
        self.output_files = self._get_output_file_paths(source_file_path, transformer_index)
        if not skip_transform:
            for output_file in self.output_files.values():
                if os.path.exists(output_file):
                    os.remove(output_file)  # Delete pre-existing file unless skip_transform is True
                    logger.info(f"Deleted existing file: {output_file}")

    def _get_output_file_paths(self, source_file_path, transformer_index):
        """
        Constructs the output file paths based on the source file path and transformer index.

        :param source_file_path: Path to the source file.
        :param transformer_index: Index of the transformer.
        :return: Paths to the output files.
        """
        base_name, _ = os.path.splitext(source_file_path)
        output_file_paths = {}
        for doc_type in ["place", "toponym", "link"]:
            output_file_paths[doc_type] = f"{base_name}_transformed_{transformer_index}_{doc_type}.ndjson"

        return output_file_paths

    async def transform_and_store(self, document):
        """
        Transforms the document and stores the result in the output file.

        :param document: The document to be transformed and stored.
        """
        place, toponyms, links = DocTransformer.transform(document, self.dataset_name, self.transformer_index)

        # Write place to file
        if place:
            await asyncio.to_thread(self._write_to_file, place, 'place')
            task_tracker.update_task(self.task_id, {"transformed_places": 1})

        # Write toponyms to file
        if toponyms:
            for toponym in toponyms:
                await asyncio.to_thread(self._write_to_file, toponym, 'toponym')
            task_tracker.update_task(self.task_id, {"transformed_toponyms": len(toponyms)})

        # Write links to file
        if links:
            for link in links:
                await asyncio.to_thread(self._write_to_file, link, 'link')
            task_tracker.update_task(self.task_id, {"transformed_links": len(links)})

    def _write_to_file(self, transformed_data, doc_type):
        """
        Synchronous method to write transformed data to a file. Called from asyncio.to_thread.
        """
        with open(self.output_files[doc_type], "a") as f:
            json.dump(transformed_data, f)
            f.write("\n")


class IngestionManager:
    def __init__(self, dataset_name, task_id, limit=None, delete_only=False, no_delete=False, skip_transform=False,
                 condense_only=False, convert_triples=False, number_of_consumers=500):
        """
        Initializes IngestionManager with dataset configuration and Vespa client.

        :param dataset_name: Name of the dataset to ingest.
        :param task_id: Unique identifier for the ingestion task.
        :param limit: Optional limit for the number of documents to process.
        :param delete_only: If True, only deletes existing data.
        :param no_delete: If True, skips deleting existing data.
        :param skip_transform: If True, skips transformation
        :param condense_only: If True, only condenses existing toponyms.
        :param convert_triples: If True, converts triples to JSON-LD.
        """
        self.dataset_name = dataset_name
        self.task_id = task_id
        self.limit = limit
        self.delete_only = delete_only
        self.no_delete = no_delete or condense_only
        self.dataset_config = self._get_dataset_config()
        self.transformer_index = None
        self.update_place = False
        self.transformation_manager = None
        self.skip_transform = skip_transform
        self.condense_only = condense_only
        self.convert_triples = convert_triples
        task_tracker.add_task(self.task_id)
        self.task_queue = asyncio.Queue()
        self.number_of_consumers = number_of_consumers

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
                response = await asyncio.to_thread(sync_app.delete_all_docs,
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
        if not self.condense_only:
            for self.transformer_index, file_config in enumerate(self.dataset_config['files']):
                logger.info(f"Fetching items from stream: {file_config['url']}")
                self.update_place = file_config.get("update_place", False)
                stream_fetcher = StreamFetcher(file_config)

                if 'ld_file' in file_config and self.convert_triples:
                    stream_fetcher = await self._convert_triples(stream_fetcher, file_config)

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

                logger.info(f"Output files: {self.transformation_manager.output_files}")
                logger.info(f"Skip transform: {self.skip_transform}")

                if self.skip_transform:
                    logger.info(f"Skipping transformation - using existing transformed file.")
                else:
                    stream = stream_fetcher.get_items()
                    logger.info(f"Starting transformation...")
                    await self._transform_documents(stream)
                    stream_fetcher.close_stream()

                # Process each document type
                with VespaClient.sync_context("feed") as sync_app:
                    for doc_type in ["place", "toponym", "link"]:
                        transformed_file_path = self.transformation_manager.output_files[doc_type]
                        if not os.path.exists(transformed_file_path):
                            logger.warning(f"No {doc_type} data found in {transformed_file_path}")
                            continue
                        transformed_stream_fetcher = StreamFetcher({
                            'url': transformed_file_path,
                            'file_type': 'ndjson'
                        })

                        transformed_stream = transformed_stream_fetcher.get_items()
                        logger.info(f"Starting ingestion from {transformed_file_path}...")
                        # Ingest data from the transformed stream
                        await self._feed_documents(doc_type, transformed_stream, sync_app)
                        transformed_stream_fetcher.close_stream()  # Close the transformed stream

        logger.info("Starting post-processing...")
        await self._condense_places()  # Condense places after all are processed
        await self._condense_toponyms()  # Condense toponyms after all are processed

        # TODO: Post-process links: check if the link already existed
        # TODO: If the predicate is symmetrical, also check if the reverse link exists

        logger.info(f"Completed processing dataset {self.dataset_name}")

    async def _convert_triples(self, stream_fetcher, file_config):
        source_file_path = stream_fetcher.get_file_path()
        ld_source_path = source_file_path.replace(file_config['local_name'], file_config['ld_file'])
        if os.path.exists(ld_source_path):
            os.remove(ld_source_path)
        stream = stream_fetcher.get_items()

        async def fetch_and_write_jsonld(triple: dict, semaphore: asyncio.Semaphore):
            async with semaphore:  # Acquire the semaphore
                try:
                    place_id = triple.get("subject", "").split('/')[-1]
                    url = f"https://vocab.getty.edu/tgn/{place_id}.jsonld"
                    async with httpx.AsyncClient() as client:
                        response = await client.get(url, timeout=10)
                        response.raise_for_status()
                        jsonld = response.json()
                        if jsonld:
                            with open(ld_source_path, "a") as f:
                                json.dump(jsonld, f)
                                f.write("\n")
                                task_tracker.update_task(self.task_id, {f"processed_triples": 1})
                except Exception as e:
                    logger.error(f"Error processing triple {triple}: {e}", exc_info=True)

        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(10)  # Allow 10 concurrent requests

        if self.limit:
            # Process only the first self.limit triples
            counter = 0
            tasks = []
            async for item in stream:
                if counter >= self.limit:
                    break
                tasks.append(fetch_and_write_jsonld(item, semaphore))
                counter += 1
        else:
            tasks = [fetch_and_write_jsonld(item, semaphore) async for item in stream]

        await asyncio.gather(*tasks)
        stream_fetcher.close_stream()

        return StreamFetcher({
            'url': ld_source_path,
            'file_type': 'ndjson'
        })


    async def _transform_documents(self, stream):
        """
        Processes documents from the stream, applying filters and handling concurrency.
        """
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

        return

    async def _feed_documents(self, doc_type, stream, async_app):
        try:

            # Start the producer to enqueue items from the stream
            producer_task = asyncio.create_task(self._enqueue_items(stream))

            # Start the consumers to process items from the queue
            consumer_tasks = [
                asyncio.create_task(self._process_item(async_app, doc_type))
                for _ in range(self.number_of_consumers)
            ]

            # Wait for the producer and consumers to finish their tasks
            await producer_task
            await self.task_queue.join()  # Ensure all items have been processed

            # Stop the consumers by adding None to the queue
            for _ in range(self.number_of_consumers):
                await self.task_queue.put(None)

            # Wait for all consumer tasks to finish
            await asyncio.gather(*consumer_tasks)

        except:
            logger.exception(f"Error feeding documents to Vespa: {doc_type}")
            raise

    async def _enqueue_items(self, stream):
        """Producer: Enqueue items from the stream."""
        async for item in stream:
            await self.task_queue.put(item)

    async def _process_item(self, app, doc_type):
        """Consumer: Dequeue an item and feed it to Vespa."""
        while True:
            try:
                item = await asyncio.wait_for(self.task_queue.get(), timeout=60)
                if item is None:
                    break  # Sentinel value

                try:
                    response = app.feed_data_point(
                        schema=doc_type,
                        namespace=self.dataset_config['namespace'],
                        data_id=item['id'],
                        fields=item['fields'],
                    )
                    if response.is_successful():
                        task_tracker.update_task(self.task_id, {f"processed_{doc_type}s": 1, "success": 1})
                        logger.debug(f"Successfully fed document {item['id']}")
                    else:
                        error_msg = f"Failed to feed document {item['id']}: {response.get_status_code()}, Response: {response}"
                        task_tracker.update_task(self.task_id, {f"processed_{doc_type}s": 1, "failure": 1, "error": error_msg})
                        logger.error(error_msg)

                except Exception as e:
                    error_msg = f"Error feeding data point: {e}, item: {item}"
                    task_tracker.update_task(self.task_id, {f"processed_{doc_type}s": 1, "failure": 1, "error": error_msg})
                    logger.error(error_msg, exc_info=True)

            except asyncio.TimeoutError:
                logger.warning("task_queue.get() timed out.")
                continue

            except Exception as e:
                logger.error(f"Error in _process_item: {e}", exc_info=True)

            finally:
                self.task_queue.task_done()

    async def _condense_places(self):
        """
        Condenses staged places in Vespa, iterating until no more are found.
        """
        with VespaClient.sync_context("feed") as sync_app:
            logger.info("Condensing places...")
            while True:
                yql = 'select * from place where is_staging = true limit 1'
                staging_place = await asyncio.to_thread(sync_app.query_existing, {'yql': yql}, schema='place')

                if not staging_place:
                    break

                staging_id = staging_place['fields']['record_id']

                # Find all staged places with the same record_id
                yql = f'select documentid, names from place where record_id contains "{staging_id}" and is_staging = true'
                query_response = await asyncio.to_thread(sync_app.query, {'yql': yql}, schema='place')

                if not query_response.is_successful():
                    logger.error(f"Failed to query places: {query_response.get_status_code()}")
                    break

                matching_places = [doc.get('fields', {}) for doc in
                                   query_response.get_json().get('root', {}).get('children', [])]

                # Delete the staged places
                matching_ids = [place['documentid'].split('::')[-1] for place in matching_places]
                for place_id in matching_ids:
                    await asyncio.to_thread(sync_app.delete_data,
                                            namespace=self.dataset_config['namespace'],
                                            schema='place',
                                            data_id=place_id
                                            )
                    task_tracker.update_task(self.task_id, {"unstaged_places": 1})

                # Fetch the parent place from Vespa
                parent_place = await asyncio.to_thread(sync_app.get_existing,
                                                       namespace=self.dataset_config['namespace'],
                                                       schema='place',
                                                       data_id=staging_id)

                # Update the parent place with the merged names
                await asyncio.to_thread(sync_app.update_existing,
                                        namespace=self.dataset_config['namespace'],
                                        schema='place',
                                        data_id=staging_id,
                                        fields={
                                            "names": distinct_dicts(
                                                parent_place['fields'].get('names', []),
                                                [name for place in matching_places for name in place.get('names', [])]
                                            )
                                        }
                                        )

    async def _condense_toponyms(self):
        """
        Condenses staged toponyms in Vespa, iterating until no more are found.
        """
        with VespaClient.sync_context("feed") as sync_app:
            logger.info("Condensing toponyms...")
            while True:
                yql = 'select * from toponym where is_staging = true limit 1'
                staging_toponym = await asyncio.to_thread(sync_app.query_existing, {'yql': yql}, schema='toponym')

                if not staging_toponym:
                    break  # No more staging toponyms

                # Find all matching toponyms, ordered by creation timestamp
                name = staging_toponym['fields']['name']
                yql = f'select documentid, places, is_staging, created from toponym where name_strict contains "{escape_yql(name)}" '
                for field in bcp47_fields:
                    if staging_toponym.get("fields", {}).get(f"bcp47_{field}"):
                        yql += f'and bcp47_{field} contains "{staging_toponym["fields"][f"bcp47_{field}"]}" '
                yql += 'order by created asc'  # Order by creation timestamp
                query_response = await asyncio.to_thread(sync_app.query, {'yql': yql}, schema='toponym')

                if not query_response.is_successful():
                    logger.error(f"Failed to query toponyms: {query_response.get_status_code()}")
                    break

                matching_toponyms = [doc.get('fields', {}) for doc in
                                     query_response.get_json().get('root', {}).get('children', [])]

                # Remove the oldest toponym from the list using pop, and if necessary clear the is_staging flag
                oldest_toponym = matching_toponyms.pop(0)
                oldest_toponym_id = oldest_toponym['documentid'].split('::')[-1]
                deleted_toponyms = []
                if oldest_toponym.get('is_staging'):
                    result = await asyncio.to_thread(
                        sync_app.update_existing,
                        namespace=self.dataset_config['namespace'],
                        schema='toponym',
                        data_id=oldest_toponym_id,
                        fields={"is_staging": False}
                    )
                    task_tracker.update_task(self.task_id, {"unstaged_toponyms": 1})

                # If any matching toponyms remain, merge them with the oldest toponym
                if matching_toponyms:
                    unique_places = set(oldest_toponym.get('places', []))

                    # For each, replace the toponym id in the linked place with the oldest toponym id
                    for toponym in matching_toponyms:
                        toponym_id = toponym['documentid'].split('::')[-1]
                        toponym_places = toponym.get('places', [])

                        # Update the place(s) linked to the toponym
                        for place_id in toponym_places:
                            place = await asyncio.to_thread(sync_app.get_existing,
                                                            namespace=self.dataset_config['namespace'],
                                                            schema='place',
                                                            data_id=place_id)
                            place_names = place['fields'].get('names', [])
                            # Find the matching name and replace the toponym id
                            for name in place_names:
                                if name.get('toponym_id') == toponym_id:
                                    name['toponym_id'] = oldest_toponym_id
                            # Update the place with the replaced toponym id
                            await asyncio.to_thread(sync_app.update_existing,
                                                    namespace=self.dataset_config['namespace'],
                                                    schema='place',
                                                    data_id=place_id,
                                                    fields={"names": place_names}
                                                    )
                            # Add the place to the unique set
                            unique_places.add(place_id)

                        # Delete the merged toponym
                        await asyncio.to_thread(sync_app.delete_data,
                                                namespace=self.dataset_config['namespace'],
                                                schema='toponym',
                                                data_id=toponym_id
                                                )
                        task_tracker.update_task(self.task_id, {"unstaged_toponyms": 1})
                        deleted_toponyms += [toponym_id]

                    # Update the oldest toponym with merged places
                    await asyncio.to_thread(sync_app.update_existing,
                                            namespace=self.dataset_config['namespace'],
                                            schema='toponym',
                                            data_id=oldest_toponym_id,
                                            fields={
                                                "places": list(unique_places)
                                            }
                                            )
