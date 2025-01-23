"""

When processing toponyms (`term`) create if not exists, using uuid
Store found or created uuid in variant

Loop variants
- Add place to toponym [places]
- Add variant (excluding place id) to place [names], assigning 0, 1, or 2 to the is_preferred flag


"""

import logging

from ..bcp_47.bcp_47 import bcp47_fields
from ..utils import get_uuid

logger = logging.getLogger(__name__)


def process_variants():
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


def feed_triple(task):
    sync_app, namespace, _, _, transformed_document, task_id, count, task_tracker = task

    if not transformed_document:
        return {
            "success": False,
            "namespace": namespace,
            "error": "No transformed document #{count} found"
        }
    try:
        for schema, document in transformed_document.items():
            if not schema:
                return {
                    "success": False,
                    "namespace": namespace,
                    "schema": schema,
                    "document_id": document.get("document_id"),
                    "error": "No schema found"
                }
            logger.info(
                f"Feeding triple #{count}: {namespace}:{schema}::{document.get('document_id')} {document.get('fields')}")

            # Check if document already exists
            if schema == "toponym":
                yql = f'select documentid, places from toponym where name_strict contains "{document.get("fields").get("name_strict")}" '
                for field in bcp47_fields:
                    if transformed_document.get("fields", {}).get(f"bcp47_{field}"):
                        yql += f'and bcp47_{field} contains "{document.get("fields").get(f"bcp47_{field}")}" '
                yql += 'limit 1'

                if (preexisting := sync_app.query_existing(
                    {'yql': yql},
                    # Do not set namespace
                    schema=schema,
                )):
                    if preexisting_errors := preexisting.get("errors"):
                        msg = f"#{count}: Error querying {schema} document: {preexisting_errors}"
                        task_tracker.update_task(task_id, {"error": msg})
                        logger.error(msg, exc_info=True)
                        return {"success": False, "error": preexisting_errors}
                    else:
                        document["document_id"] = preexisting.get("document_id")
                else:
                    document["document_id"] = get_uuid()
                # No other toponym fields to be adjusted for subsequent toponym update
                # Store toponym id in variant
                response = sync_app.update_existing(
                    # https://pyvespa.readthedocs.io/en/latest/reference-api.html#vespa.io.VespaResponse
                    namespace=namespace,
                    schema='variant',
                    data_id=document.get("variant_id"),
                    fields={
                        'toponym': document["document_id"]
                    },
                    create=True  # Create if not exists
                )
                # logger.info(f"Variant update response: {response.get_json()}")
                if not response.is_successful():
                    msg = f"#{count}: Error storing toponym id in variant: {response.get_json()}"
                    task_tracker.update_task(task_id, {"error": msg})
                    logger.error(msg, exc_info=True)

            else:
                preexisting = sync_app.get_existing(
                    data_id=document.get("document_id"),
                    namespace=namespace,
                    schema=schema,
                )
                if preexisting and schema == "place":
                    document["fields"]["types"] = preexisting.get("fields").get("types", []) + document.get(
                        "fields").get("types", [])

            # logger.info(f"Updating {schema} {preexisting} with {document}")

            response = sync_app.update_existing(
                # https://pyvespa.readthedocs.io/en/latest/reference-api.html#vespa.io.VespaResponse
                namespace=namespace,
                schema=schema,
                data_id=document.get("document_id"),
                fields=document.get("fields"),
                create=True  # Create if not exists
            )
            # Report any errors
            if not response.is_successful():
                msg = f"#{count}: Error updating {namespace}:{schema} document: {response.get_status_code()}] {response.get_json()}"
                task_tracker.update_task(task_id, {"error": msg})
                logger.error(msg, exc_info=True)

    except Exception as e:
        msg = f"#{count}: Error feeding document: {str(e)}"
        task_tracker.update_task(task_id, {"error": msg})
        logger.error(msg, exc_info=True)
        return
