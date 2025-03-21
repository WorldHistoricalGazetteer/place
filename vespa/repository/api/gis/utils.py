# /gis/utils.py
import logging
import math
from typing import Optional, Tuple

import pyproj
from fastapi import Query, HTTPException, Depends
from shapely.geometry.geo import shape, mapping
from shapely.validation import explain_validity

logger = logging.getLogger(__name__)

# Define transformer once for efficiency
_wgs84_to_ecef = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:4978", always_xy=True).transform


def geo_to_cartesian(lat: float, lon: float, elevation: float = 0) -> Tuple[float, float, float]:
    """
    Converts geographic coordinates (latitude, longitude) to 3D Cartesian (ECEF).
    Uses WGS84 ellipsoid.
    """
    result = _wgs84_to_ecef(lon, lat, elevation)

    if isinstance(result, tuple) and len(result) == 3:
        return result
    else:
        logger.warning(f"Unexpected result from _wgs84_to_ecef: {result}")
        return 0.0, 0.0, 0.0


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

    # logger.info(f"Converting geometry: {geometry}")

    if not (geometry_type := geometry.get('type')) or (
            geometry_type != 'GeometryCollection' and 'coordinates' not in geometry
    ):
        logger.warning("Invalid geometry: missing 'type' or 'coordinates'.")
        return None, None
    try:
        if geometry.get('type') == 'GeometryCollection':
            geometries = geometry.get('geometries', [])  # Prevent KeyError if 'geometries' is missing
            geometry_tuples = [get_valid_geom(g) for g in geometries]
            # logger.info(f"geometry_tuples: {geometry_tuples}")
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


def parse_bbox(bbox: Optional[str] = Query(None)) -> Optional[Tuple[float, float, float, float]]:
    if bbox:
        try:
            coords = [float(c) for c in bbox.split(',')]
            if len(coords) != 4:
                raise ValueError("bbox must contain 4 comma-separated coordinates")
            if not (-90 <= coords[0] <= 90 and -180 <= coords[1] <= 180 and -90 <= coords[2] <= 90 and -180 <= coords[
                3] <= 180):
                raise ValueError("Bounding box coordinates out of bounds")
            return tuple(coords)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return None


def parse_point(point: Optional[str] = Query(None)) -> Optional[Tuple[float, float]]:
    if point:
        try:
            coords = [float(c) for c in point.split(',')]
            if len(coords) != 2:
                raise ValueError("point must contain 2 comma-separated coordinates")
            if not (-90 <= coords[0] <= 90 and -180 <= coords[1] <= 180):
                raise ValueError("Point coordinates out of bounds")
            return tuple(coords)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
    return None


def validate_locate_params(bbox: Optional[Tuple[float, float, float, float]] = Depends(parse_bbox),
                           point: Optional[Tuple[float, float]] = Depends(parse_point),
                           radius: Optional[float] = Query(None)):
    if not bbox and not point:
        raise HTTPException(status_code=400, detail="Either bbox or point must be provided")
