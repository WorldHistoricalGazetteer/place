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


def existing_document(query_response_root):
    if query_response_root.get("fields", {}).get("totalCount", 0) == 0:
        return None
    document = query_response_root.get("children", [{}])[0].get("fields", {})
    return {
        'document_id': document.get("documentid").split("::")[-1],
        'fields': document,
    }


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
                query_response_root = sync_app.query(
                    # https://pyvespa.readthedocs.io/en/latest/reference-api.html#vespaqueryresponse
                    {'yql': yql},
                    # Do not set namespace
                    schema=schema,
                ).get_json().get("root", {})
                # logger.info(f"Existing {schema} query_response_root: {query_response_root}")
                if query_response_root.get("errors"):
                    task_tracker.update_task(task_id, {"error": f"#{count}: {query_response_root.get('errors')}"})
                    logger.error(
                        f'#{count}: Error querying {schema} document: {query_response_root.get("errors")}',
                        exc_info=True)
                    return {"success": False, "error": query_response_root.get("errors")}
                preexisting = existing_document(query_response_root)
                document["document_id"] = preexisting.get("document_id") if preexisting else get_uuid()
                # No other toponym fields to be adjusted for subsequent toponym update
                # Store toponym id in variant
                response = sync_app.update_data(
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
                    task_tracker.update_task(task_id, {"error": f"#{count}: {response.get_json()}"})
                    logger.error(
                        f'#{count}: Error storing toponym id in variant: {response.get_json()}', exc_info=True)

            else:
                response = sync_app.get_data(
                    # https://pyvespa.readthedocs.io/en/latest/reference-api.html#vespa.io.VespaResponse
                    namespace=namespace,
                    schema=schema,
                    data_id=document.get("document_id"),
                )
                # if not response.is_successful():
                #     logger.info(
                #         f'Failed to find {namespace}:{schema} document: [code: {response.get_status_code()}] {response.get_json()}',
                #         exc_info=True)
                # else:
                #     logger.info(f"Found {namespace}:{schema} document: {response.get_json()}")
                # logger.info(f"Existing {schema} response: {response.get_json()}")
                preexisting = {
                    'document_id': document.get("document_id"),
                    'fields': response.get_json().get("fields", {})
                } if response.is_successful() else None
                if preexisting and schema == "place":
                    document["fields"]["types"] = preexisting.get("fields").get("types", []) + document.get(
                        "fields").get("types", [])

            # logger.info(f"Updating {schema} {preexisting} with {document}")

            response = sync_app.update_data(
                # https://pyvespa.readthedocs.io/en/latest/reference-api.html#vespa.io.VespaResponse
                namespace=namespace,
                schema=schema,
                data_id=document.get("document_id"),
                fields=document.get("fields"),
                create=True  # Create if not exists
            )
            # Report any errors
            if not response.is_successful():
                task_tracker.update_task(task_id, {
                    "error": f"#{count}: Failed to update {namespace}:{schema} document: [code: {response.get_status_code()}] {response.get_json()}"})
                logger.error(
                    f'#{count}: Failed to update {namespace}:{schema} document: [code: {response.get_status_code()}] {response.get_json()}',
                    exc_info=True)

    except Exception as e:
        task_tracker.update_task(task_id, {"error": f"#{count}: {str(e)}"})
        logger.error(
            f'#{count}: Error feeding document: {str(e)}', exc_info=True)
        return
