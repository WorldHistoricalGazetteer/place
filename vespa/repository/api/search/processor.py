# ./search/processor.py
import logging
from typing import Dict, Any

import requests

from ..config import VespaClient

logger = logging.getLogger(__name__)


def visit(
        schema: str,
        namespace: str,
        limit: int,
        slices: int = 1,
        delete: bool = False
) -> Dict[str, Any]:
    """
    Fetch documents of a specified type from a Vespa instance.

    This function uses VespaSync's `visit` method to retrieve documents from a Vespa instance.
    It supports pagination and parallel processing through slicing. The documents are fetched
    from the feed endpoint because the query endpoint does not have the document API enabled
    (refer to `configmap-hosts-services.yaml`).

    Args:
        schema (str): The Vespa schema (document type) to query.
        namespace (str): The Vespa namespace to query.
        limit (int): The maximum number of documents to return. A value of -1 means no limit.
        slices (int): Number of slices for parallel processing. Default is 1.
        delete (bool): If True, delete existing data. Default is False.

    Returns:
        Dict[str, Any]: A dictionary containing:
            - `total_count` (int): The total number of documents retrieved.
            - `limit` (int or str): The specified document limit or "no limit" if -1 is provided.
            - `documents` (list): A list of documents, limited to the specified number.
    """

    try:
        with VespaClient.sync_context("feed") as sync_app:

            if delete:
                logger.info(f"Deleting existing documents from Vespa schema: {namespace}:{schema} on {VespaClient.get_url('feed')}")
                # Delete documents belonging to the given schema and namespace
                sync_app.delete_all_docs(
                    namespace=namespace,
                    schema=schema,
                    content_cluster_name="content"
                )

            logger.info(f"Visiting documents from Vespa schema: {namespace}:{schema} on {VespaClient.get_url('feed')}")

            all_docs = []
            total_count = 0

            # Use VespaSync.visit to retrieve documents once
            for slice in sync_app.visit(
                    namespace=namespace,
                    schema=schema,
                    content_cluster_name="content",
                    slices=slices,
            ):
                logger.info(f"Slice: {slice}")
                for response in slice:
                    logger.info(f"Response: {response}")
                    all_docs.extend(response.documents)
                    total_count += response.number_documents_retrieved

            logger.info(f"Total documents retrieved: {total_count}: returning {limit} documents.")
            return {
                "total_count": total_count,
                "namespace": namespace,
                "limit": limit if limit > -1 else "no limit",
                "documents": all_docs[:limit] if limit > -1 else all_docs
            }

    except requests.exceptions.RequestException as req_err:
        logger.error(f"HTTP Request failed: {req_err}", exc_info=True)
        raise Exception(f"Error during Vespa document visit: HTTP Request failed - {req_err}")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        raise Exception(f"Error during Vespa document visit: {e}")
