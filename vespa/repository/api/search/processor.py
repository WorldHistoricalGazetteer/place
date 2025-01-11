# ./search/processor.py
import logging
from typing import Dict, Any

import requests
from vespa.application import VespaSync, Vespa

from ..config import host_mapping, namespace

logger = logging.getLogger(__name__)


def visit(
        schema: str,
        wanted_document_count: int,
        field: str = "id",
        slices: int = 1
) -> Dict[str, Any]:
    """
    Visit and retrieve documents of a specified type from a Vespa instance.

    This function uses VespaSync's visit method to fetch documents that match a given field
    and returns a paginated list of results. It supports slicing for parallel processing.

    Args:
        schema (str): The Vespa schema (document type) to query.
        wanted_document_count (int): The maximum number of documents to retrieve.
        field (str): The field used for filtering; documents must have this field set. Default is "id".
        slices (int): Number of slices for parallel processing. Default is 1.

    Returns:
        Dict[str, Any]: A dictionary containing total document count and the list of documents.
    """

    try:
        app = Vespa(url=f"{host_mapping['query']}")
        logger.info(f"Visiting documents from Vespa schema: {schema} on {app.url}")

        with VespaSync(app) as sync_app:

            all_docs = []
            total_count = 0
            # selection = f"{field} contains ''"  # Matches documents where the field is present
            selection = "true"  # Matches all documents

            # Use VespaSync.visit to retrieve documents once
            for slice in sync_app.visit(
                    content_cluster_name="content",
                    schema=schema,
                    namespace=namespace,
                    slices=slices,
                    selection=selection,
                    wanted_document_count=wanted_document_count,
            ):
                logger.info(f"Slice: {slice}")
                for response in slice:
                    logger.info(f"Response: {response}")
                    all_docs.extend(response.documents)
                    total_count += response.number_documents_retrieved

            return {
                "total_count": total_count,
                "limit": wanted_document_count,
                "documents": all_docs
            }

    except requests.exceptions.RequestException as req_err:
        logger.error(f"HTTP Request failed: {req_err}", exc_info=True)
        raise Exception(f"Error during Vespa document visit: HTTP Request failed - {req_err}")

    except Exception as e:
        logger.error(f"An error occurred: {e}")
        raise Exception(f"Error during Vespa document visit: {e}")
