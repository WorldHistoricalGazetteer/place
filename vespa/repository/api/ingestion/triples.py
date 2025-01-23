"""

When processing toponyms (`term`) create if not exists, using uuid
Store found or created uuid in variant

Loop variants
- Add place to toponym [places]
- Add variant (excluding place id) to place [names], assigning 0, 1, or 2 to the is_preferred flag


"""

import logging

from ..utils import get_uuid

logger = logging.getLogger(__name__)


def existing_document(response):
    if response.get("root", {}).get("fields", {}).get("totalCount", 0) == 0:
        return None
    document = response.get("root", {}).get("children", [{}])[0].get("fields", {})
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
                f"Feeding document #{count}: {namespace}:{schema}::{document.get('document_id')} {document.get('fields')}")

            # Check if document already exists
            if schema == "toponym":
                yql = f'select documentid, places from toponym where name_strict contains "{document.get("fields").get("name_strict")}" '
                yql += f'and bcp47_language contains "{document.get("fields").get("bcp47_language")}" '
                yql += 'limit 1'
                response = sync_app.query(
                    {'yql': yql},
                    # Do not set namespace
                    schema=schema,
                ).json
                logger.info(f"Existing {schema} response: {response}")
                preexisting = existing_document(response)
                document["document_id"] = preexisting.get("document_id") if preexisting else get_uuid()
                # No other toponym fields to be adjusted for subsequent toponym update
                # Store toponym id in variant
                response = sync_app.update_data(
                    namespace=namespace,
                    schema='variant',
                    data_id=document.get("variant_id"),
                    fields={
                        'toponym': document["document_id"]
                    },
                    create=True  # Create if not exists
                )
                # Report any errors
                if response.status_code != 200:
                    task_tracker.update_task(task_id, {"error": f"#{count}: {response.get('error')}"})
                    logger.error(
                        f'Error storing toponym id in variant: {response.get("error")}', exc_info=True)

            else:
                response = sync_app.get_data(
                    namespace=namespace,
                    schema=schema,
                    data_id=document.get("document_id"),
                ).json
                logger.info(f"Existing {schema} response: {response}")
                preexisting = existing_document(response)
                if preexisting and schema == "place":
                    document["fields"]["types"] = preexisting.get("fields").get("types", []) + document.get("fields").get("types", [])

            logger.info(f"Updating {schema} {preexisting} with {document}")

            response = sync_app.update_data(
                namespace=namespace,
                schema=schema,
                data_id=document.get("document_id"),
                fields=document.get("fields"),
            )
            # Report any errors
            if response.status_code != 200:
                task_tracker.update_task(task_id, {"error": f"#{count}: {response.get('error')}"})
                logger.error(
                    f'Error updating {schema} document: {response.get("error")}', exc_info=True)

    except Exception as e:
        task_tracker.update_task(task_id, {"error": f"#{count}: {str(e)}"})
        logger.error(
            f'Error feeding document: {str(e)}', exc_info=True)
        return
