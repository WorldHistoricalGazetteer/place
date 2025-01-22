import logging

from ..utils import task_tracker

logger = logging.getLogger(__name__)


def update_triple(task):
    sync_app, namespace, schema, document_id, transformed_document, task_id, count, task_tracker = task



def feed_triple(sync_app, namespace, transformed_document, task_id, count):
    schema = transformed_document.get("schema")
    if not schema:
        return {
            "success": False,
            "namespace": namespace,
            "schema": schema,
            "document_id": transformed_document.get("document_id"),
            "error": "No schema found"
        }

    try:
        #

        return
    except Exception as e:
        task_tracker.update_task(task_id, {"error": f"#{count}: {str(e)}"})
        logger.error(
            f"Error feeding document: {namespace}:{schema}::{transformed_document.get("document_id")}, Error: {str(e)}",
            exc_info=True)
        return {
            "success": False,
            "namespace": namespace,
            "schema": schema,
            "document_id": transformed_document.get("document_id"),
            "error": str(e)
        }
