# ./search/processor.py
import logging
from typing import Dict, Any, Optional

import requests

from ..config import VespaClient

logger = logging.getLogger(__name__)


def search(
        query: str,
        med: Optional[int] = None,  # Omit for exact matching
        pl: Optional[int] = None,
        bcp47: Optional[str] = None,  # Combined language and script tag
        limit: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Search for toponyms in Vespa using fuzzy or exact matching.

    Args:
        query (str): The search query string.
        med (Optional[int]): Maximum edit distance for fuzzy matching; None for exact.
        pl (Optional[int]): Prefix length for fuzzy matching.
        bcp47 (Optional[str]): BCP 47 tag for language/script filtering.
        limit (Optional[int]): Maximum number of results.

    Returns:
        Dict[str, Any]: A dictionary containing the search results.
    """
    try:
        with VespaClient.sync_context("query") as sync_app:
            if med is None:  # Exact search
                return _perform_search(sync_app, query, med=None, pl=None, bcp47=bcp47, limit=limit)

            exact_results = _perform_search(sync_app, query, med=None, pl=None, bcp47=bcp47, limit=limit)
            fuzzy_results = _perform_search(sync_app, query, med=med, pl=pl, bcp47=bcp47, limit=limit)

            return _combine_results(exact_results, fuzzy_results, limit)

    except requests.exceptions.RequestException as req_err:
        logger.error(f"HTTP Request failed: {req_err}", exc_info=True)
        raise Exception(f"Error during Vespa search: HTTP Request failed - {req_err}")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        raise Exception(f"Error during Vespa search: {e}")


def _perform_search(sync_app, query, med, pl, bcp47, limit):
    """
    Perform a Vespa search using YQL.

    Args:
        sync_app: Vespa client.
        query (str): Search term.
        med (Optional[int]): Max edit distance for fuzzy matching; None for exact.
        pl (Optional[int]): Prefix length for fuzzy matching.
        bcp47 (Optional[str]): Language/script filter.
        limit (Optional[int]): Max number of results.

    Returns:
        Dict[str, Any]: Search results.
    """
    if med is None:
        # Exact match
        yql = f'select * from toponym where name_strict contains "{query}"'
    else:
        # Fuzzy match
        fuzzy_params = f'{{maxEditDistance: {med}'
        if pl is not None:
            fuzzy_params += f', prefixLength: {pl}'
        fuzzy_params += '}'

        yql = f'select * from toponym where name contains ({fuzzy_params}fuzzy("{query}"))'

    if bcp47:
        yql += f' and bcp47 contains "{bcp47}"'

    if limit:
        yql += f' limit {limit}'

    yql += ";"

    results = sync_app.query(yql=yql)

    return {
        "totalHits": results.get("root", {}).get("fields", {}).get("totalCount", 0),
        "hits": results.get("root", {}).get("children", [])
    }


def _combine_results(exact_results: Dict[str, Any], fuzzy_results: Dict[str, Any], limit=None) -> Dict[str, Any]:
    """
    Combine exact and fuzzy search results, ensuring no duplicate entries and assigning ranking scores.

    Args:
        exact_results (Dict[str, Any]): Results from exact search.
        fuzzy_results (Dict[str, Any]): Results from fuzzy search.

    Returns:
        Dict[str, Any]: Merged search results with assigned ranking scores.
    """
    exact_hits = exact_results.get("hits", [])
    fuzzy_hits = fuzzy_results.get("hits", [])

    ranked_hits = {}

    def add_hit(hit, score):
        doc_id = hit.get("id")
        if not doc_id:
            return

        if doc_id in ranked_hits:
            ranked_hits[doc_id]["ranking"] = max(ranked_hits[doc_id]["ranking"], score)
        else:
            hit["ranking"] = score
            ranked_hits[doc_id] = hit

    for hit in exact_hits:
        add_hit(hit, score=1.0)

    for hit in fuzzy_hits:
        add_hit(hit, score=0.5)

    sorted_hits = sorted(ranked_hits.values(), key=lambda h: h["ranking"], reverse=True)

    return {
        "totalHits": len(sorted_hits),
        "hits": sorted_hits[:limit] if limit else sorted_hits
    }


def visit(
        schema: str,
        limit: int,
        namespace: str = None,
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
                logger.info(
                    f"Deleting existing documents from Vespa schema: {namespace}:{schema} on {VespaClient.get_url('feed')}")
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
