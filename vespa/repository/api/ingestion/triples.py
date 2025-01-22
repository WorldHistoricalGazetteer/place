import logging

from ..utils import task_tracker

logger = logging.getLogger(__name__)


def update_triple(task):
    sync_app, namespace, schema, document_id, transformed_document, task_id, count, task_tracker = task


def feed_triple(sync_app, namespace, transformed_document, task_id, count):
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

    except Exception as e:
        task_tracker.update_task(task_id, {"error": f"#{count}: {str(e)}"})
        logger.error(
            f'Error feeding document: {str(e)}', exc_info=True)
        return
