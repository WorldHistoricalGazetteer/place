# ./search/processor.py
from typing import Dict, Any

from vespa.application import VespaSync, Vespa

from ..config import host_mapping


def visit(
    doc_type: str,
    wanted_document_count: int,
    field: str = "id",
    slices: int = 1
) -> Dict[str, Any]:
    """
    Visit and retrieve documents of a specified type from a Vespa instance.

    This function uses VespaSync's visit method to fetch documents that match a given field
    and returns a paginated list of results. It supports slicing for parallel processing.

    Args:
        doc_type (str): The Vespa schema (document type) to query.
        wanted_document_count (int): The maximum number of documents to retrieve.
        field (str): The field used for filtering; documents must have this field set. Default is "id".
        slices (int): Number of slices for parallel processing. Default is 1.

    Returns:
        Dict[str, Any]: A dictionary containing total document count and the list of documents.
    """
    app = Vespa(url=f"{host_mapping['query']}")

    results = []
    total_count = 0

    try:
        with VespaSync(app) as sync_app:
            # Build the selection query for filtering by field
            selection = f"{field} contains ''"  # Matches documents where the field is present

            # Use VespaSync.visit to retrieve documents
            for generator in sync_app.visit(
                schema=doc_type,
                cluster="content",
                selection=selection,
                continuation=None,
                wanted_document_count=wanted_document_count,
                slices=slices,
                content_cluster_name="content",
            ):
                for doc in generator:
                    results.append(doc)
                    total_count += 1

            return {
                "total_count": total_count,
                "limit": wanted_document_count,
                "documents": results,
            }

    except Exception as e:
        raise Exception(f"Error during Vespa document visit: {e}")
