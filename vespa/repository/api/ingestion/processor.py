# /ingestion/processor.py
import asyncio
import logging
import queue
import time
from concurrent.futures import ThreadPoolExecutor

from .config import REMOTE_DATASET_CONFIGS
from .streamer import StreamFetcher
from .transformers import DocTransformer
from ..bcp_47.bcp_47 import bcp47_fields
from ..config import VespaClient
from ..utils import task_tracker, get_uuid, escape_yql, distinct_dicts

logger = logging.getLogger(__name__)


class IngestionManager:
    def __init__(self, dataset_name, task_id, limit=None, delete_only=False, no_delete=False):
        self.dataset_name = dataset_name
        self.task_id = task_id
        self.limit = limit
        self.delete_only = delete_only
        self.no_delete = no_delete
        self.dataset_config = self._get_dataset_config()
        self.vespa_client = VespaClient.sync_context("feed")  # Initialize VespaClient
        self.executor = ThreadPoolExecutor(max_workers=10)  # For CPU-bound tasks
        self.max_queue_size = 100  # Queue size for document update tasks
        self.update_queue = queue.Queue(maxsize=self.max_queue_size)

    def _get_dataset_config(self):
        """ Retrieves the configuration for the given dataset. """
        config = next((config for config in REMOTE_DATASET_CONFIGS if config['dataset_name'] == self.dataset_name),
                      None)
        if config is None:
            raise ValueError(f"Dataset configuration not found for dataset: {self.dataset_name}")
        return config

    async def _delete_existing_data(self, schema=None):
        """ Deletes existing data in the namespace. """

        logger.info(f"Deleting all documents for namespace: {self.dataset_config['namespace']}")
        if schema is None:
            schema = ['place', 'toponym', 'link', 'variant']

        for schema in schema:
            # Use asyncio.to_thread to make this call non-blocking
            await asyncio.to_thread(self.vespa_client.delete_all_docs(
                namespace=self.dataset_config['namespace'],
                schema=schema,
                content_cluster_name="content"
            ))
            logger.info(f"Deleted {self.dataset_config['namespace']}:{schema} documents.")

    async def ingest_data(self):
        """ Main method to orchestrate the ingestion process."""
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
        """ Fetch items from the stream and initiate processing. """
        for transformer_index, file_config in enumerate(self.dataset_config['files']):
            logger.info(f"Fetching items from stream: {file_config['url']}")
            update_place = file_config.get("update_place", False)
            stream_fetcher = StreamFetcher(file_config)
            stream = stream_fetcher.get_items()
            logger.info(f"Starting ingestion...")
            await self._process_documents(stream, transformer_index, update_place)
            if file_config['file_type'] == 'nt':
                # Process the temporary `variants` after all triples have been processed
                self._process_variants()

        logger.info(f"Completed.")

    async def _process_documents(self, stream, transformer_index, update_place=False):
        """ Processes the documents from the stream. """
        # logger.info(f"process_documents: (update place = {update_place})")
        semaphore = asyncio.Semaphore(10)  # Limit concurrent batch processing
        batch_size = 25  # Number of documents to process at a time
        results = []  # Collect results from processed documents
        counter = 0
        current_batch = []
        count = 0
        filters = self.dataset_config.get('files')[transformer_index].get('filters')

        async def _process_batch(batch):
            async with semaphore:
                tasks = [self._process_document(doc, transformer_index, counter, update_place=update_place) for doc in
                         batch]
                batch_results = await asyncio.gather(*tasks)
                results.extend(batch_results)  # Collect results

        async for document in stream:
            # Apply filters (if any)
            if filters and not any(f(document) for f in filters):
                continue

            current_batch.append(document)
            count += 1

            # Process the batch when it reaches the batch_size or limit
            if len(current_batch) >= batch_size or (self.limit is not None and count >= self.limit):
                await _process_batch(current_batch)
                current_batch = []

                # Stop processing if the limit is reached
                if self.limit is not None and counter >= self.limit:
                    break

        # Process any remaining documents in the last batch
        if current_batch:
            await _process_batch(current_batch)

        return results  # Return aggregated results

    async def _process_document(self, document, transformer_index, count, update_place=False):
        # logger.info(f"process_document {count} (update place = {update_place})")
        transformed_document, toponyms, links = DocTransformer.transform(document, self.dataset_config['dataset_name'],
                                                                         transformer_index)
        task_tracker.update_task(self.task_id, {
            "transformed": 1,
        })

        # logger.info(f"Transformed document {transformed_document}")
        # logger.info(f"Toponyms: {toponyms}")
        # if links:
        #     logger.info(f"Links: {links}")
        # terminate
        # return {"success": True}

        try:
            if not transformed_document and not toponyms:
                # Set dummy response
                response = {"success": True}
                success = True
            else:
                response = await asyncio.get_event_loop().run_in_executor(
                    self.executor, self._feed_document, transformed_document, count, update_place
                ) or {}
                success = response.get("success", False)

                if success and toponyms:
                    toponym_responses = await asyncio.gather(*[
                        asyncio.to_thread(self._feed_document, toponym, count, False)
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
                    "document": f"{self.dataset_config['namespace']}:{self.dataset_config['vespa_schema']}:{document}",
                    "error": str(e)}

    def _feed_document(self, transformed_document, count, update_place=False):
        # logger.info(f"feed_document {count} (update place = {update_place}): {transformed_document.get('document_id')}")

        if self.dataset_config['namespace'] == 'tgn':
            # Handle triples differently
            task = (None, None, transformed_document, count)
            self.update_queue.put(task)
            return {"success": True}  # Pending processing in the worker thread

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
            preexisting = None
            yql = None
            if self.dataset_config['vespa_schema'] == 'toponym':
                # Check if toponym already exists
                yql = f'select documentid, places from toponym where name_strict contains "{escape_yql(transformed_document["fields"]["name"])}" '
                for field in bcp47_fields:
                    if transformed_document.get("fields", {}).get(f"bcp47_{field}"):
                        yql += f'and bcp47_{field} contains "{transformed_document["fields"][f"bcp47_{field}"]}" '
                yql += 'limit 1'
                preexisting = self.vespa_client.query_existing(
                    {'yql': yql},
                    # Do not set namespace
                    schema=self.dataset_config['vespa_schema'],
                )

            if preexisting:  # (and schema == 'toponym')
                # Extend `places` list
                existing_toponym_id = preexisting.get("document_id")
                existing_places = preexisting.get("fields", {}).get("places", [])

                response = self.vespa_client.update_existing(
                    # https://docs.vespa.ai/en/reference/document-json-format.html#add-array-elements
                    namespace=self.dataset_config['namespace'],
                    schema=self.dataset_config['vespa_schema'],
                    data_id=existing_toponym_id,
                    fields={
                        "places": list(set(existing_places + [document_id]))
                    }
                )
            else:
                if self.dataset_config['vespa_schema'] == 'toponym':
                    # Inject creation timestamp
                    transformed_document['fields']['created'] = int(time.time() * 1000)
                if update_place:  # (only True when schema == 'place')
                    task = (self.dataset_config['vespa_schema'], document_id, transformed_document, count)
                    self.update_queue.put(task)
                    response = None
                else:
                    response = self.vespa_client.feed_existing(
                        namespace=self.dataset_config['namespace'],
                        schema=self.dataset_config['vespa_schema'],
                        data_id=document_id,
                        fields=transformed_document['fields']
                    )

            if update_place or response.get('status_code') < 500:
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
        # TODO: Check if the link already exists
        # TODO: If the predicate is symmetrical, also check if the reverse link exists
        try:
            response = self.vespa_client.feed_existing(
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
        while True:
            task = self.update_queue.get()
            if task is None:  # Sentinel to terminate the worker thread
                break

            try:
                _, _, _, count = task

                if self.dataset_config['namespace'] == 'tgn':
                    response = self._feed_triple(task)
                    if not response.get("success", False):
                        task_tracker.update_task(self.task_id, {
                            "success": -1,
                            "failure": 1
                        })

                else:
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
        schema, document_id, transformed_document, count = task
        response = self.vespa_client.get_existing(
            namespace=self.dataset_config['namespace'],
            schema=schema,
            data_id=document_id
        )
        # logger.info(f"Response: {response.get('status_code')}: {response}")
        if response.get('status_code') < 500:
            existing_document = response
            existing_names = existing_document.get("fields", {}).get("names", [])
            # logger.info(f'Extending names with {transformed_document["fields"]["names"]} for place {document_id}')
            response = self.vespa_client.update_existing(
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

    def _feed_triple(self, task):
        _, _, transformed_document, count = task

        if not transformed_document:
            return {
                "success": False,
                "namespace": self.dataset_config['namespace'],
                "error": "No transformed document #{count} found"
            }
        try:
            for schema, document in transformed_document.items():
                if not schema:
                    return {
                        "success": False,
                        "namespace": self.dataset_config['namespace'],
                        "schema": schema,
                        "document_id": document.get("document_id"),
                        "error": "No schema found"
                    }
                # logger.info(
                #     # f"Feeding triple #{count}: {namespace}:{schema}::{document.get('document_id')} {document.get('fields')}")

                # Check if document already exists
                if schema == "toponym":
                    yql = f'select documentid, places from toponym where name_strict contains "{document.get("fields").get("name_strict")}" '
                    for field in bcp47_fields:
                        if transformed_document.get("fields", {}).get(f"bcp47_{field}"):
                            yql += f'and bcp47_{field} contains "{document.get("fields").get(f"bcp47_{field}")}" '
                    yql += 'limit 1'

                    if (preexisting := self.vespa_client.query_existing(
                            {'yql': yql},
                            # Do not set namespace
                            schema=schema,
                    )):
                        if preexisting_errors := preexisting.get("errors"):
                            msg = f"#{count}: Error querying {schema} document: {preexisting_errors}"
                            task_tracker.update_task(self.task_id, {"error": msg})
                            logger.error(msg, exc_info=True)
                            return {"success": False, "error": preexisting_errors}
                        else:
                            document["document_id"] = preexisting.get("document_id")
                    else:
                        document["document_id"] = get_uuid()
                    # No other toponym fields to be adjusted for subsequent toponym update
                    # Store toponym id in variant
                    response = self.vespa_client.update_existing(
                        namespace=self.dataset_config['namespace'],
                        schema='variant',
                        data_id=document.get("variant_id"),
                        fields={
                            'toponym': document["document_id"]
                        },
                        create=True  # Create if not exists
                    )
                    # logger.info(f"Variant update response: {response.get_json()}")
                    if not response.get('status_code') < 500:
                        msg = f"#{count}: Error storing toponym id in variant: {response.get_json()}"
                        task_tracker.update_task(self.task_id, {"error": msg})
                        logger.error(msg, exc_info=True)
                        return {"success": False, "error": response.get_json()}

                else:
                    preexisting = self.vespa_client.get_existing(
                        data_id=document.get("document_id"),
                        namespace=self.dataset_config['namespace'],
                        schema=schema,
                    )
                    if preexisting and schema == "place":
                        document["fields"]["types"] = list(
                            set(preexisting.get("fields", {}).get("types", []) + document.get("fields", {}).get("types",
                                                                                                                [])))

                # logger.info(f"Updating {schema} {preexisting} with {document}")

                response = self.vespa_client.update_existing(
                    namespace=self.dataset_config['namespace'],
                    schema=schema,
                    data_id=document.get("document_id"),
                    fields=document.get("fields"),
                    create=True  # Create if not exists
                )
                # Report any errors
                if not response.get('status_code') < 500:
                    msg = f"#{count}: Error updating {self.dataset_config['namespace']}:{schema} document: {response.get_status_code()}] {response.get_json()}"
                    task_tracker.update_task(self.task_id, {"error": msg})
                    logger.error(msg, exc_info=True)
                    return {"success": False, "error": response.get_json()}

                return {"success": True}

        except Exception as e:
            msg = f"#{count}: Error feeding document: {str(e)}"
            task_tracker.update_task(self.task_id, {"error": msg})
            logger.error(msg, exc_info=True)
            return

    def _process_variants(self):
        """
        Rewrite this function. It should loop over variants, deduplicate lists, store them in the correct documents,
        and finally delete the variant documents.
        """
        #     # Loop through all tgn documents by fetching them from Vespa (use pagination)
        #     with VespaClient.sync_context("feed") as sync_app:
        #         page = 0
        #         page_size = 250
        #         count = 0
        #         while True:
        #             response = sync_app.query(
        #                 {
        #                     "yql": f'select * from place where true',
        #                     "namespace": dataset_name,
        #                     "offset": page * page_size,
        #                     "hits": page_size
        #                 }
        #             ).json
        #             if not response.get("root", {}).get("children", []):
        #                 break
        #             # Loop through all places
        #             for place in response.get("root", {}).get("children", []):
        #                 document_id = place.get("fields", {}).get("documentid", "")
        #                 if document_id:
        #                     count += 1
        #                     # Fetch all variants for the place
        #                     response = sync_app.query(
        #                         {
        #                             "yql": f'select * from variant where places contains "{document_id}"',
        #                             "namespace": dataset_name,
        #                         }
        #                     ).json
        #                     # Add each variant to the place (using `update_triple`), prioritising prefLabelGVP above prefLabel
        #                     for variant in response.get("root", {}).get("children", []):
        #                         task = (
        #                             sync_app, dataset_config['namespace'], 'place', document_id, variant,
        #                             task_id,
        #                             count, task_tracker)
        #                         update_queue.put(task)
        #                         # Add place to the toponym (using `update_triple`)
        #                         task = (sync_app, dataset_config['namespace'], 'toponym',
        #                                 variant.get("fields", {}).get("toponym", ""),
        #                                 {
        #                                     "document_id": variant.get("fields", {}).get("toponym", ""),
        #                                     "places": [document_id]
        #                                 }, task_id, count, task_tracker)
        #                         update_queue.put(task)
        #             page += 1
        #     # Wait for all tasks to complete
        #     update_queue.join()
        #     # Delete all variant documents
        #     delete_document_namespace(sync_app, dataset_config['namespace'], ['variant'])
        pass
