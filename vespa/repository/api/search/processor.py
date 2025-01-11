# ./search/processor.py
import logging
from typing import Dict, Any

import requests

from ..config import namespace, VespaClient

logger = logging.getLogger(__name__)


def visit(
        schema: str,
        limit: int,
        slices: int = 1,
) -> Dict[str, Any]:
    """
    Visit and retrieve documents of a specified type from a Vespa instance.

    This function uses VespaSync's visit method to fetch documents that match a given field
    and returns a paginated list of results. It supports slicing for parallel processing.

    It uses the feed endpoint to visit documents because the query endpoint does not have the document-api
    service enabled (see `configmap-hosts-services.yaml`).

    Args:
        schema (str): The Vespa schema (document type) to query.
        limit (int): The maximum number of documents to return.
        slices (int): Number of slices for parallel processing. Default is 1.

    Returns:
        Dict[str, Any]: A dictionary containing total document count and the list of documents.
    """

    try:
        with VespaClient.sync_context("feed") as sync_app:
            logger.info(f"Visiting documents from Vespa schema: {schema} on {VespaClient.get_url('feed')}")

            all_docs = []
            total_count = 0
            selection = "true"  # Matches all documents

            # Use VespaSync.visit to retrieve documents once
            for slice in sync_app.visit(
                    content_cluster_name="content",
                    schema=schema,
                    namespace=namespace,
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
                "limit": limit,
                "documents": all_docs[:limit]
            }

    except requests.exceptions.RequestException as req_err:
        logger.error(f"HTTP Request failed: {req_err}", exc_info=True)
        raise Exception(f"Error during Vespa document visit: HTTP Request failed - {req_err}")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        raise Exception(f"Error during Vespa document visit: {e}")
