# /gis/utils.py
import logging
import math

from shapely.geometry.geo import shape, mapping
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
        # Vespa cannot compare fields within queries: precompute a flag to indicate bounding box spanning the antimeridian
        "bbox_antimeridial": min_lng > max_lng,
    }


def get_valid_geom(geometry) -> tuple:
    """
    Get a valid Shapely geometry object from a GeoJSON geometry, and return it together with a dictionary containing the
    original GeoJSON geometry together with any non-standard fields extracted from it.

    Args:
        geometry (dict): The GeoJSON geometry to convert.

    Returns:
        shapely.geometry.base.BaseGeometry: A Shapely geometry object if the input is valid, None otherwise.
        dict: A dictionary containing the GeoJSON geometry object if the input is valid, None otherwise.
    """
    if not geometry or 'type' not in geometry or ('coordinates' not in geometry and geometry['type'] != 'GeometryCollection'):
        logger.warning("Invalid geometry: missing type or coordinates.")
        return None, None
    try:
        if geometry.get('type') == 'GeometryCollection':
            geometries = geometry.get('geometries', []) # Prevent KeyError if 'geometries' is missing
            geometry_tuples = [get_valid_geom(g) for g in geometries]
            if all(g[0] for g in geometry_tuples) and all(g[1] for g in geometry_tuples):
                return shape(geometry), {'type': 'GeometryCollection', 'geometries': [g[1] for g in geometry_tuples]}
            logger.warning("Invalid geometry collection.")
            return None, None

        # Capture non-standard fields from geometry
        extra_fields = {k: v for k, v in geometry.items() if k not in ('type', 'coordinates')}

        geom = shape(geometry)
        if geom.is_valid and not geom.is_empty:
            # return both the geom and its mapping with extra fields re-injected
            return geom, {**mapping(geom), **extra_fields}
        logger.warning(f"Invalid geometry: {explain_validity(geom)}")

        # Attempt to fix invalid geometries by applying a zero buffer
        fixed_geom = geom.buffer(0)
        if fixed_geom.is_valid and not fixed_geom.is_empty:
            logger.info("Fixed invalid geometry using zero buffer.")
            return fixed_geom, {**mapping(fixed_geom), **extra_fields}
        else:
            logger.warning("Unable to fix geometry using zero buffer.")
    except Exception as e:
        logger.error("Error converting geometry.", exc_info=True)
    return None, None
