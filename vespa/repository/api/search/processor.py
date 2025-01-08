# ./search/processor.py
from typing import Dict, Any

import httpx

from ..config import host_mapping


async def filter_and_paginate_documents(doc_type: str, page: int, limit: int) -> Dict[str, Any]:
    """
    Fetch documents of the given type and apply pagination.

    Args:
        doc_type (str): The document type to filter by.
        page (int): The page number (starting from 1).
        limit (int): The number of results per page.

    Returns:
        Dict[str, Any]: Paginated results including metadata and documents.
    """
    # URL for querying Vespa documents
    query_url = f"{host_mapping['query']}/search/"

    # Calculate the offset based on the page and limit
    offset = (page - 1) * limit

    async with httpx.AsyncClient() as client:
        try:
            # Send a query to Vespa
            response = await client.get(query_url, params={
                "yql": f"select * from sources * where type contains '{doc_type}'",
                "hits": limit,
                "offset": offset
            })
            response.raise_for_status()
            data = response.json()

            # Extract total count and documents from the response
            total_count = data.get("root", {}).get("fields", {}).get("totalCount", 0)
            documents = data.get("root", {}).get("children", [])

            return {
                "total_count": total_count,
                "page": page,
                "limit": limit,
                "documents": [doc.get("fields", {}) for doc in documents]
            }
        except httpx.RequestError as e:
            raise Exception(f"Error contacting Vespa query service: {e}")
        except httpx.HTTPStatusError as e:
            raise Exception(f"HTTP error: {e.response.text}")
