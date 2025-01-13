# /gis/processor.py

import json
import logging

from shapely.geometry.geo import mapping
from shapely.io import to_geojson
from shapely.validation import explain_validity

from .intersections import GeometryIntersect
from .utils import get_valid_geom, vespa_bbox

logger = logging.getLogger(__name__)


class GeometryProcessor:
    """
    A class to process GeoJSON geometries, validate them, compute properties such as area and bounding box,
    and resolve ISO country codes.
    """

    def __init__(self, geometry, values=None, errors=False) -> None:
        """
        Initializes the GeometryProcessor with a given geometry, optional attributes to compute,
        and an error-handling option.

        Args:
            geometry (dict): The GeoJSON geometry to be processed.
            values (list, optional): A list of properties to compute. Defaults to ["area", "bbox",
                                      "ccodes", "convex_hull", "geometry", "length", "representative_point"]
                                      if not provided.
            errors (bool): If True, errors will be returned as messages. Defaults to False.
        """
        self.values = values or ["area", "bbox", "ccodes", "convex_hull", "geometry", "length", "representative_point"]
        self.geom = get_valid_geom(geometry) # Shapely geometry object
        self.geometry = mapping(self.geom) if self.geom else None # GeoJSON geometry object (Shapely converts Decimal values to float for serialisation)
        self.errors = errors

    def process(self) -> dict:
        """
        Processes the geometry and computes various properties such as area, bounding box, and ISO country codes.

        Returns:
            dict: A dictionary containing processed geometry properties, or:
                - {"error": "Invalid geometry"} if the input geometry is invalid.
                - {"error": "Empty geometry"} if the input geometry is empty.
                - None if `errors=False` and there are no valid properties to compute.
        """
        if not self.geom:
            # Invalidity and emptiness have been handled by get_valid_geom
            return {"error": "Invalid geometry"} if self.errors else None

        # If requested, cache values for performance efficiency
        area = self.geom.area if "area" in self.values else None
        bbox = vespa_bbox(self.geom) if "bbox" in self.values or "ccodes" in self.values else {}
        convex_hull = self.geom.convex_hull if "convex_hull" in self.values else None
        iso_codes = GeometryIntersect(geom=self.geom, bbox=bbox).resolve() if "ccodes" in self.values and bbox else {}
        # Remove "-" from the list of ISO codes if present
        iso_codes = [code['code2'] for code in iso_codes if not code['code2'] == "-"] or {} if iso_codes else {}
        length = self.geom.length if "length" in self.values else None
        representative_point = self.geom.representative_point() if "representative_point" in self.values else None

        return {
            **({"area": area} if area else {}),
            **(bbox if bbox else {}),
            **({"convex_hull": to_geojson(convex_hull)} if convex_hull else {}),
            **({"geometry": json.dumps(self.geometry)} if self.geometry else {}),
            **({"ccodes": iso_codes} if iso_codes else {}),
            **({"length": length} if length else {}),
            **({"representative_point": to_geojson(representative_point)} if representative_point else {}),
        }
