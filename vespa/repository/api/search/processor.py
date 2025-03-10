# ./search/processor.py
import logging
from typing import Dict, Any, Optional, Tuple

import requests

from ..bcp_47.bcp_47 import parse_bcp47_fields
from ..config import VespaClient
from ..gis.intersections import GeometryIntersect
from ..gis.utils import geo_to_cartesian

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
    conditions = []

    # Handle name search
    if med is None:
        conditions.append(f'name_strict contains "{query}"')
    else:
        fuzzy_params = f'{{maxEditDistance: {med}'
        if pl is not None:
            fuzzy_params += f', prefixLength: {pl}'
        fuzzy_params += '}'
        conditions.append(f'name contains ({fuzzy_params}fuzzy("{query}"))')

    # Handle BCP 47 filtering
    if bcp47:
        bcp47_parts = parse_bcp47_fields(bcp47)
        for field, value in bcp47_parts.items():
            conditions.append(f'{field} contains "{value}"')

    # Construct the YQL query
    where_clause = " and ".join(conditions)
    yql = f'select * from toponym where {where_clause} limit {limit};'

    response = sync_app.query(yql=yql)

    return {
        "totalHits": response.json.get("root", {}).get("fields", {}).get("totalCount", 0),
        "hits": response.json.get("root", {}).get("children", [])
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


def locate(
        bbox: Optional[Tuple[float, float, float, float]] = None,
        point: Optional[Tuple[float, float]] = None,
        radius: Optional[float] = None,
        limit: Optional[int] = None,
        namespace: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Locate places based on bounding box or point and radius.

    Args:
        bbox (Optional[Tuple[float, float, float, float]]): Bounding box coordinates (min_lon, min_lat, max_lon, max_lat).
        point (Optional[Tuple[float, float]]): Point coordinates (lon, lat).
        radius (Optional[float]): Radius in kilometres.
        limit (Optional[int]): Maximum number of results.
        namespace (Optional[str]): Namespace to filter results by.

    Returns:
        Dict[str, Any]: A dictionary containing the locate results.
    """
    try:
        with VespaClient.sync_context("query") as sync_app:
            if bbox:
                return _locate_by_bbox(bbox, limit, namespace)
            elif point:
                return _locate_by_point(sync_app, point, radius, limit, namespace)
            else:
                return {"totalHits": 0, "hits": []}  # Validation should avoid reaching this point

    except requests.exceptions.RequestException as req_err:
        logger.error(f"HTTP Request failed: {req_err}", exc_info=True)
        raise Exception(f"Error during Vespa locate: HTTP Request failed - {req_err}")

    except Exception as e:
        logger.error(f"An error occurred: {e}", exc_info=True)
        raise Exception(f"Error during Vespa locate: {e}")


def _locate_by_bbox(bbox, limit, namespace):
    """Locate places within a bounding box."""
    min_lon, min_lat, max_lon, max_lat = bbox
    geojson_bbox = {
        "type": "Polygon",
        "coordinates": [[[min_lon, min_lat], [max_lon, min_lat], [max_lon, max_lat], [min_lon, max_lat], [min_lon, min_lat]]]
    }
    try:
        results = GeometryIntersect(geometry=geojson_bbox, namespace=namespace).resolve()
        return {
            "totalHits": len(results),
            "hits": results[:limit] if limit else results, # TODO: limit should be implemented in the GeometryIntersect class
        }
    except Exception as e:
        logger.error(f"Error during bbox locate: {e}", exc_info=True)
        raise Exception(f"Error during bbox locate: {e}")


def _locate_by_point(sync_app, point, radius, limit, namespace):
    """Locate places closest to a point."""
    lon, lat = point
    conditions = []

    if namespace:
        conditions.append(f'namespace contains "{namespace}"')

    if radius:
        conditions.append(f'geoLocation(representative_point, {lon}, {lat}, "{radius} km")')
        query_params = {}  # No need for `query_tensor`
    else:
        x, y, z = geo_to_cartesian(lat, lon)
        conditions.append(f'{{targetHits: {max(1, limit)}}}nearestNeighbor(cartesian, query_tensor)')
        query_params = {
            "input.query(query_tensor)": {
                "cells": [{"address": {"x": i}, "value": v} for i, v in enumerate([x, y, z])]
            }
        }

    where_clause = " and ".join(conditions) if conditions else ""

    yql = f'select * from place{" where " + where_clause if where_clause else ""};'

    # Perform the query with the updated YQL and query parameters
    response = sync_app.query(yql=yql, **query_params)

    return {
        "totalHits": response.json.get("root", {}).get("fields", {}).get("totalCount", 0),
        "hits": response.json.get("root", {}).get("children", [])
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
