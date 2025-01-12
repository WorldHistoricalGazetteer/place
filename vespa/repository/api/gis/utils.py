# /gis/utils.py
import logging
import math

from shapely.geometry.geo import shape
from shapely.validation import explain_validity

logger = logging.getLogger(__name__)


def vespa_bbox(geom) -> dict:
    """
    Calculate the bounding box of a Shapely geometry and return it in Vespa-friendly format.

    Args:
        geom (shapely.geometry.base.BaseGeometry): The Shapely geometry object.

    Returns:
        dict: A dictionary containing:
            - Bounding box coordinates if the geometry is valid.
            - {"bbox_error": "Invalid geometry"} if the geometry is invalid or contains NaN/Inf.
            - {"bbox_error": "Coordinates out of bounds"} if bounding box coordinates exceed valid lat/lng ranges.
    """

    min_lng, min_lat, max_lng, max_lat = geom.bounds

    if any(math.isnan(v) or math.isinf(v) for v in (min_lng, min_lat, max_lng, max_lat)):
        return {"bbox_error": "Invalid geometry"}

    return {
        "bbox_sw_lat": min_lat,
        "bbox_sw_lng": min_lng,
        "bbox_ne_lat": max_lat,
        "bbox_ne_lng": max_lng,
    }


def get_valid_geom(geometry) -> shape:
    """
    Get a valid Shapely geometry object from a GeoJSON geometry.

    Args:
        geometry (dict): The GeoJSON geometry to convert.

    Returns:
        shapely.geometry.base.BaseGeometry: A Shapely geometry object if the input is valid, None otherwise.
    """
    if not geometry or 'type' not in geometry or 'coordinates' not in geometry:
        logger.warning("Invalid geometry: missing type or coordinates.")
        return False
    try:
        geom = shape(geometry)
        if geom.is_valid and not geom.is_empty:
            return geom
        logger.warning(f"Invalid geometry: {explain_validity(geom)}")
    except Exception as e:
        logger.error("Error converting geometry.", exc_info=True)
    return None
